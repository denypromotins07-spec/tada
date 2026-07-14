# /workspace/strategies/src/analytics/order_flow.py
# =============================================================================
# ORDER FLOW ANALYTICS ENGINE - REAL-TIME MARKET MICROSTRUCTURE METRICS
# =============================================================================
"""
This module calculates advanced order flow metrics using vectorized operations
with Polars and NumPy for maximum performance. All calculations are designed
to run in real-time on streaming tick data.

Key Metrics:
- Cumulative Volume Delta (CVD): Running sum of buy/sell volume imbalance
- Volume Profile: Volume distribution across price levels
- Delta Imbalance: Ratio of aggressive buying vs selling pressure
- Footprint Chart Data: Volume-at-price clustering for visualization
- Order Flow Imbalance: Multi-timeframe supply/demand analysis

Performance Notes:
- Uses Polars for lazy evaluation and parallel execution
- Pre-allocates arrays where possible
- Avoids Python loops on hot paths
- Designed for AMD GPU acceleration via ONNX Runtime
"""

import numpy as np
import polars as pl
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class TickData:
    """Single trade/tick record for order flow analysis"""
    timestamp_ns: int
    price: float
    quantity: float
    is_buyer_maker: bool  # True = sell, False = buy
    trade_id: int
    
    @property
    def delta(self) -> float:
        """Signed volume: positive for buys, negative for sells"""
        return self.quantity if not self.is_buyer_maker else -self.quantity


@dataclass
class VolumeProfile:
    """Volume distribution across price levels"""
    price_levels: np.ndarray  # Bin centers
    bid_volume: np.ndarray    # Volume at each level (bid side)
    ask_volume: np.ndarray    # Volume at each level (ask side)
    total_volume: np.ndarray  # Total volume at each level
    poc_price: float          # Point of Control (highest volume price)
    value_area_high: float    # VAH (70% of volume)
    value_area_low: float     # VAL (70% of volume)
    
    def to_dict(self) -> Dict:
        return {
            "price_levels": self.price_levels.tolist(),
            "bid_volume": self.bid_volume.tolist(),
            "ask_volume": self.ask_volume.tolist(),
            "total_volume": self.total_volume.tolist(),
            "poc_price": self.poc_price,
            "vah": self.value_area_high,
            "val": self.value_area_low,
        }


@dataclass
class FootprintBar:
    """Footprint chart bar showing volume at price"""
    timestamp: int
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    bid_ask_matrix: np.ndarray  # [price_bins, 2] - bid/ask volume per price
    total_volume: float
    delta: float
    delta_ratio: float  # Delta / Total Volume
    

