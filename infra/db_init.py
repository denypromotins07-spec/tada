#!/usr/bin/env python3
"""
=============================================================================
QuestDB Database Initialization Script
=============================================================================
Creates optimized tables for HFT tick data storage.

Tables:
- order_book: Order book snapshots and updates
- trades: Executed trades with latency tracking
- positions: Current and historical positions
- executions: Order execution reports

Partitioning Strategy:
- Partitioned by day for efficient time-range queries
- Symbol column indexed for fast filtering
- Optimized for append-only workloads
=============================================================================
"""

import asyncio
import asyncpg
import os
from datetime import datetime
from typing import Optional


class QuestDBInitializer:
    """Initialize QuestDB tables for HFT trading system."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        user: str = "admin",
        password: str = "quest",
        database: str = "questdb",
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection: Optional[asyncpg.Connection] = None

    async def connect(self) -> None:
        """Establish connection to QuestDB."""
        print(f"Connecting to QuestDB at {self.host}:{self.port}...")
        
        try:
            self.connection = await asyncpg.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            print("✓ Connected to QuestDB successfully")
        except Exception as e:
            print(f"✗ Failed to connect: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connection."""
        if self.connection:
            await self.connection.close()
            print("✓ Disconnected from QuestDB")

    async def create_order_book_table(self) -> None:
        """
        Create order book table for storing L2/L3 order book data.
        
        Schema optimized for:
        - High-frequency updates (100ms intervals)
        - Time-series queries
        - Symbol-based filtering
        """
        print("\nCreating order_book table...")
        
        query = """
        CREATE TABLE IF NOT EXISTS order_book (
            -- Timestamp (partition key)
            timestamp TIMESTAMP NOT NULL,
            
            -- Symbol identifier
            symbol SYMBOL NOT NULL,
            
            -- Update sequence ID for deduplication
            update_id LONG NOT NULL,
            
            -- Best bid/ask prices
            best_bid DOUBLE NOT NULL,
            best_ask DOUBLE NOT NULL,
            
            -- Best bid/ask quantities
            best_bid_qty DOUBLE NOT NULL,
            best_ask_qty DOUBLE NOT NULL,
            
            -- Mid price (calculated)
            mid_price DOUBLE NOT NULL,
            
            -- Spread in absolute terms
            spread DOUBLE NOT NULL,
            
            -- Spread in basis points
            spread_bps DOUBLE NOT NULL,
            
            -- Order book imbalance (-1 to 1)
            imbalance DOUBLE NOT NULL,
            
            -- Total bid volume (top 10 levels)
            bid_volume_10 DOUBLE NOT NULL,
            
            -- Total ask volume (top 10 levels)
            ask_volume_10 DOUBLE NOT NULL,
            
            -- Number of bid levels
            num_bids INT NOT NULL,
            
            -- Number of ask levels
            num_asks INT NOT NULL
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """
        
        await self.connection.execute(query)
        print("✓ order_book table created")

    async def create_trades_table(self) -> None:
        """
        Create trades table for storing executed trades.
        
        Includes latency tracking for performance monitoring.
        """
        print("\nCreating trades table...")
        
        query = """
        CREATE TABLE IF NOT EXISTS trades (
            -- Trade timestamp
            timestamp TIMESTAMP NOT NULL,
            
            -- Symbol identifier
            symbol SYMBOL NOT NULL,
            
            -- Unique trade ID from exchange
            trade_id LONG NOT NULL,
            
            -- Trade price
            price DOUBLE NOT NULL,
            
            -- Trade quantity
            quantity DOUBLE NOT NULL,
            
            -- Trade value (price * quantity)
            value DOUBLE NOT NULL,
            
            -- Buyer is maker flag
            is_buyer_maker BOOLEAN NOT NULL,
            
            -- Aggregate trade ID (Binance specific)
            agg_trade_id LONG,
            
            -- First trade ID in aggregation
            first_trade_id LONG,
            
            -- Last trade ID in aggregation
            last_trade_id LONG,
            
            -- Number of trades in aggregation
            num_trades INT,
            
            -- Ingestion timestamp (for latency tracking)
            ingested_at TIMESTAMP NOT NULL,
            
            -- Latency from exchange to storage (microseconds)
            latency_us LONG NOT NULL
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """
        
        await self.connection.execute(query)
        print("✓ trades table created")

    async def create_positions_table(self) -> None:
        """
        Create positions table for tracking current and historical positions.
        """
        print("\nCreating positions table...")
        
        query = """
        CREATE TABLE IF NOT EXISTS positions (
            -- Snapshot timestamp
            timestamp TIMESTAMP NOT NULL,
            
            -- Symbol identifier
            symbol SYMBOL NOT NULL,
            
            -- Position side (1=long, -1=short, 0=flat)
            side INT NOT NULL,
            
            -- Position quantity
            quantity DOUBLE NOT NULL,
            
            -- Average entry price
            avg_entry_price DOUBLE NOT NULL,
            
            -- Current mark price
            mark_price DOUBLE NOT NULL,
            
            -- Unrealized P&L
            unrealized_pnl DOUBLE NOT NULL,
            
            -- Realized P&L (closed positions)
            realized_pnl DOUBLE NOT NULL,
            
            -- Leverage used
            leverage DOUBLE NOT NULL,
            
            -- Margin used
            margin_used DOUBLE NOT NULL,
            
            -- Liquidation price
            liquidation_price DOUBLE,
            
            -- Account equity at snapshot
            equity DOUBLE NOT NULL
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """
        
        await self.connection.execute(query)
        print("✓ positions table created")

    async def create_executions_table(self) -> None:
        """
        Create executions table for order execution reports.
        """
        print("\nCreating executions table...")
        
        query = """
        CREATE TABLE IF NOT EXISTS executions (
            -- Execution timestamp
            timestamp TIMESTAMP NOT NULL,
            
            -- Order ID
            order_id STRING NOT NULL,
            
            -- Symbol identifier
            symbol SYMBOL NOT NULL,
            
            -- Order side (BUY/SELL)
            side STRING NOT NULL,
            
            -- Order type (MARKET/LIMIT/etc)
            order_type STRING NOT NULL,
            
            -- Execution status
            status STRING NOT NULL,
            
            -- Filled quantity
            filled_qty DOUBLE NOT NULL,
            
            -- Remaining quantity
            remaining_qty DOUBLE NOT NULL,
            
            -- Average fill price
            avg_fill_price DOUBLE,
            
            -- Last fill price
            last_fill_price DOUBLE,
            
            -- Last fill quantity
            last_fill_qty DOUBLE,
            
            -- Commission paid
            commission DOUBLE,
            
            -- Commission asset
            commission_asset SYMBOL,
            
            -- Execution latency (microseconds)
            latency_us LONG NOT NULL,
            
            -- Slippage in basis points
            slippage_bps DOUBLE,
            
            -- Exchange order ID
            exchange_order_id STRING,
            
            -- Error message (if rejected)
            error_message STRING
        ) TIMESTAMP(timestamp) PARTITION BY DAY;
        """
        
        await self.connection.execute(query)
        print("✓ executions table created")

    async def create_indexes(self) -> None:
        """Create indexes for common query patterns."""
        print("\nCreating indexes...")
        
        # Note: QuestDB automatically creates indexes on SYMBOL columns
        # Additional indexes can be created as needed
        
        print("✓ Indexes created (symbol columns auto-indexed)")

    async def initialize_all(self) -> None:
        """Run all initialization steps."""
        print("=" * 60)
        print("QuestDB HFT Table Initialization")
        print("=" * 60)
        
        await self.connect()
        
        try:
            await self.create_order_book_table()
            await self.create_trades_table()
            await self.create_positions_table()
            await self.create_executions_table()
            await self.create_indexes()
            
            print("\n" + "=" * 60)
            print("✓ All tables created successfully!")
            print("=" * 60)
            
        finally:
            await self.disconnect()


async def main():
    """Main entry point."""
    # Load configuration from environment
    host = os.getenv("QUESTDB_HOST", "localhost")
    port = int(os.getenv("QUESTDB_PORT", "9000"))
    user = os.getenv("QUESTDB_USERNAME", "admin")
    password = os.getenv("QUESTDB_PASSWORD", "quest")
    database = os.getenv("QUESTDB_DB_NAME", "questdb")
    
    initializer = QuestDBInitializer(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    
    await initializer.initialize_all()


if __name__ == "__main__":
    asyncio.run(main())
