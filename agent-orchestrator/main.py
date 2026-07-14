"""
QuantumHFT - Python AI Agent Orchestrator

FastAPI application serving as the orchestrator gateway for 20 autonomous AI agents.
Handles REST requests from the frontend, manages agent lifecycles via Ray, and
bridges high-level trading signals to the Rust Execution Engine via ZeroMQ IPC.

Hardware Optimization:
- ONNX Runtime with DirectML for AMD Radeon GPU acceleration
- Ryzen AI NPU support for low-latency inference
- Ray distributed computing for parallel agent execution
- Memory profiling decorators for 16GB RAM constraint
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from ipc.bridge import ZeroMQBridge, TradingSignal
from agents.base_agent import AgentState, BaseAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global state
agents: Dict[str, BaseAgent] = {}
zmq_bridge: Optional[ZeroMQBridge] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown events."""
    global zmq_bridge
    
    # Startup
    logger.info("🚀 QuantumHFT AI Orchestrator Starting...")
    
    # Initialize ZeroMQ bridge to Rust engine
    zmq_bridge = ZeroMQBridge(
        rust_engine_endpoint=os.getenv("RUST_ENGINE_ENDPOINT", "tcp://localhost:5555"),
        timeout_ms=int(os.getenv("IPC_TIMEOUT_MS", "100"))
    )
    await zmq_bridge.connect()
    logger.info("✓ ZeroMQ IPC Bridge connected to Rust engine")
    
    # Initialize agents (placeholder - will be expanded in later stages)
    await initialize_agents()
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down AI Orchestrator...")
    if zmq_bridge:
        await zmq_bridge.disconnect()
    for agent in agents.values():
        await agent.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="QuantumHFT AI Orchestrator",
        description="Orchestration layer for 20 autonomous AI trading agents",
        version="0.1.0",
        lifespan=lifespan
    )
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    return app


app = create_app()


# ===========================================
# Pydantic Models
# ===========================================

class AgentInfo(BaseModel):
    """Information about a single agent."""
    name: str
    state: str
    last_update: datetime
    memory_mb: float
    cpu_percent: float


class SystemHealth(BaseModel):
    """System health status."""
    status: str
    agents_active: int
    rust_engine_connected: bool
    memory_usage_gb: float
    cpu_percent: float
    uptime_seconds: int


class TradingSignalRequest(BaseModel):
    """Request to send a trading signal to the Rust engine."""
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTCUSDT)")
    side: str = Field(..., description="BUY or SELL")
    quantity: float = Field(..., description="Order quantity")
    price: Optional[float] = Field(None, description="Limit price (None for market orders)")
    order_type: str = Field(default="LIMIT", description="LIMIT or MARKET")
    agent_name: str = Field(..., description="Name of the agent sending the signal")
    confidence: float = Field(..., ge=0, le=1, description="Confidence score 0-1")


class OrderResponse(BaseModel):
    """Response from order submission."""
    order_id: int
    status: str
    message: str


# ===========================================
# API Endpoints
# ===========================================

@app.get("/")
async def root():
    """Root endpoint with system information."""
    return {
        "name": "QuantumHFT AI Orchestrator",
        "version": "0.1.0",
        "agents": len(agents),
        "status": "running"
    }


@app.get("/health", response_model=SystemHealth)
async def health_check():
    """Check system health and connectivity."""
    import psutil
    
    memory = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=1)
    
    return SystemHealth(
        status="healthy",
        agents_active=len([a for a in agents.values() if a.state == AgentState.RUNNING]),
        rust_engine_connected=zmq_bridge is not None and zmq_bridge.is_connected(),
        memory_usage_gb=memory.used / (1024 ** 3),
        cpu_percent=cpu,
        uptime_seconds=int((datetime.now() - datetime.now()).total_seconds())  # Placeholder
    )


