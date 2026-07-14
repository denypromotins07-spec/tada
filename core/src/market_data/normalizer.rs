// /workspace/core/src/market_data/normalizer.rs
// =============================================================================
// MARKET DATA NORMALIZER - UNIFIED INTERNAL FORMAT
// =============================================================================
// This module standardizes incoming messages from different exchanges into a
// unified internal MarketDataEvent format. It handles:
// - Exchange-specific message parsing
// - Price/quantity normalization
// - Timestamp synchronization
// - Symbol mapping (exchange-specific to internal)
//
// Design Goals:
// - Zero-copy where possible
// - Minimal allocation on hot path
// - Extensible for multiple exchanges

use crate::market_data::orderbook::{MarketDataEvent, PriceLevel};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

/// Internal representation of an exchange identifier
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ExchangeId {
    Binance,
    Coinbase,
    Kraken,
    Ftx,
    Bybit,
    Okx,
    Unknown,
}

impl ExchangeId {
    pub fn from_str(s: &str) -> Self {
        match s.to_lowercase().as_str() {
            "binance" => Self::Binance,
            "coinbase" | "cb" => Self::Coinbase,
            "kraken" => Self::Kraken,
            "ftx" => Self::Ftx,
            "bybit" => Self::Bybit,
            "okx" => Self::Okx,
            _ => Self::Unknown,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Binance => "binance",
            Self::Coinbase => "coinbase",
            Self::Kraken => "kraken",
            Self::Ftx => "ftx",
            Self::Bybit => "bybit",
            Self::Okx => "okx",
            Self::Unknown => "unknown",
        }
    }
}

/// Normalized symbol (uppercase, standardized format)
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct NormalizedSymbol {
    /// Base asset (e.g., "BTC")
    pub base: String,
    /// Quote asset (e.g., "USDT")
    pub quote: String,
    /// Original exchange-specific symbol
    pub original: String,
    /// Exchange this symbol belongs to
    pub exchange: ExchangeId,
}

impl NormalizedSymbol {
    /// Create a normalized symbol from exchange-specific format
    pub fn new(original: &str, exchange: ExchangeId) -> Self {
        let (base, quote) = Self::parse_symbol(original, exchange);
        
        Self {
            base: base.to_uppercase(),
            quote: quote.to_uppercase(),
            original: original.to_string(),
            exchange,
        }
    }

    /// Parse symbol into base and quote components
    fn parse_symbol(symbol: &str, exchange: ExchangeId) -> (&str, &str) {
        match exchange {
            ExchangeId::Binance | ExchangeId::Bybit | ExchangeId::Okx => {
                // Format: BTCUSDT, ETHUSDC, etc.
                if symbol.ends_with("USDT") {
                    (&symbol[..symbol.len()-4], "USDT")
                } else if symbol.ends_with("USDC") {
                    (&symbol[..symbol.len()-4], "USDC")
                } else if symbol.ends_with("BUSD") {
                    (&symbol[..symbol.len()-4], "BUSD")
                } else if symbol.ends_with("BTC") {
                    (&symbol[..symbol.len()-3], "BTC")
                } else if symbol.ends_with("ETH") {
                    (&symbol[..symbol.len()-3], "ETH")
                } else {
                    // Default split heuristic
                    Self::heuristic_split(symbol)
                }
            }
            ExchangeId::Coinbase => {
                // Format: BTC-USD, ETH-USDT
                if let Some(idx) = symbol.find('-') {
                    (&symbol[..idx], &symbol[idx+1..])
                } else {
                    Self::heuristic_split(symbol)
                }
            }
            ExchangeId::Kraken => {
                // Format: XBT/USD, XXRP/EUR
                if let Some(idx) = symbol.find('/') {
                    (&symbol[..idx], &symbol[idx+1..])
                } else {
                    Self::heuristic_split(symbol)
                }
            }
            _ => Self::heuristic_split(symbol),
        }
    }

    /// Heuristic symbol splitting for unknown formats
    fn heuristic_split(symbol: &str) -> (&str, &str) {
        // Common quote assets
        let quotes = ["USDT", "USDC", "BUSD", "USD", "EUR", "GBP", "BTC", "ETH"];
        
        for quote in &quotes {
            if symbol.ends_with(quote) {
                return (&symbol[..symbol.len()-quote.len()], quote);
            }
        }
        
        // Default: assume last 3-4 chars are quote
        if symbol.len() > 6 {
            (&symbol[..symbol.len()-3], &symbol[symbol.len()-3..])
        } else {
            (symbol, "USD")
        }
    }

