#!/usr/bin/env bash
# Long-polling Telegram bot — auto-replies to /start with the caller's chat_id.
set -euo pipefail
cd "$(dirname "$0")/.."

# Optional outbound proxy (see scripts/run_webui.sh).
if [[ -n "${TRADINGAGENTS_PROXY_SH:-}" && -r "$TRADINGAGENTS_PROXY_SH" ]]; then
    # shellcheck disable=SC1090
    source "$TRADINGAGENTS_PROXY_SH"
fi

PYTHON_BIN="${TRADINGAGENTS_PYTHON_BIN:-$(command -v python3 || command -v python)}"
exec "$PYTHON_BIN" bot_listener.py
