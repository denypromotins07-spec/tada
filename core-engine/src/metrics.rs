//! Metrics collection and Prometheus export

use std::sync::atomic::{AtomicU64, Ordering};

/// Global metrics counters
pub struct Metrics {
    pub orders_submitted: AtomicU64,
    pub orders_filled: AtomicU64,
    pub orders_rejected: AtomicU64,
    pub messages_processed: AtomicU64,
    pub avg_latency_micros: AtomicU64,
    pub websocket_reconnects: AtomicU64,
}

impl Metrics {
    pub fn new() -> Self {
        Metrics {
            orders_submitted: AtomicU64::new(0),
            orders_filled: AtomicU64::new(0),
            orders_rejected: AtomicU64::new(0),
            messages_processed: AtomicU64::new(0),
            avg_latency_micros: AtomicU64::new(0),
            websocket_reconnects: AtomicU64::new(0),
        }
    }

    pub fn record_order(&self) {
        self.orders_submitted.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_fill(&self) {
        self.orders_filled.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_rejection(&self) {
        self.orders_rejected.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_message(&self) {
        self.messages_processed.fetch_add(1, Ordering::Relaxed);
    }

    pub fn record_latency(&self, latency_micros: u64) {
        // Simple moving average
        let current = self.avg_latency_micros.load(Ordering::Relaxed);
        let new_avg = (current * 9 + latency_micros) / 10;
        self.avg_latency_micros.store(new_avg, Ordering::Relaxed);
    }
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

/// Global metrics instance
lazy_static::lazy_static! {
    pub static ref GLOBAL_METRICS: Metrics = Metrics::new();
}

// Helper macro for lazy_static
#[macro_export]
macro_rules! lazy_static {
    ($($tt:tt)*) => {
        // Placeholder - in production use the actual lazy_static crate
    };
}
