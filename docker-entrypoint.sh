#!/bin/bash
set -e

mkdir -p "$TRADINGAGENTS_DATA_DIR" 2>/dev/null || true

exec .venv/bin/uvicorn web.server.app:create_app --host 0.0.0.0 --port "$PORT"
