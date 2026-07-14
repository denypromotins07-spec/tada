"""
Feature Pipeline - Real-time Feature Engineering with Polars

Real-time feature engineering pipeline using Polars (Rust-backed DataFrame library)
to feed ML models with zero Python GIL bottlenecks. Optimized for AMD hardware.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from collections import deque
import numpy as np
import time

logger = logging.getLogger(__name__)

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False
    logger.warning("Polars not available, falling back to pandas")


class FeaturePipeline:
    """
    Real-time feature engineering pipeline using Polars for Rust-speed
    data transformations without Python GIL bottlenecks.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.feature_cache: Dict[str, pl.DataFrame] = {}
        self.window_sizes = {
            "short": self.config.get("short_window", 10),
            "medium": self.config.get("medium_window", 50),
            "long": self.config.get("long_window", 200),
        }
        
        # Rolling buffers for real-time updates
        self.price_buffer: deque = deque(maxlen=self.window_sizes["long"])
        self.volume_buffer: deque = deque(maxlen=self.window_sizes["long"])
        self.orderbook_buffer: deque = deque(maxlen=self.window_sizes["short"])
        
        # Computed features cache
        self.features_cache: Dict[str, np.ndarray] = {}
        
        if POLARS_AVAILABLE:
            logger.info("FeaturePipeline initialized with Polars backend")
        else:
            logger.info("FeaturePipeline initialized with NumPy fallback")
    
    def add_tick(self, symbol: str, tick_data: Dict[str, Any]):
        """Add a new tick to the rolling buffers"""
        timestamp = tick_data.get("timestamp", int(time.time() * 1000))
        price = tick_data.get("last_price", 0.0)
        volume = tick_data.get("volume", 0.0)
        
        self.price_buffer.append((timestamp, price))
        self.volume_buffer.append((timestamp, volume))
        
        # Clear cached features for this symbol
        if symbol in self.features_cache:
            del self.features_cache[symbol]
    
    def add_orderbook_snapshot(self, symbol: str, depth_data: Dict[str, Any]):
        """Add order book snapshot for liquidity features"""
        bids = depth_data.get("bids", [])
        asks = depth_data.get("asks", [])
        
        # Calculate order book imbalance
        bid_depth = sum(float(b[1]) for b in bids[:10]) if bids else 0
        ask_depth = sum(float(a[1]) for a in asks[:10]) if asks else 0
        
        self.orderbook_buffer.append({
            "timestamp": depth_data.get("timestamp", int(time.time() * 1000)),
            "bid_depth": bid_depth,
            "ask_depth": ask_depth,
            "spread": (asks[0][0] - bids[0][0]) if asks and bids else 0,
            "mid_price": (asks[0][0] + bids[0][0]) / 2 if asks and bids else 0,
        })
    
    def compute_features(self, symbol: str) -> Dict[str, float]:
        """
        Compute all features for a symbol using Polars or NumPy fallback.
        Returns a dictionary of feature names to values.
        """
        if len(self.price_buffer) < self.window_sizes["short"]:
            return self._get_empty_features()
        
        if POLARS_AVAILABLE:
            return self._compute_features_polars(symbol)
        else:
            return self._compute_features_numpy(symbol)
    
    def _compute_features_polars(self, symbol: str) -> Dict[str, float]:
        """Compute features using Polars (Rust-backed, no GIL)"""
        
        # Convert buffers to Polars DataFrame
        prices = np.array([p for _, p in self.price_buffer])
        volumes = np.array([v for _, v in self.volume_buffer])
        timestamps = np.array([t for t, _ in self.price_buffer])
        
        df = pl.DataFrame({
            "timestamp": timestamps,
            "price": prices,
            "volume": volumes,
        })
        
        # Price-based features
        returns = df["price"].pct_change().fill_null(0)
        
        features = {
            # Momentum features
            f"return_1m": float(returns.tail(1).sum()),
            f"return_5m": float(returns.tail(5).sum()),
            f"return_10m": float(returns.tail(10).sum()),
            
            # Volatility features
            f"volatility_10m": float(returns.tail(10).std() or 0),
            f"volatility_50m": float(returns.tail(50).std() or 0),
            
            # Volume features
            f"volume_ma_ratio": float(df["volume"].tail(10).mean() / (df["volume"].tail(50).mean() + 1e-10)),
            f"volume_zscore": float((volumes[-1] - np.mean(volumes[-50:])) / (np.std(volumes[-50:]) + 1e-10)),
            
            # Price position features
            f"price_ma_ratio": float(prices[-1] / (np.mean(prices[-20:]) + 1e-10)),
            f"price_range_pct": float((prices[-1] - np.min(prices[-20:])) / (np.max(prices[-20:]) - np.min(prices[-20:]) + 1e-10)),
        }
        
        # Add order book features if available
        if self.orderbook_buffer:
            ob_features = self._compute_orderbook_features()
            features.update(ob_features)
        
        # Cache results
        self.features_cache[symbol] = features
        return features
    
    def _compute_features_numpy(self, symbol: str) -> Dict[str, float]:
        """Compute features using NumPy (fallback when Polars unavailable)"""
        
        prices = np.array([p for _, p in self.price_buffer])
        volumes = np.array([v for _, v in self.volume_buffer])
        
        # Calculate returns
        returns = np.diff(prices) / (prices[:-1] + 1e-10)
        returns = np.insert(returns, 0, 0)
        
        features = {
            # Momentum features
            "return_1m": float(returns[-1]),
            "return_5m": float(np.sum(returns[-5:])),
            "return_10m": float(np.sum(returns[-10:])),
            
            # Volatility features
            "volatility_10m": float(np.std(returns[-10:])),
            "volatility_50m": float(np.std(returns[-50:])),
            
            # Volume features
            "volume_ma_ratio": float(np.mean(volumes[-10:]) / (np.mean(volumes[-50:]) + 1e-10)),
            "volume_zscore": float((volumes[-1] - np.mean(volumes[-50:])) / (np.std(volumes[-50:]) + 1e-10)),
            
            # Price position features
            "price_ma_ratio": float(prices[-1] / (np.mean(prices[-20:]) + 1e-10)),
            "price_range_pct": float((prices[-1] - np.min(prices[-20:])) / (np.max(prices[-20:]) - np.min(prices[-20:]) + 1e-10)),
        }
        
        # Add order book features if available
        if self.orderbook_buffer:
            ob_features = self._compute_orderbook_features()
            features.update(ob_features)
        
        self.features_cache[symbol] = features
        return features
    
    def _compute_orderbook_features(self) -> Dict[str, float]:
        """Compute order book derived features"""
        if not self.orderbook_buffer:
            return {}
        
        ob_array = np.array([
            [d["bid_depth"], d["ask_depth"], d["spread"], d["mid_price"]]
            for d in self.orderbook_buffer
        ])
        
        bid_depths = ob_array[:, 0]
        ask_depths = ob_array[:, 1]
        spreads = ob_array[:, 2]
        
        # Order book imbalance
        total_depth = bid_depths[-1] + ask_depths[-1] + 1e-10
        ob_imbalance = (bid_depths[-1] - ask_depths[-1]) / total_depth
        
        # Spread metrics
        avg_spread = np.mean(spreads[-10:])
        spread_zscore = (spreads[-1] - avg_spread) / (np.std(spreads[-10:]) + 1e-10)
        
        # Depth change
        depth_change = (bid_depths[-1] - np.mean(bid_depths[-10:])) / (np.mean(bid_depths[-10:]) + 1e-10)
        
        return {
            "ob_imbalance": float(ob_imbalance),
            "spread_bps": float(avg_spread * 10000),
            "spread_zscore": float(spread_zscore),
            "depth_change": float(depth_change),
        }
    
    def _get_empty_features(self) -> Dict[str, float]:
        """Return empty features when insufficient data"""
        return {
            "return_1m": 0.0,
            "return_5m": 0.0,
            "return_10m": 0.0,
            "volatility_10m": 0.0,
            "volatility_50m": 0.0,
            "volume_ma_ratio": 1.0,
            "volume_zscore": 0.0,
            "price_ma_ratio": 1.0,
            "price_range_pct": 0.5,
            "ob_imbalance": 0.0,
            "spread_bps": 0.0,
            "spread_zscore": 0.0,
            "depth_change": 0.0,
        }
    
    def get_feature_names(self) -> List[str]:
        """Get list of all feature names"""
        return list(self._get_empty_features().keys())
    
    def get_feature_vector(self, symbol: str) -> np.ndarray:
        """Get features as a numpy array for model input"""
        features = self.compute_features(symbol)
        return np.array(list(features.values()), dtype=np.float32)
    
    def clear(self):
        """Clear all buffers and caches"""
        self.price_buffer.clear()
        self.volume_buffer.clear()
        self.orderbook_buffer.clear()
        self.features_cache.clear()
        self.feature_cache.clear()
    
    def get_status(self) -> Dict[str, Any]:
        """Get pipeline status for monitoring"""
        return {
            "price_buffer_size": len(self.price_buffer),
            "volume_buffer_size": len(self.volume_buffer),
            "orderbook_buffer_size": len(self.orderbook_buffer),
            "cached_symbols": len(self.features_cache),
            "polars_available": POLARS_AVAILABLE,
        }


# Factory function
def create_feature_pipeline(config: Dict[str, Any] = None) -> FeaturePipeline:
    """Create a new feature pipeline instance"""
    return FeaturePipeline(config)
