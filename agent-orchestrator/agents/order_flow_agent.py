"""
Order Flow Agent - Domains 31-45
Responsible for detecting Liquidity Sweeps, Absorption, Iceberg Orders,
and aggressive buying/selling imbalances.

Receives pre-calculated Rust metrics and applies sliding window analysis
to detect order flow anomalies.
"""

import asyncio
import json
import time
from typing import Dict, List, Optional, Any
from collections import deque
import numpy as np
import redis.asyncio as redis

from agents.base_agent import BaseAgent, memory_profile, observe, think, act


class OrderFlowSignal:
    """Enum-like class for order flow signals"""
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    ABSORPTION = "ABSORPTION"
    ICEBERG_DETECTED = "ICEBERG"
    AGGRESSIVE_BUYING = "AGGRESSIVE_BUY"
    AGGRESSIVE_SELLING = "AGGRESSIVE_SELL"
    IMBALANCE = "IMBALANCE"
    STOP_RUN = "STOP_RUN"


class OrderFlowAgent(BaseAgent):
    """
    Order Flow Agent (Domains 31-45):
    - Domain 31-35: Order Book Dynamics
    - Domain 36-40: Volume Analysis & CVD
    - Domain 41-45: Smart Money Detection (Icebergs, Absorption, Sweeps)
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("OrderFlowAgent", config)
        
        self.redis_client: Optional[redis.Redis] = None
        
        # Sliding window configurations
        self.imbalance_window = config.get("imbalance_window", 100)  # trades
        self.absorption_window = config.get("absorption_window", 50)  # trades
        self.sweep_detection_threshold = config.get("sweep_threshold", 0.85)  # 85% of book eaten
        
        # State tracking per symbol
        self.cvd_history: Dict[str, deque] = {}
        self.volume_history: Dict[str, deque] = {}
        self.trade_imbalance_history: Dict[str, deque] = {}
        self.price_levels_touched: Dict[str, Dict[float, int]] = {}
        
        # Detection state
        self.active_sweeps: Dict[str, bool] = {}
        self.iceberg_candidates: Dict[str, List[Dict]] = {}
        
    async def initialize(self):
        """Initialize connections and state"""
        await super().initialize()
        
        # Initialize Redis connection
        self.redis_client = redis.Redis(
            host=self.config.get("redis_host", "localhost"),
            port=self.config.get("redis_port", 6379),
            decode_responses=True
        )
        
        # Subscribe to Rust engine order flow metrics
        self.pubsub = self.redis_client.pubsub()
        await self.pubsub.subscribe("rust:orderflow:metrics")
        
        self.logger.info(f"OrderFlowAgent initialized with ID: {self.agent_id}")

    @memory_profile
    @observe
    async def observe(self, data: Optional[Dict] = None) -> Dict:
        """
        Observe order flow metrics from Rust engine
        Receives pre-calculated CVD, volume profile, and footprint data
        """
        observations = {
            "timestamp": int(time.time() * 1000),
            "symbols": {},
            "cvd_data": {},
            "volume_profile": {},
            "footprint_bars": {},
        }
        
        # Listen for messages from Rust engine via Redis
        try:
            message = await asyncio.wait_for(
                self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1),
                timeout=0.2
            )
            
            if message and message["type"] == "message":
                payload = json.loads(message["data"])
                symbol = payload.get("symbol", "UNKNOWN")
                
                # Update CVD history
                if symbol not in self.cvd_history:
                    self.cvd_history[symbol] = deque(maxlen=self.imbalance_window * 2)
                    self.volume_history[symbol] = deque(maxlen=self.imbalance_window * 2)
                    self.trade_imbalance_history[symbol] = deque(maxlen=self.imbalance_window)
                    self.price_levels_touched[symbol] = {}
                    self.iceberg_candidates[symbol] = []
                
                # Store CVD data
                cvd_value = payload.get("cvd", 0)
                self.cvd_history[symbol].append((time.time(), cvd_value))
                
                # Store volume data
                total_volume = payload.get("total_volume", 0)
                self.volume_history[symbol].append((time.time(), total_volume))
                
                # Store trade imbalance
                buy_ratio = payload.get("buy_ratio", 0.5)
                self.trade_imbalance_history[symbol].append((time.time(), buy_ratio))
                
                # Track price levels touched
                price = payload.get("price", 0)
                if price > 0:
                    price_key = round(price, 2)
                    self.price_levels_touched[symbol][price_key] = \
                        self.price_levels_touched[symbol].get(price_key, 0) + 1
                
                observations["symbols"][symbol] = payload
                observations["cvd_data"][symbol] = list(self.cvd_history[symbol])[-20:]
                
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            self.logger.error(f"Error observing order flow: {e}")
        
        return observations

    @memory_profile
    @think
    async def think(self, observations: Dict) -> Dict:
        """
        Process order flow observations to detect:
        - Liquidity sweeps
        - Absorption patterns
        - Iceberg orders
        - Aggressive buying/selling
        """
        thoughts = {
            "detected_signals": [],
            "sweep_analysis": {},
            "absorption_analysis": {},
            "iceberg_analysis": {},
            "imbalance_analysis": {},
        }
        
        for symbol in observations.get("symbols", {}).keys():
            # Detect liquidity sweeps
            sweep_detected = self._detect_liquidity_sweep(symbol, observations)
            if sweep_detected:
                thoughts["detected_signals"].append({
                    "signal_type": OrderFlowSignal.LIQUIDITY_SWEEP,
                    "symbol": symbol,
                    "confidence": sweep_detected["confidence"],
                    "details": sweep_detected,
                })
            
            # Detect absorption
            absorption_detected = self._detect_absorption(symbol, observations)
            if absorption_detected:
                thoughts["detected_signals"].append({
                    "signal_type": OrderFlowSignal.ABSORPTION,
                    "symbol": symbol,
                    "confidence": absorption_detected["confidence"],
                    "details": absorption_detected,
                })
            
            # Detect iceberg orders
            iceberg_detected = self._detect_iceberg(symbol, observations)
            if iceberg_detected:
                thoughts["detected_signals"].append({
                    "signal_type": OrderFlowSignal.ICEBERG_DETECTED,
                    "symbol": symbol,
                    "confidence": iceberg_detected["confidence"],
                    "details": iceberg_detected,
                })
            
            # Analyze trade imbalance
            imbalance_state = self._analyze_imbalance(symbol)
            if imbalance_state["significant"]:
                signal_type = (
                    OrderFlowSignal.AGGRESSIVE_BUYING 
                    if imbalance_state["direction"] > 0 
                    else OrderFlowSignal.AGGRESSIVE_SELLING
                )
                thoughts["detected_signals"].append({
                    "signal_type": signal_type,
                    "symbol": symbol,
                    "confidence": abs(imbalance_state["direction"]),
                    "details": imbalance_state,
                })
            
            thoughts["imbalance_analysis"][symbol] = imbalance_state
        
        return thoughts

    @memory_profile
    @act
    async def act(self, thoughts: Dict) -> Dict:
        """
        Publish order flow signals to Redis Pub/Sub
        Alert other agents about detected patterns
        """
        actions = {
            "signals_published": [],
            "alerts_sent": [],
        }
        
        for signal in thoughts.get("detected_signals", []):
            signal_payload = {
                "agent": self.agent_name,
                "signal_type": signal["signal_type"],
                "symbol": signal["symbol"],
                "confidence": signal["confidence"],
                "details": signal["details"],
                "timestamp": int(time.time() * 1000),
            }
            
            # Publish to supervisor
            await self.redis_client.publish(
                "agent:supervisor:signals",
                json.dumps(signal_payload)
            )
            
            # Publish to execution agent for immediate action
            if signal["confidence"] > 0.7:
                await self.redis_client.publish(
                    "agent:execution:signals",
                    json.dumps(signal_payload)
                )
            
            actions["signals_published"].append(signal_payload)
            
            # Send high-priority alert for sweeps and icebergs
            if signal["signal_type"] in [OrderFlowSignal.LIQUIDITY_SWEEP, OrderFlowSignal.ICEBERG_DETECTED]:
                if signal["confidence"] > 0.8:
                    alert_payload = {
                        "level": "HIGH",
                        "message": f"{signal['signal_type']} detected for {signal['symbol']}",
                        "data": signal_payload,
                    }
                    await self.redis_client.publish(
                        "system:alerts",
                        json.dumps(alert_payload)
                    )
                    actions["alerts_sent"].append(alert_payload)
        
        return actions

    def _detect_liquidity_sweep(self, symbol: str, observations: Dict) -> Optional[Dict]:
        """
        Detect liquidity sweeps - when aggressive orders eat through multiple price levels
        A sweep occurs when >85% of book depth is consumed rapidly
        """
        if symbol not in self.cvd_history or len(self.cvd_history[symbol]) < 10:
            return None
        
        recent_cvd = [v for _, v in list(self.cvd_history[symbol])[-20:]]
        if len(recent_cvd) < 10:
            return None
        
        # Calculate CVD delta (change in cumulative volume)
        cvd_delta = recent_cvd[-1] - recent_cvd[0]
        avg_cvd_change = np.mean(np.diff(recent_cvd))
        
        # Sweep detection: large CVD move relative to recent average
        if abs(cvd_delta) > abs(avg_cvd_change) * self.sweep_detection_threshold * 10:
            direction = "BUY" if cvd_delta > 0 else "SELL"
            confidence = min(abs(cvd_delta) / (abs(avg_cvd_change) * 10), 1.0)
            
            return {
                "direction": direction,
                "cvd_delta": float(cvd_delta),
                "confidence": float(confidence),
                "levels_swept": self._estimate_levels_swept(symbol, cvd_delta),
            }
        
        return None

    def _detect_absorption(self, symbol: str, observations: Dict) -> Optional[Dict]:
        """
        Detect absorption - when price doesn't move despite large volume
        Indicates passive orders absorbing aggressive flow
        """
        if symbol not in self.volume_history or len(self.volume_history[symbol]) < 20:
            return None
        
        volumes = [v for _, v in list(self.volume_history[symbol])[-30:]]
        if len(volumes) < 20:
            return None
        
        # Check for high volume with low price movement
        recent_volume = np.mean(volumes[-10:])
        older_volume = np.mean(volumes[-20:-10])
        
        volume_spike = recent_volume / (older_volume + 0.001)
        
        # Get price range from observations
        symbol_data = observations.get("symbols", {}).get(symbol, {})
        price_range = symbol_data.get("price_range", 0)
        
        # Absorption: high volume spike but minimal price movement
        if volume_spike > 2.0 and price_range < 0.001:  # Volume doubled, price moved <0.1%
            confidence = min(volume_spike / 5.0, 1.0)
            return {
                "volume_spike": float(volume_spike),
                "price_range": float(price_range),
                "confidence": float(confidence),
                "interpretation": "PASSIVE_ABSORPTION",
            }
        
        return None

    def _detect_iceberg(self, symbol: str, observations: Dict) -> Optional[Dict]:
        """
        Detect iceberg orders - repeated trades at same price level
        Indicates hidden large order being worked
        """
        if symbol not in self.price_levels_touched:
            return None
        
        level_counts = self.price_levels_touched[symbol]
        
        # Find price levels with unusually high touch counts
        if not level_counts:
            return None
        
        avg_touches = np.mean(list(level_counts.values()))
        std_touches = np.std(list(level_counts.values())) + 0.001
        
        for price_level, count in level_counts.items():
            z_score = (count - avg_touches) / std_touches
            
            # Iceberg: same price level hit many times (>3 std dev)
            if z_score > 3.0:
                # Clean up old candidates
                self.iceberg_candidates[symbol] = [
                    c for c in self.iceberg_candidates[symbol]
                    if time.time() - c["first_seen"] < 60  # 1 minute expiry
                ]
                
                # Check if we've already flagged this level
                existing = [
                    c for c in self.iceberg_candidates[symbol]
                    if abs(c["price_level"] - price_level) < 0.01
                ]
                
                if not existing:
                    candidate = {
                        "price_level": price_level,
                        "touch_count": count,
                        "z_score": float(z_score),
                        "first_seen": time.time(),
                    }
                    self.iceberg_candidates[symbol].append(candidate)
                    
                    return {
                        "price_level": price_level,
                        "touch_count": count,
                        "z_score": float(z_score),
                        "confidence": min(z_score / 5.0, 1.0),
                        "estimated_size": count * 0.1,  # Rough estimate
                    }
        
        return None

    def _analyze_imbalance(self, symbol: str) -> Dict:
        """
        Analyze trade imbalance using sliding window
        Returns direction and significance
        """
        if symbol not in self.trade_imbalance_history or len(self.trade_imbalance_history[symbol]) < 10:
            return {"significant": False, "direction": 0.0}
        
        imbalances = [v for _, v in list(self.trade_imbalance_history[symbol])[-50:]]
        if len(imbalances) < 10:
            return {"significant": False, "direction": 0.0}
        
        recent_avg = np.mean(imbalances[-10:])
        historical_avg = np.mean(imbalances[:-10])
        
        # Direction: positive = buying pressure, negative = selling pressure
        direction = (recent_avg - 0.5) * 2  # Normalize to -1 to 1
        
        # Significant if deviation from historical norm
        significant = abs(recent_avg - historical_avg) > 0.15
        
        return {
            "significant": significant,
            "direction": float(direction),
            "recent_buy_ratio": float(recent_avg),
            "historical_buy_ratio": float(historical_avg),
            "trade_count": len(imbalances),
        }

    def _estimate_levels_swept(self, symbol: str, cvd_delta: float) -> int:
        """Estimate number of price levels swept based on CVD delta"""
        # Simplified estimation - would use actual order book depth in production
        base_levels = abs(cvd_delta) / 1000  # Rough heuristic
        return max(1, int(base_levels))

    async def cleanup(self):
        """Cleanup resources"""
        if self.pubsub:
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        await super().cleanup()


# Factory function
def create_order_flow_agent(config: Dict[str, Any]) -> OrderFlowAgent:
    """Factory function to create an Order Flow Agent instance"""
    return OrderFlowAgent(config)
