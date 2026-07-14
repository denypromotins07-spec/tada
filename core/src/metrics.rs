//! =============================================================================
//! Metrics Module
//! =============================================================================
//! Prometheus metrics registry for monitoring system performance.
//! 
//! Tracks:
//! - Order submission latency (microseconds)
//! - WebSocket message rate
//! - Order book update frequency
//! - Memory usage
//! - CPU utilization per core
//! =============================================================================

use prometheus::{Counter, Gauge, Histogram, Registry};
use std::sync::Arc;

/// Metrics registry wrapper
pub struct MetricsRegistry {
    /// Prometheus registry
    pub registry: Registry,
    
    /// Total orders sent counter
    pub orders_sent: Counter,
    
    /// Latency histogram (in microseconds)
    pub latency_us: Histogram,
    
    /// WebSocket messages received counter
    pub ws_messages: Counter,
    
    /// Active orders gauge
    pub active_orders: Gauge,
    
    /// Memory usage gauge (bytes)
    pub memory_bytes: Gauge,
}

impl MetricsRegistry {
    /// Create a new metrics registry
    pub fn new() -> Self {
        let registry = Registry::new();

        // Orders sent counter
        let orders_sent = Counter::new(
            "hft_orders_sent_total",
            "Total number of orders sent to exchanges"
        ).unwrap();
        registry.register(Box::new(orders_sent.clone())).unwrap();

        // Latency histogram
        let latency_buckets = vec![
            10.0, 25.0, 50.0, 100.0, 250.0, 500.0,
            1000.0, 2500.0, 5000.0, 10000.0,
        ];
        let latency_us = Histogram::with_opts(
            prometheus::HistogramOpts::new(
                "hft_order_latency_microseconds",
                "Order execution latency in microseconds"
            )
            .buckets(latency_buckets)
        ).unwrap();
        registry.register(Box::new(latency_us.clone())).unwrap();

        // WebSocket messages counter
        let ws_messages = Counter::new(
            "hft_websocket_messages_total",
            "Total WebSocket messages received"
        ).unwrap();
        registry.register(Box::new(ws_messages.clone())).unwrap();

        // Active orders gauge
        let active_orders = Gauge::new(
            "hft_active_orders",
            "Number of currently active orders"
        ).unwrap();
        registry.register(Box::new(active_orders.clone())).unwrap();

        // Memory usage gauge
        let memory_bytes = Gauge::new(
            "hft_memory_usage_bytes",
            "Current memory usage in bytes"
        ).unwrap();
        registry.register(Box::new(memory_bytes.clone())).unwrap();

        Self {
            registry,
            orders_sent,
            latency_us,
            ws_messages,
            active_orders,
            memory_bytes,
        }
    }

    /// Gather all metrics
    pub fn gather(&self) -> Vec<prometheus::proto::MetricFamily> {
        self.registry.gather()
    }

    /// Export metrics as Prometheus text format
    pub fn export_text(&self) -> String {
        use prometheus::Encoder;
        let mut buffer = Vec::new();
        let encoder = prometheus::TextEncoder::new();
        
        if let Err(e) = encoder.encode(&self.gather(), &mut buffer) {
            return format!("Error encoding metrics: {}", e);
        }

        String::from_utf8_lossy(&buffer).to_string()
    }
}

impl Default for MetricsRegistry {
    fn default() -> Self {
        Self::new()
    }
}
