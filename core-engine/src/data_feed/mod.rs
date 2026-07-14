//! Real-Time Market Data Ingestion & Normalization Module
//! 
//! Orchestrates multiple WebSocket connections for Order Book, Trades, and Tickers.
//! Uses tokio-tungstenite for async WebSocket handling with exponential backoff.

pub mod orderbook;
pub mod normalizer;

use crate::config::Config;
use crate::models::{TickData, DepthSnapshot, TradeData};
use futures_util::{stream::SplitSink, SinkExt, StreamExt};
use tokio::net::TcpStream;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{info, warn, error, debug};
use std::time::Duration;
use std::sync::Arc;

/// Data feed types supported by the ingestion engine
#[derive(Debug, Clone, PartialEq)]
pub enum FeedType {
    OrderBook,
    Trades,
    Ticker,
}

/// Configuration for a single data stream
#[derive(Debug, Clone)]
pub struct StreamConfig {
    pub feed_type: FeedType,
    pub symbol: String,
    pub ws_url: String,
}

impl StreamConfig {
    pub fn new(feed_type: FeedType, symbol: &str, base_url: &str) -> Self {
        let stream_name = match feed_type {
            FeedType::OrderBook => format!("{}@depth20@100ms", symbol.to_lowercase()),
            FeedType::Trades => format!("{}@trade", symbol.to_lowercase()),
            FeedType::Ticker => format!("{}@ticker", symbol.to_lowercase()),
        };
        
        Self {
            feed_type,
            symbol: symbol.to_string(),
            ws_url: format!("{}/ws/{}", base_url, stream_name),
        }
    }
}

/// Main data feed manager handling multiple WebSocket connections
pub struct DataFeedManager {
    configs: Vec<StreamConfig>,
    tx_tick: mpsc::Sender<TickData>,
    tx_depth: mpsc::Sender<DepthSnapshot>,
    tx_trade: mpsc::Sender<TradeData>,
    shutdown: tokio::sync::broadcast::Receiver<()>,
}

impl DataFeedManager {
    pub fn new(
        configs: Vec<StreamConfig>,
        tx_tick: mpsc::Sender<TickData>,
        tx_depth: mpsc::Sender<DepthSnapshot>,
        tx_trade: mpsc::Sender<TradeData>,
        shutdown: tokio::sync::broadcast::Receiver<()>,
    ) -> Self {
        Self {
            configs,
            tx_tick,
            tx_depth,
            tx_trade,
            shutdown,
        }
    }

    /// Run all data feed streams concurrently
    pub async fn run(mut self) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let mut handles = Vec::new();

        for config in self.configs {
            let tx_tick = self.tx_tick.clone();
            let tx_depth = self.tx_depth.clone();
            let tx_trade = self.tx_trade.clone();
            let mut shutdown = self.shutdown.resubscribe();

            let handle = tokio::spawn(async move {
                let mut backoff = Duration::from_millis(100);
                let max_backoff = Duration::from_secs(30);

                loop {
                    tokio::select! {
                        _ = shutdown.recv() => {
                            info!("Shutting down stream for {}", config.symbol);
                            break Ok::<_, Box<dyn std::error::Error + Send + Sync>>(());
                        }
                        result = Self::run_stream(config.clone(), tx_tick.clone(), tx_depth.clone(), tx_trade.clone()) => {
                            match result {
                                Ok(_) => {
                                    warn!("Stream ended unexpectedly for {}, reconnecting...", config.symbol);
                                }
                                Err(e) => {
                                    error!("Stream error for {}: {}. Reconnecting in {:?}", config.symbol, e, backoff);
                                    tokio::time::sleep(backoff).await;
                                    backoff = std::cmp::min(backoff * 2, max_backoff);
                                }
                            }
                        }
                    }
                }
            });

            handles.push(handle);
        }

        // Wait for all streams to complete
        for handle in handles {
            if let Err(e) = handle.await {
                error!("Task join error: {}", e);
            }
        }

