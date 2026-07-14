#!/usr/bin/env python3
"""
=============================================================================
HFT Strategy Engine - Main Entry Point
=============================================================================
Nautilus Trader kernel initialization with Ray cluster integration.

Features:
- Event-driven backtesting and live trading via Nautilus
- Distributed ML inference via Ray actors
- Redis pub/sub for real-time state sync
- QuestDB integration for tick storage
- AMD GPU/NPU acceleration for model inference

Usage:
    python main.py --mode backtest  # Run backtest
    python main.py --mode live      # Run live trading (DANGER!)
=============================================================================
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import ray
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler

# Load environment variables
load_dotenv()

# Initialize Rich console for beautiful output
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True)],
)
log = logging.getLogger(__name__)


class HFTStrategyEngine:
    """
    Main strategy engine coordinating Nautilus Trader and Ray.
    
    Architecture:
    1. Initialize Ray cluster for distributed computing
    2. Connect to Redis for state synchronization
    3. Initialize Nautilus Trader kernel
    4. Register strategies and data engines
    5. Run backtest or live trading loop
    """

    def __init__(
        self,
        mode: str = "backtest",
        redis_url: str = "redis://localhost:6379",
        ray_address: Optional[str] = None,
    ):
        self.mode = mode
        self.redis_url = redis_url
        self.ray_address = ray_address
        self.ray_initialized = False
        self.nautilus_kernel = None
        
    def initialize_ray(self) -> None:
        """
        Initialize or connect to Ray cluster.
        
        For AMD GPU acceleration, ensure ONNXRUNTIME_PROVIDERS=rocm
        is set in environment variables.
        """
        console.print("\n[bold blue]Initializing Ray Cluster...[/bold blue]")
        
        try:
            if self.ray_address:
                # Connect to existing cluster
                ray.init(
                    address=self.ray_address,
                    ignore_reinit_error=True,
                    log_to_driver=True,
                )
                console.print(f"[green]✓ Connected to existing Ray cluster at {self.ray_address}[/green]")
            else:
                # Start local cluster
                ray.init(
                    include_dashboard=True,
                    dashboard_port=8265,
                    num_cpus=6,  # AMD Ryzen AI 5 has 6 cores
                    _temp_dir="/tmp/ray",
                )
                console.print("[green]✓ Started local Ray cluster[/green]")
            
            self.ray_initialized = True
            
            # Print cluster info
            cluster_info = ray.cluster_resources()
            console.print(f"  CPU cores: {cluster_info.get('CPU', 0)}")
            console.print(f"  Object store: {cluster_info.get('object_store_memory', 0) / 1e9:.2f} GB")
            
        except Exception as e:
            console.print(f"[red]✗ Failed to initialize Ray: {e}[/red]")
            raise

    def connect_redis(self) -> None:
        """Connect to Redis for state synchronization."""
        console.print("\n[bold blue]Connecting to Redis...[/bold blue]")
        
        try:
            import redis
            self.redis_client = redis.from_url(self.redis_url)
            self.redis_client.ping()
            console.print(f"[green]✓ Connected to Redis at {self.redis_url}[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Redis connection failed: {e}[/yellow]")
            console.print("[yellow]  Continuing without Redis pub/sub[/yellow]")
            self.redis_client = None

    def initialize_nautilus(self) -> None:
        """Initialize Nautilus Trader kernel."""
        console.print("\n[bold blue]Initializing Nautilus Trader...[/bold blue]")
        
        try:
            from nautilus_trader.core import NautilusKernel
            from nautilus_trader.config import LoggingConfig, TradingConfig
            
            # Create configuration
            logging_config = LoggingConfig(
                log_level="INFO",
                log_colors=True,
            )
            
            trading_config = TradingConfig(
                logging=logging_config,
                use_trader=False,  # We'll use custom execution
            )
            
            # Initialize kernel
            self.nautilus_kernel = NautilusKernel(
                instance_id="hft-core-001",
                trading_config=trading_config,
            )
            
            console.print("[green]✓ Nautilus Trader kernel initialized[/green]")
            
        except ImportError as e:
            console.print(f"[red]✗ Nautilus Trader not installed: {e}[/red]")
            console.print("[red]  Install with: pip install nautilus_trader[/red]")
            raise
        except Exception as e:
            console.print(f"[red]✗ Failed to initialize Nautilus: {e}[/red]")
            raise

    def register_strategies(self) -> None:
        """Register trading strategies with Nautilus."""
        console.print("\n[bold blue]Registering Strategies...[/bold blue]")
        
        # Import strategies (to be implemented)
        # from .strategies.trend_following import TrendFollowingStrategy
        # from .strategies.mean_reversion import MeanReversionStrategy
        
        console.print("[yellow]⚠ Strategy registration pending implementation[/yellow]")
        console.print("  Add your strategies in src/strategies/")

    async def run_backtest(self) -> None:
        """Run backtesting mode."""
        console.print("\n[bold magenta]Running Backtest Mode[/bold magenta]")
        
        # TODO: Implement backtest logic using Nautilus backtest engine
        # This would load historical data from QuestDB and run strategies
        
        console.print("[yellow]Backtest engine pending implementation[/yellow]")

    async def run_live(self) -> None:
        """Run live trading mode."""
        console.print("\n[bold red]Running LIVE Trading Mode[/bold red]")
        console.print("[red]⚠ WARNING: Real money at risk![/red]")
        
        # TODO: Implement live trading logic
        # This would connect to Binance via Rust core and execute trades
        
        console.print("[yellow]Live trading engine pending implementation[/yellow]")

    async def run(self) -> None:
        """Main execution loop."""
        console.print("\n[bold cyan]HFT Strategy Engine Starting...[/bold cyan]")
        console.print(f"Mode: [bold]{self.mode}[/bold]")
        
        # Initialize components
        self.initialize_ray()
        self.connect_redis()
        self.initialize_nautilus()
        self.register_strategies()
        
        # Run based on mode
        if self.mode == "backtest":
            await self.run_backtest()
        elif self.mode == "live":
            await self.run_live()
        else:
            console.print(f"[red]Unknown mode: {self.mode}[/red]")
            sys.exit(1)
        
        # Cleanup
        self.shutdown()

    def shutdown(self) -> None:
        """Clean shutdown of all resources."""
        console.print("\n[bold blue]Shutting down...[/bold blue]")
        
        if self.ray_initialized:
            ray.shutdown()
            console.print("[green]✓ Ray cluster shut down[/green]")
        
        console.print("[green]✓ Shutdown complete[/green]")


def main(
    mode: str = typer.Option(
        "backtest",
        "--mode",
        "-m",
        help="Execution mode: backtest or live",
    ),
    redis_url: str = typer.Option(
        "redis://localhost:6379",
        "--redis",
        "-r",
        help="Redis connection URL",
    ),
    ray_address: Optional[str] = typer.Option(
        None,
        "--ray",
        help="Ray cluster address (optional, starts local if not provided)",
    ),
) -> None:
    """
    HFT Strategy Engine CLI entry point.
    
    Examples:
        python main.py --mode backtest
        python main.py --mode live --redis redis://redis:6379
    """
    engine = HFTStrategyEngine(
        mode=mode,
        redis_url=redis_url,
        ray_address=ray_address,
    )
    
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        engine.shutdown()
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        engine.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
