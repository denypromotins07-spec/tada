//! Real-Time Order Flow Analytics Module
//! 
//! Calculates Cumulative Volume Delta (CVD), Volume Profile, and Footprint charts.
//! Uses lock-free accumulators for high-performance tick-level processing.

use crate::models::TradeData;
use rust_decimal::Decimal;
use dashmap::DashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

/// Lock-free accumulator for CVD calculation
#[derive(Debug)]
pub struct CvdAccumulator {
    total_buy_volume: AtomicU64,
    total_sell_volume: AtomicU64,
    net_cvd: AtomicU64,
    last_reset_timestamp: AtomicU64,
}

impl CvdAccumulator {
    pub fn new() -> Self {
        Self {
            total_buy_volume: AtomicU64::new(0),
            total_sell_volume: AtomicU64::new(0),
            net_cvd: AtomicU64::new(0),
            last_reset_timestamp: AtomicU64::new(0),
        }
    }

    /// Add a trade to the CVD accumulator
    pub fn add_trade(&self, trade: &TradeData) {
        // Convert decimal to u64 cents for atomic operations
        let volume_cents = (trade.quantity * Decimal::new(10000, 0)).to_u64().unwrap_or(0);

        if trade.is_buyer_maker {
            // Seller initiated (maker is seller)
            self.total_sell_volume.fetch_add(volume_cents, Ordering::Relaxed);
        } else {
            // Buyer initiated (maker is buyer)
            self.total_buy_volume.fetch_add(volume_cents, Ordering::Relaxed);
        }

        // Update net CVD
        let buy_vol = self.total_buy_volume.load(Ordering::Relaxed);
        let sell_vol = self.total_sell_volume.load(Ordering::Relaxed);
        
        let net = if buy_vol >= sell_vol {
            buy_vol - sell_vol
        } else {
            0xFFFFFFFFFFFFFFFFu64 - (sell_vol - buy_vol) // Represent negative as two's complement
        };
        
        self.net_cvd.store(net, Ordering::Relaxed);
    }

    /// Get current CVD value (returns i64 for signed representation)
    pub fn get_cvd(&self) -> i64 {
        let buy_vol = self.total_buy_volume.load(Ordering::Relaxed);
        let sell_vol = self.total_sell_volume.load(Ordering::Relaxed);
        
        if buy_vol >= sell_vol {
            (buy_vol - sell_vol) as i64
        } else {
            -((sell_vol - buy_vol) as i64)
        }
    }

    /// Get total buy volume
    pub fn get_buy_volume(&self) -> u64 {
        self.total_buy_volume.load(Ordering::Relaxed)
    }

    /// Get total sell volume
    pub fn get_sell_volume(&self) -> u64 {
        self.total_sell_volume.load(Ordering::Relaxed)
    }

    /// Reset accumulator
    pub fn reset(&self, timestamp: u64) {
        self.total_buy_volume.store(0, Ordering::Relaxed);
        self.total_sell_volume.store(0, Ordering::Relaxed);
        self.net_cvd.store(0, Ordering::Relaxed);
        self.last_reset_timestamp.store(timestamp, Ordering::Relaxed);
    }

    /// Get imbalance ratio (buy / total)
    pub fn get_imbalance_ratio(&self) -> f64 {
        let buy = self.total_buy_volume.load(Ordering::Relaxed) as f64;
        let sell = self.total_sell_volume.load(Ordering::Relaxed) as f64;
        let total = buy + sell;
        
        if total > 0.0 {
            buy / total
        } else {
            0.5
        }
    }
}

impl Default for CvdAccumulator {
    fn default() -> Self {
        Self::new()
    }
}

/// Volume profile bucket at a specific price level
#[derive(Debug, Clone)]
pub struct VolumeBucket {
    pub price: Decimal,
    pub buy_volume: Decimal,
    pub sell_volume: Decimal,
    pub trade_count: u32,
}

impl VolumeBucket {
    pub fn new(price: Decimal) -> Self {
        Self {
            price,
            buy_volume: Decimal::ZERO,
            sell_volume: Decimal::ZERO,
            trade_count: 0,
        }
    }

