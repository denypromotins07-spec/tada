# /workspace/strategies/src/analytics/microstructure.py
# =============================================================================
# MARKET MICROSTRUCTURE ANALYTICS ENGINE
# =============================================================================
"""
Advanced market microstructure analysis for detecting:
- Liquidity Sweeps: Rapid price movements that take out stops
- Absorption: Large orders preventing price movement
- Aggressive Buying/Selling: Market order imbalances
- Iceberg Order Detection: Hidden large orders
- Order Flow Toxicity: Adverse selection risk

These metrics help identify institutional activity and potential reversals.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class MicrostructureSignal(Enum):
    LIQUIDITY_SWEEP = "liquidity_sweep"
    ABSORPTION = "absorption"
    AGGRESSIVE_BUY = "aggressive_buy"
    AGGRESSIVE_SELL = "aggressive_sell"
    ICEBERG_DETECTED = "iceberg_detected"
    TOXIC_FLOW = "toxic_flow"


@dataclass
class TickData:
    """Single tick for microstructure analysis"""
    timestamp_ns: int
    price: float
    quantity: float
    is_buyer_maker: bool
    trade_id: int


@dataclass
class OrderBookSnapshot:
    """Order book state snapshot"""
    timestamp_ns: int
    bids: List[Tuple[float, float]]  # (price, size)
    asks: List[Tuple[float, float]]
    spread: float
    mid_price: float


@dataclass
class MicrostructureEvent:
    """Detected microstructure event"""
    signal_type: MicrostructureSignal
    timestamp_ns: int
    price: float
    confidence: float  # 0.0 to 1.0
    metadata: Dict = field(default_factory=dict)


class MicrostructureAnalyzer:
    """
    Real-time market microstructure analyzer.
    
    Detects subtle patterns in order flow and order book dynamics
    that indicate institutional activity or market manipulation.
    """
    
    def __init__(
        self,
        symbol: str,
        tick_window: int = 500,
        absorption_threshold: float = 5.0,  # Volume z-score
        iceberg_min_size: float = 10.0,     # Minimum hidden volume ratio
    ):
        self.symbol = symbol
        self.tick_window = tick_window
        self.absorption_threshold = absorption_threshold
        self.iceberg_min_size = iceberg_min_size
        
        # Tick buffers
        self._tick_buffer: deque = deque(maxlen=tick_window)
        self._price_buffer: deque = deque(maxlen=tick_window)
        self._volume_buffer: deque = deque(maxlen=tick_window)
        self._delta_buffer: deque = deque(maxlen=tick_window)
        
        # Order book snapshots
        self._ob_buffer: deque = deque(maxlen=100)
        
        # Statistics tracking
        self._volume_mean: float = 0.0
        self._volume_std: float = 1.0
        self._price_change_mean: float = 0.0
        self._price_change_std: float = 0.001
        
        # Detected events
        self._events: deque = deque(maxlen=200)
        
        # State flags
        self._last_liquidity_high: Optional[float] = None
        self._last_liquidity_low: Optional[float] = None
        
    def add_tick(self, tick: TickData) -> Optional[MicrostructureEvent]:
        """
        Add a tick and check for microstructure patterns.
        
        Returns detected event if any pattern triggered.
        """
        # Add to buffers
        self._tick_buffer.append(tick)
        self._price_buffer.append(tick.price)
        self._volume_buffer.append(tick.quantity)
        
        delta = tick.quantity if not tick.is_buyer_maker else -tick.quantity
        self._delta_buffer.append(delta)
        
        # Update rolling statistics
        self._update_statistics()
        
        # Check for patterns
        event = None
        
        if len(self._tick_buffer) >= 50:
            # Check for absorption
            if self._check_absorption(tick):
                event = MicrostructureEvent(
                    signal_type=MicrostructureSignal.ABSORPTION,
                    timestamp_ns=tick.timestamp_ns,
                    price=tick.price,
                    confidence=0.8,
                    metadata={"volume": tick.quantity}
                )
            
            # Check for aggressive flow
            elif self._check_aggressive_flow(tick):
                direction = (
                    MicrostructureSignal.AGGRESSIVE_BUY 
                    if not tick.is_buyer_maker 
                    else MicrostructureSignal.AGGRESSIVE_SELL
                )
                event = MicrostructureEvent(
                    signal_type=direction,
                    timestamp_ns=tick.timestamp_ns,
                    price=tick.price,
                    confidence=0.7,
                    metadata={"volume": tick.quantity, "delta": delta}
                )
            
            # Check for iceberg orders
            elif self._check_iceberg(tick):
                event = MicrostructureEvent(
                    signal_type=MicrostructureSignal.ICEBERG_DETECTED,
                    timestamp_ns=tick.timestamp_ns,
                    price=tick.price,
                    confidence=0.6,
                    metadata={"estimated_hidden": tick.quantity * self.iceberg_min_size}
                )
        
        if event:
            self._events.append(event)
        
        return event
    
    def add_order_book_snapshot(self, snapshot: OrderBookSnapshot) -> None:
        """Add order book snapshot for liquidity analysis"""
        self._ob_buffer.append(snapshot)
        
        # Track liquidity levels
        if snapshot.bids:
            best_bid = snapshot.bids[0][0]
            if self._last_liquidity_low is None or best_bid < self._last_liquidity_low:
                self._last_liquidity_low = best_bid
        
        if snapshot.asks:
            best_ask = snapshot.asks[0][0]
            if self._last_liquidity_high is None or best_ask > self._last_liquidity_high:
                self._last_liquidity_high = best_ask
    
    def _update_statistics(self) -> None:
        """Update rolling statistics for anomaly detection"""
        if len(self._volume_buffer) < 10:
            return
        
        volumes = list(self._volume_buffer)[-100:]
        self._volume_mean = np.mean(volumes)
        self._volume_std = max(np.std(volumes), 0.0001)
        
        if len(self._price_buffer) >= 2:
            prices = list(self._price_buffer)[-100:]
            changes = np.diff(prices) / prices[:-1]
            self._price_change_mean = np.mean(changes)
            self._price_change_std = max(np.std(changes), 0.00001)
    
    def _check_absorption(self, tick: TickData) -> bool:
        """
        Detect absorption: large volume with minimal price impact.
        
        This indicates passive limit orders absorbing aggressive flow.
        """
        if self._volume_std == 0:
            return False
        
        # Calculate volume z-score
        volume_zscore = (tick.quantity - self._volume_mean) / self._volume_std
        
        if volume_zscore < self.absorption_threshold:
            return False
        
        # Check price impact over recent ticks
        if len(self._price_buffer) < 10:
            return False
        
        recent_prices = list(self._price_buffer)[-10:]
        price_range = max(recent_prices) - min(recent_prices)
        avg_price = np.mean(recent_prices)
        
        if avg_price == 0:
            return False
        
        price_impact = price_range / avg_price
        
        # Absorption: high volume but low price movement
        return price_impact < 0.0005  # Less than 0.05% movement
    
    def _check_aggressive_flow(self, tick: TickData) -> bool:
        """
        Detect sustained aggressive buying or selling.
        
        Identifies when one side is dominating the order flow.
        """
        if len(self._delta_buffer) < 20:
            return False
        
        recent_deltas = list(self._delta_buffer)[-20:]
        total_delta = sum(recent_deltas)
        total_volume = sum(abs(d) for d in recent_deltas)
        
        if total_volume == 0:
            return False
        
        # Calculate imbalance ratio
        imbalance = total_delta / total_volume
        
        # Check if current tick is part of aggressive flow
        current_delta = tick.quantity if not tick.is_buyer_maker else -tick.quantity
        
        return (
            abs(imbalance) > 0.6 and  # Strong directional bias
            abs(current_delta) > self._volume_mean * 2  # Above average size
        )
    
    def _check_iceberg(self, tick: TickData) -> bool:
        """
        Detect potential iceberg orders.
        
        Icebergs show as repeated trades at same price level
        without significant price movement.
        """
        if len(self._price_buffer) < 20:
            return False
        
        # Look for repeated trades at similar price
        recent_ticks = list(self._tick_buffer)[-20:]
        
        # Group by price level (rounded to nearest tick)
        price_tolerance = tick.price * 0.0001  # 0.01%
        same_price_trades = [
            t for t in recent_ticks
            if abs(t.price - tick.price) < price_tolerance
        ]
        
        if len(same_price_trades) < 5:
            return False
        
        # Calculate total volume at this price
        total_at_price = sum(t.quantity for t in same_price_trades)
        
        # Compare to average trade size
        avg_trade_size = np.mean([t.quantity for t in recent_ticks])
        
        # Iceberg indicator: many trades at same price with large total volume
        return (
            total_at_price > avg_trade_size * self.iceberg_min_size and
            len(same_price_trades) >= 5
        )
    
    def check_liquidity_sweep(
        self,
        high_price: float,
        low_price: float,
        timestamp_ns: int,
    ) -> Optional[MicrostructureEvent]:
        """
        Detect liquidity sweeps (stop hunts).
        
        A sweep occurs when price briefly takes out a key level
        then quickly reverses.
        """
        if self._last_liquidity_high is None or self._last_liquidity_low is None:
            return None
        
        event = None
        
        # Check for buy-side liquidity sweep
        if high_price > self._last_liquidity_high:
            # Verify quick reversal (check last few ticks)
            if len(self._price_buffer) >= 5:
                recent = list(self._price_buffer)[-5:]
                if recent[-1] < self._last_liquidity_high:  # Reversed back
                    event = MicrostructureEvent(
                        signal_type=MicrostructureSignal.LIQUIDITY_SWEEP,
                        timestamp_ns=timestamp_ns,
                        price=high_price,
                        confidence=0.75,
                        metadata={
                            "swept_level": self._last_liquidity_high,
                            "type": "buy_side",
                        }
                    )
        
        # Check for sell-side liquidity sweep
        elif low_price < self._last_liquidity_low:
            if len(self._price_buffer) >= 5:
                recent = list(self._price_buffer)[-5:]
                if recent[-1] > self._last_liquidity_low:  # Reversed back
                    event = MicrostructureEvent(
                        signal_type=MicrostructureSignal.LIQUIDITY_SWEEP,
                        timestamp_ns=timestamp_ns,
                        price=low_price,
                        confidence=0.75,
                        metadata={
                            "swept_level": self._last_liquidity_low,
                            "type": "sell_side",
                        }
                    )
        
        if event:
            self._events.append(event)
        
        return event
    
    def calculate_vpin(self, window_size: int = 50) -> Optional[float]:
        """
        Calculate VPIN (Volume-Synchronized Probability of Informed Trading).
        
        VPIN measures order flow toxicity - the probability that trades
        are driven by informed traders rather than noise.
        
        High VPIN indicates adverse selection risk.
        """
        if len(self._delta_buffer) < window_size:
            return None
        
        deltas = list(self._delta_buffer)[-window_size:]
        
        # Calculate buy and sell volumes
        buy_vol = sum(d for d in deltas if d > 0)
        sell_vol = sum(-d for d in deltas if d < 0)
        
        total_vol = buy_vol + sell_vol
        if total_vol == 0:
            return 0.0
        
        # VPIN = |Buy - Sell| / (Buy + Sell)
        vpin = abs(buy_vol - sell_vol) / total_vol
        
        return vpin
    
    def calculate_spread_metrics(self) -> Dict:
        """Calculate spread-related metrics from order book snapshots"""
        if len(self._ob_buffer) < 5:
            return {}
        
        spreads = [ob.spread for ob in self._ob_buffer]
        mid_prices = [ob.mid_price for ob in self._ob_buffer]
        
        return {
            "avg_spread": np.mean(spreads),
            "spread_std": np.std(spreads),
            "min_spread": min(spreads),
            "max_spread": max(spreads),
            "current_spread": spreads[-1],
            "avg_mid_price": np.mean(mid_prices),
        }
    
    def get_recent_events(self, limit: int = 20) -> List[MicrostructureEvent]:
        """Get most recent microstructure events"""
        return list(self._events)[-limit:]
    
    def get_statistics_summary(self) -> Dict:
        """Get summary of current microstructure statistics"""
        vpin = self.calculate_vpin()
        spread_metrics = self.calculate_spread_metrics()
        
        return {
            "symbol": self.symbol,
            "tick_count": len(self._tick_buffer),
            "volume_mean": self._volume_mean,
            "volume_std": self._volume_std,
            "vpin": vpin,
            "spread_metrics": spread_metrics,
            "recent_event_count": len(self._events),
        }


def calculate_kyle_lambda(
    returns: np.ndarray,
    volumes: np.ndarray,
    window: int = 100,
) -> np.ndarray:
    """
    Calculate Kyle's Lambda (price impact coefficient).
    
    Kyle's Lambda measures how much price moves per unit of volume.
    Higher values indicate lower liquidity / higher impact.
    
    Args:
        returns: Array of price returns
        volumes: Array of traded volumes
        window: Rolling window size
        
    Returns:
        Array of Kyle's Lambda estimates
    """
    if len(returns) < window:
        return np.array([])
    
    lambdas = []
    
    for i in range(window, len(returns)):
        r_window = returns[i-window:i]
        v_window = volumes[i-window:i]
        
        # Kyle's Lambda = Cov(return, signed_volume) / Var(signed_volume)
        # Simplified: use absolute volume as proxy
        if np.var(v_window) > 0:
            cov = np.cov(r_window, v_window)[0, 1]
            var = np.var(v_window)
            lambda_val = cov / var if var > 0 else 0
        else:
            lambda_val = 0
        
        lambdas.append(lambda_val)
    
    return np.array(lambdas)


def hasbrouck_information_share(
    price_changes_1: np.ndarray,
    price_changes_2: np.ndarray,
) -> float:
    """
    Calculate Hasbrouck Information Share between two markets.
    
    Measures which market contributes more to price discovery.
    Useful for multi-exchange arbitrage analysis.
    
    Args:
        price_changes_1: Returns from market 1
        price_changes_2: Returns from market 2
        
    Returns:
        Information share of market 1 (0 to 1)
    """
    if len(price_changes_1) != len(price_changes_2):
        raise ValueError("Arrays must have same length")
    
    # Simple variance decomposition
    var1 = np.var(price_changes_1)
    var2 = np.var(price_changes_2)
    cov = np.cov(price_changes_1, price_changes_2)[0, 1]
    
    total_var = var1 + var2 + 2 * cov
    
    if total_var == 0:
        return 0.5
    
    # Market 1's contribution to common efficient price
    info_share = (var1 + cov) / total_var
    
    return max(0.0, min(1.0, info_share))