        Ok(())
    }

    /// Run a single WebSocket stream with automatic reconnection
    async fn run_stream(
        config: StreamConfig,
        tx_tick: mpsc::Sender<TickData>,
        tx_depth: mpsc::Sender<DepthSnapshot>,
        tx_trade: mpsc::Sender<TradeData>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        info!("Connecting to WebSocket: {}", config.ws_url);

        let (ws_stream, _) = connect_async(&config.ws_url).await?;
        let (mut write, mut read) = ws_stream.split();

        // Send ping periodically to keep connection alive
        let ping_interval = tokio::time::interval(Duration::from_secs(30));
        tokio::pin!(ping_interval);

        loop {
            tokio::select! {
                _ = ping_interval.tick() => {
                    let _ = write.send(Message::Ping(Vec::new())).await;
                }
                msg = read.next() => {
                    match msg {
                        Some(Ok(Message::Text(text))) => {
                            Self::process_message(&text, &config, &tx_tick, &tx_depth, &tx_trade).await?;
                        }
                        Some(Ok(Message::Binary(data))) => {
                            // Handle binary messages if needed
                            debug!("Received binary message: {} bytes", data.len());
                        }
                        Some(Ok(Message::Ping(data))) => {
                            let _ = write.send(Message::Pong(data)).await;
                        }
                        Some(Ok(Message::Pong(_))) => {
                            // Heartbeat received
                        }
                        Some(Ok(Message::Close(frame))) => {
                            warn!("WebSocket closed: {:?}", frame);
                            return Err("Connection closed".into());
                        }
                        Some(Err(e)) => {
                            return Err(Box::new(e));
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    /// Process incoming WebSocket message and route to appropriate channel
    async fn process_message(
        text: &str,
        config: &StreamConfig,
        tx_tick: &mpsc::Sender<TickData>,
        tx_depth: &mpsc::Sender<DepthSnapshot>,
        tx_trade: &mpsc::Sender<TradeData>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        match config.feed_type {
            FeedType::OrderBook => {
                // Parse order book update using simd-json for zero-allocation
                if let Ok(depth) = normalizer::parse_depth_update(text, &config.symbol) {
                    let _ = tx_depth.send(depth).await;
                }
            }
            FeedType::Trades => {
                if let Ok(trade) = normalizer::parse_trade_update(text, &config.symbol) {
                    let _ = tx_trade.send(trade).await;
                }
            }
            FeedType::Ticker => {
                if let Ok(tick) = normalizer::parse_ticker_update(text, &config.symbol) {
                    let _ = tx_tick.send(tick).await;
                }
            }
        }

        Ok(())
    }
}

/// Exponential backoff helper for reconnection logic
pub fn calculate_backoff(attempt: u32, base_ms: u64, max_ms: u64) -> Duration {
    let delay_ms = base_ms.saturating_mul(2u64.saturating_pow(attempt.min(10)));
    Duration::from_millis(delay_ms.min(max_ms))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_stream_config_generation() {
        let config = StreamConfig::new(FeedType::OrderBook, "BTCUSDT", "wss://stream.binance.com:9443");
        assert!(config.ws_url.contains("btcusdt@depth20@100ms"));
        
        let trade_config = StreamConfig::new(FeedType::Trades, "ETHUSDT", "wss://stream.binance.com:9443");
        assert!(trade_config.ws_url.contains("ethusdt@trade"));
    }

    #[test]
    fn test_exponential_backoff() {
        assert_eq!(calculate_backoff(0, 100, 30000), Duration::from_millis(100));
        assert_eq!(calculate_backoff(1, 100, 30000), Duration::from_millis(200));
        assert_eq!(calculate_backoff(5, 100, 30000), Duration::from_millis(3200));
        assert_eq!(calculate_backoff(20, 100, 30000), Duration::from_millis(30000));
    }
}
