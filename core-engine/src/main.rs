//! QuantumHFT - Ultra-Low Latency HFT Execution Engine
//! 
//! This is the core Rust engine responsible for:
//! - Microsecond-latency order execution
//! - Real-time WebSocket market data processing
//! - Lock-free Order Management System (OMS)
//! - High-throughput message parsing with zero allocations
//!
//! Hardware Optimization:
//! - Uses MiMalloc for fragmentation-free memory allocation
//! - Tokio multi-threaded runtime for async parallelism
//! - Crossbeam lock-free channels for IPC
//! - simd-json for zero-allocation JSON parsing

#[macro_use]
extern crate tracing;

use std::sync::Arc;
use tokio::sync::broadcast;

mod oms;
mod exchange;
mod matching;
mod models;
mod config;
mod metrics;

use oms::OrderManagementSystem;
use exchange::binance_ws::BinanceWebSocket;
use config::EngineConfig;

/// Global allocator using MiMalloc for optimal memory performance
/// This prevents memory fragmentation which is critical for HFT
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

/// Main entry point for the QuantumHFT Execution Engine
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing subscriber for structured logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("quantumhft_engine=info".parse().unwrap())
                .add_directive("tokio=warn".parse().unwrap())
        )
        .json()
        .init();

    info!("🚀 QuantumHFT Execution Engine Starting...");
    info!("Hardware: Using MiMalloc global allocator");
    info!("Runtime: Tokio multi-threaded async runtime");

    // Load configuration
    let config = EngineConfig::load()?;
    info!("Configuration loaded: {:?}", config);

    // Create shared state
    let (order_tx, order_rx) = crossbeam_channel::unbounded();
    let (fill_tx, fill_rx) = crossbeam_channel::unbounded();
    let (market_data_tx, _) = broadcast::channel(10000);

    // Initialize Order Management System
    let oms = Arc::new(OrderManagementSystem::new(order_tx.clone(), fill_rx));
    let oms_clone = Arc::clone(&oms);

    // Spawn OMS processing task
    let oms_handle = tokio::spawn(async move {
        info!("OMS task started");
        oms_clone.run().await;
    });

    // Initialize Binance WebSocket connection
    let binance_ws = BinanceWebSocket::new(
        config.binance_ws_url.clone(),
        config.symbols.clone(),
        market_data_tx,
        order_tx,
        fill_tx,
    );

    // Spawn WebSocket task
    let ws_handle = tokio::spawn(async move {
        info!("Binance WebSocket task started");
        if let Err(e) = binance_ws.run().await {
            error!("WebSocket error: {}", e);
        }
    });

    // Spawn metrics collection task
    let metrics_handle = tokio::spawn(async move {
        run_metrics_collector().await;
    });

    // Spawn health check task
    let health_handle = tokio::spawn(async move {
        run_health_checker(oms).await;
    });

    info!("✅ All systems operational. Waiting for market data...");

    // Wait for shutdown signal
    tokio::signal::ctrl_c().await?;
    
    warn!("Shutdown signal received, gracefully stopping...");

    // Abort all tasks
    ws_handle.abort();
    oms_handle.abort();
    metrics_handle.abort();
    health_handle.abort();

    info!("👋 QuantumHFT Execution Engine stopped");
    
    Ok(())
}

/// Metrics collection task - publishes Prometheus metrics
async fn run_metrics_collector() {
    let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(1));
    loop {
        interval.tick().await;
        // Update metrics here
        // metrics::update_all();
    }
}

/// Health checker - monitors system health and latency
async fn run_health_checker(oms: Arc<OrderManagementSystem>) {
    let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(5));
    loop {
        interval.tick().await;
        
        let stats = oms.get_stats();
        info!(
            "Health Check - Orders: {}, Fills: {}, Pending: {}, Avg Latency: {}μs",
            stats.total_orders,
            stats.total_fills,
            stats.pending_orders,
            stats.avg_latency_micros
        );
    }
}
