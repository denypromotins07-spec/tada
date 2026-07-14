# /workspace/strategies/src/analytics/smart_money.py
# =============================================================================
# SMART MONEY CONCEPTS (SMC) ANALYTICS ENGINE
# =============================================================================
"""
Real-time detection of Smart Money Concepts patterns:
- Break of Structure (BOS): Price breaking previous high/low with momentum
- Change of Character (CHoCH): First sign of trend reversal
- Fair Value Gaps (FVG): Imbalance zones where price moved too quickly
- Order Blocks: Institutional accumulation/distribution zones
- Liquidity Sweeps: Stop hunts and liquidity grabs

These patterns identify institutional footprints in market data.
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import logging

logger = logging.getLogger(__name__)


class TrendDirection(Enum):
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0


class PatternStrength(Enum):
    WEAK = 1
    MODERATE = 2
    STRONG = 3


@dataclass
class SwingPoint:
    """Represents a significant swing high or low"""
    timestamp_ns: int
    price: float
    is_high: bool  # True = swing high, False = swing low
    strength: PatternStrength
    confirmed: bool = False


@dataclass
class FairValueGap:
    """Fair Value Gap (FVG) / Imbalance zone"""
    start_price: float
    end_price: float
    midpoint: float
    is_bullish: bool  # True = bullish FVG (buying imbalance)
    timestamp_start: int
    timestamp_end: int
    filled: bool = False
    fill_timestamp: Optional[int] = None
    
    def contains_price(self, price: float) -> bool:
        """Check if price is within the FVG zone"""
        min_p = min(self.start_price, self.end_price)
        max_p = max(self.start_price, self.end_price)
        return min_p <= price <= max_p


@dataclass
class OrderBlock:
    """Institutional order block (accumulation/distribution zone)"""
    high: float
    low: float
    midpoint: float
    is_bullish: bool  # True = bullish OB (accumulation)
    timestamp: int
    volume: float
    tested_count: int = 0
    broken: bool = False
    
    def contains_price(self, price: float) -> bool:
        return self.low <= price <= self.high


@dataclass
class LiquidityLevel:
    """Significant liquidity pool (equal highs/lows, swing points)"""
    price: float
    liquidity_type: str  # "BSL" (buy-side), "SSL" (sell-side), "EQH", "EQL"
    strength: float  # Estimated liquidity amount
    timestamp: int
    swept: bool = False
    sweep_timestamp: Optional[int] = None


@dataclass
class SMCSignal:
    """Smart Money Concept signal/event"""
    pattern_type: str  # "BOS", "CHoCH", "FVG", "OB", "LIQUIDITY_SWEEP"
    direction: TrendDirection
    price: float
    timestamp: int
    strength: PatternStrength
    metadata: Dict = field(default_factory=dict)


class SmartMoneyAnalyzer:
    """
    Real-time Smart Money Concepts pattern detector.
    
    Analyzes price action to identify institutional footprints
    including BOS, CHoCH, FVGs, Order Blocks, and Liquidity sweeps.
    """
    
    def __init__(
        self,
        symbol: str,
        swing_lookback: int = 5,  # Bars to look back for swing confirmation
        fvg_min_size: float = 0.001,  # Minimum FVG size (0.1%)
    ):
        self.symbol = symbol
        self.swing_lookback = swing_lookback
        self.fvg_min_size = fvg_min_size
        
        # Price buffer for pattern detection
        self._price_buffer: deque = deque(maxlen=50)
        self._volume_buffer: deque = deque(maxlen=50)
        self._high_buffer: deque = deque(maxlen=50)
        self._low_buffer: deque = deque(maxlen=50)
        self._timestamp_buffer: deque = deque(maxlen=50)
        
        # Detected patterns
        self.swing_points: List[SwingPoint] = []
        self.fvg_list: List[FairValueGap] = []
        self.order_blocks: List[OrderBlock] = []
        self.liquidity_levels: List[LiquidityLevel] = []
        
        # State tracking
        self.last_trend: TrendDirection = TrendDirection.NEUTRAL
        self.last_significant_high: Optional[float] = None
        self.last_significant_low: Optional[float] = None
        
        # Signals queue
        self._signals: deque = deque(maxlen=100)
        
    def add_candle(
        self,
        timestamp_ns: int,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float,
    ) -> List[SMCSignal]:
        """
        Add a new candle and detect SMC patterns.
        
        Returns list of newly detected signals.
        """
        # Add to buffers
        self._price_buffer.append(close_price)
        self._volume_buffer.append(volume)
        self._high_buffer.append(high_price)
        self._low_buffer.append(low_price)
        self._timestamp_buffer.append(timestamp_ns)
        
        signals = []
        
        # Need enough data for pattern detection
        if len(self._price_buffer) >= self.swing_lookback + 2:
            # Detect swing points
            self._detect_swing_points()
            
            # Detect Fair Value Gaps
            new_fvgs = self._detect_fvg(
                open_price, high_price, low_price, close_price, timestamp_ns
            )
            
            # Detect Order Blocks
            new_obs = self._detect_order_block(
                open_price, high_price, low_price, close_price, volume, timestamp_ns
            )
            
            # Check for BOS/CHoCH
            bos_signals = self._check_structure_break(close_price, timestamp_ns)
            signals.extend(bos_signals)
            
            # Check for liquidity sweeps
            sweep_signals = self._check_liquidity_sweep(high_price, low_price, timestamp_ns)
            signals.extend(sweep_signals)
            
            # Update FVG fill status
            self._update_fvg_fills(close_price, timestamp_ns)
            
            # Update order block test status
            self._update_order_block_tests(close_price, timestamp_ns)
        
        return signals
    
    def _detect_swing_points(self) -> None:
        """Detect swing highs and lows from price buffer"""
        if len(self._high_buffer) < self.swing_lookback * 2 + 1:
            return
        
        idx = len(self._high_buffer) - 1 - self.swing_lookback
        
        # Check for swing high
        is_swing_high = all(
            self._high_buffer[idx] > self._high_buffer[idx - i]
            for i in range(1, self.swing_lookback + 1)
        ) and all(
            self._high_buffer[idx] > self._high_buffer[idx + i]
            for i in range(1, self.swing_lookback + 1)
        )
        
        # Check for swing low
        is_swing_low = all(
            self._low_buffer[idx] < self._low_buffer[idx - i]
            for i in range(1, self.swing_lookback + 1)
        ) and all(
            self._low_buffer[idx] < self._low_buffer[idx + i]
            for i in range(1, self.swing_lookback + 1)
        )
        
        if is_swing_high:
            swing = SwingPoint(
                timestamp_ns=self._timestamp_buffer[idx],
                price=self._high_buffer[idx],
                is_high=True,
                strength=self._calculate_swing_strength(idx, is_high=True),
                confirmed=True,
            )
            self.swing_points.append(swing)
            
            # Track significant high
            if self.last_significant_high is None or swing.price > self.last_significant_high:
                self.last_significant_high = swing.price
                
            # Add liquidity level (equal highs potential)
            self._add_liquidity_level(swing.price, "EQH", swing.timestamp_ns)
        
        elif is_swing_low:
            swing = SwingPoint(
                timestamp_ns=self._timestamp_buffer[idx],
                price=self._low_buffer[idx],
                is_high=False,
                strength=self._calculate_swing_strength(idx, is_high=False),
                confirmed=True,
            )
            self.swing_points.append(swing)
            
            # Track significant low
            if self.last_significant_low is None or swing.price < self.last_significant_low:
                self.last_significant_low = swing.price
                
            # Add liquidity level (equal lows potential)
            self._add_liquidity_level(swing.price, "EQL", swing.timestamp_ns)
        
        # Keep only recent swing points
        if len(self.swing_points) > 100:
            self.swing_points = self.swing_points[-50:]
    
    def _calculate_swing_strength(self, idx: int, is_high: bool) -> PatternStrength:
        """Calculate strength of a swing point based on surrounding price action"""
        if is_high:
            center = self._high_buffer[idx]
            surroundings = [
                self._high_buffer[idx - i] for i in range(1, self.swing_lookback + 1)
            ] + [
                self._high_buffer[idx + i] for i in range(1, self.swing_lookback + 1)
            ]
        else:
            center = self._low_buffer[idx]
            surroundings = [
                self._low_buffer[idx - i] for i in range(1, self.swing_lookback + 1)
            ] + [
                self._low_buffer[idx + i] for i in range(1, self.swing_lookback + 1)
            ]
        
        avg_diff = abs(center - np.mean(surroundings))
        pct_diff = avg_diff / center if center > 0 else 0
        
        if pct_diff > 0.02:  # > 2%
            return PatternStrength.STRONG
        elif pct_diff > 0.01:  # > 1%
            return PatternStrength.MODERATE
        else:
            return PatternStrength.WEAK
    
    def _detect_fvg(
        self,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        timestamp_ns: int,
    ) -> List[FairValueGap]:
        """Detect Fair Value Gaps (imbalances)"""
        if len(self._price_buffer) < 3:
            return []
        
        prev_close = self._price_buffer[-2]
        prev2_close = self._price_buffer[-3]
        
        fvgs = []
        
        # Bullish FVG: current low > previous high with gap
        if low_price > high_price and prev_close < prev2_close:
            gap_start = prev_close
            gap_end = low_price
            gap_size = (gap_end - gap_start) / gap_start if gap_start > 0 else 0
            
            if gap_size >= self.fvg_min_size:
                fvg = FairValueGap(
                    start_price=gap_start,
                    end_price=gap_end,
                    midpoint=(gap_start + gap_end) / 2,
                    is_bullish=True,
                    timestamp_start=self._timestamp_buffer[-2],
                    timestamp_end=timestamp_ns,
                )
                self.fvg_list.append(fvg)
                fvgs.append(fvg)
        
        # Bearish FVG: current high < previous low with gap
        elif high_price < low_price and prev_close > prev2_close:
            gap_start = prev_close
            gap_end = high_price
            gap_size = (gap_start - gap_end) / gap_start if gap_start > 0 else 0
            
            if gap_size >= self.fvg_min_size:
                fvg = FairValueGap(
                    start_price=gap_start,
                    end_price=gap_end,
                    midpoint=(gap_start + gap_end) / 2,
                    is_bullish=False,
                    timestamp_start=self._timestamp_buffer[-2],
                    timestamp_end=timestamp_ns,
                )
                self.fvg_list.append(fvg)
                fvgs.append(fvg)
        
        # Keep only recent FVGs
        if len(self.fvg_list) > 50:
            self.fvg_list = [f for f in self.fvg_list if not f.filled][-25:]
        
        return fvgs
    
    def _detect_order_block(
        self,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        volume: float,
        timestamp_ns: int,
    ) -> List[OrderBlock]:
        """Detect potential order blocks (institutional accumulation/distribution)"""
        if len(self._price_buffer) < 5:
            return []
        
        obs = []
        
        # Bullish OB: strong bullish candle after downtrend
        if close_price > open_price and (close_price - open_price) / open_price > 0.01:
            # Check if preceded by bearish candles
            prev_trend_bearish = all(
                self._price_buffer[-i] < self._price_buffer[-i-1]
                for i in range(2, 5)
            )
            
            if prev_trend_bearish:
                ob = OrderBlock(
                    high=high_price,
                    low=low_price,
                    midpoint=(high_price + low_price) / 2,
                    is_bullish=True,
                    timestamp=timestamp_ns,
                    volume=volume,
                )
                self.order_blocks.append(ob)
                obs.append(ob)
        
        # Bearish OB: strong bearish candle after uptrend
        elif close_price < open_price and (open_price - close_price) / open_price > 0.01:
            prev_trend_bullish = all(
                self._price_buffer[-i] > self._price_buffer[-i-1]
                for i in range(2, 5)
            )
            
            if prev_trend_bullish:
                ob = OrderBlock(
                    high=high_price,
                    low=low_price,
                    midpoint=(high_price + low_price) / 2,
                    is_bullish=False,
                    timestamp=timestamp_ns,
                    volume=volume,
                )
                self.order_blocks.append(ob)
                obs.append(ob)
        
        # Keep only recent order blocks
        if len(self.order_blocks) > 30:
            self.order_blocks = [ob for ob in self.order_blocks if not ob.broken][-15:]
        
        return obs
    
    def _check_structure_break(
        self,
        current_price: float,
        timestamp_ns: int,
    ) -> List[SMCSignal]:
        """Check for Break of Structure (BOS) or Change of Character (CHoCH)"""
        signals = []
        
        if self.last_significant_high is None or self.last_significant_low is None:
            return signals
        
        # Bullish BOS: Price breaks above previous significant high
        if current_price > self.last_significant_high and self.last_trend != TrendDirection.BULLISH:
            signal = SMCSignal(
                pattern_type="BOS",
                direction=TrendDirection.BULLISH,
                price=current_price,
                timestamp=timestamp_ns,
                strength=PatternStrength.STRONG,
                metadata={
                    "broken_level": self.last_significant_high,
                    "previous_trend": self.last_trend.name,
                }
            )
            signals.append(signal)
            self._signals.append(signal)
            self.last_trend = TrendDirection.BULLISH
        
        # Bearish BOS: Price breaks below previous significant low
        elif current_price < self.last_significant_low and self.last_trend != TrendDirection.BEARISH:
            signal = SMCSignal(
                pattern_type="BOS",
                direction=TrendDirection.BEARISH,
                price=current_price,
                timestamp=timestamp_ns,
                strength=PatternStrength.STRONG,
                metadata={
                    "broken_level": self.last_significant_low,
                    "previous_trend": self.last_trend.name,
                }
            )
            signals.append(signal)
            self._signals.append(signal)
            self.last_trend = TrendDirection.BEARISH
        
        return signals
    
    def _check_liquidity_sweep(
        self,
        high_price: float,
        low_price: float,
        timestamp_ns: int,
    ) -> List[SMCSignal]:
        """Check for liquidity sweeps (stop hunts)"""
        signals = []
        
        for liq in self.liquidity_levels:
            if liq.swept:
                continue
            
            # Buy-side liquidity sweep (high taken out then rejected)
            if liq.liquidity_type in ["BSL", "EQH"] and high_price > liq.price:
                signal = SMCSignal(
                    pattern_type="LIQUIDITY_SWEEP",
                    direction=TrendDirection.BEARISH,  # Sweep often leads to reversal
                    price=high_price,
                    timestamp=timestamp_ns,
                    strength=PatternStrength.MODERATE,
                    metadata={
                        "swept_level": liq.price,
                        "liquidity_type": liq.liquidity_type,
                    }
                )
                signals.append(signal)
                self._signals.append(signal)
                liq.swept = True
                liq.sweep_timestamp = timestamp_ns
            
            # Sell-side liquidity sweep (low taken out then rejected)
            elif liq.liquidity_type in ["SSL", "EQL"] and low_price < liq.price:
                signal = SMCSignal(
                    pattern_type="LIQUIDITY_SWEEP",
                    direction=TrendDirection.BULLISH,
                    price=low_price,
                    timestamp=timestamp_ns,
                    strength=PatternStrength.MODERATE,
                    metadata={
                        "swept_level": liq.price,
                        "liquidity_type": liq.liquidity_type,
                    }
                )
                signals.append(signal)
                self._signals.append(signal)
                liq.swept = True
                liq.sweep_timestamp = timestamp_ns
        
        return signals
    
    def _add_liquidity_level(self, price: float, liq_type: str, timestamp_ns: int) -> None:
        """Add a liquidity level"""
        # Check if similar level already exists
        for liq in self.liquidity_levels:
            if abs(liq.price - price) / price < 0.001:  # Within 0.1%
                liq.strength += 1.0
                return
        
        liq = LiquidityLevel(
            price=price,
            liquidity_type=liq_type,
            strength=1.0,
            timestamp=timestamp_ns,
        )
        self.liquidity_levels.append(liq)
        
        if len(self.liquidity_levels) > 50:
            self.liquidity_levels = self.liquidity_levels[-25:]
    
    def _update_fvg_fills(self, current_price: float, timestamp_ns: int) -> None:
        """Update FVG fill status"""
        for fvg in self.fvg_list:
            if not fvg.filled and fvg.contains_price(current_price):
                fvg.filled = True
                fvg.fill_timestamp = timestamp_ns
    
    def _update_order_block_tests(self, current_price: float, timestamp_ns: int) -> None:
        """Update order block test count and broken status"""
        for ob in self.order_blocks:
            if ob.contains_price(current_price):
                ob.tested_count += 1
            
            # Check if broken
            if ob.is_bullish and current_price < ob.low:
                ob.broken = True
            elif not ob.is_bullish and current_price > ob.high:
                ob.broken = True
    
    def get_active_fvgs(self) -> List[FairValueGap]:
        """Get unfilled Fair Value Gaps"""
        return [fvg for fvg in self.fvg_list if not fvg.filled]
    
    def get_active_order_blocks(self) -> List[OrderBlock]:
        """Get unbroken Order Blocks"""
        return [ob for ob in self.order_blocks if not ob.broken]
    
    def get_recent_signals(self, limit: int = 10) -> List[SMCSignal]:
        """Get most recent SMC signals"""
        return list(self._signals)[-limit:]
    
    def get_market_structure(self) -> Dict:
        """Get current market structure summary"""
        return {
            "trend": self.last_trend.name,
            "last_significant_high": self.last_significant_high,
            "last_significant_low": self.last_significant_low,
            "active_fvg_count": len(self.get_active_fvgs()),
            "active_ob_count": len(self.get_active_order_blocks()),
            "swing_points_count": len(self.swing_points),
        }