    pub fn add_trade(&mut self, quantity: Decimal, is_buyer_maker: bool) {
        self.trade_count += 1;
        if is_buyer_maker {
            self.sell_volume += quantity;
        } else {
            self.buy_volume += quantity;
        }
    }

    pub fn total_volume(&self) -> Decimal {
        self.buy_volume + self.sell_volume
    }

    pub fn point_of_control(&self) -> Decimal {
        self.total_volume()
    }
}

/// Real-time volume profile calculator
#[derive(Debug)]
pub struct VolumeProfile {
    buckets: DashMap<u64, VolumeBucket>, // Price bucket key (price * precision)
    price_precision: u32,
    min_price: AtomicU64,
    max_price: AtomicU64,
}

impl VolumeProfile {
    pub fn new(price_precision: u32) -> Self {
        Self {
            buckets: DashMap::new(),
            price_precision,
            min_price: AtomicU64::new(u64::MAX),
            max_price: AtomicU64::new(0),
        }
    }

    /// Add a trade to the volume profile
    pub fn add_trade(&self, trade: &TradeData) {
        // Bucket the price
        let price_bucket = (trade.price * Decimal::new(10i64.pow(self.price_precision), 0))
            .to_u64()
            .unwrap_or(0);

        // Update min/max price tracking
        let mut current_min = self.min_price.load(Ordering::Relaxed);
        while price_bucket < current_min {
            if self.min_price.compare_exchange_weak(current_min, price_bucket, Ordering::Relaxed, Ordering::Relaxed).is_ok() {
                break;
            }
            current_min = self.min_price.load(Ordering::Relaxed);
        }

        let mut current_max = self.max_price.load(Ordering::Relaxed);
        while price_bucket > current_max {
            if self.max_price.compare_exchange_weak(current_max, price_bucket, Ordering::Relaxed, Ordering::Relaxed).is_ok() {
                break;
            }
            current_max = self.max_price.load(Ordering::Relaxed);
        }

        // Add to bucket
        let mut bucket = self.buckets.entry(price_bucket).or_insert_with(|| {
            VolumeBucket::new(trade.price)
        });
        bucket.add_trade(trade.quantity, trade.is_buyer_maker);
    }

    /// Get all buckets sorted by price
    pub fn get_sorted_buckets(&self) -> Vec<VolumeBucket> {
        let mut buckets: Vec<_> = self.buckets.iter().map(|r| r.value().clone()).collect();
        buckets.sort_by(|a, b| a.price.cmp(&b.price));
        buckets
    }

    /// Get Point of Control (POC) - price with highest volume
    pub fn get_poc(&self) -> Option<VolumeBucket> {
        self.buckets
            .iter()
            .max_by(|a, b| a.value().total_volume().cmp(&b.value().total_volume()))
            .map(|r| r.value().clone())
    }

    /// Get Value Area (70% of volume around POC)
    pub fn get_value_area(&self) -> Option<(Decimal, Decimal)> {
        let poc = self.get_poc()?;
        let total_volume: Decimal = self.buckets.iter().map(|r| r.value().total_volume()).sum();
        let target_volume = total_volume * Decimal::from_f64_retain(0.7).unwrap_or(Decimal::new(7, 1));

        let mut sorted_buckets = self.get_sorted_buckets();
        
        // Find POC index
        let poc_index = sorted_buckets.iter().position(|b| b.price == poc.price)?;
        
        let mut left = poc_index;
        let mut right = poc_index;
        let mut accumulated_volume = sorted_buckets[poc_index].total_volume();

        // Expand outward from POC until we have 70% of volume
        while accumulated_volume < target_volume && (left > 0 || right < sorted_buckets.len() - 1) {
            let left_vol = if left > 0 { sorted_buckets[left - 1].total_volume() } else { Decimal::ZERO };
            let right_vol = if right < sorted_buckets.len() - 1 { sorted_buckets[right + 1].total_volume() } else { Decimal::ZERO };

            if left_vol >= right_vol && left > 0 {
                left -= 1;
                accumulated_volume += left_vol;
            } else if right < sorted_buckets.len() - 1 {
                right += 1;
                accumulated_volume += right_vol;
            } else {
                break;
            }
        }

        Some((sorted_buckets[left].price, sorted_buckets[right].price))
    }

