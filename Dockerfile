# TradingAgents Docker Image
#
# This Dockerfile creates a container with TradingAgents and all dependencies.
#
# Build:
#   docker build -t tradingagents:latest .
#
# Run:
#   docker run -it --env-file .env tradingagents:latest

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install TradingAgents in development mode
RUN pip install -e .

# Create necessary directories
RUN mkdir -p /app/data \
    /app/eval_results \
    /app/dataflows/data_cache \
    /app/portfolio_data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV TRADINGAGENTS_DATA_DIR=/app/data
ENV TRADINGAGENTS_RESULTS_DIR=/app/eval_results

# Expose port for web interface
EXPOSE 8000

# Default command: Run web interface
CMD ["chainlit", "run", "web_app.py", "--host", "0.0.0.0", "--port", "8000"]
