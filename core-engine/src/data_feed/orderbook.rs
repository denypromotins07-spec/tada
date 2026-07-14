//! Local Order Book Reconstruction with Sequence ID Tracking
//! 
//! Handles order book updates, sequence gap detection, and automatic REST API resync.
//! Uses DashMap for lock-free concurrent access during high volatility.

use crate::models::{DepthSnapshot, OrderBookLevel};
use dashmap::DashMap;
use rust_decimal::Decimal;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{warn, info, debug};

/// Represents the local state of an order book
#[derive(Debug)]
pub struct LocalOrderBook {
    symbol: String,
    last_update_id: i64,
    bids: DashMap<Decimal, Decimal, rustc_hash::FxBuildHasher>,
    asks: DashMap<Decimal, Decimal, rustc_hash::FxBuildHasher>,
    sequence_gap_count: u32,
}

impl LocalOrderBook {
    pub fn new(symbol: &str) -> Self {
        Self {
            symbol: symbol.to_string(),
            last_update_id: 0,
            bids: DashMap::with_hasher(rustc_hash::FxBuildHasher::default()),
            asks: DashMap::with_hasher(rustc_hash::FxBuildHasher::default()),
            sequence_gap_count: 0,
        }
    }

    /// Initialize order book from a REST API snapshot
    pub async fn initialize_from_rest(
        &mut self,
        snapshot: DepthSnapshot,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        self.last_update_id = snapshot.last_update_id;
        
        // Clear existing data
        self.bids.clear();
        self.asks.clear();

        // Insert bid levels
        for level in snapshot.bids {
            self.bids.insert(level.price, level.quantity);
        }

        // Insert ask levels
        for level in snapshot.asks {
            self.asks.insert(level.price, level.quantity);
        }

        info!(
            "Initialized order book for {} with {} bids and {} asks",
            self.symbol,
            self.bids.len(),
            self.asks.len()
        );

        Ok(())
    }

    /// Apply an incremental update to the order book
    pub fn apply_update(
        &mut self,
        update: DepthSnapshot,
    ) -> Result<bool, Box<dyn std::error::Error + Send + Sync>> {
        // Check for sequence gaps
        if self.last_update_id > 0 && update.first_update_id != self.last_update_id + 1 {
            self.sequence_gap_count += 1;
            warn!(
                "Sequence gap detected for {}: expected {}, got {}. Gap count: {}",
                self.symbol,
                self.last_update_id + 1,
                update.first_update_id,
                self.sequence_gap_count
            );

            // If too many gaps, trigger resync
            if self.sequence_gap_count > 5 {
                return Ok(true); // Signal that resync is needed
            }
        }

        self.last_update_id = update.last_update_id;
        self.sequence_gap_count = 0; // Reset on successful update

        // Update bids
        for level in update.bids {
            if level.quantity == Decimal::ZERO {
                self.bids.remove(&level.price);
            } else {
                self.bids.insert(level.price, level.quantity);
            }
        }

        // Update asks
        for level in update.asks {
            if level.quantity == Decimal::ZERO {
                self.asks.remove(&level.price);
            } else {
                self.asks.insert(level.price, level.quantity);
            }
        }

        // Prune order book to maintain memory efficiency (keep top 100 levels)
        self.prune_book(100);

        Ok(false)
    }

    /// Prune order book to keep only top N levels on each side
    fn prune_book(&mut self, max_levels: usize) {
        // Get all bid prices and sort descending
        let mut bid_prices: Vec<_> = self.bids.iter().map(|r| *r.key()).collect();
        bid_prices.sort_by(|a, b| b.cmp(a));
        
        // Remove excess bids
        if bid_prices.len() > max_levels {
            for price in bid_prices.into_iter().skip(max_levels) {
                self.bids.remove(&price);
            }
        }

        // Get all ask prices and sort ascending
        let mut ask_prices: Vec<_> = self.asks.iter().map(|r| *r.key()).collect();
        ask_prices.sort_by(|a, b| a.cmp(b));
        
        // Remove excess asks
        if ask_prices.len() > max_levels {
            for price in ask_prices.into_iter().skip(max_levels) {
                self.asks.remove(&price);
            }
        }
    }

    /// Get the current best bid price and quantity
    pub fn get_best_bid(&self) -> Option<(Decimal, Decimal)> {
        self.bids
            .iter()
            .max_by_key(|r| *r.key())
            .map(|r| (*r.key(), *r.value()))
    }

    /// Get the current best ask price and quantity
    pub fn get_best_ask(&self) -> Option<(Decimal, Decimal)> {
        self.asks
            .iter()
            .min_by_key(|r| *r.key())
            .map(|r| (*r.key(), *r.value()))
    }

    /// Get the mid price
    pub fn get_mid_price(&self) -> Option<Decimal> {
        match (self.get_best_bid(), self.get_best_ask()) {
            (Some((bid, _)), Some((ask, _))) => Some((bid + ask) / Decimal::new(2, 0)),
            _ => None,
        }
    }

    /// Get the spread in decimal terms
    pub fn get_spread(&self) -> Option<Decimal> {
        match (self.get_best_bid(), self.get_best_ask()) {
            (Some((bid, _)), Some((ask, _))) => Some(ask - bid),
            _ => None,
        }
    }

    /// Calculate total liquidity within a percentage range
    pub fn get_liquidity_within_range(&self, pct_range: Decimal) -> (Decimal, Decimal) {
        let mid = match self.get_mid_price() {
            Some(m) => m,
            None => return (Decimal::ZERO, Decimal::ZERO),
        };

        let lower_bound = mid * (Decimal::ONE - pct_range);
        let upper_bound = mid * (Decimal::ONE + pct_range);

        let bid_liquidity: Decimal = self
            .bids
            .iter()
            .filter(|r| *r.key() >= lower_bound && *r.key() <= mid)
            .map(|r| *r.value())
            .sum();

        let ask_liquidity: Decimal = self
            .asks
            .iter()
            .filter(|r| *r.key() > mid && *r.key() <= upper_bound)
            .map(|r| *r.value())
            .sum();

        (bid_liquidity, ask_liquidity)
    }

