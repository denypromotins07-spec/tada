# 🚀 HFT Quant Trading System

> **Elite High-Frequency Trading (HFT) Quant Developer & Systems Architecture**  
> Fully automated, microsecond-latency crypto trading bot for AMD Ryzen AI 5 laptops

![Rust](https://img.shields.io/badge/Rust-1.70+-orange.svg)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)
![Ray](https://img.shields.io/badge/Ray-2.7+-red.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Hardware Requirements](#hardware-requirements)
- [System Components](#system-components)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Development](#development)
- [Performance Optimization](#performance-optimization)
- [Risk Management](#risk-management)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## 🎯 Overview

This is a production-ready, ultra-low-latency cryptocurrency trading system designed specifically for **AMD Ryzen AI 5 laptops with 16GB RAM**. The entire stack is containerized with strict memory boundaries (max 14GB RAM allocation) to ensure host OS stability.

### Key Features

- ⚡ **Microsecond Latency**: Rust-based execution core with zero-copy networking
- 🧠 **ML-Powered Strategies**: Ray-distributed regime detection using Hidden Markov Models
- 📊 **Real-Time Visualization**: Stunning Next.js dashboard with WebGL footprint charts
- 🗄️ **High-Performance Storage**: QuestDB for tick data, Redis for sub-millisecond pub/sub
- 🛡️ **Memory Safety**: Hard memory limits and OOM protection for all services
- 🎨 **AMD GPU/NPU Acceleration**: ROCm support for Radeon graphics, VitisAI for Ryzen AI

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HOST OS (AMD Ryzen AI 5)                      │
│                         16GB RAM Total                           │
│                     Reserved: 2GB for OS                         │
│                   Available: 14GB for Services                   │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────┐
│   QuestDB     │   │    Redis        │   │   Frontend    │
│   4GB Limit   │   │   1GB Limit     │   │   1GB Limit   │
│  Tick Storage │   │  Pub/Sub State  │   │  Next.js UI   │
└───────────────┘   └─────────────────┘   └───────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                           │
        ▼                                           ▼
┌───────────────────┐                   ┌───────────────────┐
│    Rust Core      │                   │   Ray Cluster     │
│   2GB Limit       │                   │   6GB Limit       │
│  Microsecond      │◄───────►          │  Strategy Engine  │
│  Execution        │  Shared Memory    │  ML Inference     │
└───────────────────┘                   └───────────────────┘
```

### Memory Allocation Breakdown

| Service     | Memory Limit | Purpose                          |
|-------------|--------------|----------------------------------|
| QuestDB     | 4GB          | Time-series tick storage         |
| Redis       | 1GB          | Sub-millisecond state sync       |
| Rust Core   | 2GB          | Order book reconstruction, routing |
| Ray Head    | 4GB          | Strategy orchestration           |
| Ray Worker  | 2GB          | Parallel ML inference            |
| Frontend    | 1GB          | Real-time dashboard              |
| **Total**   | **14GB**     | **Host OS reserved: 2GB**        |

---

## 💻 Hardware Requirements

### Minimum Requirements

- **CPU**: AMD Ryzen AI 5 (6 cores / 12 threads) or equivalent
- **RAM**: 16GB DDR4/DDR5
- **Storage**: 100GB NVMe SSD (for QuestDB WAL and logs)
- **GPU**: AMD Radeon Graphics (ROCm support) - optional but recommended
- **NPU**: AMD Ryzen AI NPU (VitisAI) - optional for ML acceleration
- **OS**: Linux (Ubuntu 22.04+ recommended) or WSL2 on Windows

### Recommended Network

- **Latency**: <10ms to Binance servers (use AWS Tokyo/Virginia for colocation)
- **Bandwidth**: 100Mbps+ stable connection
- **Backup**: Secondary internet connection for failover

---

## 🔧 System Components

### 1. Rust Core (`/core`)

The heart of the execution engine, written in Rust for maximum performance:

- **Tokio Runtime**: Async runtime with real-time thread priorities
- **CPU Pinning**: Binds critical threads to specific AMD cores
- **Zero-Copy Networking**: `io_uring` / optimized `epoll` for WebSocket feeds
- **Lock-Free Data Structures**: `crossbeam` and `dashmap` for concurrent access
- **Smart Order Router**: TWAP/VWAP algorithms with slippage modeling

**Key Files:**
- `src/main.rs` - Tokio runtime setup with CPU pinning
- `src/exchange/binance/mod.rs` - Binance WebSocket connector
- `src/execution/router.rs` - Lock-free Smart Order Router

### 2. Python Strategy Engine (`/strategies`)

Nautilus Trader integration with Ray-distributed ML:

- **Nautilus Kernel**: Event-driven backtesting and live trading loop
- **Ray Actors**: Parallel regime detection using Hidden Markov Models
- **ONNX Runtime**: AMD GPU/NPU accelerated model inference
- **GARCH Volatility**: Real-time volatility modeling
- **Monte Carlo Simulations**: Walk-forward testing without blocking

**Key Files:**
- `src/main.py` - Nautilus kernel initialization
- `src/nautilus_adapter.py` - Rust ↔ Nautilus bridge
- `src/ray_cluster.py` - Ray actor definitions

### 3. Database Layer (`/infra`)

High-performance storage for millions of ticks:

- **QuestDB**: SIMD-optimized time-series database
  - Append-only architecture
  - InfluxDB Line Protocol ingestion
  - Optimal partitioning by symbol and date
- **Redis**: In-memory pub/sub for state synchronization
  - `volatile-lru` eviction policy
  - No persistence (purely in-memory)

### 4. Frontend Dashboard (`/frontend`)

Stunning real-time visualization:

- **Next.js 14**: App Router with server components
- **Tailwind CSS**: Glassmorphism UI aesthetics
- **Framer Motion**: Smooth animations
- **Lightweight Charts**: TradingView-grade charting
- **WebGL/Three.js**: 3D footprint charts and order book heatmaps
- **WebSocket Client**: Direct Redis pub/sub subscription

---

## 🚀 Quick Start

### Prerequisites

```bash
# Install Docker and Docker Compose
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Rust (for local development)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install Node.js 18+
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install Python 3.10+
sudo apt-get install python3.10 python3.10-venv python3-pip
```

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/hft-quant-trading.git
cd hft-quant-trading

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
nano .env
```

### Build and Run

```bash
# Build all services (first time ~10 minutes)
make build

# Start all services
make up

# View logs
make logs

# Initialize database tables
make db-init
```

### Access Services

| Service     | URL                      | Credentials               |
|-------------|--------------------------|---------------------------|
| Frontend    | http://localhost:3000    | None (local)              |
| QuestDB     | http://localhost:9003    | admin / quest             |
| Ray Dashboard | http://localhost:8265  | None (local)              |
| Redis       | localhost:6379           | Set in `.env`             |

---

## ⚙️ Configuration

### Environment Variables

See `.env.example` for all available options:

```bash
# Critical variables to configure:
BINANCE_API_KEY=your_key_here
BINANCE_API_SECRET=your_secret_here
BINANCE_TESTNET=true  # ALWAYS start with testnet!

REDIS_PASSWORD=strong_password_here

# Risk limits (DO NOT exceed these on laptop hardware)
MAX_POSITION_SIZE_USD=10000
MAX_DAILY_LOSS_USD=500
```

### CPU Pinning

The Rust core is pinned to cores 0-3 by default. Adjust in `.env`:

```bash
CPU_AFFINITY=0-3  # First 4 cores for Rust
RT_PRIORITY=99    # Maximum real-time priority
```

### GPU Acceleration

Enable AMD Radeon GPU for ML inference:

```bash
ONNXRUNTIME_PROVIDERS=rocm  # For Radeon
# OR
ONNXRUNTIME_PROVIDERS=vitisai  # For Ryzen AI NPU
```

---

## 👨‍💻 Development

### Rust Development

```bash
# Build in debug mode
make rust-debug

# Run with real-time priority (requires sudo)
make rust-run-rt

# Lint and format
make rust-lint
make rust-fmt

# Run tests
make rust-test
```

### Python Development

```bash
# Create virtual environment
make python-venv
source .venv/bin/activate

# Install dependencies
pip install -e strategies/

# Run backtest
python strategies/src/main.py --mode backtest

# Start Ray cluster locally
ray start --head --port=6379
```

### Frontend Development

```bash
# Install dependencies
cd frontend && npm install

# Run dev server
npm run dev

# Build for production
npm run build
```

---

## ⚡ Performance Optimization

### Memory Management

All services have hard memory limits enforced by Docker:

```yaml
mem_limit: 2g
memswap_limit: 2g
ulimits:
  memlock:
    soft: -1
    hard: -1
```

### Zero-Copy Networking

The Rust core uses `tokio` with `io_uring` for zero-copy WebSocket handling:

```rust
// See core/src/exchange/binance/mod.rs
let socket = tokio::net::TcpStream::connect(addr).await?;
let mut stream = MaybeTlsStream::Raw(socket);
```

### Lock-Free Concurrency

Order book updates use `dashmap` for lock-free concurrent access:

```rust
use dashmap::DashMap;
let order_book: DashMap<u64, Order> = DashMap::new();
```

### Ray Parallelization

Heavy computations are distributed across Ray actors:

```python
@ray.remote(num_cpus=2)
class RegimeDetector:
    def detect(self, data):
        # Runs on separate CPU core
        pass
```

---

## 🛡️ Risk Management

### Built-In Safeguards

1. **Position Limits**: Max position size enforced at Rust level
2. **Daily Loss Limit**: Auto-shutdown if exceeded
3. **Leverage Cap**: Maximum 3x leverage
4. **Circuit Breakers**: Pause trading on abnormal volatility
5. **Heartbeat Monitoring**: Auto-restart on connection loss

### Emergency Stop

```bash
# Immediately stop all trading
docker-compose stop rust_core

# Kill switch (stops everything)
make down
```

---

## 📊 Monitoring

### Real-Time Dashboards

- **Frontend**: http://localhost:3000 - Main trading dashboard
- **QuestDB**: http://localhost:9003 - SQL console for tick data
- **Ray**: http://localhost:8265 - Cluster resource monitoring

### Logs

```bash
# All services
make logs

# Specific service
make logs-rust
make logs-ray
```

### Metrics

```bash
# Resource usage
make stats

# Prometheus metrics (if enabled)
curl http://localhost:9090/metrics
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Out of Memory Errors**

```bash
# Check memory usage
docker stats

# Reduce Ray workers if needed
# Edit docker-compose.yml: ray_worker mem_limit: 2g → 1g
```

**2. Rust Core Won't Start**

```bash
# Check logs
make logs-rust

# Verify CPU affinity settings
cat /proc/cpuinfo
```

**3. Redis Connection Refused**

```bash
# Restart Redis
docker-compose restart redis

# Check password in .env
```

**4. Frontend Blank Page**

```bash
# Rebuild frontend
make frontend-build
docker-compose restart frontend
```

### Performance Tuning

If latency exceeds 1ms:

1. Ensure no other heavy processes running
2. Check CPU governor: `cpufreq-info`
3. Set to performance mode: `sudo cpufreq-set -g performance`
4. Disable hyperthreading for critical cores

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feat/amazing-feature`
5. Open a Pull Request

### Code Standards

- **Rust**: `cargo fmt`, `cargo clippy -- -D warnings`
- **Python**: `black`, `flake8`, `mypy`
- **TypeScript**: `eslint`, `prettier`

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## ⚠️ Disclaimer

**THIS SOFTWARE IS FOR EDUCATIONAL PURPOSES ONLY.**

Trading cryptocurrencies involves substantial risk of loss and is not suitable for every investor. The use of this software for live trading is at your own risk. Past performance is not indicative of future results. Always test thoroughly on a testnet before deploying real capital.

The authors and contributors are not responsible for any financial losses, damages, or legal issues arising from the use of this software.

---

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: `/docs` folder

---

**Built with ❤️ for AMD Ryzen AI 5 laptops**  
*Microseconds matter in HFT*
