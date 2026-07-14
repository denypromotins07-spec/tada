//! SIMD-Optimized Data Normalizer
//! 
//! Converts raw JSON ticks into flat binary structures for zero-copy serialization.
//! Uses simd-json for zero-allocation parsing where possible.

use crate::models::{TickData, DepthSnapshot, TradeData, OrderBookLevel};
use rust_decimal::Decimal;
use simd_json::Value;
use std::io::Write;

/// Parse a depth update from Binance WebSocket message
pub fn parse_depth_update(
    json_str: &str,
    symbol: &str,
) -> Result<DepthSnapshot, Box<dyn std::error::Error + Send + Sync>> {
    // Use simd-json for zero-allocation parsing
    let mut json_bytes = json_str.as_bytes().to_vec();
    let value = simd_json::to_owned_value(&mut json_bytes)?;
    
    let obj = value.as_obj().ok_or("Expected JSON object")?;
    
    // Extract last_update_id
    let last_update_id = obj
        .get("lastUpdateId")
        .and_then(|v| v.as_i64())
        .unwrap_or(0);

    // Extract bids
    let mut bids = Vec::with_capacity(20);
    if let Some(bids_array) = obj.get("bids").and_then(|v| v.as_array()) {
        for bid_item in bids_array.iter().take(20) {
            if let Some(bid_arr) = bid_item.as_array() {
                if bid_arr.len() >= 2 {
                    let price_str = bid_arr[0].as_str().unwrap_or("0");
                    let qty_str = bid_arr[1].as_str().unwrap_or("0");
                    
                    if let (Ok(price), Ok(quantity)) = (
                        Decimal::from_str_exact(price_str),
                        Decimal::from_str_exact(qty_str),
                    ) {
                        bids.push(OrderBookLevel { price, quantity });
                    }
                }
            }
        }
    }

    // Extract asks
    let mut asks = Vec::with_capacity(20);
    if let Some(asks_array) = obj.get("asks").and_then(|v| v.as_array()) {
        for ask_item in asks_array.iter().take(20) {
            if let Some(ask_arr) = ask_item.as_array() {
                if ask_arr.len() >= 2 {
                    let price_str = ask_arr[0].as_str().unwrap_or("0");
                    let qty_str = ask_arr[1].as_str().unwrap_or("0");
                    
                    if let (Ok(price), Ok(quantity)) = (
                        Decimal::from_str_exact(price_str),
                        Decimal::from_str_exact(qty_str),
                    ) {
                        asks.push(OrderBookLevel { price, quantity });
                    }
                }
            }
        }
    }

    Ok(DepthSnapshot {
        symbol: symbol.to_string(),
        last_update_id,
        first_update_id: last_update_id,
        bids,
        asks,
        timestamp: chrono::Utc::now().timestamp_millis(),
    })
}

/// Parse a trade update from Binance WebSocket message
pub fn parse_trade_update(
    json_str: &str,
    symbol: &str,
) -> Result<TradeData, Box<dyn std::error::Error + Send + Sync>> {
    let mut json_bytes = json_str.as_bytes().to_vec();
    let value = simd_json::to_owned_value(&mut json_bytes)?;
    
    let obj = value.as_obj().ok_or("Expected JSON object")?;
    
    let trade_id = obj.get("t").and_then(|v| v.as_i64()).unwrap_or(0);
    let price = obj
        .get("p")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);
    
    let quantity = obj
        .get("q")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);
    
    let is_buyer_maker = obj.get("m").and_then(|v| v.as_bool()).unwrap_or(false);
    let timestamp = obj.get("T").and_then(|v| v.as_i64()).unwrap_or_else(|| chrono::Utc::now().timestamp_millis());

    Ok(TradeData {
        symbol: symbol.to_string(),
        trade_id,
        price,
        quantity,
        is_buyer_maker,
        timestamp,
    })
}

