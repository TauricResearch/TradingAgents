# Multi-stage build for FastAPI backend
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements from backend directory
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

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

# Create results directory
RUN mkdir -p /app/results

# Expose port
EXPOSE 8000

# Run the application
# Run the application using the PORT environment variable (required by Railway)
# Using --reload false to prevent hot-reload issues in production
CMD ["sh", "-c", "python -m backend --reload false --port ${PORT:-8000}"]
