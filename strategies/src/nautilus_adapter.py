#!/usr/bin/env python3
"""
=============================================================================
Nautilus Trader Adapter - Bridge between Rust Core and Nautilus
=============================================================================
Bridges order book snapshots from Rust core to Nautilus DataEngine.

This adapter:
1. Subscribes to Redis pub/sub channels for order book updates
2. Converts Rust core messages to Nautilus data types
3. Publishes to Nautilus DataEngine for strategy consumption
4. Handles latency tracking and synchronization
=============================================================================
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from nautilus_trader.core.data import Data
from nautilus_trader.core.message import Event
from nautilus_trader.model.data import OrderBookDeltas, TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity

log = logging.getLogger(__name__)


class NautilusAdapter:
    """
    Adapter bridging Rust core order book data to Nautilus Trader.
    
    The Rust core publishes order book updates to Redis channels.
    This adapter subscribes to those channels and forwards data
    to the Nautilus DataEngine for strategy consumption.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        venue: str = "BINANCE",
    ):
        self.redis_url = redis_url
        self.venue = Venue(venue)
        self.redis_client = None
        self.pubsub = None
        self.data_callback = None
        
    async def connect(self) -> None:
        """Connect to Redis and subscribe to order book channels."""
        import redis.asyncio as redis
        
        log.info("Connecting to Redis...")
        self.redis_client = redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        
        # Test connection
        await self.redis_client.ping()
        log.info("✓ Connected to Redis")
        
        # Create pubsub connection
        self.pubsub = self.redis_client.pubsub()
        
    async def subscribe_order_book(self, symbol: str) -> None:
        """
        Subscribe to order book updates for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
        """
        channel = f"hft:depth:{symbol}"
        await self.pubsub.subscribe(channel)
        log.info(f"✓ Subscribed to {channel}")
        
    async def subscribe_trades(self, symbol: str) -> None:
        """
        Subscribe to trade updates for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g., "BTCUSDT")
        """
        channel = f"hft:trades:{symbol}"
        await self.pubsub.subscribe(channel)
        log.info(f"✓ Subscribed to {channel}")
        
    def set_data_callback(self, callback) -> None:
        """
        Set callback function for received data.
        
        Args:
            callback: Async function to call with Nautilus data objects
        """
        self.data_callback = callback
        
    async def process_message(self, message: Dict[str, Any]) -> None:
        """
        Process incoming Redis message and convert to Nautilus format.
        
        Args:
            message: Raw message from Redis pub/sub
        """
        try:
            data = json.loads(message["data"])
            event_type = message.get("type", "unknown")
            
            if event_type == "depthUpdate":
                await self._process_depth_update(data)
            elif event_type == "aggTrade":
                await self._process_trade(data)
            else:
                log.debug(f"Unknown event type: {event_type}")
                
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse message: {e}")
        except Exception as e:
            log.error(f"Error processing message: {e}")
            
    async def _process_depth_update(self, data: Dict[str, Any]) -> None:
        """
        Process order book depth update.
        
        Converts Binance depth update to Nautilus OrderBookDeltas.
        """
        symbol = data.get("symbol", "UNKNOWN")
        instrument_id = InstrumentId(
            symbol=Symbol(symbol),
            venue=self.venue,
        )
        
        # Parse bids and asks
        bids = [
            {"price": Price(float(p), precision=8), "size": Quantity(float(q), precision=8)}
            for p, q in data.get("bids", [])
        ]
        
        asks = [
            {"price": Price(float(p), precision=8), "size": Quantity(float(q), precision=8)}
            for p, q in data.get("asks", [])
        ]
        
        # Create Nautilus OrderBookDeltas
        deltas = OrderBookDeltas(
            instrument_id=instrument_id,
            ts_event=int(data.get("event_time", 0)) * 1_000_000,  # ms to ns
            ts_init=int(datetime.utcnow().timestamp() * 1e9),
            deltas=bids + asks,  # Simplified - real implementation needs proper delta structure
        )
        
        if self.data_callback:
            await self.data_callback(deltas)
            
    async def _process_trade(self, data: Dict[str, Any]) -> None:
        """
        Process trade tick.
        
        Converts Binance aggregate trade to Nautilus TradeTick.
        """
        symbol = data.get("symbol", "UNKNOWN")
        instrument_id = InstrumentId(
            symbol=Symbol(symbol),
            venue=self.venue,
        )
        
        # Create Nautilus TradeTick
        tick = TradeTick(
            instrument_id=instrument_id,
            price=Price(float(data.get("price", 0)), precision=8),
            size=Quantity(float(data.get("quantity", 0)), precision=8),
            aggressor_side=AggressorSide.BUYER if not data.get("is_buyer_maker", True) else AggressorSide.SELLER,
            trade_id=str(data.get("agg_trade_id", 0)),
            ts_event=int(data.get("trade_time", 0)) * 1_000_000,
            ts_init=int(datetime.utcnow().timestamp() * 1e9),
        )
        
        if self.data_callback:
            await self.data_callback(tick)
            
    async def run_listener(self) -> None:
        """
        Run continuous listener for Redis pub/sub messages.
        
        This is the main loop that receives and processes messages.
        """
        if not self.pubsub:
            raise RuntimeError("Not connected to Redis")
            
        log.info("Starting Redis pub/sub listener...")
        
        while True:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                
                if message and message["type"] == "message":
                    await self.process_message(message)
                    
            except asyncio.CancelledError:
                log.info("Listener cancelled")
                break
            except Exception as e:
                log.error(f"Listener error: {e}")
                await asyncio.sleep(1)  # Backoff on error
                
    async def close(self) -> None:
        """Close Redis connections."""
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        if self.redis_client:
            await self.redis_client.close()
        log.info("✓ Redis connections closed")
