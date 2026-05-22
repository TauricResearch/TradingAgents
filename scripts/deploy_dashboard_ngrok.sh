#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${TRADINGAGENTS_DASHBOARD_PORT:-8787}"
DASHBOARD_DIR="$ROOT/dashboard"

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok is not installed. Install with: brew install ngrok/ngrok/ngrok" >&2
  exit 1
fi

if [ ! -d "$DASHBOARD_DIR" ]; then
  echo "Dashboard dir not found: $DASHBOARD_DIR" >&2
  exit 1
fi

if ! pgrep -f "python3 -m http.server ${PORT} --directory dashboard" >/dev/null 2>&1; then
  echo "Starting local dashboard server on http://127.0.0.1:${PORT}/"
  (cd "$ROOT" && nohup python3 -m http.server "$PORT" --directory dashboard > /tmp/tradingagents-dashboard-${PORT}.log 2>&1 &)
else
  echo "Local dashboard server already running on http://127.0.0.1:${PORT}/"
fi

echo "Starting ngrok tunnel for http://127.0.0.1:${PORT}/"
echo "After startup, open http://127.0.0.1:4040/api/tunnels to see the public URL."
exec ngrok http "$PORT"