    /// Export current state as a snapshot
    pub fn to_snapshot(&self) -> DepthSnapshot {
        let mut bids: Vec<OrderBookLevel> = self
            .bids
            .iter()
            .map(|r| OrderBookLevel {
                price: *r.key(),
                quantity: *r.value(),
            })
            .collect();
        bids.sort_by(|a, b| b.price.cmp(&a.price));
        bids.truncate(20);

        let mut asks: Vec<OrderBookLevel> = self
            .asks
            .iter()
            .map(|r| OrderBookLevel {
                price: *r.key(),
                quantity: *r.value(),
            })
            .collect();
        asks.sort_by(|a, b| a.price.cmp(&b.price));
        asks.truncate(20);

        DepthSnapshot {
            symbol: self.symbol.clone(),
            last_update_id: self.last_update_id,
            first_update_id: self.last_update_id,
            bids,
            asks,
            timestamp: chrono::Utc::now().timestamp_millis(),
        }
    }

    pub fn symbol(&self) -> &str {
        &self.symbol
    }

    pub fn last_update_id(&self) -> i64 {
        self.last_update_id
    }
}

/// Order book manager handling multiple symbols concurrently
pub struct OrderBookManager {
    books: DashMap<String, Arc<RwLock<LocalOrderBook>>, rustc_hash::FxBuildHasher>,
}

impl OrderBookManager {
    pub fn new() -> Self {
        Self {
            books: DashMap::with_hasher(rustc_hash::FxBuildHasher::default()),
        }
    }

    pub fn get_or_create(&self, symbol: &str) -> Arc<RwLock<LocalOrderBook>> {
        self.books
            .entry(symbol.to_string())
            .or_insert_with(|| {
                Arc::new(RwLock::new(LocalOrderBook::new(symbol)))
            })
            .clone()
    }

    pub fn get(&self, symbol: &str) -> Option<Arc<RwLock<LocalOrderBook>>> {
        self.books.get(symbol).map(|r| r.clone())
    }

    pub fn remove(&self, symbol: &str) {
        self.books.remove(symbol);
    }

    pub fn symbols(&self) -> Vec<String> {
        self.books.iter().map(|r| r.key().clone()).collect()
    }
}

impl Default for OrderBookManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rust_decimal::prelude::*;

    #[test]
    fn test_orderbook_initialization() {
        let mut book = LocalOrderBook::new("BTCUSDT");
        
        let snapshot = DepthSnapshot {
            symbol: "BTCUSDT".to_string(),
            last_update_id: 1000,
            first_update_id: 900,
            bids: vec![
                OrderBookLevel { price: Decimal::from_f64_retain(50000.0).unwrap(), quantity: Decimal::from_f64_retain(1.5).unwrap() },
                OrderBookLevel { price: Decimal::from_f64_retain(49900.0).unwrap(), quantity: Decimal::from_f64_retain(2.0).unwrap() },
            ],
            asks: vec![
                OrderBookLevel { price: Decimal::from_f64_retain(50100.0).unwrap(), quantity: Decimal::from_f64_retain(1.0).unwrap() },
                OrderBookLevel { price: Decimal::from_f64_retain(50200.0).unwrap(), quantity: Decimal::from_f64_retain(2.5).unwrap() },
            ],
            timestamp: 1234567890,
        };

        futures_executor::block_on(book.initialize_from_rest(snapshot)).unwrap();

        assert_eq!(book.last_update_id, 1000);
        assert_eq!(book.bids.len(), 2);
        assert_eq!(book.asks.len(), 2);
    }

    #[test]
    fn test_best_bid_ask() {
        let mut book = LocalOrderBook::new("ETHUSDT");
        
        book.bids.insert(Decimal::from_f64_retain(3000.0).unwrap(), Decimal::from_f64_retain(10.0).unwrap());
        book.bids.insert(Decimal::from_f64_retain(2990.0).unwrap(), Decimal::from_f64_retain(20.0).unwrap());
        book.asks.insert(Decimal::from_f64_retain(3010.0).unwrap(), Decimal::from_f64_retain(5.0).unwrap());
        book.asks.insert(Decimal::from_f64_retain(3020.0).unwrap(), Decimal::from_f64_retain(15.0).unwrap());

        let (best_bid_price, best_bid_qty) = book.get_best_bid().unwrap();
        assert_eq!(best_bid_price, Decimal::from_f64_retain(3000.0).unwrap());
        assert_eq!(best_bid_qty, Decimal::from_f64_retain(10.0).unwrap());

        let (best_ask_price, best_ask_qty) = book.get_best_ask().unwrap();
        assert_eq!(best_ask_price, Decimal::from_f64_retain(3010.0).unwrap());
        assert_eq!(best_ask_qty, Decimal::from_f64_retain(5.0).unwrap());
    }

    #[test]
    fn test_mid_price_and_spread() {
        let mut book = LocalOrderBook::new("BTCUSDT");
        
        book.bids.insert(Decimal::from_f64_retain(50000.0).unwrap(), Decimal::ONE);
        book.asks.insert(Decimal::from_f64_retain(50100.0).unwrap(), Decimal::ONE);

        let mid = book.get_mid_price().unwrap();
        assert_eq!(mid, Decimal::from_f64_retain(50050.0).unwrap());

        let spread = book.get_spread().unwrap();
        assert_eq!(spread, Decimal::from_f64_retain(100.0).unwrap());
    }
}
