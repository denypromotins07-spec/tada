//! Core data models for the HFT engine

use rust_decimal::Decimal;
use serde::{Deserialize, Serialize};

/// Symbol information
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Symbol {
    pub symbol: String,
    pub base_asset: String,
    pub quote_asset: String,
    pub price_precision: u8,
    pub quantity_precision: u8,
    pub min_qty: Decimal,
    pub max_qty: Decimal,
    pub step_size: Decimal,
    pub min_notional: Decimal,
}

/// OHLCV candlestick data
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Candlestick {
    pub symbol: String,
    pub interval: String,
    pub open_time: u64,
    pub close_time: u64,
    pub open: Decimal,
    pub high: Decimal,
    pub low: Decimal,
    pub close: Decimal,
    pub volume: Decimal,
    pub trades: u64,
}

/// Order book level
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBookLevel {
    pub price: Decimal,
    pub quantity: Decimal,
}

/// Full order book snapshot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderBook {
    pub symbol: String,
    pub timestamp: u64,
    pub bids: Vec<OrderBookLevel>,
    pub asks: Vec<OrderBookLevel>,
}

impl OrderBook {
    pub fn new(symbol: String) -> Self {
        OrderBook {
            symbol,
            timestamp: 0,
            bids: Vec::new(),
            asks: Vec::new(),
        }
    }

    pub fn best_bid(&self) -> Option<&OrderBookLevel> {
        self.bids.first()
    }

    pub fn best_ask(&self) -> Option<&OrderBookLevel> {
        self.asks.first()
    }

    pub fn mid_price(&self) -> Option<Decimal> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some((bid.price + ask.price) / Decimal::from(2)),
            _ => None,
        }
    }

    pub fn spread(&self) -> Option<Decimal> {
        match (self.best_bid(), self.best_ask()) {
            (Some(bid), Some(ask)) => Some(ask.price - bid.price),
            _ => None,
        }
    }
}
