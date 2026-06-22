#!/bin/sh
set -e

DATA_DIR="/home/appuser/.tradingagents/data"

mkdir -p "$DATA_DIR"
chown -R appuser:appuser /home/appuser/.tradingagents

exec su appuser -c "uvicorn web.server.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"
