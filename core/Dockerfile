# =============================================================================
# HFT Rust Core - Dockerfile
# =============================================================================
# Multi-stage build for minimal production image
# Optimized for low latency and small footprint
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 1: Builder
# -----------------------------------------------------------------------------
FROM rust:1.75-bookworm AS builder

# Install dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    cmake \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy manifest files first for better caching
COPY Cargo.toml Cargo.lock* ./

# Create dummy source to build dependencies
RUN mkdir -p src && echo "fn main() {}" > src/main.rs && \
    for mod in exchange execution orderbook metrics; do \
        mkdir -p src/$mod && echo "" > src/$mod/mod.rs; \
    done && \
    cargo build --release && \
    rm -rf src

# Copy actual source code
COPY . .

# Build in release mode with all optimizations
RUN cargo build --release --locked

# -----------------------------------------------------------------------------
# STAGE 2: Runtime
# -----------------------------------------------------------------------------
FROM debian:bookworm-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' appuser

# Set working directory
WORKDIR /app

# Copy binary from builder
COPY --from=builder /app/target/release/hft_core /app/hft_core

# Change ownership
RUN chown appuser:appuser /app/hft_core

# Switch to non-root user
USER appuser

# Set environment variables
ENV RUST_LOG=info
ENV BINANCE_WS_URL=wss://stream.binance.com:9443/ws
ENV REDIS_URL=redis://redis:6379

# Expose metrics port (if we add HTTP server later)
EXPOSE 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD pgrep hft_core || exit 1

# Run the binary
CMD ["/app/hft_core"]