class OrderFlowAnalyzer:
    """
    Real-time order flow analytics engine.
    
    Calculates cumulative volume delta, volume profiles, footprint charts,
    and delta imbalances from streaming tick data.
    """
    
    def __init__(
        self,
        symbol: str,
        cvd_window_size: int = 10000,
        footprint_num_levels: int = 50,
        volume_profile_bins: int = 100,
    ):
        self.symbol = symbol
        self.cvd_window_size = cvd_window_size
        self.footprint_num_levels = footprint_num_levels
        self.volume_profile_bins = volume_profile_bins
        
        # Rolling buffers for real-time calculation
        self._tick_buffer: deque = deque(maxlen=cvd_window_size)
        
        # Cumulative Volume Delta
        self.cvd_total: float = 0.0
        self.cvd_rolling: List[float] = []
        
        # Volume profile state
        self._price_min: Optional[float] = None
        self._price_max: Optional[float] = None
        
        # Footprint chart state (current bar)
        self._current_bar_open: Optional[float] = None
        self._current_bar_ticks: List[TickData] = []
        
        # Statistics
        self.total_trades: int = 0
        self.total_volume: float = 0.0
        self.buy_volume: float = 0.0
        self.sell_volume: float = 0.0
        
        # Polars DataFrame for batch analysis
        self._df_cache: Optional[pl.DataFrame] = None
        
    def add_tick(self, tick: TickData) -> None:
        """
        Add a new tick and update all order flow metrics.
        
        This is the main entry point for streaming data.
        All calculations are incremental for low latency.
        """
        # Add to buffer
        self._tick_buffer.append(tick)
        
        # Update cumulative statistics
        self.total_trades += 1
        self.total_volume += tick.quantity
        
        if tick.is_buyer_maker:
            self.sell_volume += tick.quantity
            self.cvd_total -= tick.quantity
        else:
            self.buy_volume += tick.quantity
            self.cvd_total += tick.quantity
        
        # Update price range for volume profile
        if self._price_min is None or tick.price < self._price_min:
            self._price_min = tick.price
        if self._price_max is None or tick.price > self._price_max:
            self._price_max = tick.price
        
        # Add to current footprint bar
        self._current_bar_ticks.append(tick)
        
        # Update rolling CVD
        if len(self._tick_buffer) >= self.cvd_window_size:
            rolling_cvd = sum(t.delta for t in self._tick_buffer)
            self.cvd_rolling.append(rolling_cvd)
            if len(self.cvd_rolling) > 1000:  # Keep last 1000 values
                self.cvd_rolling.pop(0)
    
    def get_cvd(self) -> float:
        """Get current cumulative volume delta"""
        return self.cvd_total
    
    def get_rolling_cvd(self) -> Optional[float]:
        """Get rolling CVD over window size"""
        if len(self.cvd_rolling) > 0:
            return self.cvd_rolling[-1]
        return None
    
    def get_delta_imbalance(self, window_ticks: int = 100) -> float:
        """
        Calculate delta imbalance ratio over recent ticks.
        
        Returns: Ratio between -1 (all sells) and 1 (all buys)
        """
        if len(self._tick_buffer) < window_ticks:
            return 0.0
        
        recent_ticks = list(self._tick_buffer)[-window_ticks:]
        buy_vol = sum(t.quantity for t in recent_ticks if not t.is_buyer_maker)
        sell_vol = sum(t.quantity for t in recent_ticks if t.is_buyer_maker)
        
        total = buy_vol + sell_vol
        if total == 0:
            return 0.0
        
        return (buy_vol - sell_vol) / total
    
    def calculate_volume_profile(
        self,
        lookback_ticks: Optional[int] = None,
    ) -> Optional[VolumeProfile]:
        """
        Calculate volume profile (volume distribution across price levels).
        
        Args:
            lookback_ticks: Number of ticks to include (None = all in buffer)
            
        Returns:
            VolumeProfile with POC, VAH, VAL
        """
        if self._price_min is None or self._price_max is None:
            return None
        
        # Get ticks for analysis
        if lookback_ticks is None:
            ticks = list(self._tick_buffer)
        else:
            ticks = list(self._tick_buffer)[-lookback_ticks:]
        
        if len(ticks) == 0:
            return None
        
        # Create price bins
        price_range = self._price_max - self._price_min
        if price_range == 0:
            return None
            
        bin_size = price_range / self.volume_profile_bins
        bins = np.linspace(self._price_min, self._price_max, self.volume_profile_bins + 1)
        
        # Initialize arrays
        bid_volume = np.zeros(self.volume_profile_bins)
        ask_volume = np.zeros(self.volume_profile_bins)
        
        # Accumulate volume into bins
        for tick in ticks:
            bin_idx = min(
                int((tick.price - self._price_min) / bin_size),
                self.volume_profile_bins - 1
            )
            
            if tick.is_buyer_maker:
                ask_volume[bin_idx] += tick.quantity
            else:
                bid_volume[bin_idx] += tick.quantity
        
        total_volume = bid_volume + ask_volume
        
        # Find Point of Control (price with highest volume)
        poc_idx = np.argmax(total_volume)
        poc_price = (bins[poc_idx] + bins[poc_idx + 1]) / 2
        
        # Calculate Value Area (70% of volume around POC)
        total_vol = total_volume.sum()
        if total_vol > 0:
            va_target = total_vol * 0.70
            
            # Expand from POC until we capture 70% of volume
            cumsum = 0.0
            left_idx = poc_idx
            right_idx = poc_idx
            
            while cumsum < va_target and (left_idx > 0 or right_idx < self.volume_profile_bins - 1):
                if left_idx > 0 and (right_idx < self.volume_profile_bins - 1):
                    if total_volume[left_idx - 1] > total_volume[right_idx + 1]:
                        left_idx -= 1
                        cumsum += total_volume[left_idx]
                    else:
                        right_idx += 1
                        cumsum += total_volume[right_idx]
                elif left_idx > 0:
                    left_idx -= 1
                    cumsum += total_volume[left_idx]
                else:
                    right_idx += 1
                    cumsum += total_volume[right_idx]
            
            value_area_low = bins[left_idx]
            value_area_high = bins[right_idx + 1]
        else:
            value_area_low = self._price_min
            value_area_high = self._price_max
        
        price_levels = (bins[:-1] + bins[1:]) / 2
        
        return VolumeProfile(
            price_levels=price_levels,
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            total_volume=total_volume,
            poc_price=poc_price,
            value_area_high=value_area_high,
            value_area_low=value_area_low,
        )
    
    def calculate_footprint_bars(
        self,
        bar_duration_ns: int = 60_000_000_000,  # 1 minute in nanoseconds
    ) -> List[FootprintBar]:
        """
        Generate footprint chart bars from tick buffer.
        
        Footprint charts show volume traded at each price level within a time period,
        separated by aggressive buys and sells.
        
        Args:
            bar_duration_ns: Duration of each bar in nanoseconds
            
        Returns:
            List of FootprintBar objects
        """
        if len(self._tick_buffer) < 2:
            return []
        
        ticks = list(self._tick_buffer)
        bars = []
        
        # Group ticks by time bucket
        current_bar_start = ticks[0].timestamp_ns
        current_ticks = []
        
        for tick in ticks:
            if tick.timestamp_ns - current_bar_start >= bar_duration_ns:
                # Finalize current bar
                if len(current_ticks) > 0:
                    bar = self._create_footprint_bar(current_ticks, current_bar_start)
                    if bar:
                        bars.append(bar)
                
                # Start new bar
                current_bar_start = tick.timestamp_ns
                current_ticks = []
            
            current_ticks.append(tick)
        
        # Handle remaining ticks
        if len(current_ticks) > 0:
            bar = self._create_footprint_bar(current_ticks, current_bar_start)
            if bar:
                bars.append(bar)
        
        return bars
    
    def _create_footprint_bar(
        self,
        ticks: List[TickData],
        start_time: int,
    ) -> Optional[FootprintBar]:
        """Create a single footprint bar from a list of ticks"""
        if len(ticks) == 0:
            return None
        
        prices = [t.price for t in ticks]
        open_price = prices[0]
        close_price = prices[-1]
        high_price = max(prices)
        low_price = min(prices)
        
        # Create price bins for this bar
        price_range = high_price - low_price
        if price_range == 0:
            # All trades at same price
            bin_size = 0.0001 * open_price  # 0.01% of price
            bins = np.array([low_price - bin_size/2, low_price + bin_size/2])
        else:
            bins = np.linspace(low_price, high_price, self.footprint_num_levels + 1)
        
        bin_size = bins[1] - bins[0] if len(bins) > 1 else 0.0001
        
        # Accumulate bid/ask volume per price level
        num_bins = len(bins) - 1
        bid_ask_matrix = np.zeros((num_bins, 2))  # [price_bin, bid/ask]
        
        for tick in ticks:
            bin_idx = min(
                int((tick.price - bins[0]) / bin_size),
                num_bins - 1
            )
            
            if tick.is_buyer_maker:
                bid_ask_matrix[bin_idx, 1] += tick.quantity  # Ask volume (sells)
            else:
                bid_ask_matrix[bin_idx, 0] += tick.quantity  # Bid volume (buys)
        
        total_volume = sum(t.quantity for t in ticks)
        delta = sum(t.delta for t in ticks)
        delta_ratio = delta / total_volume if total_volume > 0 else 0.0
        
        return FootprintBar(
            timestamp=start_time,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            bid_ask_matrix=bid_ask_matrix,
            total_volume=total_volume,
            delta=delta,
            delta_ratio=delta_ratio,
        )
    
    def get_polars_dataframe(self) -> pl.DataFrame:
        """
        Convert tick buffer to Polars DataFrame for advanced analysis.
        
        This enables lazy evaluation and GPU-accelerated computations.
        """
        if len(self._tick_buffer) == 0:
            return pl.DataFrame()
        
        data = {
            "timestamp_ns": [t.timestamp_ns for t in self._tick_buffer],
            "price": [t.price for t in self._tick_buffer],
            "quantity": [t.quantity for t in self._tick_buffer],
            "is_buyer_maker": [t.is_buyer_maker for t in self._tick_buffer],
            "delta": [t.delta for t in self._tick_buffer],
        }
        
        df = pl.DataFrame(data)
        
        # Cache for reuse
        self._df_cache = df
        
        return df
    
    def calculate_vwap(self, lookback_ticks: int = 1000) -> Optional[float]:
        """Calculate Volume Weighted Average Price"""
        if len(self._tick_buffer) < 2:
            return None
        
        ticks = list(self._tick_buffer)[-lookback_ticks:]
        
        total_pv = sum(t.price * t.quantity for t in ticks)
        total_v = sum(t.quantity for t in ticks)
        
        if total_v == 0:
            return None
        
        return total_pv / total_v
    
    def get_statistics(self) -> Dict:
        """Get summary statistics"""
        return {
            "symbol": self.symbol,
            "total_trades": self.total_trades,
            "total_volume": self.total_volume,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "cvd_total": self.cvd_total,
            "cvd_rolling": self.get_rolling_cvd(),
            "delta_imbalance_100": self.get_delta_imbalance(100),
            "delta_imbalance_500": self.get_delta_imbalance(500),
            "vwap": self.calculate_vwap(),
            "tick_count_in_buffer": len(self._tick_buffer),
        }


