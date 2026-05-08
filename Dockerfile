FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# --- Dependency layer (cached as long as pyproject.toml + README are unchanged) ---
# Copy only the project manifest and a minimal source stub so pip can resolve
# and install all dependencies without the full application source tree.
# This layer is NOT rebuilt when only application code changes.
COPY pyproject.toml README.md ./
RUN mkdir -p tradingagents cli \
    && touch tradingagents/__init__.py cli/__init__.py
RUN pip install --no-cache-dir .

# --- Application layer (rebuilt on any source change) ---
COPY . .
RUN pip install --no-cache-dir --no-deps .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

ENTRYPOINT ["tradingagents"]
