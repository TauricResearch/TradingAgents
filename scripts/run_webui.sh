#!/usr/bin/env bash
# Launch the Streamlit webui bound to 127.0.0.1.
# Public access should be fronted by your own reverse proxy / tunnel.
set -euo pipefail
cd "$(dirname "$0")/.."

# Optional: source a proxy-setup script if your host needs an outbound proxy
# to reach LLM APIs (e.g. Google generativelanguage). Set TRADINGAGENTS_PROXY_SH
# to its path. Skipped if unset.
if [[ -n "${TRADINGAGENTS_PROXY_SH:-}" && -r "$TRADINGAGENTS_PROXY_SH" ]]; then
    # shellcheck disable=SC1090
    source "$TRADINGAGENTS_PROXY_SH"
fi

PYTHON_BIN="${TRADINGAGENTS_PYTHON_BIN:-$(command -v python3 || command -v python)}"
exec "$PYTHON_BIN" -m streamlit run webui.py \
    --server.address "${TRADINGAGENTS_BIND:-127.0.0.1}" \
    --server.port "${TRADINGAGENTS_PORT:-8501}" \
    --server.headless true \
    --browser.gatherUsageStats false