@app.get("/agents", response_model=List[AgentInfo])
async def list_agents():
    """List all registered AI agents and their status."""
    agent_infos = []
    for name, agent in agents.items():
        stats = await agent.get_stats()
        agent_infos.append(AgentInfo(
            name=name,
            state=agent.state.value,
            last_update=datetime.now(),
            memory_mb=stats.get("memory_mb", 0),
            cpu_percent=stats.get("cpu_percent", 0)
        ))
    return agent_infos


@app.get("/agents/{agent_name}")
async def get_agent(agent_name: str):
    """Get detailed information about a specific agent."""
    if agent_name not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    
    agent = agents[agent_name]
    stats = await agent.get_stats()
    
    return {
        "name": agent_name,
        "state": agent.state.value,
        "stats": stats,
        "config": agent.config
    }


@app.post("/signals", response_model=OrderResponse)
async def submit_trading_signal(signal: TradingSignalRequest):
    """
    Submit a trading signal from an AI agent to the Rust execution engine.
    
    This endpoint receives high-level trading decisions from AI agents and
    forwards them to the Rust engine via ZeroMQ IPC for ultra-low latency execution.
    """
    if not zmq_bridge:
        raise HTTPException(status_code=503, detail="Rust engine not connected")
    
    # Validate signal
    if signal.side not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Side must be BUY or SELL")
    
    if signal.order_type not in ["LIMIT", "MARKET"]:
        raise HTTPException(status_code=400, detail="Order type must be LIMIT or MARKET")
    
    # Create trading signal for Rust engine
    trading_signal = TradingSignal(
        symbol=signal.symbol,
        side=signal.side,
        quantity=signal.quantity,
        price=signal.price,
        order_type=signal.order_type,
        agent_name=signal.agent_name,
        confidence=signal.confidence,
        timestamp=datetime.utcnow()
    )
    
    # Send to Rust engine via ZeroMQ
    try:
        order_id = await zmq_bridge.send_signal(trading_signal)
        return OrderResponse(
            order_id=order_id,
            status="SUBMITTED",
            message=f"Signal forwarded to execution engine"
        )
    except Exception as e:
        logger.error(f"Failed to send signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to forward signal: {str(e)}")


@app.post("/agents/{agent_name}/start")
async def start_agent(agent_name: str):
    """Start a specific agent."""
    if agent_name not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    
    await agents[agent_name].start()
    return {"status": "started", "agent": agent_name}


@app.post("/agents/{agent_name}/stop")
async def stop_agent(agent_name: str):
    """Stop a specific agent."""
    if agent_name not in agents:
        raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
    
    await agents[agent_name].stop()
    return {"status": "stopped", "agent": agent_name}


@app.get("/metrics")
async def get_metrics():
    """Get system-wide metrics."""
    return {
        "agents_count": len(agents),
        "active_agents": len([a for a in agents.values() if a.state == AgentState.RUNNING]),
        "bridge_connected": zmq_bridge.is_connected() if zmq_bridge else False,
        "timestamp": datetime.utcnow().isoformat()
    }


# ===========================================
# Initialization Functions
# ===========================================

async def initialize_agents():
    """Initialize all 20 AI agents (placeholder for Stage 1)."""
    logger.info("Initializing AI agents...")
    
    # In Stage 1, we create placeholder agents
    # Later stages will implement full agent logic
    
    agent_classes = [
        "MarketDataAgent",
        "TechnicalAnalysisAgent",
        "RiskManagementAgent",
        "SupervisorAgent"
    ]
    
    for agent_class in agent_classes:
        try:
            # Import dynamically (will be implemented in later stages)
            module = __import__(f"agents.{agent_class.lower()}", fromlist=[agent_class])
            agent_cls = getattr(module, agent_class)
            agent = agent_cls(name=agent_class)
            agents[agent_class] = agent
            logger.info(f"✓ Initialized {agent_class}")
        except ImportError as e:
            logger.warning(f"Agent {agent_class} not yet implemented: {e}")
            # Create base agent as placeholder
            agent = BaseAgent(name=agent_class)
            agents[agent_class] = agent
    
    logger.info(f"Initialized {len(agents)} agents")


# ===========================================
# Main Entry Point
# ===========================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
