//! Order Management System (OMS)
//! 
//! Handles order lifecycle management using lock-free data structures
//! for maximum throughput and minimal latency.
//! 
//! Features:
//! - Lock-free crossbeam channels for order submission
//! - Atomic order state management with DashMap
//! - Zero-copy message parsing
//! - Microsecond-level latency tracking

use std::sync::atomic::{AtomicU64, AtomicUsize, Ordering};
use std::time::{Duration, Instant};
use crossbeam_channel::{Receiver, Sender};
use dashmap::DashMap;
use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

/// Order states in the lifecycle
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderState {
    PendingNew,
    New,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
    Expired,
}

/// Order side (Buy/Sell)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Side {
    Buy,
    Sell,
}

/// Order type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderType {
    Limit,
    Market,
    StopLimit,
    StopMarket,
}

/// Time in force
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TimeInForce {
    GTC, // Good Till Cancel
    IOC, // Immediate Or Cancel
    FOK, // Fill Or Kill
    GTD, // Good Till Date
}

/// Internal order representation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Order {
    pub order_id: u64,
    pub client_order_id: String,
    pub symbol: String,
    pub side: Side,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub quantity: Decimal,
    pub price: Option<Decimal>,
    pub stop_price: Option<Decimal>,
    pub state: OrderState,
    pub filled_quantity: Decimal,
    pub avg_fill_price: Option<Decimal>,
    pub created_at: u64,  // Unix timestamp micros
    pub updated_at: u64,
    pub latencies: OrderLatencies,
}

/// Latency tracking for each order
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OrderLatencies {
    pub submission_time_micros: u64,
    pub ack_time_micros: u64,
    pub first_fill_time_micros: u64,
    pub completion_time_micros: u64,
}

impl Order {
    pub fn new(
        order_id: u64,
        client_order_id: String,
        symbol: String,
        side: Side,
        order_type: OrderType,
        time_in_force: TimeInForce,
        quantity: Decimal,
        price: Option<Decimal>,
        stop_price: Option<Decimal>,
    ) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_micros() as u64;

        Order {
            order_id,
            client_order_id,
            symbol,
            side,
            order_type,
            time_in_force,
            quantity,
            price,
            stop_price,
            state: OrderState::PendingNew,
            filled_quantity: Decimal::ZERO,
            avg_fill_price: None,
            created_at: now,
            updated_at: now,
            latencies: OrderLatencies {
                submission_time_micros: now,
                ..Default::default()
            },
        }
    }

    pub fn update_state(&mut self, new_state: OrderState) {
        self.state = new_state;
        self.updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_micros() as u64;
    }

    pub fn add_fill(&mut self, fill_qty: Decimal, fill_price: Decimal, fill_time: u64) {
        self.filled_quantity += fill_qty;
        
        // Update average fill price
        self.avg_fill_price = match self.avg_fill_price {
            Some(avg) => Some((avg * self.filled_quantity - fill_qty + fill_price * fill_qty) / self.filled_quantity),
            None => Some(fill_price),
        };

        if self.latencies.first_fill_time_micros == 0 {
            self.latencies.first_fill_time_micros = fill_time;
        }

        // Check if fully filled
        if self.filled_quantity >= self.quantity {
            self.update_state(OrderState::Filled);
            self.latencies.completion_time_micros = fill_time;
        } else {
            self.update_state(OrderState::PartiallyFilled);
        }
    }

    pub fn is_active(&self) -> bool {
        matches!(self.state, OrderState::PendingNew | OrderState::New | OrderState::PartiallyFilled)
    }
}

/// Fill execution report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Fill {
    pub order_id: u64,
    pub fill_id: u64,
    pub symbol: String,
    pub side: Side,
    pub quantity: Decimal,
    pub price: Decimal,
    pub commission: Decimal,
    pub commission_asset: String,
    pub timestamp: u64,
    pub is_maker: bool,
}

/// OMS Statistics
#[derive(Debug, Clone)]
pub struct OmsStats {
    pub total_orders: u64,
    pub total_fills: u64,
    pub pending_orders: usize,
    pub active_orders: usize,
    pub avg_latency_micros: u64,
}

/// Order Management System
/// Uses lock-free data structures for maximum performance
pub struct OrderManagementSystem {
    /// All orders stored in a concurrent hash map
    orders: DashMap<u64, Order>,
    
    /// Channel for receiving new order requests
    order_receiver: Receiver<OrderRequest>,
    
    /// Channel for sending fill reports
    fill_sender: Sender<Fill>,
    
    /// Atomic order ID counter
    order_counter: AtomicU64,
    
    /// Statistics counters
    total_orders: AtomicU64,
    total_fills: AtomicU64,
    sum_latency: AtomicU64,
}

/// Incoming order request from trading agents
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderRequest {
    pub symbol: String,
    pub side: Side,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub quantity: Decimal,
    pub price: Option<Decimal>,
    pub stop_price: Option<Decimal>,
    pub client_order_id: Option<String>,
}

