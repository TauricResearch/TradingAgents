# Multi-stage Dockerfile for Autonomous Trading System
# Optimized for security and minimal image size

# === Stage 1: Builder ===
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements files
COPY requirements.txt requirements_autonomous.txt /tmp/

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r /tmp/requirements.txt && \
    pip install -r /tmp/requirements_autonomous.txt

# === Stage 2: Runtime ===
FROM python:3.11-slim

# Security: Create non-root user
RUN groupadd -r trader && \
    useradd -r -g trader -d /home/trader -s /bin/bash -m trader

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH" \
    # Default environment (can be overridden)
    ENVIRONMENT=production \
    LOG_LEVEL=INFO

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/share/zoneinfo/America/New_York /etc/localtime \
    && echo "America/New_York" > /etc/timezone

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create app directory
WORKDIR /app

# Copy application code
COPY --chown=trader:trader . /app/

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/data /app/cache && \
    chown -R trader:trader /app/logs /app/data /app/cache && \
    chmod 755 /app/logs /app/data /app/cache

# Security: Set proper file permissions
RUN find /app -type f -name "*.py" -exec chmod 644 {} \; && \
    find /app -type d -exec chmod 755 {} \; && \
    chmod +x /app/autonomous_trader.py

# Switch to non-root user
USER trader

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app'); from autonomous.core.health_check import health_check; exit(0 if health_check() else 1)" || exit 1

# Expose ports
# 8000 - API/Dashboard
# 9090 - Prometheus metrics
EXPOSE 8000 9090

# Default command (can be overridden)
CMD ["python", "autonomous_trader.py"]