    /// Get combined symbol (e.g., "BTC/USDT")
    pub fn combined(&self) -> String {
        format!("{}/{}", self.base, self.quote)
    }

    /// Get internal key for storage/lookup
    pub fn key(&self) -> String {
        format!("{}_{}_{}", self.exchange.as_str(), self.base, self.quote)
    }
}

/// Unified market data event with nanosecond timestamps
#[derive(Debug, Clone)]
pub struct NormalizedMarketDataEvent {
    /// Event type
    pub event: NormalizedEvent,
    /// Exchange this event came from
    pub exchange: ExchangeId,
    /// Normalized symbol
    pub symbol: NormalizedSymbol,
    /// Exchange timestamp (nanoseconds since epoch)
    pub exchange_timestamp_ns: u64,
    /// Local receipt timestamp (nanoseconds since epoch)
    pub local_timestamp_ns: u64,
    /// Sequence number (if available)
    pub sequence: Option<u64>,
}

/// Normalized event types
#[derive(Debug, Clone)]
pub enum NormalizedEvent {
    /// Order book snapshot
    Snapshot {
        bids: Vec<NormalizedPriceLevel>,
        asks: Vec<NormalizedPriceLevel>,
    },
    /// Order book delta update
    Delta {
        price: i64,
        quantity: f64,
        order_count: u32,
        is_bid: bool,
    },
    /// Trade execution
    Trade {
        price: i64,
        quantity: f64,
        is_buyer_maker: bool,
        trade_id: u64,
    },
    /// Ticker update
    Ticker {
        best_bid: Option<i64>,
        best_ask: Option<i64>,
        last_price: Option<i64>,
        volume_24h: Option<f64>,
    },
}

/// Normalized price level
#[derive(Debug, Clone)]
pub struct NormalizedPriceLevel {
    /// Price (scaled integer, 8 decimal places)
    pub price: i64,
    /// Quantity
    pub quantity: f64,
    /// Order count (if available)
    pub order_count: Option<u32>,
}

impl NormalizedPriceLevel {
    pub fn new(price: i64, quantity: f64) -> Self {
        Self {
            price,
            quantity,
            order_count: None,
        }
    }

    pub fn with_order_count(price: i64, quantity: f64, order_count: u32) -> Self {
        Self {
            price,
            quantity,
            order_count: Some(order_count),
        }
    }
}

/// Market data normalizer - converts exchange-specific messages to unified format
pub struct MarketDataNormalizer {
    /// Symbol mappings (exchange symbol -> normalized symbol)
    symbol_cache: dashmap::DashMap<String, NormalizedSymbol>,
    /// Price scaling factors per symbol (for exchanges with different precision)
    price_scales: dashmap::DashMap<String, u32>,
    /// Quantity scaling factors per symbol
    qty_scales: dashmap::DashMap<String, u32>,
}

impl MarketDataNormalizer {
    pub fn new() -> Self {
        Self {
            symbol_cache: dashmap::DashMap::with_shard_amount(32),
            price_scales: dashmap::DashMap::with_shard_amount(32),
            qty_scales: dashmap::DashMap::with_shard_amount(32),
        }
    }

