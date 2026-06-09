#!/usr/bin/env bash
# Run the FastAPI server (API + built Vue SPA) reachable on the LAN.
# Access at  http://<this-host-ip>:8502  (e.g. http://192.168.0.110:8502).
# Plain HTTP, so the session cookie is non-Secure (config default).
set -euo pipefail
cd "$(dirname "$0")/.."

export TRADINGAGENTS_BIND="${TRADINGAGENTS_BIND:-0.0.0.0}"
export TRADINGAGENTS_API_PORT="${TRADINGAGENTS_API_PORT:-8502}"
export TRADINGAGENTS_COOKIE_SECURE=0
export TRADINGAGENTS_FRONTEND_DIST="$(pwd)/frontend/dist"

# Build the SPA if it hasn't been built yet.
if [[ ! -f frontend/dist/index.html ]]; then
    echo "[run_api_lan] frontend/dist missing — building…" >&2
    ( cd frontend && npm run build )
fi

exec bash scripts/run_api.sh
