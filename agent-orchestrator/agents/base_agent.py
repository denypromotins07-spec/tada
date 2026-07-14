"""
Base Agent Class for all 20 AI Agents

Abstract base class implementing the standardized agent architecture with:
- observe(): Receive and process market data
- think(): Analyze data and make decisions  
- act(): Execute trading decisions

Features:
- Memory profiling decorators for 16GB RAM constraint
- Standardized state management
- Async execution support
- Resource monitoring and limits
"""

import asyncio
import logging
import time
import psutil
import os
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from functools import wraps

logger = logging.getLogger(__name__)


class AgentState(Enum):
    """Possible states for an AI agent."""
    INITIALIZED = "INITIALIZED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


@dataclass
class AgentStats:
    """Statistics for agent performance monitoring."""
    name: str
    state: str
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    messages_processed: int = 0
    signals_generated: int = 0
    last_update: datetime = field(default_factory=datetime.now)
    avg_think_time_ms: float = 0.0
    errors: int = 0


def memory_limit(max_memory_mb: int = 512):
    """
    Decorator to enforce memory limits on agent methods.
    
    Args:
        max_memory_mb: Maximum memory in megabytes allowed for the method
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            process = psutil.Process(os.getpid())
            initial_memory = process.memory_info().rss / (1024 * 1024)
            
            try:
                result = await func(self, *args, **kwargs)
                
                final_memory = process.memory_info().rss / (1024 * 1024)
                memory_used = final_memory - initial_memory
                
                if memory_used > max_memory_mb:
                    logger.warning(
                        f"{self.name}.{func.__name__} exceeded memory limit: "
                        f"{memory_used:.2f}MB > {max_memory_mb}MB"
                    )
                
                return result
            except Exception as e:
                logger.error(f"{self.name}.{func.__name__} failed: {e}")
                raise
        
        return wrapper
    return decorator


def profile_execution(func):
    """
    Decorator to profile execution time of agent methods.
    """
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        start_time = time.perf_counter()
        
        try:
            result = await func(self, *args, **kwargs)
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            # Update running average
            self._execution_times.append(elapsed_ms)
            if len(self._execution_times) > 100:
                self._execution_times.pop(0)
            
            if elapsed_ms > 100:  # Log slow executions
                logger.warning(
                    f"{self.name}.{func.__name__} took {elapsed_ms:.2f}ms"
                )
            
            return result
        except Exception as e:
            logger.error(f"{self.name}.{func.__name__} failed after {(time.perf_counter() - start_time) * 1000:.2f}ms: {e}")
            raise
    
    return wrapper


class BaseAgent(ABC):
    """
    Abstract base class for all 20 AI agents.
    
    Implements the observe-think-act paradigm with memory profiling
    and resource management for the 16GB RAM constraint.
    """
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.state = AgentState.INITIALIZED
        self._running = False
        self._execution_times: List[float] = []
        self._stats = AgentStats(name=name, state=self.state.value)
        self._process = psutil.Process(os.getpid())
        
        logger.info(f"Agent {name} initialized")
    
    @property
    def stats(self) -> AgentStats:
        """Get current agent statistics."""
        return self._stats
    
    async def start(self):
        """Start the agent's main loop."""
        if self.state == AgentState.RUNNING:
            logger.warning(f"Agent {self.name} is already running")
            return
        
        logger.info(f"Starting agent {self.name}")
        self.state = AgentState.STARTING
        self._running = True
        self.state = AgentState.RUNNING
        
        # Start the main processing loop
        asyncio.create_task(self._run_loop())
    
    async def stop(self):
        """Stop the agent gracefully."""
        logger.info(f"Stopping agent {self.name}")
        self.state = AgentState.STOPPING
        self._running = False
        self.state = AgentState.STOPPED
        logger.info(f"Agent {self.name} stopped")
    
    async def _run_loop(self):
        """Main agent loop - runs continuously while agent is active."""
        while self._running and self.state == AgentState.RUNNING:
            try:
                # Observe: Get latest market data
                data = await self.observe()
                
                if data is not None:
                    self._stats.messages_processed += 1
                    
                    # Think: Analyze and make decision
                    decision = await self.think(data)
                    
                    # Act: Execute decision if warranted
                    if decision is not None:
                        await self.act(decision)
                        self._stats.signals_generated += 1
                
                # Small delay to prevent CPU spinning
                await asyncio.sleep(0.001)  # 1ms
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Agent {self.name} error in run loop: {e}")
                self._stats.errors += 1
                self.state = AgentState.ERROR
                
                # Try to recover after a brief pause
                await asyncio.sleep(1)
                self.state = AgentState.RUNNING
    
    @abstractmethod
    async def observe(self) -> Optional[Dict[str, Any]]:
        """
        Observe/Receive market data and environment state.
        
        Returns:
            Optional[Dict]: Market data or None if no new data
        """
        pass
    
    @abstractmethod
    async def think(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Analyze observed data and make trading decision.
        
        Args:
            data: Market data from observe()
            
        Returns:
            Optional[Dict]: Trading decision or None if no action needed
        """
        pass
    
    @abstractmethod
    async def act(self, decision: Dict[str, Any]):
        """
        Execute trading decision by sending signal to execution engine.
        
        Args:
            decision: Trading decision from think()
        """
        pass
    
    @profile_execution
    @memory_limit(max_memory_mb=256)
    async def process_cycle(self) -> Optional[Dict[str, Any]]:
        """
        Complete observe-think-act cycle with profiling.
        
        Returns:
            Optional[Dict]: Result of the cycle
        """
        data = await self.observe()
        if data is None:
            return None
        
        decision = await self.think(data)
        if decision is not None:
            await self.act(decision)
            return decision
        
        return None
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get detailed agent statistics including resource usage."""
        # Update resource metrics
        try:
            memory_info = self._process.memory_info()
            self._stats.memory_mb = memory_info.rss / (1024 * 1024)
            self._stats.cpu_percent = self._process.cpu_percent()
        except Exception:
            pass
        
        self._stats.state = self.state.value
        self._stats.last_update = datetime.now()
        
        if self._execution_times:
            self._stats.avg_think_time_ms = sum(self._execution_times) / len(self._execution_times)
        
        return {
            "name": self._stats.name,
            "state": self._stats.state,
            "memory_mb": round(self._stats.memory_mb, 2),
            "cpu_percent": round(self._stats.cpu_percent, 2),
            "messages_processed": self._stats.messages_processed,
            "signals_generated": self._stats.signals_generated,
            "avg_think_time_ms": round(self._stats.avg_think_time_ms, 3),
            "errors": self._stats.errors,
            "last_update": self._stats.last_update.isoformat()
        }
    
    def reset_stats(self):
        """Reset all statistics counters."""
        self._stats = AgentStats(name=self.name, state=self.state.value)
        self._execution_times.clear()
        logger.info(f"Agent {self.name} statistics reset")


# Example implementation for testing
class TestAgent(BaseAgent):
    """Simple test agent for validation."""
    
    async def observe(self) -> Optional[Dict[str, Any]]:
        # Simulate receiving market data
        return {"price": 50000, "volume": 100}
    
    async def think(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Simple logic: buy if price < threshold
        if data.get("price", 0) < 60000:
            return {"action": "BUY", "confidence": 0.8}
        return None
    
    async def act(self, decision: Dict[str, Any]):
        logger.info(f"Agent {self.name} acting: {decision}")
