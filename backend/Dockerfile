# syntax=docker/dockerfile:1.4
# Multi-stage build for FastAPI backend with optimized caching

FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies (cached layer)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip once (cached layer)
RUN pip install --no-cache-dir --upgrade pip

# Copy ONLY requirements first for better layer caching
# This layer only rebuilds when requirements.txt changes
COPY backend/requirements.txt .

# Install Python dependencies with BuildKit cache mount
# This caches downloaded packages between builds, dramatically speeding up rebuilds
RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip \
    pip install --prefer-binary -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code from backend directory (including __main__.py for python -m)
COPY backend ./backend

# Copy tradingagents package from project root
COPY tradingagents ./tradingagents

# Copy fonts for PDF generation (Noto Serif TC for Chinese)
COPY Cactus_Classical_Serif,Noto_Serif_TC ./Cactus_Classical_Serif,Noto_Serif_TC

# Create results directory
RUN mkdir -p /app/results

# Expose port
EXPOSE 8000

# Run the application using the PORT environment variable (required by Railway)
# Using --reload false to prevent hot-reload issues in production
CMD ["sh", "-c", "python -m backend --reload false --port ${PORT:-8000}"]
