# =============================================================================
# HFT Python Strategy Engine - Dockerfile
# =============================================================================
# Multi-stage build for Ray cluster with AMD GPU support
# Optimized for 6GB RAM allocation in Docker container
# =============================================================================

# -----------------------------------------------------------------------------
# STAGE 1: Base Image with Python
# -----------------------------------------------------------------------------
FROM python:3.11-slim-bookworm AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -----------------------------------------------------------------------------
# STAGE 2: Dependencies
# -----------------------------------------------------------------------------
FROM base AS dependencies

# Copy requirements first for better caching
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install . --no-cache-dir

# -----------------------------------------------------------------------------
# STAGE 3: Runtime
# -----------------------------------------------------------------------------
FROM base AS runtime

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' appuser

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Copy application code
COPY src/ /app/src/

# Change ownership
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set environment variables for AMD GPU
ENV ONNXRUNTIME_PROVIDERS=rocm \
    OPENBLAS_NUM_THREADS=2 \
    MKL_NUM_THREADS=2 \
    OMP_NUM_THREADS=2

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import ray; print('OK')" || exit 1

# Default command (can be overridden by docker-compose)
CMD ["python", "-m", "hft_strategies.main", "--mode", "backtest"]
