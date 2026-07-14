"""
Market Data Agent - Domains 1-15
Responsible for understanding Market Fundamentals: Liquidity, Exchange types, 
Tokenomics, Stablecoin flows, and Market Regime detection.

This agent subscribes to Redpanda streams, calculates rolling liquidity metrics,
and identifies exchange routing anomalies. It publishes "Market Regime" signals
to the Supervisor Agent via Redis Pub/Sub.
"""

import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
import redis.asyncio as redis
from confluent_kafka import Consumer, KafkaError
import numpy as np
import networkx as nx

from agents.base_agent import BaseAgent, memory_profile, observe, think, act


class MarketRegime:
    """Enum-like class for market regime states"""
    LOW_VOLATILITY_HIGH_LIQUIDITY = "LOW_VOL_HIGH_LIQ"
    HIGH_VOLATILITY_HIGH_LIQUIDITY = "HIGH_VOL_HIGH_LIQ"
    LOW_VOLATILITY_LOW_LIQUIDITY = "LOW_VOL_LOW_LIQ"
    HIGH_VOLATILITY_LOW_LIQUIDITY = "HIGH_VOL_LOW_LIQ"
    STRESS = "STRESS"
    TRANSITION = "TRANSITION"


class MarketDataAgent(BaseAgent):
    """
    Market Data Agent (Domains 1-15):
    - Domain 1: Liquidity Analysis
    - Domain 2: Exchange Types & Structure
    - Domain 3: Tokenomics
    - Domain 4: Stablecoin Flows
    - Domain 5-14: Market Cycles, Cross-chain Ecosystems, etc.
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__("MarketDataAgent", config)
        
        self.redis_client: Optional[redis.Redis] = None
        self.kafka_consumer: Optional[Consumer] = None
        
        # Rolling windows for metrics
        self.liquidity_window_size = config.get("liquidity_window_size", 60)  # seconds
        self.volatility_window_size = config.get("volatility_window_size", 300)  # seconds
        
        # State tracking
        self.price_history: Dict[str, List[float]] = {}
        self.liquidity_history: Dict[str, List[float]] = {}
        self.volume_history: Dict[str, List[float]] = {}
        self.stablecoin_flows: Dict[str, float] = {}
        
        # Market regime state
        self.current_regime: Dict[str, str] = {}
        self.regime_change_timestamp: Dict[str, int] = {}
        
        # NetworkX graph for cross-chain ecosystems
        self.ecosystem_graph = nx.DiGraph()
        
    async def initialize(self):
        """Initialize connections and state"""
        await super().initialize()
        
        # Initialize Redis connection
        self.redis_client = redis.Redis(
            host=self.config.get("redis_host", "localhost"),
            port=self.config.get("redis_port", 6379),
            decode_responses=True
        )
        
        # Initialize Kafka consumer for Redpanda
        consumer_config = {
            'bootstrap.servers': self.config.get("kafka_servers", "localhost:9092"),
            'group.id': f'market-data-agent-{self.agent_id}',
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
            'session.timeout.ms': 30000,
        }
        
        self.kafka_consumer = Consumer(consumer_config)
        self.kafka_consumer.subscribe(['market-data-ticks', 'market-data-depth'])
        
        self.logger.info(f"MarketDataAgent initialized with ID: {self.agent_id}")
        
    @memory_profile
    @observe
    async def observe(self, data: Optional[Dict] = None) -> Dict:
        """
        Observe market data from Redpanda streams
        Aggregates 1-minute and 5-minute liquidity snapshots
        """
        observations = {
            "timestamp": int(time.time() * 1000),
            "symbols": {},
            "liquidity_metrics": {},
            "volume_metrics": {},
            "stablecoin_flows": {},
        }
        
        # Consume messages from Kafka/Redpanda
        try:
            msg = self.kafka_consumer.poll(timeout=1.0)
            
            if msg is None:
                return observations
                
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    return observations
                else:
                    self.logger.error(f"Kafka error: {msg.error()}")
                    return observations
            
            # Parse message
            value = msg.value()
            topic = msg.topic()
            
            if topic == 'market-data-ticks':
                tick_data = json.loads(value)
                symbol = tick_data.get('symbol', 'UNKNOWN')
                
                # Update price history
                if symbol not in self.price_history:
                    self.price_history[symbol] = []
                    self.liquidity_history[symbol] = []
                    self.volume_history[symbol] = []
                
                price = float(tick_data.get('last_price', 0))
                volume = float(tick_data.get('volume', 0))
                best_bid = float(tick_data.get('best_bid', 0))
                best_ask = float(tick_data.get('best_ask', 0))
                
                # Store observation
                self.price_history[symbol].append((time.time(), price))
                self.volume_history[symbol].append((time.time(), volume))
                
                # Calculate spread-based liquidity metric
                if best_bid > 0 and best_ask > 0:
                    spread_pct = ((best_ask - best_bid) / best_bid) * 100
                    liquidity_metric = 1.0 / (spread_pct + 0.001)  # Inverse of spread
                    self.liquidity_history[symbol].append((time.time(), liquidity_metric))
                
                # Trim history to window size
                cutoff_time = time.time() - max(self.liquidity_window_size, self.volatility_window_size)
                self._trim_history(symbol, cutoff_time)
                
                observations["symbols"][symbol] = {
                    "price": price,
                    "volume": volume,
                    "bid": best_bid,
                    "ask": best_ask,
                }
                
            elif topic == 'market-data-depth':
                depth_data = json.loads(value)
                symbol = depth_data.get('symbol', 'UNKNOWN')
                
                # Calculate depth liquidity
                bids = depth_data.get('bids', [])
                asks = depth_data.get('asks', [])
                
                bid_depth = sum(float(b[1]) for b in bids[:10]) if bids else 0
                ask_depth = sum(float(a[1]) for a in asks[:10]) if asks else 0
                
                observations["liquidity_metrics"][symbol] = {
                    "bid_depth_10": bid_depth,
                    "ask_depth_10": ask_depth,
                    "total_depth": bid_depth + ask_depth,
                }
                
        except Exception as e:
            self.logger.error(f"Error observing market data: {e}")
        
        return observations
    
    @memory_profile
    @think
    async def think(self, observations: Dict) -> Dict:
        """
        Process observations to determine market regime
        Detects stablecoin flows and market cycle position
        """
        thoughts = {
            "regime_analysis": {},
            "liquidity_analysis": {},
            "volatility_analysis": {},
            "stablecoin_flow_analysis": {},
            "ecosystem_state": {},
        }
        
        for symbol in self.price_history.keys():
            # Calculate volatility
            prices = [p for _, p in self.price_history.get(symbol, [])[-100:]]
            if len(prices) > 10:
                returns = np.diff(prices) / np.array(prices[:-1])
                volatility = np.std(returns) * np.sqrt(len(returns)) * 100  # Annualized %
            else:
                volatility = 0.0
            
            # Calculate liquidity
            liquidity_vals = [l for _, l in self.liquidity_history.get(symbol, [])[-60:]]
            avg_liquidity = np.mean(liquidity_vals) if liquidity_vals else 0.0
            
            # Determine regime
            vol_threshold_high = self.config.get("volatility_threshold_high", 2.0)
            liq_threshold_low = self.config.get("liquidity_threshold_low", 0.5)
            
            if volatility > vol_threshold_high * 2:
                regime = MarketRegime.STRESS
            elif volatility > vol_threshold_high and avg_liquidity < liq_threshold_low:
                regime = MarketRegime.HIGH_VOLATILITY_LOW_LIQUIDITY
            elif volatility > vol_threshold_high:
                regime = MarketRegime.HIGH_VOLATILITY_HIGH_LIQUIDITY
            elif avg_liquidity < liq_threshold_low:
                regime = MarketRegime.LOW_VOLATILITY_LOW_LIQUIDITY
            else:
                regime = MarketRegime.LOW_VOLATILITY_HIGH_LIQUIDITY
            
            # Check for regime change
            old_regime = self.current_regime.get(symbol)
            if old_regime != regime:
                self.current_regime[symbol] = regime
                self.regime_change_timestamp[symbol] = int(time.time() * 1000)
                self.logger.info(f"Regime change for {symbol}: {old_regime} -> {regime}")
            
            thoughts["regime_analysis"][symbol] = {
                "current_regime": regime,
                "volatility": volatility,
                "liquidity": avg_liquidity,
                "regime_changed": old_regime != regime,
            }
            
            thoughts["liquidity_analysis"][symbol] = {
                "avg_liquidity": float(avg_liquidity),
                "liquidity_trend": self._calculate_trend(liquidity_vals),
            }
            
            thoughts["volatility_analysis"][symbol] = {
                "current_volatility": float(volatility),
                "volatility_percentile": self._calculate_volatility_percentile(symbol, volatility),
            }
        
        # Analyze stablecoin flows (simplified - would integrate with on-chain data)
        thoughts["stablecoin_flow_analysis"] = self._analyze_stablecoin_flows()
        
        # Update ecosystem graph
        thoughts["ecosystem_state"] = self._update_ecosystem_graph()
        
        return thoughts
    
    @memory_profile
    @act
    async def act(self, thoughts: Dict) -> Dict:
        """
        Publish market regime signals to Redis Pub/Sub
        Send alerts for regime changes and anomalies
        """
        actions = {
            "signals_published": [],
            "alerts_sent": [],
            "state_updated": True,
        }
        
        # Publish regime signals to Redis
        for symbol, regime_info in thoughts.get("regime_analysis", {}).items():
            signal_payload = {
                "agent": self.agent_name,
                "signal_type": "MARKET_REGIME",
                "symbol": symbol,
                "regime": regime_info["current_regime"],
                "volatility": regime_info["volatility"],
                "liquidity": regime_info["liquidity"],
                "timestamp": int(time.time() * 1000),
            }
            
            await self.redis_client.publish(
                "agent:supervisor:signals",
                json.dumps(signal_payload)
            )
            actions["signals_published"].append(signal_payload)
            
            # Send alert for stress regime
            if regime_info["current_regime"] == MarketRegime.STRESS:
                alert_payload = {
                    "level": "CRITICAL",
                    "message": f"STRESS regime detected for {symbol}",
                    "data": regime_info,
                }
                await self.redis_client.publish(
                    "system:alerts",
                    json.dumps(alert_payload)
                )
                actions["alerts_sent"].append(alert_payload)
        
        # Publish liquidity metrics
        for symbol, liq_info in thoughts.get("liquidity_analysis", {}).items():
            metric_payload = {
                "agent": self.agent_name,
                "signal_type": "LIQUIDITY_METRIC",
                "symbol": symbol,
                "metric": liq_info,
                "timestamp": int(time.time() * 1000),
            }
            await self.redis_client.publish(
                "agent:portfolio:metrics",
                json.dumps(metric_payload)
            )
        
        # Cache current state in Redis for other agents
        cache_data = {
            "regimes": self.current_regime,
            "last_update": int(time.time() * 1000),
        }
        await self.redis_client.setex(
            f"agent:{self.agent_name}:state",
            60,  # TTL 60 seconds
            json.dumps(cache_data)
        )
        
        return actions
    
    def _trim_history(self, symbol: str, cutoff_time: float):
        """Trim history arrays to stay within memory limits"""
        if symbol in self.price_history:
            self.price_history[symbol] = [
                (t, p) for t, p in self.price_history[symbol] if t > cutoff_time
            ]
        if symbol in self.liquidity_history:
            self.liquidity_history[symbol] = [
                (t, l) for t, l in self.liquidity_history[symbol] if t > cutoff_time
            ]
        if symbol in self.volume_history:
            self.volume_history[symbol] = [
                (t, v) for t, v in self.volume_history[symbol] if t > cutoff_time
            ]
    
    def _calculate_trend(self, values: List[float], window: int = 10) -> str:
        """Calculate trend direction from recent values"""
        if len(values) < window:
            return "NEUTRAL"
        
        recent_avg = np.mean(values[-window:])
        older_avg = np.mean(values[-window*2:-window]) if len(values) >= window*2 else recent_avg
        
        if recent_avg > older_avg * 1.05:
            return "INCREASING"
        elif recent_avg < older_avg * 0.95:
            return "DECREASING"
        else:
            return "STABLE"
    
    def _calculate_volatility_percentile(self, symbol: str, current_vol: float) -> float:
        """Calculate where current volatility sits in historical distribution"""
        # Simplified - would use full historical distribution in production
        return 0.5  # Placeholder
    
    def _analyze_stablecoin_flows(self) -> Dict:
        """Analyze stablecoin inflows/outflows (simplified)"""
        # Would integrate with on-chain data sources in production
        return {
            "usdt_flow_24h": 0.0,
            "usdc_flow_24h": 0.0,
            "net_stablecoin_flow": 0.0,
            "flow_signal": "NEUTRAL",
        }
    
    def _update_ecosystem_graph(self) -> Dict:
        """Update cross-chain ecosystem graph (Domain 14)"""
        # Build graph of token/ecosystem relationships
        # This would be populated with real data in production
        self.ecosystem_graph.add_node("ethereum", type="layer1")
        self.ecosystem_graph.add_node("arbitrum", type="layer2", parent="ethereum")
        self.ecosystem_graph.add_node("optimism", type="layer2", parent="ethereum")
        
        return {
            "node_count": self.ecosystem_graph.number_of_nodes(),
            "edge_count": self.ecosystem_graph.number_of_edges(),
            "connected_components": nx.number_connected_components(self.ecosystem_graph.to_undirected()),
        }
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.kafka_consumer:
            self.kafka_consumer.close()
        if self.redis_client:
            await self.redis_client.close()
        await super().cleanup()


# Factory function for creating the agent
def create_market_data_agent(config: Dict[str, Any]) -> MarketDataAgent:
    """Factory function to create a Market Data Agent instance"""
    return MarketDataAgent(config)
