#!/usr/bin/env bash
# Launch the FastAPI backend (serves /api + the built Vue SPA) on 127.0.0.1.
# Public access should be fronted by your own reverse proxy / tunnel.
set -euo pipefail
cd "$(dirname "$0")/.."

# Optional outbound proxy for reaching LLM APIs (mirrors run_webui.sh).
if [[ -n "${TRADINGAGENTS_PROXY_SH:-}" && -r "$TRADINGAGENTS_PROXY_SH" ]]; then
    # shellcheck disable=SC1090
    source "$TRADINGAGENTS_PROXY_SH"
fi

PYTHON_BIN="${TRADINGAGENTS_PYTHON_BIN:-$(command -v python3 || command -v python)}"
exec "$PYTHON_BIN" -m uvicorn server.app:app \
    --host "${TRADINGAGENTS_BIND:-127.0.0.1}" \
    --port "${TRADINGAGENTS_API_PORT:-8502}"
