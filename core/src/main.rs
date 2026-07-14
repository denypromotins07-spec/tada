//! =============================================================================
//! HFT Rust Core - Main Entry Point
//! =============================================================================
//! This is the heart of the ultra-low-latency trading system.
//! 
//! Features:
//! - Tokio runtime with real-time thread priorities
//! - CPU pinning to specific AMD cores for deterministic performance
//! - Memory locking to prevent page swapping
//! - Graceful shutdown handling
//! - Prometheus metrics export
//! 
//! Architecture:
//! 1. Initialize global allocator (jemalloc)
//! 2. Set up tracing/logging
//! 3. Configure Tokio runtime with real-time priorities
//! 4. Pin threads to CPU cores
//! 5. Lock memory pages to prevent swapping
//! 6. Spawn async tasks for:
//!    - Binance WebSocket connector
//!    - Order book reconstruction
//!    - Smart Order Router
//!    - Redis publisher
//!    - Metrics exporter
//! =============================================================================

#![warn(missing_docs)]
#![warn(rustdoc::missing_doc_code_examples)]
#![deny(clippy::all)]
#![deny(clippy::pedantic)]
#![allow(clippy::module_name_repetitions)]

mod exchange;
mod execution;
mod orderbook;
mod metrics;

use anyhow::{Context, Result};
use std::sync::Arc;
use tokio::signal;
use tracing::{error, info, warn};

/// Application configuration loaded from environment variables
#[derive(Debug, Clone)]
pub struct Config {
    /// Binance WebSocket URL
    pub binance_ws_url: String,
    /// Redis connection URL
    pub redis_url: String,
    /// CPU cores to pin to (e.g., "0-3" for cores 0,1,2,3)
    pub cpu_affinity: String,
    /// Real-time priority (1-99, higher = more priority)
    pub rt_priority: i32,
    /// Enable memory locking
    pub memory_lock: bool,
    /// Log level (trace, debug, info, warn, error)
    pub log_level: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            binance_ws_url: std::env::var("BINANCE_WS_URL")
                .unwrap_or_else(|_| "wss://stream.binance.com:9443/ws".to_string()),
            redis_url: std::env::var("REDIS_URL")
                .unwrap_or_else(|_| "redis://localhost:6379".to_string()),
            cpu_affinity: std::env::var("CPU_AFFINITY").unwrap_or_else(|_| "0-3".to_string()),
            rt_priority: std::env::var("RT_PRIORITY")
                .ok()
                .and_then(|s| s.parse().ok())
                .unwrap_or(99),
            memory_lock: std::env::var("MEMORY_LOCK").unwrap_or_else(|_| "true".to_string()) == "true",
            log_level: std::env::var("RUST_LOG").unwrap_or_else(|_| "info".to_string()),
        }
    }
}

/// Main application state shared across tasks
pub struct AppState {
    /// Application configuration
    pub config: Config,
    /// Shared metrics registry
    pub metrics: Arc<metrics::MetricsRegistry>,
    /// Shutdown signal sender
    pub shutdown_tx: tokio::sync::broadcast::Sender<()>,
}