    /// Get current timestamp in nanoseconds
    #[inline]
    pub fn get_timestamp_ns() -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos() as u64
    }

    /// Register a symbol with custom scaling factors
    pub fn register_symbol(
        &self,
        exchange: ExchangeId,
        original_symbol: &str,
        price_scale: u32,
        qty_scale: u32,
    ) -> NormalizedSymbol {
        let normalized = NormalizedSymbol::new(original_symbol, exchange);
        let key = normalized.key();
        
        self.symbol_cache.insert(key.clone(), normalized.clone());
        self.price_scales.insert(key.clone(), price_scale);
        self.qty_scales.insert(key, qty_scale);
        
        normalized
    }

    /// Normalize a price value based on symbol
    #[inline]
    pub fn normalize_price(&self, symbol: &NormalizedSymbol, price: f64) -> i64 {
        let key = symbol.key();
        let scale = self.price_scales.get(&key).map(|r| *r).unwrap_or(8);
        (price * 10f64.powi(scale as i32)) as i64
    }

    /// Normalize a quantity value based on symbol
    #[inline]
    pub fn normalize_quantity(&self, symbol: &NormalizedSymbol, quantity: f64) -> f64 {
        let key = symbol.key();
        let scale = self.qty_scales.get(&key).map(|r| *r).unwrap_or(8);
        quantity * 10f64.powi(-(scale as i32))
    }

    /// Convert normalized event to internal MarketDataEvent
    pub fn to_internal_event(&self, normalized: &NormalizedMarketDataEvent) -> Option<MarketDataEvent> {
        match &normalized.event {
            NormalizedEvent::Snapshot { bids, asks } => {
                let internal_bids: Vec<PriceLevel> = bids.iter().map(|b| {
                    PriceLevel {
                        price: b.price,
                        quantity: b.quantity,
                        order_count: b.order_count.unwrap_or(1),
                        last_update_us: normalized.exchange_timestamp_ns / 1000,
                    }
                }).collect();
                
                let internal_asks: Vec<PriceLevel> = asks.iter().map(|a| {
                    PriceLevel {
                        price: a.price,
                        quantity: a.quantity,
                        order_count: a.order_count.unwrap_or(1),
                        last_update_us: normalized.exchange_timestamp_ns / 1000,
                    }
                }).collect();
                
                Some(MarketDataEvent::Snapshot {
                    bids: internal_bids,
                    asks: internal_asks,
                    sequence: normalized.sequence.unwrap_or(0),
                    timestamp_us: normalized.local_timestamp_ns / 1000,
                })
            }
            NormalizedEvent::Delta { price, quantity, order_count, is_bid } => {
                Some(MarketDataEvent::Delta {
                    price: *price,
                    quantity: *quantity,
                    order_count: *order_count,
                    is_bid: *is_bid,
                    sequence: normalized.sequence.unwrap_or(0),
                    timestamp_us: normalized.local_timestamp_ns / 1000,
                })
            }
            NormalizedEvent::Trade { price, quantity, is_buyer_maker, trade_id } => {
                Some(MarketDataEvent::Trade {
                    price: *price,
                    quantity: *quantity,
                    is_buyer_maker: *is_buyer_maker,
                    trade_id: *trade_id,
                    timestamp_us: normalized.local_timestamp_ns / 1000,
                })
            }
            NormalizedEvent::Ticker { .. } => None, // Tickers handled separately
        }
    }

    /// Calculate latency between exchange and local receipt
    #[inline]
    pub fn calculate_latency_ns(&self, event: &NormalizedMarketDataEvent) -> u64 {
        event.local_timestamp_ns.saturating_sub(event.exchange_timestamp_ns)
    }

    /// Get or create normalized symbol
    pub fn get_or_create_symbol(&self, exchange: ExchangeId, original: &str) -> NormalizedSymbol {
        let key = format!("{}_{}", exchange.as_str(), original);
        
        if let Some(cached) = self.symbol_cache.get(&key) {
            cached.clone()
        } else {
            let normalized = NormalizedSymbol::new(original, exchange);
            self.symbol_cache.insert(key, normalized.clone());
            normalized
        }
    }
}

impl Default for MarketDataNormalizer {
    fn default() -> Self {
        Self::new()
    }
}

/// Builder for creating normalized events
pub struct NormalizedEventBuilder {
    exchange: ExchangeId,
    symbol: NormalizedSymbol,
    exchange_timestamp_ns: u64,
    local_timestamp_ns: u64,
    sequence: Option<u64>,
}

impl NormalizedEventBuilder {
    pub fn new(exchange: ExchangeId, symbol: &str) -> Self {
        let normalized = NormalizedSymbol::new(symbol, exchange);
        let now = MarketDataNormalizer::get_timestamp_ns();
        
        Self {
            exchange,
            symbol: normalized,
            exchange_timestamp_ns: now,
            local_timestamp_ns: now,
            sequence: None,
        }
    }

    pub fn exchange_timestamp(mut self, ts_ns: u64) -> Self {
        self.exchange_timestamp_ns = ts_ns;
        self
    }

    pub fn local_timestamp(mut self, ts_ns: u64) -> Self {
        self.local_timestamp_ns = ts_ns;
        self
    }