impl OrderManagementSystem {
    pub fn new(
        order_sender: Sender<OrderRequest>,
        fill_receiver: Receiver<Fill>,
    ) -> Self {
        // We need reverse channels - receive orders, send fills
        let (order_tx, order_rx) = crossbeam_channel::unbounded();
        let (fill_tx, fill_rx) = crossbeam_channel::unbounded();
        
        OrderManagementSystem {
            orders: DashMap::new(),
            order_receiver: order_rx,
            fill_sender: fill_tx,
            order_counter: AtomicU64::new(1),
            total_orders: AtomicU64::new(0),
            total_fills: AtomicU64::new(0),
            sum_latency: AtomicU64::new(0),
        }
    }

    /// Generate unique order ID
    fn generate_order_id(&self) -> u64 {
        self.order_counter.fetch_add(1, Ordering::Relaxed)
    }

    /// Submit a new order
    pub async fn submit_order(&self, request: OrderRequest) -> Result<u64, OmsError> {
        let order_id = self.generate_order_id();
        let client_order_id = request.client_order_id.unwrap_or_else(|| {
            format!("{}_{}_{}", request.symbol, order_id, std::process::id())
        });

        let mut order = Order::new(
            order_id,
            client_order_id,
            request.symbol,
            request.side,
            request.order_type,
            request.time_in_force,
            request.quantity,
            request.price,
            request.stop_price,
        );

        // Insert order into state
        self.orders.insert(order_id, order);
        self.total_orders.fetch_add(1, Ordering::Relaxed);

        info!("Order submitted: {} - {} {} @ {:?}", order_id, request.side, request.quantity, request.price);

        Ok(order_id)
    }

    /// Cancel an existing order
    pub async fn cancel_order(&self, order_id: u64) -> Result<(), OmsError> {
        if let Some(mut order) = self.orders.get_mut(&order_id) {
            if order.is_active() {
                order.update_state(OrderState::Cancelled);
                info!("Order cancelled: {}", order_id);
                return Ok(());
            }
            Err(OmsError::OrderNotCancellable)
        } else {
            Err(OmsError::OrderNotFound)
        }
    }

    /// Process a fill report
    pub fn process_fill(&self, fill: Fill) {
        if let Some(mut order) = self.orders.get_mut(&fill.order_id) {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_micros() as u64;
            
            order.add_fill(fill.quantity, fill.price, now);
            self.total_fills.fetch_add(1, Ordering::Relaxed);
            
            // Track latency
            let latency = now - order.latencies.submission_time_micros;
            self.sum_latency.fetch_add(latency, Ordering::Relaxed);

            info!(
                "Fill processed: Order {} - {} {} @ {} (Total: {}/{})",
                fill.order_id,
                fill.side,
                fill.quantity,
                fill.price,
                order.filled_quantity,
                order.quantity
            );
        }
    }

    /// Get order by ID
    pub fn get_order(&self, order_id: u64) -> Option<Order> {
        self.orders.get(&order_id).map(|o| o.clone())
    }

    /// Get all active orders for a symbol
    pub fn get_active_orders(&self, symbol: &str) -> Vec<Order> {
        self.orders
            .iter()
            .filter(|o| o.value().symbol == symbol && o.value().is_active())
            .map(|o| o.clone())
            .collect()
    }

    /// Get OMS statistics
    pub fn get_stats(&self) -> OmsStats {
        let total_orders = self.total_orders.load(Ordering::Relaxed);
        let total_fills = self.total_fills.load(Ordering::Relaxed);
        let sum_latency = self.sum_latency.load(Ordering::Relaxed);
        
        let avg_latency = if total_orders > 0 {
            sum_latency / total_orders
        } else {
            0
        };

        let mut pending = 0;
        let mut active = 0;
        for o in self.orders.iter() {
            if matches!(o.value().state, OrderState::PendingNew) {
                pending += 1;
            }
            if o.value().is_active() {
                active += 1;
            }
        }

        OmsStats {
            total_orders,
            total_fills,
            pending_orders: pending,
            active_orders: active,
            avg_latency_micros: avg_latency,
        }
    }

    /// Main OMS processing loop
    pub async fn run(&self) {
        info!("OMS main loop started");
        
        loop {
            // Process incoming messages
            tokio::select! {
                Ok(order_request) = self.order_receiver.recv() => {
                    if let Err(e) = self.submit_order(order_request).await {
                        error!("Failed to submit order: {}", e);
                    }
                }
            }
        }
    }
}

/// OMS Error types
#[derive(Debug, thiserror::Error)]
pub enum OmsError {
    #[error("Order not found")]
    OrderNotFound,
    #[error("Order is not cancellable in current state")]
    OrderNotCancellable,
    #[error("Invalid order parameters: {0}")]
    InvalidParameters(String),
    #[error("Insufficient balance")]
    InsufficientBalance,
    #[error("Position limit exceeded")]
    PositionLimitExceeded,
}
