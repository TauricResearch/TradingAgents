# syntax=docker/dockerfile:1.4

# Build stage for dependencies
FROM python:3.9-slim-bookworm AS builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Install build dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && apt-get clean

# Install Ollama in builder stage with cache mount for downloads
RUN --mount=type=cache,target=/tmp/ollama-cache \
    curl -fsSL https://ollama.com/install.sh | sh

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.9-slim-bookworm AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    OLLAMA_HOST=0.0.0.0

# Install runtime dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && apt-get clean

# Copy Ollama from builder stage instead of installing again
COPY --from=builder /usr/local/bin/ollama /usr/local/bin/ollama

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/bash -d /app appuser

# Create app directory
WORKDIR /app

# Copy the entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy the application code
COPY . .

# Change ownership of the app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Set the entrypoint
ENTRYPOINT ["/bin/sh", "-c", "if [ \"$LLM_PROVIDER\" = \"ollama\" ]; then ./docker-entrypoint.sh; else exec \"$@\"; fi", "--"]


# Default command (can be overridden, e.g., by pytest command in CI)
CMD ["python", "-m", "cli.main"]

EXPOSE 11434
