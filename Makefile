# =============================================================================
# HFT QUANT TRADING SYSTEM - MAKEFILE
# =============================================================================
# Build, run, and manage the entire HFT trading stack
# Optimized for AMD Ryzen AI 5 laptops with 16GB RAM
# =============================================================================

.PHONY: all build up down clean rust-release rust-debug python-venv frontend-dev help

# Default target
all: build up

# -----------------------------------------------------------------------------
# DOCKER COMPOSE COMMANDS
# -----------------------------------------------------------------------------

# Build all services with no cache (fresh build)
build:
	@echo "🔨 Building all services with fresh cache..."
	docker-compose build --no-cache

# Build only specific services
build-rust:
	@echo "🦀 Building Rust core in release mode..."
	docker-compose build rust_core

build-ray:
	@echo "☸️  Building Ray cluster..."
	docker-compose build ray_head ray_worker

build-frontend:
	@echo "⚛️  Building Next.js frontend..."
	docker-compose build frontend

# Start all services
up:
	@echo "🚀 Starting all HFT services..."
	docker-compose up -d
	@echo "✅ Services started. Check status with 'make logs'"
	@echo "📊 Frontend: http://localhost:3000"
	@echo "🗄️  QuestDB: http://localhost:9003"
	@echo "☸️  Ray Dashboard: http://localhost:8265"

# Start services in foreground (for debugging)
up-dev:
	docker-compose up

# Stop all services
down:
	@echo "🛑 Stopping all services..."
	docker-compose down

# Stop and remove volumes (clean slate)
down-clean:
	@echo "🧹 Cleaning up everything..."
	docker-compose down -v

# -----------------------------------------------------------------------------
# RUST CORE COMMANDS
# -----------------------------------------------------------------------------

# Build Rust core in release mode (optimized for production)
rust-release:
	@echo "🦀 Building Rust core in RELEASE mode (optimized)..."
	cd core && cargo build --release
	@echo "✅ Release binary ready at core/target/release/hft_core"

# Build Rust core in debug mode (for development)
rust-debug:
	@echo "🐛 Building Rust core in DEBUG mode..."
	cd core && cargo build
	@echo "✅ Debug binary ready at core/target/debug/hft_core"

# Run Rust core locally (outside Docker)
rust-run:
	@echo "🏃 Running Rust core locally..."
	cd core && cargo run

# Run Rust core with real-time priority (requires sudo)
rust-run-rt:
	@echo "⚡ Running Rust core with REAL-TIME priority..."
	sudo chrt -f 99 cargo run --manifest-path core/Cargo.toml

# Check Rust code quality
rust-lint:
	@echo "🔍 Linting Rust code..."
	cd core && cargo clippy -- -D warnings

# Format Rust code
rust-fmt:
	@echo "✨ Formatting Rust code..."
	cd core && cargo fmt

# Run Rust tests
rust-test:
	@echo "🧪 Running Rust tests..."
	cd core && cargo test -- --nocapture

# -----------------------------------------------------------------------------
# PYTHON STRATEGY COMMANDS
# -----------------------------------------------------------------------------

# Create Python virtual environment
python-venv:
	@echo "🐍 Creating Python virtual environment..."
	python3 -m venv .venv
	@echo "✅ Virtual environment created. Activate with: source .venv/bin/activate"

# Install Python dependencies
python-install:
	@echo "📦 Installing Python dependencies..."
	pip install -e strategies/

# Run Nautilus backtest
backtest:
	@echo "📈 Running Nautilus backtest..."
	python strategies/src/main.py --mode backtest

# Run live trading (DANGER: Use with caution)
live:
	@echo "⚠️  Starting LIVE trading (Ctrl+C to stop)..."
	python strategies/src/main.py --mode live

# Run Ray cluster locally
ray-start:
	@echo "☸️  Starting local Ray cluster..."
	ray start --head --port=6379 --dashboard-port=8265

ray-stop:
	@echo "🛑 Stopping Ray cluster..."
	ray stop

