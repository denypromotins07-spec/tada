-- QuantumHFT TimescaleDB Initialization Script
-- Optimized for crypto tick data with hypertables

-- ===========================================
-- Enable TimescaleDB Extension
-- ===========================================
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ===========================================
-- Tick Data Hypertable
-- Stores raw tick/trade data with microsecond precision
-- ===========================================
CREATE TABLE IF NOT EXISTS tick_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    is_buyer_maker BOOLEAN NOT NULL,
    trade_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable with 1-hour chunks (optimized for crypto)
SELECT create_hypertable('tick_data', 'time', chunk_time_interval => INTERVAL '1 hour', if_not_exists => TRUE);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tick_data_symbol_time ON tick_data (symbol, time DESC);
CREATE INDEX IF NOT EXISTS idx_tick_data_trade_id ON tick_data (trade_id);

-- Compression policy (compress data older than 7 days)
SELECT add_compression_policy('tick_data', INTERVAL '7 days') ON CONFLICT DO NOTHING;

-- ===========================================
-- OHLCV Candlestick Data
-- Pre-aggregated candlesticks for fast chart rendering
-- ===========================================
CREATE TABLE IF NOT EXISTS ohlcv_data (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- 1m, 5m, 15m, 1h, 4h, 1d
    open DECIMAL(20, 8) NOT NULL,
    high DECIMAL(20, 8) NOT NULL,
    low DECIMAL(20, 8) NOT NULL,
    close DECIMAL(20, 8) NOT NULL,
    volume DECIMAL(20, 8) NOT NULL,
    trades BIGINT NOT NULL,
    vwap DECIMAL(20, 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable with 1-day chunks
SELECT create_hypertable('ohlcv_data', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_time_interval ON ohlcv_data (symbol, interval, time DESC);

-- ===========================================
-- Order Book Snapshots
-- Periodic order book depth snapshots
-- ===========================================
CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    time TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    bids JSONB NOT NULL,  -- Array of [price, quantity]
    asks JSONB NOT NULL,
    spread DECIMAL(20, 8),
    mid_price DECIMAL(20, 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Convert to hypertable with 6-hour chunks
SELECT create_hypertable('orderbook_snapshots', 'time', chunk_time_interval => INTERVAL '6 hours', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_orderbook_symbol_time ON orderbook_snapshots (symbol, time DESC);

-- ===========================================
-- Orders History
-- All executed orders
-- ===========================================
CREATE TABLE IF NOT EXISTS orders (
    order_id BIGINT PRIMARY KEY,
    client_order_id VARCHAR(100) UNIQUE,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,  -- BUY or SELL
    order_type VARCHAR(20) NOT NULL,  -- LIMIT, MARKET, etc.
    time_in_force VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8),
    stop_price DECIMAL(20, 8),
    status VARCHAR(20) NOT NULL,
    filled_quantity DECIMAL(20, 8) DEFAULT 0,
    avg_fill_price DECIMAL(20, 8),
    commission DECIMAL(20, 8),
    commission_asset VARCHAR(20),
    agent_name VARCHAR(50),
    submission_time TIMESTAMPTZ,
    ack_time TIMESTAMPTZ,
    fill_time TIMESTAMPTZ,
    completion_time TIMESTAMPTZ,
    latency_micros BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_orders_symbol_time ON orders (symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_agent ON orders (agent_name);

-- ===========================================
-- Fills/Executions
-- Individual fill records
-- ===========================================
CREATE TABLE IF NOT EXISTS fills (
    fill_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    price DECIMAL(20, 8) NOT NULL,
    commission DECIMAL(20, 8),
    commission_asset VARCHAR(20),
    is_maker BOOLEAN,
    timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_fills_order_id ON fills (order_id);
CREATE INDEX IF NOT EXISTS idx_fills_symbol_time ON fills (symbol, timestamp DESC);

-- ===========================================
-- Agent Signals & Decisions
-- Track AI agent trading signals
-- ===========================================
CREATE TABLE IF NOT EXISTS agent_signals (
    signal_id BIGSERIAL PRIMARY KEY,
    agent_name VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    confidence DECIMAL(5, 4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    target_quantity DECIMAL(20, 8),
    target_price DECIMAL(20, 8),
    stop_loss DECIMAL(20, 8),
    take_profit DECIMAL(20, 8),
    reasoning TEXT,
    executed BOOLEAN DEFAULT FALSE,
    order_id BIGINT REFERENCES orders(order_id),
    pnl DECIMAL(20, 8),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_signals_agent_time ON agent_signals (agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON agent_signals (symbol);
CREATE INDEX IF NOT EXISTS idx_signals_executed ON agent_signals (executed);

-- ===========================================
-- System Metrics & Health
-- Monitor system performance
-- ===========================================
CREATE TABLE IF NOT EXISTS system_metrics (
    time TIMESTAMPTZ NOT NULL,
    metric_name VARCHAR(50) NOT NULL,
    metric_value DECIMAL(20, 8) NOT NULL,
    unit VARCHAR(20),
    tags JSONB
);

-- Convert to hypertable with 1-day chunks
SELECT create_hypertable('system_metrics', 'time', chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON system_metrics (metric_name, time DESC);

-- ===========================================
-- Continuous Aggregates (for fast analytics)
-- ===========================================

-- 1-minute OHLCV aggregation
CREATE MATERIALIZED VIEW IF NOT EXISTS ohlcv_1m
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 minute', time) AS bucket,
    first(price, time) AS open,
    max(price) AS high,
    min(price) AS low,
    last(price, time) AS close,
    sum(quantity) AS volume,
    count(*) AS trades
FROM tick_data
GROUP BY symbol, bucket
WITH NO DATA;

-- Add refresh policy
SELECT add_continuous_aggregate_policy('ohlcv_1m',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');

-- ===========================================
-- Utility Functions
-- ===========================================

-- Function to get latest price for a symbol
CREATE OR REPLACE FUNCTION get_latest_price(sym VARCHAR)
RETURNS DECIMAL AS $$
BEGIN
    RETURN (
        SELECT price 
        FROM tick_data 
        WHERE symbol = sym 
        ORDER BY time DESC 
        LIMIT 1
    );
END;
$$ LANGUAGE plpgsql;

-- Function to calculate VWAP for a time range
CREATE OR REPLACE FUNCTION calculate_vwap(
    sym VARCHAR,
    start_time TIMESTAMPTZ,
    end_time TIMESTAMPTZ
)
RETURNS DECIMAL AS $$
BEGIN
    RETURN (
        SELECT SUM(price * quantity) / SUM(quantity)
        FROM tick_data
        WHERE symbol = sym
          AND time BETWEEN start_time AND end_time
    );
END;
$$ LANGUAGE plpgsql;

-- ===========================================
-- Insert Sample Data (for testing)
-- ===========================================
-- Uncomment to insert test data
-- INSERT INTO tick_data (time, symbol, price, quantity, is_buyer_maker, trade_id)
-- VALUES 
--     (NOW(), 'BTCUSDT', 42350.50, 0.15, false, 1000001),
--     (NOW(), 'BTCUSDT', 42351.00, 0.08, true, 1000002),
--     (NOW(), 'ETHUSDT', 2245.75, 1.5, false, 2000001);
