# QuantumHFT Makefile
# Build, run, and manage the autonomous trading bot system

.PHONY: all build-all clean up-infra down init-db run-engine run-orchestrator run-frontend help

# ===========================================
# Configuration
# ===========================================
RUST_ENGINE_DIR = core-engine
PYTHON_ORCHESTRATOR_DIR = agent-orchestrator
FRONTEND_DIR = frontend
DATABASE_DIR = database
CONFIG_DIR = config

# Colors for output
COLOR_RESET = \033[0m
COLOR_GREEN = \033[32m
COLOR_BLUE = \033[34m
COLOR_YELLOW = \033[33m
COLOR_RED = \033[31m

# ===========================================
# Main Build Targets
# ===========================================

all: build-all

build-all: build-rust build-python build-frontend
	@echo "$(COLOR_GREEN)✓ All components built successfully$(COLOR_RESET)"

build-rust:
	@echo "$(COLOR_BLUE)Building Rust HFT Engine...$(COLOR_RESET)"
	cd $(RUST_ENGINE_DIR) && cargo build --release
	@echo "$(COLOR_GREEN)✓ Rust engine built in release mode$(COLOR_RESET)"

build-python:
	@echo "$(COLOR_BLUE)Installing Python dependencies...$(COLOR_RESET)"
	pip install -r requirements.txt
	pip install -r $(PYTHON_ORCHESTRATOR_DIR)/requirements.txt
	@echo "$(COLOR_GREEN)✓ Python dependencies installed$(COLOR_RESET)"

build-frontend:
	@echo "$(COLOR_BLUE)Building Next.js Frontend...$(COLOR_RESET)"
	cd $(FRONTEND_DIR) && npm install && npm run build
	@echo "$(COLOR_GREEN)✓ Frontend built successfully$(COLOR_RESET)"

# ===========================================
# Docker & Infrastructure
# ===========================================

up-infra:
	@echo "$(COLOR_BLUE)Starting infrastructure containers (TimescaleDB, Redis, Redpanda)...$(COLOR_RESET)"
	docker-compose up -d timescaledb redis redpanda
	@echo "$(COLOR_GREEN)✓ Infrastructure services started$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Waiting for services to be ready...$(COLOR_RESET)"
	sleep 5

down:
	@echo "$(COLOR_RED)Stopping all containers...$(COLOR_RESET)"
	docker-compose down

restart-infra: down up-infra

init-db:
	@echo "$(COLOR_BLUE)Initializing TimescaleDB schema...$(COLOR_RESET)"
	docker-compose exec -T timescaledb psql -U quantumhft -d quantumhft_timeseries -f /docker-entrypoint-initdb.d/init.sql || \
	docker cp $(DATABASE_DIR)/init.sql $$(docker ps -q --filter "name=timescaledb"):/docker-entrypoint-initdb.d/init.sql
	docker-compose restart timescaledb
	@echo "$(COLOR_GREEN)✓ Database initialized$(COLOR_RESET)"

# ===========================================
# Run Commands
# ===========================================

run-engine:
	@echo "$(COLOR_BLUE)Starting Rust HFT Execution Engine...$(COLOR_RESET)"
	cd $(RUST_ENGINE_DIR) && cargo run --release

run-engine-dev:
	@echo "$(COLOR_YELLOW)Starting Rust engine in development mode...$(COLOR_RESET)"
	cd $(RUST_ENGINE_DIR) && cargo run

run-orchestrator:
	@echo "$(COLOR_BLUE)Starting Python AI Orchestrator with hot-reload...$(COLOR_RESET)"
	cd $(PYTHON_ORCHESTRATOR_DIR) && uvicorn main:app --reload --host 0.0.0.0 --port 8000

run-orchestrator-prod:
	@echo "$(COLOR_BLUE)Starting Python AI Orchestrator (production)...$(COLOR_RESET)"
	cd $(PYTHON_ORCHESTRATOR_DIR) && uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

run-frontend:
	@echo "$(COLOR_BLUE)Starting Next.js Frontend (dev mode)...$(COLOR_RESET)"
	cd $(FRONTEND_DIR) && npm run dev

run-frontend-prod:
	@echo "$(COLOR_BLUE)Starting Next.js Frontend (production)...$(COLOR_RESET)"
	cd $(FRONTEND_DIR) && npm start

run-ray:
	@echo "$(COLOR_BLUE)Starting Ray cluster...$(COLOR_RESET)"
	ray start --head --port=6379 --dashboard-port=8265 --num-cpus=8 --object-store-memory=4294967296

stop-ray:
	ray stop

# ===========================================
# Testing & Validation
# ===========================================

test-rust:
	@echo "$(COLOR_BLUE)Running Rust tests...$(COLOR_RESET)"
	cd $(RUST_ENGINE_DIR) && cargo test

test-python:
	@echo "$(COLOR_BLUE)Running Python tests...$(COLOR_RESET)"
	cd $(PYTHON_ORCHESTRATOR_DIR) && pytest

test-all: test-rust test-python

lint-rust:
	cd $(RUST_ENGINE_DIR) && cargo clippy -- -D warnings

lint-python:
	flake8 $(PYTHON_ORCHESTRATOR_DIR)
	pylint $(PYTHON_ORCHESTRATOR_DIR)

format-rust:
	cd $(RUST_ENGINE_DIR) && cargo fmt

format-python:
	black $(PYTHON_ORCHESTRATOR_DIR)
	isort $(PYTHON_ORCHESTRATOR_DIR)

# ===========================================
# Utility Commands
# ===========================================

clean:
	@echo "$(COLOR_RED)Cleaning build artifacts...$(COLOR_RESET)"
	cd $(RUST_ENGINE_DIR) && cargo clean
	cd $(FRONTEND_DIR) && rm -rf node_modules .next out
	find $(PYTHON_ORCHESTRATOR_DIR) -type d -name __pycache__ -exec rm -rf {} +
	find $(PYTHON_ORCHESTRATOR_DIR) -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache
	@echo "$(COLOR_GREEN)✓ Clean complete$(COLOR_RESET)"

clean-all: clean
	docker-compose down -v
	rm -rf .env

logs:
	docker-compose logs -f

logs-engine:
	docker-compose logs -f rust-engine

logs-orchestrator:
	docker-compose logs -f python-orchestrator

status:
	docker-compose ps

health-check:
	@echo "$(COLOR_BLUE)Running health checks...$(COLOR_RESET)"
	curl -f http://localhost:8000/health || echo "Orchestrator not running"
	curl -f http://localhost:3000 || echo "Frontend not running"
	docker-compose ps

# ===========================================
# Development Helpers
# ===========================================

dev-all: up-infra
	@echo "$(COLOR_GREEN)Development environment ready!$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Next steps:$(COLOR_RESET)"
	@echo "  Terminal 1: make run-engine"
	@echo "  Terminal 2: make run-orchestrator"
	@echo "  Terminal 3: make run-frontend"

setup-env:
	@echo "$(COLOR_BLUE)Setting up environment...$(COLOR_RESET)"
	cp -n .env.example .env || true
	@echo "$(COLOR_GREEN)✓ Environment file created (.env)$(COLOR_RESET)"
	@echo "$(COLOR_YELLOW)Please edit .env with your actual API keys and credentials$(COLOR_RESET)"

install-hooks:
	@echo "$(COLOR_BLUE)Installing Git hooks...$(COLOR_RESET)"
	git config core.hooksPath .githooks || true
	@echo "$(COLOR_GREEN)✓ Git hooks configured$(COLOR_RESET)"

# ===========================================
# Help
# ===========================================

help:
	@echo "$(COLOR_BLUE)╔══════════════════════════════════════════════════════════╗$(COLOR_RESET)"
	@echo "$(COLOR_BLUE)║           QuantumHFT - Build & Run Commands              ║$(COLOR_RESET)"
	@echo "$(COLOR_BLUE)╚══════════════════════════════════════════════════════════╝$(COLOR_RESET)"
	@echo ""
	@echo "$(COLOR_GREEN)Build Commands:$(COLOR_RESET)"
	@echo "  make build-all        - Build all components (Rust, Python, Frontend)"
	@echo "  make build-rust       - Build Rust HFT engine (release mode)"
	@echo "  make build-python     - Install Python dependencies"
	@echo "  make build-frontend   - Build Next.js frontend"
	@echo ""
	@echo "$(COLOR_GREEN)Infrastructure:$(COLOR_RESET)"
	@echo "  make up-infra         - Start Docker containers (DB, Redis, Redpanda)"
	@echo "  make down             - Stop all containers"
	@echo "  make init-db          - Initialize TimescaleDB schema"
	@echo ""
	@echo "$(COLOR_GREEN)Run Commands:$(COLOR_RESET)"
	@echo "  make run-engine       - Run Rust HFT engine"
	@echo "  make run-orchestrator - Run Python orchestrator (dev with hot-reload)"
	@echo "  make run-frontend     - Run Next.js frontend (dev mode)"
	@echo "  make run-ray          - Start Ray distributed computing cluster"
	@echo ""
	@echo "$(COLOR_GREEN)Testing:$(COLOR_RESET)"
	@echo "  make test-all         - Run all tests"
	@echo "  make test-rust        - Run Rust tests"
	@echo "  make test-python      - Run Python tests"
	@echo ""
	@echo "$(COLOR_GREEN)Utilities:$(COLOR_RESET)"
	@echo "  make clean            - Clean build artifacts"
	@echo "  make setup-env        - Create .env from .env.example"
	@echo "  make logs             - View Docker logs"
	@echo "  make status           - Show container status"
	@echo "  make help             - Show this help message"
	@echo ""
	@echo "$(COLOR_YELLOW)Quick Start:$(COLOR_RESET)"
	@echo "  1. make setup-env     # Configure your API keys"
	@echo "  2. make build-all     # Build everything"
	@echo "  3. make up-infra      # Start databases"
	@echo "  4. make init-db       # Initialize schema"
	@echo "  5. make dev-all       # Ready for development!"