    /// Clear all buckets
    pub fn clear(&self) {
        self.buckets.clear();
        self.min_price.store(u64::MAX, Ordering::Relaxed);
        self.max_price.store(0, Ordering::Relaxed);
    }
}

/// Footprint chart data for a single price bar
#[derive(Debug, Clone)]
pub struct FootprintBar {
    pub timestamp: i64,
    pub open: Decimal,
    pub high: Decimal,
    pub low: Decimal,
    pub close: Decimal,
    pub buy_volume: Decimal,
    pub sell_volume: Decimal,
    pub price_levels: Vec<(Decimal, Decimal, Decimal)>, // (price, buy_vol, sell_vol)
}

/// Real-time footprint chart builder
#[derive(Debug)]
pub struct FootprintBuilder {
    bars: DashMap<i64, FootprintBar>,
    bar_duration_ms: i64,
    levels_per_bar: DashMap<i64, DashMap<u64, (Decimal, Decimal)>>, // timestamp -> price_bucket -> (buy, sell)
}

impl FootprintBuilder {
    pub fn new(bar_duration_ms: i64) -> Self {
        Self {
            bars: DashMap::new(),
            bar_duration_ms,
            levels_per_bar: DashMap::new(),
        }
    }

    /// Add a trade to the footprint
    pub fn add_trade(&self, trade: &TradeData) {
        let bar_timestamp = (trade.timestamp / self.bar_duration_ms) * self.bar_duration_ms;
        let price_bucket = (trade.price * Decimal::new(1000, 0)).to_u64().unwrap_or(0);

        // Initialize bar if needed
        self.bars.entry(bar_timestamp).or_insert_with(|| FootprintBar {
            timestamp: bar_timestamp,
            open: trade.price,
            high: trade.price,
            low: trade.price,
            close: trade.price,
            buy_volume: Decimal::ZERO,
            sell_volume: Decimal::ZERO,
            price_levels: Vec::new(),
        });

        // Update bar OHLC
        if let Some(mut bar) = self.bars.get_mut(&bar_timestamp) {
            if trade.price > bar.high {
                bar.high = trade.price;
            }
            if trade.price < bar.low {
                bar.low = trade.price;
            }
            bar.close = trade.price;

            if trade.is_buyer_maker {
                bar.sell_volume += trade.quantity;
            } else {
                bar.buy_volume += trade.quantity;
            }
        }

        // Track price level volumes
        let levels = self.levels_per_bar.entry(bar_timestamp).or_insert_with(DashMap::new);
        let mut level_entry = levels.entry(price_bucket).or_insert((Decimal::ZERO, Decimal::ZERO));
        
        if trade.is_buyer_maker {
            level_entry.1 += trade.quantity;
        } else {
            level_entry.0 += trade.quantity;
        }
    }

    /// Get completed bars
    pub fn get_bars(&self) -> Vec<FootprintBar> {
        let mut bars: Vec<_> = self.bars.iter().map(|r| r.value().clone()).collect();
        bars.sort_by_key(|b| b.timestamp);
        bars
    }

    /// Get latest bar
    pub fn get_latest_bar(&self) -> Option<FootprintBar> {
        self.bars
            .iter()
            .max_by_key(|r| *r.key())
            .map(|r| r.value().clone())
    }
}

/// Order flow metrics aggregator
#[derive(Debug)]
pub struct OrderFlowMetrics {
    cvd: CvdAccumulator,
    volume_profile: VolumeProfile,
    footprint: FootprintBuilder,
    aggressive_buy_count: AtomicU64,
    aggressive_sell_count: AtomicU64,
}

impl OrderFlowMetrics {
    pub fn new() -> Self {
        Self {
            cvd: CvdAccumulator::new(),
            volume_profile: VolumeProfile::new(2), // 2 decimal precision
            footprint: FootprintBuilder::new(60000), // 1-minute bars
            aggressive_buy_count: AtomicU64::new(0),
            aggressive_sell_count: AtomicU64::new(0),
        }
    }

