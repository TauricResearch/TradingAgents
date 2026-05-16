# Builds the trading-agents-service FastAPI wrapper around the upstream
# TauricResearch/TradingAgents library. Two-stage build to keep the runtime
# image lean — the builder installs deps into a venv, the runtime copies
# the venv + source.
#
# Upstream's original Dockerfile (before the Two Trees fork) ran the
# interactive `tradingagents` CLI as ENTRYPOINT, which crashes in any
# non-TTY environment. We replace it with `uvicorn app.main:app`.

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir .

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home appuser \
 && install -d -m 0755 -o appuser -g appuser /home/appuser/.tradingagents
USER appuser
WORKDIR /home/appuser/app

COPY --from=builder --chown=appuser:appuser /build .

# Railway injects $PORT at runtime. Default 8000 for local docker runs.
ENV PORT=8000
EXPOSE 8000

# Bind 0.0.0.0 so Railway's proxy can reach the container. uvicorn imports
# `app.main:app` from the wrapper layer; the upstream `tradingagents/`
# library is on PYTHONPATH and gets called from within the FastAPI routes.
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
