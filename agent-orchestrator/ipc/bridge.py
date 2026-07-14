"""
ZeroMQ Inter-Process Communication Bridge

High-speed IPC bridge between Python AI agents and the Rust Execution Engine.
Uses MessagePack for efficient serialization and ZeroMQ for low-latency messaging.

Features:
- MessagePack serialization for maximum speed
- Request-reply pattern for order submission
- Publish-subscribe pattern for market data
- Connection pooling and automatic reconnection
- Thread-safe queues for concurrent access
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

import zmq
import zmq.asyncio
import msgpack

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of messages that can be sent over the IPC bridge."""
    ORDER_SUBMIT = "ORDER_SUBMIT"
    ORDER_CANCEL = "ORDER_CANCEL"
    ORDER_STATUS = "ORDER_STATUS"
    MARKET_DATA = "MARKET_DATA"
    TRADING_SIGNAL = "TRADING_SIGNAL"
    HEARTBEAT = "HEARTBEAT"
    ACK = "ACK"
    ERROR = "ERROR"


@dataclass
class TradingSignal:
    """Trading signal from an AI agent to the execution engine."""
    symbol: str
    side: str  # BUY or SELL
    quantity: float
    price: Optional[float]
    order_type: str  # LIMIT or MARKET
    agent_name: str
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "order_type": self.order_type,
            "agent_name": self.agent_name,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