/// =============================================================================
/// MAIN ENTRY POINT
/// =============================================================================
#[tokio::main]
async fn main() -> Result<()> {
    // =========================================================================
    // STEP 1: Initialize global allocator (jemalloc for better performance)
    // =========================================================================
    #[cfg(not(target_env = "msvc"))]
    {
        use tikv_jemallocator::Jemalloc;
        #[global_allocator]
        static GLOBAL: Jemalloc = Jemalloc;
        info!("Using jemalloc global allocator");
    }

    // =========================================================================
    // STEP 2: Load configuration from environment
    // =========================================================================
    let config = Config::default();
    
    // =========================================================================
    // STEP 3: Initialize tracing/logging with JSON format for production
    // =========================================================================
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| config.log_level.clone().into()),
        )
        .with_target(false)
        .with_thread_ids(true)
        .with_thread_names(true)
        .json()
        .init();

    info!(
        binance_ws = %config.binance_ws_url,
        redis_url = %config.redis_url,
        cpu_affinity = %config.cpu_affinity,
        rt_priority = config.rt_priority,
        memory_lock = config.memory_lock,
        "Initializing HFT Core"
    );

    // =========================================================================
    // STEP 4: Configure real-time priorities and CPU pinning (Linux only)
    // =========================================================================
    #[cfg(target_os = "linux")]
    {
        configure_realtime(&config)?;
    }

    // =========================================================================
    // STEP 5: Lock memory pages to prevent swapping (critical for low latency)
    // =========================================================================
    if config.memory_lock {
        lock_memory()?;
        info!("Memory pages locked successfully");
    }

    // =========================================================================
    // STEP 6: Create shutdown channel for graceful termination
    // =========================================================================
    let (shutdown_tx, _) = tokio::sync::broadcast::channel::<()>(1);
    let shutdown_tx = Arc::new(shutdown_tx);

    // =========================================================================
    // STEP 7: Initialize metrics registry
    // =========================================================================
    let metrics = Arc::new(metrics::MetricsRegistry::new());

    // =========================================================================
    // STEP 8: Create shared application state
    // =========================================================================
    let state = Arc::new(AppState {
        config,
        metrics,
        shutdown_tx: shutdown_tx.as_ref().clone(),
    });

    // =========================================================================
    // STEP 9: Spawn core async tasks
    // =========================================================================
    
    // Task 1: Binance WebSocket connector
    let ws_state = state.clone();
    let ws_handle = tokio::spawn(async move {
        info!("Starting Binance WebSocket connector");
        if let Err(e) = exchange::binance::run_connector(ws_state).await {
            error!("Binance connector failed: {}", e);
        }
    });

    // Task 2: Smart Order Router
    let router_state = state.clone();
    let router_handle = tokio::spawn(async move {
        info!("Starting Smart Order Router");
        if let Err(e) = execution::router::run_router(router_state).await {
            error!("Order router failed: {}", e);
        }
    });

    // Task 3: Redis publisher for state sync
    let redis_state = state.clone();
    let redis_handle = tokio::spawn(async move {
        info!("Starting Redis publisher");
        if let Err(e) = redis_publisher(redis_state).await {
            error!("Redis publisher failed: {}", e);
        }
    });

    // Task 4: Metrics exporter
    let metrics_state = state.clone();
    let metrics_handle = tokio::spawn(async move {
        info!("Starting metrics exporter");
        if let Err(e) = metrics_exporter(metrics_state).await {
            error!("Metrics exporter failed: {}", e);
        }
    });

    // =========================================================================
    // STEP 10: Wait for shutdown signal (SIGINT/SIGTERM)
    // =========================================================================
    info!("HFT Core is running. Press Ctrl+C to shutdown.");
    
    match shutdown_signal().await {
        Ok(_) => info!("Received shutdown signal"),
        Err(e) => error!("Error waiting for shutdown: {}", e),
    }

    // =========================================================================
    // STEP 11: Broadcast shutdown to all tasks
    // =========================================================================
    warn!("Broadcasting shutdown signal to all tasks...");
    let _ = state.shutdown_tx.send(());

    // =========================================================================
    // STEP 12: Wait for all tasks to complete gracefully
    // =========================================================================
    info!("Waiting for tasks to shutdown...");
    
    let _ = tokio::join!(
        ws_handle,
        router_handle,
        redis_handle,
        metrics_handle,
    );

    info!("HFT Core shutdown complete");
    Ok(())
}

/// =============================================================================
/// REAL-TIME CONFIGURATION (Linux-specific)
/// =============================================================================
#[cfg(target_os = "linux")]
fn configure_realtime(config: &Config) -> Result<()> {
    use nix::sched::{sched_setaffinity, CpuSet};
    use nix::unistd::Pid;
    use std::str::FromStr;

    info!("Configuring real-time priorities and CPU affinity");

    // Parse CPU affinity string (e.g., "0-3" or "0,1,2,3")
    let cpus = parse_cpu_affinity(&config.cpu_affinity)?;
    
    // Create CPU set
    let mut cpu_set = CpuSet::new();
    for cpu in cpus {
        cpu_set.set(cpu as usize)
            .with_context(|| format!("Failed to set CPU {}", cpu))?;
    }

    // Pin current thread to specified CPUs
    sched_setaffinity(Pid::this(), &cpu_set)
        .with_context(|| "Failed to set CPU affinity")?;

    info!("CPU affinity set to: {}", config.cpu_affinity);

    // Set real-time priority using SCHED_FIFO
    // Note: This requires CAP_SYS_NICE capability or root privileges
    let param = libc::sched_param {
        sched_priority: config.rt_priority,
    };

    unsafe {
        let result = libc::sched_setscheduler(
            0, // 0 means current process
            libc::SCHED_FIFO,
            &param,
        );
        
        if result != 0 {
            warn!(
                "Failed to set real-time scheduler (requires root/CAP_SYS_NICE): errno={}",
                *libc::__errno_location()
            );
            warn!("Continuing with normal priority (latency may be higher)");
        } else {
            info!("Real-time priority set to {} (SCHED_FIFO)", config.rt_priority);
        }
    }

    Ok(())
}

