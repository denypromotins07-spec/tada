//! Engine configuration

use serde::{Deserialize, Serialize};
use std::path::Path;

/// Engine configuration loaded from environment or config file
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EngineConfig {
    pub binance_ws_url: String,
    pub binance_rest_url: String,
    pub symbols: Vec<String>,
    pub api_key: Option<String>,
    pub api_secret: Option<String>,
    pub testnet: bool,
    pub log_level: String,
}

impl EngineConfig {
    pub fn load() -> Result<Self, ConfigError> {
        // Try to load from .env file using dotenv
        dotenv::dotenv().ok();

        let config = EngineConfig {
            binance_ws_url: std::env::var("BINANCE_WS_URL")
                .unwrap_or_else(|_| "wss://stream.binance.com:9443/ws".to_string()),
            binance_rest_url: std::env::var("BINANCE_REST_URL")
                .unwrap_or_else(|_| "https://api.binance.com".to_string()),
            symbols: std::env::var("DEFAULT_SYMBOL")
                .unwrap_or_else(|_| "BTCUSDT".to_string())
                .split(',')
                .map(|s| s.trim().to_string())
                .collect(),
            api_key: std::env::var("BINANCE_API_KEY").ok(),
            api_secret: std::env::var("BINANCE_API_SECRET").ok(),
            testnet: std::env::var("BINANCE_TESTNET")
                .unwrap_or_else(|_| "true".to_string())
                .parse()
                .unwrap_or(true),
            log_level: std::env::var("LOG_LEVEL")
                .unwrap_or_else(|_| "info".to_string()),
        };

        Ok(config)
    }

    pub fn is_testnet(&self) -> bool {
        self.testnet
    }
}

/// Configuration error types
#[derive(Debug, thiserror::Error)]
pub enum ConfigError {
    #[error("Failed to load configuration: {0}")]
    LoadError(String),
    #[error("Invalid configuration value: {0}")]
    InvalidValue(String),
}

// Helper for dotenv
mod dotenv {
    pub fn dotenv() -> Result<(), ()> {
        // Simple dotenv loader placeholder
        // In production, use the actual dotenv crate
        Ok(())
    }
}