    pub fn sequence(mut self, seq: u64) -> Self {
        self.sequence = Some(seq);
        self
    }

    pub fn snapshot(self, bids: Vec<NormalizedPriceLevel>, asks: Vec<NormalizedPriceLevel>) -> NormalizedMarketDataEvent {
        NormalizedMarketDataEvent {
            event: NormalizedEvent::Snapshot { bids, asks },
            exchange: self.exchange,
            symbol: self.symbol,
            exchange_timestamp_ns: self.exchange_timestamp_ns,
            local_timestamp_ns: self.local_timestamp_ns,
            sequence: self.sequence,
        }
    }

    pub fn delta(self, price: i64, quantity: f64, order_count: u32, is_bid: bool) -> NormalizedMarketDataEvent {
        NormalizedMarketDataEvent {
            event: NormalizedEvent::Delta { price, quantity, order_count, is_bid },
            exchange: self.exchange,
            symbol: self.symbol,
            exchange_timestamp_ns: self.exchange_timestamp_ns,
            local_timestamp_ns: self.local_timestamp_ns,
            sequence: self.sequence,
        }
    }

    pub fn trade(self, price: i64, quantity: f64, is_buyer_maker: bool, trade_id: u64) -> NormalizedMarketDataEvent {
        NormalizedMarketDataEvent {
            event: NormalizedEvent::Trade { price, quantity, is_buyer_maker, trade_id },
            exchange: self.exchange,
            symbol: self.symbol,
            exchange_timestamp_ns: self.exchange_timestamp_ns,
            local_timestamp_ns: self.local_timestamp_ns,
            sequence: self.sequence,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exchange_id_parsing() {
        assert_eq!(ExchangeId::from_str("binance"), ExchangeId::Binance);
        assert_eq!(ExchangeId::from_str("BINANCE"), ExchangeId::Binance);
        assert_eq!(ExchangeId::from_str("coinbase"), ExchangeId::Coinbase);
        assert_eq!(ExchangeId::from_str("cb"), ExchangeId::Coinbase);
        assert_eq!(ExchangeId::from_str("unknown_exchange"), ExchangeId::Unknown);
    }

    #[test]
    fn test_symbol_normalization_binance() {
        let sym = NormalizedSymbol::new("BTCUSDT", ExchangeId::Binance);
        assert_eq!(sym.base, "BTC");
        assert_eq!(sym.quote, "USDT");
        assert_eq!(sym.combined(), "BTC/USDT");
    }

    #[test]
    fn test_symbol_normalization_coinbase() {
        let sym = NormalizedSymbol::new("BTC-USD", ExchangeId::Coinbase);
        assert_eq!(sym.base, "BTC");
        assert_eq!(sym.quote, "USD");
    }

    #[test]
    fn test_symbol_normalization_kraken() {
        let sym = NormalizedSymbol::new("XBT/USD", ExchangeId::Kraken);
        assert_eq!(sym.base, "XBT");
        assert_eq!(sym.quote, "USD");
    }

    #[test]
    fn test_normalizer_creation() {
        let normalizer = MarketDataNormalizer::new();
        
        let sym = normalizer.register_symbol(
            ExchangeId::Binance,
            "BTCUSDT",
            8, // price scale
            8, // qty scale
        );
        
        assert_eq!(sym.base, "BTC");
        assert_eq!(sym.quote, "USDT");
        
        let normalized_price = normalizer.normalize_price(&sym, 50000.0);
        assert_eq!(normalized_price, 5_000_000_000_000i64);
    }

    #[test]
    fn test_event_builder() {
        let builder = NormalizedEventBuilder::new(ExchangeId::Binance, "BTCUSDT")
            .sequence(12345);
        
        let bids = vec![NormalizedPriceLevel::new(50000_00000000i64, 1.5)];
        let asks = vec![NormalizedPriceLevel::new(50100_00000000i64, 2.0)];
        
        let event = builder.snapshot(bids, asks);
        
        assert_eq!(event.sequence, Some(12345));
        assert_eq!(event.symbol.base, "BTC");
        
        if let NormalizedEvent::Snapshot { bids, asks } = event.event {
            assert_eq!(bids.len(), 1);
            assert_eq!(asks.len(), 1);
        } else {
            panic!("Expected Snapshot event");
        }
    }
}
