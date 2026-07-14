"""
Technical Analysis Agent - Domains 16-30
Responsible for calculating SMC concepts (BOS, CHoCH, Order Blocks, FVG)
and traditional indicators (RSI, MACD, VWAP).

Uses vectorized NumPy/Pandas operations for efficient calculation.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from collections import deque
import numpy as np
import pandas as pd
import redis.asyncio as redis

from agents.base_agent import BaseAgent, memory_profile, observe, think, act


class SMCConcept:
    """Smart Money Concepts signal types"""
    BOS = "BREAK_OF_STRUCTURE"  # Higher high in uptrend, lower low in downtrend
    CHOC = "CHANGE_OF_CHARACTER"  # First sign of trend reversal
    ORDER_BLOCK = "ORDER_BLOCK"
    FAIR_VALUE_GAP = "FVG"
    LIQUIDITY_POOL = "LIQUIDITY_POOL"
    MITIGATION = "MITIGATION"


class TechnicalAnalysisAgent(BaseAgent):
    """
    Technical Analysis Agent (Domains 16-30):
    - Domain 16-20: Traditional Indicators (RSI, MACD, Bollinger Bands)
    - Domain 21-25: Volume Analysis (VWAP, Volume Profile)
    - Domain 26-30: Smart Money Concepts (SMC)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("TechnicalAnalysisAgent", config)
        
        self.redis_client: Optional[redis.Redis] = None
        
        # OHLCV data storage per symbol
        self.ohlcv_data: Dict[str, deque] = {}
        self.max_ohlcv_length = config.get("max_ohlcv_length", 500)  # Keep 500 candles
        
        # SMC detection parameters
        self.swing_lookback = config.get("swing_lookback", 5)  # Bars for swing detection
        self.fvg_min_size = config.get("fvg_min_size_pct", 0.0005)  # 0.05% min FVG size
        
        # Detected patterns cache
        self.order_blocks: Dict[str, List[Dict]] = {}
        self.fvgs: Dict[str, List[Dict]] = {}
        self.structure_points: Dict[str, List[Dict]] = {}
        
    async def initialize(self):
        """Initialize connections and state"""
        await super().initialize()
        
        self.redis_client = redis.Redis(
            host=self.config.get("redis_host", "localhost"),
            port=self.config.get("redis_port", 6379),
            decode_responses=True
        )
        
        self.logger.info(f"TechnicalAnalysisAgent initialized with ID: {self.agent_id}")

    @memory_profile
    @observe
    async def observe(self, data: Optional[Dict] = None) -> Dict:
        """
        Observe price data and update OHLCV candles
        """
        observations = {
            "timestamp": int(time.time() * 1000),
            "symbols": {},
            "candle_count": {},
        }
        
        if data:
            symbol = data.get("symbol", "UNKNOWN")
            
            if symbol not in self.ohlcv_data:
                self.ohlcv_data[symbol] = deque(maxlen=self.max_ohlcv_length)
                self.order_blocks[symbol] = []
                self.fvgs[symbol] = []
                self.structure_points[symbol] = []
            
            # Convert tick to candle (simplified - would aggregate properly in production)
            candle = {
                "timestamp": data.get("timestamp", int(time.time() * 1000)),
                "open": float(data.get("last_price", 0)),
                "high": float(data.get("high_price", data.get("last_price", 0))),
                "low": float(data.get("low_price", data.get("last_price", 0))),
                "close": float(data.get("last_price", 0)),
                "volume": float(data.get("volume", 0)),
            }
            
            # Update current candle or add new one
            if self.ohlcv_data[symbol] and self._same_candle_period(
                self.ohlcv_data[symbol][-1]["timestamp"], candle["timestamp"]
            ):
                # Update existing candle
                last_candle = self.ohlcv_data[symbol][-1]
                last_candle["high"] = max(last_candle["high"], candle["high"])
                last_candle["low"] = min(last_candle["low"], candle["low"])
                last_candle["close"] = candle["close"]
                last_candle["volume"] += candle["volume"]
            else:
                # Add new candle
                self.ohlcv_data[symbol].append(candle)
            
            observations["symbols"][symbol] = candle
            observations["candle_count"][symbol] = len(self.ohlcv_data[symbol])
        
        return observations

    @memory_profile
    @think
    async def think(self, observations: Dict) -> Dict:
        """
        Calculate technical indicators and detect SMC patterns:
        - RSI, MACD, Bollinger Bands
        - VWAP, Volume Profile
        - BOS, CHoCH, Order Blocks, FVG
        """
        thoughts = {
            "traditional_indicators": {},
            "volume_indicators": {},
            "smc_patterns": [],
            "structure_analysis": {},
        }
        
        for symbol in observations.get("symbols", {}).keys():
            if symbol not in self.ohlcv_data or len(self.ohlcv_data[symbol]) < 50:
                continue
            
            # Convert to DataFrame for vectorized calculations
            df = pd.DataFrame(list(self.ohlcv_data[symbol]))
            
            # Calculate traditional indicators
            thoughts["traditional_indicators"][symbol] = self._calculate_traditional_indicators(df)
            
            # Calculate volume indicators
            thoughts["volume_indicators"][symbol] = self._calculate_volume_indicators(df)
            
            # Detect SMC patterns
            smc_patterns = self._detect_smc_patterns(df, symbol)
            thoughts["smc_patterns"].extend(smc_patterns)
            
            # Analyze market structure
            thoughts["structure_analysis"][symbol] = self._analyze_structure(df, symbol)
        
        return thoughts

    @memory_profile
    @act
    async def act(self, thoughts: Dict) -> Dict:
        """
        Publish technical analysis signals to Redis Pub/Sub
        """
        actions = {
            "signals_published": [],
            "patterns_cached": 0,
        }
        
        # Publish traditional indicator signals
        for symbol, indicators in thoughts.get("traditional_indicators", {}).items():
            signal_payload = {
                "agent": self.agent_name,
                "signal_type": "TECHNICAL_INDICATORS",
                "symbol": symbol,
                "data": indicators,
                "timestamp": int(time.time() * 1000),
            }
            await self.redis_client.publish(
                "agent:strategy:indicators",
                json.dumps(signal_payload)
            )
            actions["signals_published"].append(signal_payload)
        
        # Publish SMC pattern signals
        for pattern in thoughts.get("smc_patterns", []):
            signal_payload = {
                "agent": self.agent_name,
                "signal_type": pattern["pattern_type"],
                "symbol": pattern["symbol"],
                "direction": pattern.get("direction", "NEUTRAL"),
                "price_level": pattern.get("price_level", 0),
                "confidence": pattern.get("confidence", 0.5),
                "timestamp": int(time.time() * 1000),
            }
            
            await self.redis_client.publish(
                "agent:supervisor:signals",
                json.dumps(signal_payload)
            )
            actions["signals_published"].append(signal_payload)
            actions["patterns_cached"] += 1
        
        return actions

    def _same_candle_period(self, ts1: int, ts2: int, period_ms: int = 60000) -> bool:
        """Check if two timestamps are in the same candle period"""
        return (ts1 // period_ms) == (ts2 // period_ms)

    def _calculate_traditional_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate RSI, MACD, Bollinger Bands using vectorized operations"""
        close = df["close"].values
        
        # RSI (14-period)
        rsi_period = 14
        delta = np.diff(close)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        
        avg_gain = np.convolve(gain, np.ones(rsi_period)/rsi_period, mode='valid')
        avg_loss = np.convolve(loss, np.ones(rsi_period)/rsi_period, mode='valid')
        
        rs = np.divide(avg_gain, avg_loss + 1e-10, out=np.zeros_like(avg_gain), where=avg_loss!=0)
        rsi = 100 - (100 / (1 + rs))
        
        # MACD (12, 26, 9)
        ema12 = self._ema(close, 12)
        ema26 = self._ema(close, 26)
        macd_line = ema12 - ema26
        signal_line = self._ema(macd_line, 9)
        macd_histogram = macd_line - signal_line
        
        # Bollinger Bands (20, 2)
        bb_period = 20
        bb_std = 2
        sma = np.convolve(close, np.ones(bb_period)/bb_period, mode='valid')
        std = np.array([np.std(close[i:i+bb_period]) for i in range(len(close)-bb_period+1)])
        bb_upper = sma + bb_std * std
        bb_lower = sma - bb_std * std
        bb_width = (bb_upper - bb_lower) / sma
        
        return {
            "rsi": float(rsi[-1]) if len(rsi) > 0 else 50.0,
            "macd": {
                "line": float(macd_line[-1]) if len(macd_line) > 0 else 0.0,
                "signal": float(signal_line[-1]) if len(signal_line) > 0 else 0.0,
                "histogram": float(macd_histogram[-1]) if len(macd_histogram) > 0 else 0.0,
            },
            "bollinger_bands": {
                "upper": float(bb_upper[-1]) if len(bb_upper) > 0 else close[-1],
                "middle": float(sma[-1]) if len(sma) > 0 else close[-1],
                "lower": float(bb_lower[-1]) if len(bb_lower) > 0 else close[-1],
                "width": float(bb_width[-1]) if len(bb_width) > 0 else 0.0,
                "position": float((close[-1] - bb_lower[-1]) / (bb_upper[-1] - bb_lower[-1] + 1e-10)) if len(bb_lower) > 0 else 0.5,
            },
        }

    def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate VWAP and volume profile metrics"""
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        volume = df["volume"].values
        
        # VWAP (cumulative)
        cum_vol = np.cumsum(volume)
        cum_tp_vol = np.cumsum(typical_price.values * volume)
        vwap = cum_tp_vol / cum_vol
        
        # Volume-weighted momentum
        vol_weighted_return = np.sum(np.diff(typical_price.values) * volume[:-1]) / np.sum(volume[:-1] + 1e-10)
        
        return {
            "vwap": float(vwap[-1]) if len(vwap) > 0 else typical_price.iloc[-1],
            "vwap_deviation": float((typical_price.iloc[-1] - vwap[-1]) / vwap[-1]) if len(vwap) > 0 else 0.0,
            "volume_weighted_momentum": float(vol_weighted_return),
            "avg_volume": float(np.mean(volume[-20:])) if len(volume) >= 20 else float(np.mean(volume)),
        }

    def _detect_smc_patterns(self, df: pd.DataFrame, symbol: str) -> List[Dict]:
        """Detect Smart Money Concepts patterns"""
        patterns = []
        
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        
        # Detect swings
        swing_highs = self._find_swing_highs(highs, self.swing_lookback)
        swing_lows = self._find_swing_lows(lows, self.swing_lookback)
        
        # Detect BOS (Break of Structure)
        bos_patterns = self._detect_bos(swing_highs, swing_lows, closes)
        for bos in bos_patterns:
            patterns.append({
                "pattern_type": SMCConcept.BOS,
                "symbol": symbol,
                "direction": bos["direction"],
                "price_level": bos["price"],
                "confidence": bos["confidence"],
                "timestamp": int(time.time() * 1000),
            })
        
        # Detect Fair Value Gaps (FVG)
        fvg_patterns = self._detect_fvg(df)
        for fvg in fvg_patterns:
            patterns.append({
                "pattern_type": SMCConcept.FAIR_VALUE_GAP,
                "symbol": symbol,
                "direction": fvg["direction"],
                "price_level": fvg["mid_price"],
                "zone_top": fvg["zone_top"],
                "zone_bottom": fvg["zone_bottom"],
                "confidence": fvg["confidence"],
                "timestamp": int(time.time() * 1000),
            })
        
        # Detect Order Blocks
        ob_patterns = self._detect_order_blocks(df)
        for ob in ob_patterns:
            patterns.append({
                "pattern_type": SMCConcept.ORDER_BLOCK,
                "symbol": symbol,
                "direction": ob["direction"],
                "zone_top": ob["zone_top"],
                "zone_bottom": ob["zone_bottom"],
                "confidence": ob["confidence"],
                "timestamp": int(time.time() * 1000),
            })
        
        return patterns

    def _find_swing_highs(self, highs: np.ndarray, lookback: int) -> List[Tuple[int, float]]:
        """Find swing high points"""
        swing_highs = []
        for i in range(lookback, len(highs) - lookback):
            if all(highs[i] >= highs[i-j] for j in range(1, lookback+1)) and \
               all(highs[i] >= highs[i+j] for j in range(1, lookback+1)):
                swing_highs.append((i, float(highs[i])))
        return swing_highs

    def _find_swing_lows(self, lows: np.ndarray, lookback: int) -> List[Tuple[int, float]]:
        """Find swing low points"""
        swing_lows = []
        for i in range(lookback, len(lows) - lookback):
            if all(lows[i] <= lows[i-j] for j in range(1, lookback+1)) and \
               all(lows[i] <= lows[i+j] for j in range(1, lookback+1)):
                swing_lows.append((i, float(lows[i])))
        return swing_lows

    def _detect_bos(self, swing_highs: List, swing_lows: List, closes: np.ndarray) -> List[Dict]:
        """Detect Break of Structure"""
        bos_signals = []
        
        if len(swing_highs) >= 2:
            # Check for higher high (bullish BOS)
            recent_high = swing_highs[-1][1]
            prev_high = swing_highs[-2][1]
            
            if recent_high > prev_high and closes[-1] > recent_high:
                bos_signals.append({
                    "direction": "BULLISH",
                    "price": float(recent_high),
                    "confidence": min((recent_high - prev_high) / prev_high * 100, 1.0),
                })
        
        if len(swing_lows) >= 2:
            # Check for lower low (bearish BOS)
            recent_low = swing_lows[-1][1]
            prev_low = swing_lows[-2][1]
            
            if recent_low < prev_low and closes[-1] < recent_low:
                bos_signals.append({
                    "direction": "BEARISH",
                    "price": float(recent_low),
                    "confidence": min((prev_low - recent_low) / prev_low * 100, 1.0),
                })
        
        return bos_signals

    def _detect_fvg(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Fair Value Gaps"""
        fvgs = []
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        
        for i in range(2, len(closes)):
            # Bullish FVG: previous candle low > current candle high
            if lows[i-2] > highs[i]:
                gap_size = (lows[i-2] - highs[i]) / lows[i-2]
                if gap_size >= self.fvg_min_size:
                    fvgs.append({
                        "direction": "BULLISH",
                        "zone_top": float(lows[i-2]),
                        "zone_bottom": float(highs[i]),
                        "mid_price": (float(lows[i-2]) + float(highs[i])) / 2,
                        "confidence": min(gap_size / 0.001, 1.0),
                    })
            
            # Bearish FVG: previous candle high < current candle low
            if highs[i-2] < lows[i]:
                gap_size = (lows[i] - highs[i-2]) / highs[i-2]
                if gap_size >= self.fvg_min_size:
                    fvgs.append({
                        "direction": "BEARISH",
                        "zone_top": float(highs[i-2]),
                        "zone_bottom": float(lows[i]),
                        "mid_price": (float(highs[i-2]) + float(lows[i])) / 2,
                        "confidence": min(gap_size / 0.001, 1.0),
                    })
        
        return fvgs[-5:]  # Return last 5 FVGs

    def _detect_order_blocks(self, df: pd.DataFrame) -> List[Dict]:
        """Detect Order Blocks (last opposite candle before strong move)"""
        order_blocks = []
        closes = df["close"].values
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        
        for i in range(5, len(closes)):
            # Look for strong bullish move preceded by bearish candle
            if closes[i-1] > opens[i-1] and closes[i-5] < opens[i-5]:
                move_strength = (closes[i-1] - opens[i-5]) / opens[i-5]
                if move_strength > 0.01:  # 1% move
                    order_blocks.append({
                        "direction": "BULLISH",
                        "zone_top": float(opens[i-5]),
                        "zone_bottom": float(min(closes[i-5], opens[i-5])),
                        "confidence": min(move_strength / 0.02, 1.0),
                    })
            
            # Look for strong bearish move preceded by bullish candle
            if closes[i-1] < opens[i-1] and closes[i-5] > opens[i-5]:
                move_strength = (opens[i-5] - closes[i-1]) / opens[i-5]
                if move_strength > 0.01:
                    order_blocks.append({
                        "direction": "BEARISH",
                        "zone_top": float(max(closes[i-5], opens[i-5])),
                        "zone_bottom": float(opens[i-5]),
                        "confidence": min(move_strength / 0.02, 1.0),
                    })
        
        return order_blocks[-3:]  # Return last 3 order blocks

    def _analyze_structure(self, df: pd.DataFrame, symbol: str) -> Dict:
        """Analyze overall market structure"""
        closes = df["close"].values
        
        # Determine trend based on higher highs/lows
        recent_highs = closes[-20:].max()
        older_highs = closes[-40:-20].max()
        recent_lows = closes[-20:].min()
        older_lows = closes[-40:-20].min()
        
        if recent_highs > older_highs and recent_lows > older_lows:
            trend = "UPTREND"
        elif recent_highs < older_highs and recent_lows < older_lows:
            trend = "DOWNTREND"
        else:
            trend = "RANGING"
        
        return {
            "trend": trend,
            "recent_range": float(recent_highs - recent_lows),
            "structure_strength": abs(recent_highs - older_highs) / older_highs + abs(recent_lows - older_lows) / older_lows,
        }

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average"""
        multiplier = 2 / (period + 1)
        ema = np.zeros_like(data, dtype=float)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = (data[i] - ema[i-1]) * multiplier + ema[i-1]
        return ema

    async def cleanup(self):
        """Cleanup resources"""
        if self.redis_client:
            await self.redis_client.close()
        await super().cleanup()


# Factory function
def create_technical_analysis_agent(config: Dict[str, Any]) -> TechnicalAnalysisAgent:
    """Factory function to create a Technical Analysis Agent instance"""
    return TechnicalAnalysisAgent(config)