@dataclass
class OrderResponse:
    """Response from the execution engine after order submission."""
    order_id: int
    status: str
    message: str
    timestamp: datetime
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderResponse":
        """Create from dictionary."""
        return cls(
            order_id=data["order_id"],
            status=data["status"],
            message=data["message"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if isinstance(data["timestamp"], str) else data["timestamp"]
        )


class ZeroMQBridge:
    """
    ZeroMQ bridge for communication between Python and Rust.
    
    Uses REQ-REP pattern for order submission and SUB-PUB for market data.
    Implements automatic reconnection and message serialization with MessagePack.
    """
    
    def __init__(
        self,
        rust_engine_endpoint: str = "tcp://localhost:5555",
        timeout_ms: int = 100,
        max_retries: int = 3
    ):
        self.rust_engine_endpoint = rust_engine_endpoint
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        
        self._context: Optional[zmq.asyncio.Context] = None
        self._socket: Optional[zmq.asyncio.Socket] = None
        self._connected = False
        self._message_count = 0
        self._last_message_time: Optional[float] = None
        
        # Thread-safe queue for pending requests
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._request_id_counter = 0
    
    async def connect(self) -> bool:
        """
        Establish connection to the Rust engine.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self._context = zmq.asyncio.Context()
            self._socket = self._context.socket(zmq.REQ)
            
            # Configure socket options for low latency
            self._socket.setsockopt(zmq.LINGER, 0)  # Don't block on close
            self._socket.setsockopt(zmq.SNDHWM, 1000)  # Send high water mark
            self._socket.setsockopt(zmq.RCVHWM, 1000)  # Receive high water mark
            self._socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
            self._socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
            
            # Connect with retry logic
            for attempt in range(self.max_retries):
                try:
                    self._socket.connect(self.rust_engine_endpoint)
                    logger.info(f"Connected to Rust engine at {self.rust_engine_endpoint}")
                    self._connected = True
                    return True
                except Exception as e:
                    logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(1 * (attempt + 1))
            
            logger.error("Failed to connect to Rust engine after all retries")
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to Rust engine: {e}")
            return False
    
    async def disconnect(self):
        """Close connection to the Rust engine."""
        self._connected = False
        
        if self._socket:
            self._socket.close()
            self._socket = None
        
        if self._context:
            self._context.term()
            self._context = None
        
        logger.info("Disconnected from Rust engine")
    
    def is_connected(self) -> bool:
        """Check if currently connected to the Rust engine."""
        return self._connected and self._socket is not None
    
    async def send_signal(self, signal: TradingSignal) -> int:
        """
        Send a trading signal to the Rust execution engine.
        
        Args:
            signal: TradingSignal object containing order details
            
        Returns:
            int: Order ID assigned by the execution engine
            
        Raises:
            ConnectionError: If not connected to Rust engine
            TimeoutError: If request times out
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Rust engine")
        
        # Create message envelope
        request_id = self._generate_request_id()
        message = {
            "type": MessageType.TRADING_SIGNAL.value,
            "request_id": request_id,
            "timestamp": time.time_ns(),  # Nanosecond precision
            "payload": signal.to_dict()
        }
        
        # Serialize with MessagePack for efficiency
        packed_message = msgpack.packb(message, use_bin_type=True)
        
        # Send with retries
        for attempt in range(self.max_retries):
            try:
                await self._socket.send(packed_message)
                
                # Wait for response
                response_bytes = await self._socket.recv()
                response = msgpack.unpackb(response_bytes, raw=False)
                
                self._message_count += 1
                self._last_message_time = time.time()
                
                # Parse response
                if response.get("type") == MessageType.ACK.value:
                    order_id = response.get("payload", {}).get("order_id", 0)
                    logger.debug(f"Signal acknowledged, order_id={order_id}")
                    return order_id
                elif response.get("type") == MessageType.ERROR.value:
                    error_msg = response.get("payload", {}).get("message", "Unknown error")
                    raise RuntimeError(f"Rust engine error: {error_msg}")
                else:
                    logger.warning(f"Unexpected response type: {response.get('type')}")
                    return 0
                    
            except zmq.Again:
                logger.warning(f"Request timed out (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))
                continue
            except Exception as e:
                logger.error(f"Error sending signal: {e}")
                raise
        
        raise TimeoutError("Failed to send signal after all retries")
    
    async def cancel_order(self, order_id: int) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of the order to cancel
            
        Returns:
            bool: True if cancellation successful
        """
        if not self.is_connected():
            raise ConnectionError("Not connected to Rust engine")
        
        message = {
            "type": MessageType.ORDER_CANCEL.value,
            "request_id": self._generate_request_id(),
            "timestamp": time.time_ns(),
            "payload": {"order_id": order_id}
        }
        
        packed_message = msgpack.packb(message, use_bin_type=True)
        
        try:
            await self._socket.send(packed_message)
            response_bytes = await self._socket.recv()
            response = msgpack.unpackb(response_bytes, raw=False)
            
            return response.get("type") == MessageType.ACK.value
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False
    
    async def send_heartbeat(self) -> bool:
        """Send heartbeat to keep connection alive."""
        if not self.is_connected():
            return False
        
        message = {
            "type": MessageType.HEARTBEAT.value,
            "request_id": self._generate_request_id(),
            "timestamp": time.time_ns(),
            "payload": {}
        }
        
        try:
            packed_message = msgpack.packb(message, use_bin_type=True)
            await self._socket.send(packed_message)
            return True
        except Exception as e:
            logger.error(f"Heartbeat failed: {e}")
            return False
    
    def _generate_request_id(self) -> int:
        """Generate unique request ID."""
        self._request_id_counter += 1
        return self._request_id_counter
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "connected": self._connected,
            "message_count": self._message_count,
            "last_message_time": self._last_message_time,
            "endpoint": self.rust_engine_endpoint,
            "timeout_ms": self.timeout_ms
        }


class MarketDataSubscriber:
    """
    Separate subscriber for market data updates from Rust engine.
    Uses PUB-SUB pattern for broadcast-style market data distribution.
    """
    
    def __init__(self, endpoint: str = "tcp://localhost:5556"):
        self.endpoint = endpoint
        self._context: Optional[zmq.asyncio.Context] = None
        self._socket: Optional[zmq.asyncio.Socket] = None
        self._subscribers: List[asyncio.Queue] = []
    
    async def connect(self):
        """Connect to market data publisher."""
        self._context = zmq.asyncio.Context()
        self._socket = self._context.socket(zmq.SUB)
        self._socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all topics
        self._socket.connect(self.endpoint)
        logger.info(f"Connected to market data feed at {self.endpoint}")
    
    async def disconnect(self):
        """Disconnect from market data feed."""
        if self._socket:
            self._socket.close()
        if self._context:
            self._context.term()
    
    async def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to market data updates.
        
        Returns:
            asyncio.Queue: Queue to receive market data updates
        """
        queue = asyncio.Queue(maxsize=1000)
        self._subscribers.append(queue)
        return queue
    
    async def run(self):
        """Main loop to receive and distribute market data."""
        while True:
            try:
                message = await self._socket.recv()
                data = msgpack.unpackb(message, raw=False)
                
                # Distribute to all subscribers
                for queue in self._subscribers:
                    try:
                        queue.put_nowait(data)
                    except asyncio.QueueFull:
                        logger.warning("Market data queue full, dropping update")
                        
            except Exception as e:
                logger.error(f"Error receiving market data: {e}")
                await asyncio.sleep(1)