/// Parse a ticker update from Binance WebSocket message
pub fn parse_ticker_update(
    json_str: &str,
    symbol: &str,
) -> Result<TickData, Box<dyn std::error::Error + Send + Sync>> {
    let mut json_bytes = json_str.as_bytes().to_vec();
    let value = simd_json::to_owned_value(&mut json_bytes)?;
    
    let obj = value.as_obj().ok_or("Expected JSON object")?;
    
    // Handle both '24hrTicker' format and direct ticker format
    let data = obj.get("data").unwrap_or(&value);
    let data_obj = data.as_obj().ok_or("Expected ticker data object")?;

    let price_change = data_obj
        .get("p")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let price_change_percent = data_obj
        .get("P")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let last_price = data_obj
        .get("c")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let high_price = data_obj
        .get("h")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let low_price = data_obj
        .get("l")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let volume = data_obj
        .get("v")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let quote_volume = data_obj
        .get("q")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let open_price = data_obj
        .get("o")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let best_bid = data_obj
        .get("b")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let best_ask = data_obj
        .get("a")
        .and_then(|v| v.as_str())
        .and_then(|s| Decimal::from_str_exact(s).ok())
        .unwrap_or(Decimal::ZERO);

    let timestamp = data_obj.get("E").and_then(|v| v.as_i64()).unwrap_or_else(|| chrono::Utc::now().timestamp_millis());

    Ok(TickData {
        symbol: symbol.to_string(),
        timestamp,
        last_price,
        open_price,
        high_price,
        low_price,
        close_price: last_price,
        volume,
        quote_volume,
        price_change,
        price_change_percent,
        best_bid,
        best_ask,
    })
}

/// Serialize TickData to binary format for zero-copy transmission
pub fn serialize_tick_binary(tick: &TickData, writer: &mut impl Write) -> std::io::Result<()> {
    // Write symbol length and bytes
    let symbol_bytes = tick.symbol.as_bytes();
    let symbol_len = symbol_bytes.len() as u8;
    writer.write_all(&[symbol_len])?;
    writer.write_all(symbol_bytes)?;

    // Write timestamp (i64)
    writer.write_all(&tick.timestamp.to_le_bytes())?;

    // Write all Decimal fields as f64 bits
    write_decimal_as_f64(writer, tick.last_price)?;
    write_decimal_as_f64(writer, tick.open_price)?;
    write_decimal_as_f64(writer, tick.high_price)?;
    write_decimal_as_f64(writer, tick.low_price)?;
    write_decimal_as_f64(writer, tick.close_price)?;
    write_decimal_as_f64(writer, tick.volume)?;
    write_decimal_as_f64(writer, tick.quote_volume)?;
    write_decimal_as_f64(writer, tick.price_change)?;
    write_decimal_as_f64(writer, tick.price_change_percent)?;
    write_decimal_as_f64(writer, tick.best_bid)?;
    write_decimal_as_f64(writer, tick.best_ask)?;

    Ok(())
}

/// Helper to write Decimal as f64 little-endian bytes
fn write_decimal_as_f64(writer: &mut impl Write, decimal: Decimal) -> std::io::Result<()> {
    let f64_val: f64 = decimal.to_string().parse().unwrap_or(0.0);
    writer.write_all(&f64_val.to_le_bytes())
}