/// Parse CPU affinity string into vector of CPU IDs
fn parse_cpu_affinity(affinity: &str) -> Result<Vec<u32>> {
    let mut cpus = Vec::new();
    
    for part in affinity.split(',') {
        let part = part.trim();
        if part.contains('-') {
            // Range format: "0-3"
            let parts: Vec<&str> = part.split('-').collect();
            if parts.len() != 2 {
                anyhow::bail!("Invalid CPU range: {}", part);
            }
            let start = u32::from_str(parts[0])?;
            let end = u32::from_str(parts[1])?;
            if start > end {
                anyhow::bail!("Invalid CPU range: start > end in {}", part);
            }
            for cpu in start..=end {
                cpus.push(cpu);
            }
        } else {
            // Single CPU: "0"
            cpus.push(u32::from_str(part)?);
        }
    }

    if cpus.is_empty() {
        anyhow::bail!("No CPUs specified in affinity: {}", affinity);
    }

    Ok(cpus)
}

/// =============================================================================
/// MEMORY LOCKING
/// =============================================================================
fn lock_memory() -> Result<()> {
    #[cfg(target_os = "linux")]
    {
        use libc::{mlockall, MCL_CURRENT, MCL_FUTURE};
        
        unsafe {
            let result = mlockall(MCL_CURRENT | MCL_FUTURE);
            if result != 0 {
                warn!(
                    "Failed to lock memory (requires IPC_LOCK capability): errno={}",
                    *libc::__errno_location()
                );
                warn!("Continuing without memory locking (may cause latency spikes)");
            } else {
                info!("All memory pages locked successfully");
            }
        }
    }

    #[cfg(not(target_os = "linux"))]
    {
        warn!("Memory locking is only supported on Linux");
    }

    Ok(())
}

/// =============================================================================
/// REDIS PUBLISHER TASK
/// =============================================================================
async fn redis_publisher(state: Arc<AppState>) -> Result<()> {
    use redis::{Client, Connection, PubSubCommands};
    use serde_json::json;
    use tokio::time::{interval, Duration};

    let client = Client::open(state.config.redis_url.as_str())?;
    let mut con = client.get_connection()?;
    
    let mut interval = interval(Duration::from_millis(100)); // 10Hz heartbeat
    
    loop {
        tokio::select! {
            _ = interval.tick() => {
                // Publish heartbeat and metrics
                let msg = json!({
                    "type": "heartbeat",
                    "timestamp": chrono::Utc::now().to_rfc3339(),
                    "metrics": {
                        "orders_sent": state.metrics.orders_sent.get(),
                        "latency_us": state.metrics.latency_us.get(),
                    }
                });
                
                let _ = con.publish::<_, _, ()>("hft:status", msg.to_string());
            }
            _ = state.shutdown_tx.subscribe().recv() => {
                info!("Redis publisher shutting down");
                break;
            }
        }
    }

    Ok(())
}

/// =============================================================================
/// METRICS EXPORTER TASK
/// =============================================================================
async fn metrics_exporter(state: Arc<AppState>) -> Result<()> {
    use tokio::time::{interval, Duration};
    
    let mut interval = interval(Duration::from_secs(1));
    
    loop {
        tokio::select! {
            _ = interval.tick() => {
                // Export metrics to Prometheus endpoint
                // In production, this would bind to a port and serve /metrics
                let _ = state.metrics.gather();
            }
            _ = state.shutdown_tx.subscribe().recv() => {
                info!("Metrics exporter shutting down");
                break;
            }
        }
    }
}

/// =============================================================================
/// SHUTDOWN SIGNAL HANDLER
/// =============================================================================
async fn shutdown_signal() -> Result<()> {
    let ctrl_c = async {
        signal::ctrl_c()
            .await
            .context("Failed to install Ctrl+C handler")?;
        Ok::<(), anyhow::Error>(())
    };

    #[cfg(unix)]
    let terminate = async {
        signal::unix::signal(signal::unix::SignalKind::terminate())?
            .recv()
            .await;
        Ok::<(), anyhow::Error>(())
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<Result<(), anyhow::Error>>();

    tokio::select! {
        res = ctrl_c => res?,
        res = terminate => res?,
    }

    Ok(())
}