# -----------------------------------------------------------------------------
# FRONTEND COMMANDS
# -----------------------------------------------------------------------------

# Install frontend dependencies
frontend-install:
	@echo "⚛️  Installing frontend dependencies..."
	cd frontend && npm install

# Run frontend in development mode
frontend-dev:
	@echo "🎨 Running frontend in DEV mode..."
	cd frontend && npm run dev

# Build frontend for production
frontend-build:
	@echo "🏗️  Building frontend for PRODUCTION..."
	cd frontend && npm run build

# Run frontend in production mode
frontend-start:
	@echo "🚀 Running frontend in PRODUCTION mode..."
	cd frontend && npm start

# -----------------------------------------------------------------------------
# DATABASE COMMANDS
# -----------------------------------------------------------------------------

# Initialize QuestDB tables
db-init:
	@echo "🗄️  Initializing QuestDB tables..."
	python infra/db_init.py

# Connect to Redis CLI
redis-cli:
	@echo "🔴 Connecting to Redis..."
	docker exec -it hft_redis redis-cli

# Connect to QuestDB via psql
questdb-psql:
	@echo "🔵 Connecting to QuestDB..."
	docker exec -it hft_questdb psql -U admin -W quest

# -----------------------------------------------------------------------------
# MONITORING & LOGS
# -----------------------------------------------------------------------------

# View all logs
logs:
	docker-compose logs -f

# View specific service logs
logs-rust:
	docker-compose logs -f rust_core

logs-ray:
	docker-compose logs -f ray_head ray_worker

logs-frontend:
	docker-compose logs -f frontend

logs-db:
	docker-compose logs -f questdb redis

# Show system resource usage
stats:
	@echo "📊 System Resource Usage:"
	docker stats --no-stream

# -----------------------------------------------------------------------------
# CLEANUP
# -----------------------------------------------------------------------------

# Clean all build artifacts
clean:
	@echo "🧹 Cleaning all build artifacts..."
	cd core && cargo clean
	cd frontend && rm -rf .next node_modules out
	rm -rf .venv __pycache__ **/__pycache__
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	@echo "✅ Cleanup complete"

# Remove Docker images
docker-clean:
	@echo "🗑️  Removing Docker images..."
	docker-compose down -v --rmi all
	docker system prune -f

# -----------------------------------------------------------------------------
# HELP
# -----------------------------------------------------------------------------

help:
	@echo "🤖 HFT Quant Trading System - Makefile Commands"
	@echo ""
	@echo "📦 BUILD & RUN:"
	@echo "  make build        - Build all Docker services"
	@echo "  make up           - Start all services"
	@echo "  make down         - Stop all services"
	@echo "  make clean        - Clean all build artifacts"
	@echo ""
	@echo "🦀 RUST CORE:"
	@echo "  make rust-release - Build Rust core (release mode)"
	@echo "  make rust-debug   - Build Rust core (debug mode)"
	@echo "  make rust-run     - Run Rust core locally"
	@echo "  make rust-lint    - Lint Rust code"
	@echo "  make rust-test    - Run Rust tests"
	@echo ""
	@echo "🐍 PYTHON STRATEGIES:"
	@echo "  make python-venv  - Create Python virtual environment"
	@echo "  make backtest     - Run Nautilus backtest"
	@echo "  make live         - Run live trading (DANGER)"
	@echo "  make ray-start    - Start local Ray cluster"
	@echo ""
	@echo "⚛️  FRONTEND:"
	@echo "  make frontend-dev - Run frontend in dev mode"
	@echo "  make frontend-build - Build frontend for production"
	@echo ""
	@echo "🗄️  DATABASE:"
	@echo "  make db-init      - Initialize QuestDB tables"
	@echo "  make redis-cli    - Connect to Redis CLI"
	@echo ""
	@echo "📊 MONITORING:"
	@echo "  make logs         - View all logs"
	@echo "  make stats        - Show system resource usage"