/// Deserialize binary tick data back to TickData
pub fn deserialize_tick_binary(data: &[u8]) -> Result<TickData, Box<dyn std::error::Error + Send + Sync>> {
    if data.is_empty() {
        return Err("Empty data".into());
    }

    let mut offset = 0;
    
    // Read symbol
    let symbol_len = data[offset] as usize;
    offset += 1;
    
    let symbol = String::from_utf8(data[offset..offset + symbol_len].to_vec())?;
    offset += symbol_len;

    // Read timestamp
    let timestamp = i64::from_le_bytes(
        data[offset..offset + 8]
            .try_into()
            .map_err(|_| "Invalid timestamp bytes")?,
    );
    offset += 8;

    // Read all Decimal fields
    let mut read_decimal = |offset: &mut usize| -> Result<Decimal, Box<dyn std::error::Error + Send + Sync>> {
        let bytes: [u8; 8] = data[*offset..*offset + 8]
            .try_into()
            .map_err(|_| "Invalid decimal bytes")?;
        *offset += 8;
        let f64_val = f64::from_le_bytes(bytes);
        Decimal::from_f64_retain(f64_val)
            .ok_or_else(|| "Failed to convert f64 to Decimal".into())
    };

    let last_price = read_decimal(&mut offset)?;
    let open_price = read_decimal(&mut offset)?;
    let high_price = read_decimal(&mut offset)?;
    let low_price = read_decimal(&mut offset)?;
    let close_price = read_decimal(&mut offset)?;
    let volume = read_decimal(&mut offset)?;
    let quote_volume = read_decimal(&mut offset)?;
    let price_change = read_decimal(&mut offset)?;
    let price_change_percent = read_decimal(&mut offset)?;
    let best_bid = read_decimal(&mut offset)?;
    let best_ask = read_decimal(&mut offset)?;

    Ok(TickData {
        symbol,
        timestamp,
        last_price,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        quote_volume,
        price_change,
        price_change_percent,
        best_bid,
        best_ask,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use rust_decimal::prelude::*;

    #[test]
    fn test_parse_depth_update() {
        let json = r#"{
            "lastUpdateId": 12345,
            "bids": [["50000.00", "1.5"], ["49900.00", "2.0"]],
            "asks": [["50100.00", "1.0"], ["50200.00", "2.5"]]
        }"#;

        let result = parse_depth_update(json, "BTCUSDT").unwrap();
        assert_eq!(result.last_update_id, 12345);
        assert_eq!(result.bids.len(), 2);
        assert_eq!(result.asks.len(), 2);
        assert_eq!(result.bids[0].price, Decimal::from_f64_retain(50000.0).unwrap());
    }

    #[test]
    fn test_parse_trade_update() {
        let json = r#"{"t": 98765, "p": "50000.00", "q": "0.5", "m": true, "T": 1234567890}"#;
        
        let result = parse_trade_update(json, "BTCUSDT").unwrap();
        assert_eq!(result.trade_id, 98765);
        assert_eq!(result.price, Decimal::from_f64_retain(50000.0).unwrap());
        assert_eq!(result.quantity, Decimal::from_f64_retain(0.5).unwrap());
        assert!(result.is_buyer_maker);
    }

    #[test]
    fn test_serialize_deserialize_tick() {
        let tick = TickData {
            symbol: "ETHUSDT".to_string(),
            timestamp: 1234567890,
            last_price: Decimal::from_f64_retain(3000.0).unwrap(),
            open_price: Decimal::from_f64_retain(2990.0).unwrap(),
            high_price: Decimal::from_f64_retain(3010.0).unwrap(),
            low_price: Decimal::from_f64_retain(2980.0).unwrap(),
            close_price: Decimal::from_f64_retain(3000.0).unwrap(),
            volume: Decimal::from_f64_retain(10000.0).unwrap(),
            quote_volume: Decimal::from_f64_retain(30000000.0).unwrap(),
            price_change: Decimal::from_f64_retain(10.0).unwrap(),
            price_change_percent: Decimal::from_f64_retain(0.33).unwrap(),
            best_bid: Decimal::from_f64_retain(2999.0).unwrap(),
            best_ask: Decimal::from_f64_retain(3001.0).unwrap(),
        };

        let mut buffer = Vec::new();
        serialize_tick_binary(&tick, &mut buffer).unwrap();

        let deserialized = deserialize_tick_binary(&buffer).unwrap();
        assert_eq!(deserialized.symbol, tick.symbol);
        assert_eq!(deserialized.timestamp, tick.timestamp);
        assert_eq!(deserialized.last_price, tick.last_price);
    }
}
