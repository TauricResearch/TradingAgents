# Multi-stage build for FastAPI backend - Railway optimized
# Optimization: Split dependencies into stable base + app layers for better cache hits

FROM python:3.11-slim as builder

WORKDIR /app

# Install system dependencies (cached layer - rarely changes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip (cached layer)
RUN pip install --no-cache-dir --upgrade pip

# OPTIMIZATION: Install heavy/stable dependencies first (better layer caching)
# These packages rarely change and take longest to install
RUN pip install --no-cache-dir --prefer-binary \
    torch --index-url https://download.pytorch.org/whl/cpu || true

# Install ML/NLP packages that are large but stable
RUN pip install --no-cache-dir --prefer-binary \
    sentence-transformers \
    chromadb \
    langchain-openai \
    langchain-experimental \
    langchain_anthropic \
    langchain-google-genai \
    langgraph

# Install data processing packages
RUN pip install --no-cache-dir --prefer-binary \
    polars \
    pyarrow \
    pandas \
    numpy \
    matplotlib

# Copy and install remaining requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code from backend directory
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
CMD ["sh", "-c", "python -m backend --reload false --port ${PORT:-8000}"]