    /// Process a single trade
    pub fn process_trade(&self, trade: &TradeData) {
        self.cvd.add_trade(trade);
        self.volume_profile.add_trade(trade);
        self.footprint.add_trade(trade);

        if trade.is_buyer_maker {
            self.aggressive_sell_count.fetch_add(1, Ordering::Relaxed);
        } else {
            self.aggressive_buy_count.fetch_add(1, Ordering::Relaxed);
        }
    }

    /// Get current CVD
    pub fn get_cvd(&self) -> i64 {
        self.cvd.get_cvd()
    }

    /// Get volume profile POC
    pub fn get_poc(&self) -> Option<VolumeBucket> {
        self.volume_profile.get_poc()
    }

    /// Get value area
    pub fn get_value_area(&self) -> Option<(Decimal, Decimal)> {
        self.volume_profile.get_value_area()
    }

    /// Get footprint bars
    pub fn get_footprint_bars(&self) -> Vec<FootprintBar> {
        self.footprint.get_bars()
    }

    /// Get trade count imbalance
    pub fn get_trade_imbalance(&self) -> f64 {
        let buys = self.aggressive_buy_count.load(Ordering::Relaxed) as f64;
        let sells = self.aggressive_sell_count.load(Ordering::Relaxed) as f64;
        let total = buys + sells;
        
        if total > 0.0 {
            buys / total
        } else {
            0.5
        }
    }

    /// Reset all metrics
    pub fn reset(&self) {
        self.cvd.reset(0);
        self.volume_profile.clear();
        self.footprint.bars.clear();
        self.footprint.levels_per_bar.clear();
        self.aggressive_buy_count.store(0, Ordering::Relaxed);
        self.aggressive_sell_count.store(0, Ordering::Relaxed);
    }
}

impl Default for OrderFlowMetrics {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cvd_accumulator() {
        let cvd = CvdAccumulator::new();
        
        let buy_trade = TradeData {
            symbol: "BTCUSDT".to_string(),
            trade_id: 1,
            price: Decimal::from_f64_retain(50000.0).unwrap(),
            quantity: Decimal::from_f64_retain(1.0).unwrap(),
            is_buyer_maker: false, // Aggressive buy
            timestamp: 1234567890,
        };

        let sell_trade = TradeData {
            symbol: "BTCUSDT".to_string(),
            trade_id: 2,
            price: Decimal::from_f64_retain(50000.0).unwrap(),
            quantity: Decimal::from_f64_retain(0.5).unwrap(),
            is_buyer_maker: true, // Aggressive sell
            timestamp: 1234567891,
        };

        cvd.add_trade(&buy_trade);
        assert_eq!(cvd.get_cvd(), 10000); // 1.0 * 10000

        cvd.add_trade(&sell_trade);
        assert_eq!(cvd.get_cvd(), 5000); // (1.0 - 0.5) * 10000
    }

    #[test]
    fn test_volume_profile() {
        let vp = VolumeProfile::new(2);
        
        let trade1 = TradeData {
            symbol: "BTCUSDT".to_string(),
            trade_id: 1,
            price: Decimal::from_f64_retain(50000.0).unwrap(),
            quantity: Decimal::from_f64_retain(2.0).unwrap(),
            is_buyer_maker: false,
            timestamp: 1234567890,
        };

        let trade2 = TradeData {
            symbol: "BTCUSDT".to_string(),
            trade_id: 2,
            price: Decimal::from_f64_retain(50000.0).unwrap(),
            quantity: Decimal::from_f64_retain(3.0).unwrap(),
            is_buyer_maker: true,
            timestamp: 1234567891,
        };

        vp.add_trade(&trade1);
        vp.add_trade(&trade2);

        let poc = vp.get_poc().unwrap();
        assert_eq!(poc.price, Decimal::from_f64_retain(50000.0).unwrap());
        assert_eq!(poc.total_volume(), Decimal::from_f64_retain(5.0).unwrap());
    }
}