def calculate_aggressive_flow(
    df: pl.DataFrame,
    window_size: int = 100,
) -> pl.DataFrame:
    """
    Calculate aggressive buying/selling flow using Polars.
    
    This function identifies periods of sustained aggressive orders,
    which often indicate institutional activity.
    
    Args:
        df: Polars DataFrame with columns: price, quantity, is_buyer_maker
        window_size: Rolling window for aggregation
        
    Returns:
        DataFrame with aggressive flow metrics
    """
    return (
        df
        .with_columns([
            # Rolling sum of buy volume
            pl.col("quantity")
            .filter(pl.col("is_buyer_maker") == False)
            .rolling_sum(window_size=window_size)
            .alias("rolling_buy_volume"),
            
            # Rolling sum of sell volume
            pl.col("quantity")
            .filter(pl.col("is_buyer_maker") == True)
            .rolling_sum(window_size=window_size)
            .alias("rolling_sell_volume"),
            
            # Rolling delta
            pl.col("delta")
            .rolling_sum(window_size=window_size)
            .alias("rolling_delta"),
            
            # Aggressive buy ratio
            (pl.col("rolling_buy_volume") / 
             (pl.col("rolling_buy_volume") + pl.col("rolling_sell_volume")))
            .alias("aggressive_buy_ratio"),
        ])
        .fill_null(0.0)
    )


def detect_absorption(
    df: pl.DataFrame,
    price_threshold: float = 0.001,  # 0.1% price movement
    volume_threshold: float = 10.0,   # 10x average volume
) -> pl.DataFrame:
    """
    Detect absorption patterns where large orders prevent price movement.
    
    Absorption occurs when aggressive selling/buying fails to move price,
    indicating passive limit order absorption (often smart money).
    
    Args:
        df: DataFrame with tick data
        price_threshold: Maximum price change to consider as absorption
        volume_threshold: Minimum volume multiple to flag as absorption
        
    Returns:
        DataFrame with absorption signals
    """
    return (
        df
        .with_columns([
            # Rolling price change
            pl.col("price").pct_change().over("time_bucket").alias("price_change"),
            
            # Rolling volume z-score
            ((pl.col("quantity") - pl.col("quantity").mean()) / 
             pl.col("quantity").std())
            .alias("volume_zscore"),
        ])
        .with_columns([
            # Absorption signal: high volume + low price movement
            (
                (pl.col("volume_zscore") > volume_threshold) &
                (pl.col("price_change").abs() < price_threshold)
            ).alias("absorption_signal")
        ])
    )
