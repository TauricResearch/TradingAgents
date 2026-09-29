#!/usr/bin/env bash
# Run missing reports through CLIProxyAPI using its existing Claude login.
# Usage:
#   bash scripts/run_missing_today_claude.sh --check-only
#   bash scripts/run_missing_today_claude.sh NVDA AMD
#   CONCURRENCY=2 bash scripts/run_missing_today_claude.sh
#
# CLIPROXY_API_KEY overrides the client key read from CLIPROXY_CONFIG
# (default: /opt/homebrew/etc/cliproxyapi.conf). This is the proxy client key,
# not the upstream OAuth token. TRADINGAGENTS_LLM_BACKEND_URL overrides the
# default http://127.0.0.1:8317 server root.
# TRADINGAGENTS_DEEP_MODEL / TRADINGAGENTS_QUICK_MODEL must be advertised by
# the proxy. --check-only checks access and model IDs without generating reports.
# For the public Anthropic API, set TRADINGAGENTS_MODE=direct and
# ANTHROPIC_API_KEY. The direct API key may also come from the project's .env.
# TRADINGAGENTS_MODE defaults to proxy; TRADINGAGENTS_CLAUDE_MODE overrides it.
# TRADINGAGENTS_OPENAI_REASONING_EFFORT also sets Claude effort (default high).
# TRADINGAGENTS_LLM_RPM controls per-worker request pacing.

# Parse the complete body before running; edits during a batch must not shift
# the file positions Bash reads after workers finish. Exit inside this block.
{
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

# These launchers discover completed runs under this repository's docs/.
# Override stale .env paths so saving and completion checks use the same root.
export TRADINGAGENTS_REPORTS_DIR="$ROOT/docs"

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
DATE_SLUG="${DATE//-/}"                       # 2026-06-01 -> 20260601 (folder prefix)
PROVIDER="anthropic"
MODE="${TRADINGAGENTS_CLAUDE_MODE:-${TRADINGAGENTS_MODE:-proxy}}"
case "$MODE" in
  proxy) BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-http://127.0.0.1:8317}" ;;
  direct) BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-https://api.anthropic.com}" ;;
  *) echo "TRADINGAGENTS_CLAUDE_MODE/TRADINGAGENTS_MODE must be proxy or direct" >&2; exit 1 ;;
esac
PYTHON="${TRADINGAGENTS_PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
CHECK_ONLY=0
if [ "${1:-}" = "--check-only" ]; then
  CHECK_ONLY=1
  shift
fi
proxy_preflight() {
  if [ "$MODE" = proxy ]; then
    # Homebrew leaves an already-running service in place.
    if ! brew services start cliproxyapi; then
      echo "Could not start CLIProxyAPI with Homebrew; proxy preflight aborted." >&2
      return 1
    fi
    # Keep credentials out of worker command-line arguments and log output.
    CLIPROXY_API_KEY="$("$PYTHON" scripts/claude_proxy.py --key)" || return 1
    export CLIPROXY_API_KEY
    export ANTHROPIC_API_KEY="$CLIPROXY_API_KEY"
    unset ANTHROPIC_AUTH_TOKEN
    "$PYTHON" scripts/claude_proxy.py --base-url "$BACKEND_URL" "$DEEP_MODEL" "$QUICK_MODEL" || return 1
  else
    echo "Direct Anthropic API selected; proxy preflight does not apply."
  fi
}
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-claude-opus-5-5}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-claude-sonnet-5}"
REASONING_EFFORT="${TRADINGAGENTS_OPENAI_REASONING_EFFORT:-high}"
ANALYSTS="${TRADINGAGENTS_ANALYSTS:-market,social,news,fundamentals}"
DEPTH="${TRADINGAGENTS_DEPTH:-5}"
model_slug() {
  local slug="$1"
  slug="${slug//\//-}"
  slug="${slug//:/-}"
  slug="${slug//./-}"
  printf '%s\n' "$slug"
}
MODEL_SLUG="$(model_slug "$DEEP_MODEL")"
REPORT_GLOB="${DATE_SLUG}_${MODEL_SLUG}_*"
CONCURRENCY="${CONCURRENCY:-5}"
case "$CONCURRENCY" in
  ''|*[!0-9]*|0) echo "CONCURRENCY must be a positive integer" >&2; exit 1 ;;
esac
if [ "$CHECK_ONLY" -eq 1 ]; then
  proxy_preflight
  exit $?
fi
LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs}"
mkdir -p "$LOGDIR"

source "$ROOT/scripts/default_tickers.sh"
ALL_TICKERS=()
if [ "$#" -gt 0 ]; then
  for t in "$@"; do
    ALL_TICKERS+=("$(printf '%s' "$t" | tr '[:lower:]' '[:upper:]')")
  done
else
  ALL_TICKERS=("${DEFAULT_TICKERS[@]}")
fi

# --- a ticker is "missing" if it has no docs/<T>/<DATESLUG>_<MODEL_SLUG>_*/ folder ------
missing_tickers() {
  for t in "${ALL_TICKERS[@]}"; do
    if [ -z "$(find "docs/$t" -maxdepth 1 -type d -name "$REPORT_GLOB" 2>/dev/null | head -1)" ]; then
      printf '%s\n' "$t"
    fi
  done
}

# --- run one heavy-run pass over a list of tickers ------------------------
# Mirrors the skill.md "heavy run" one-liner exactly.
run_pass() {
  local conc="$1"; shift
  printf '%s\n' "$@" | xargs -P"$conc" -I{} bash -c '
      t="$1"; DATE="$2"; LOGDIR="$3"; PROVIDER="$4"; BACKEND_URL="$5"; DEEP_MODEL="$6"; QUICK_MODEL="$7"; ANALYSTS="$8"; DEPTH="$9"; REASONING_EFFORT="${10}"
      echo "[START $t] $(date +%T)"
      TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT="${TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT:-0}" \
      TRADINGAGENTS_ANTHROPIC_CACHE=1 \
      TRADINGAGENTS_LLM_PROVIDER="$PROVIDER" \
      TRADINGAGENTS_LLM_BACKEND_URL="$BACKEND_URL" \
      TRADINGAGENTS_DEEP_THINK_LLM="$DEEP_MODEL" \
      TRADINGAGENTS_QUICK_THINK_LLM="$QUICK_MODEL" \
      uv run python -m cli.main run \
        --ticker "$t" --date "$DATE" \
        --analysts "$ANALYSTS" \
        --depth "$DEPTH" --language English \
        --provider "$PROVIDER" \
        --deep-model "$DEEP_MODEL" --quick-model "$QUICK_MODEL" \
        --anthropic-effort "$REASONING_EFFORT" \
        --checkpoint --clear-checkpoints \
        > "${LOGDIR}/${t}.log" 2>&1 \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR" "$PROVIDER" "$BACKEND_URL" "$DEEP_MODEL" "$QUICK_MODEL" "$ANALYSTS" "$DEPTH" "$REASONING_EFFORT"
}

# Portable (bash 3.2 / macOS) array-from-lines; sets the named global array.
read_into() {  # read_into ARRAYNAME < input
  local __name="$1" __line
  eval "$__name=()"
  while IFS= read -r __line; do
    [ -n "$__line" ] && eval "$__name+=(\"\$__line\")"
  done
}

# --- pass 1: everything missing, at the safe concurrency ------------------
read_into TODO < <(missing_tickers)
if [ "${#TODO[@]}" -eq 0 ]; then
  echo "Nothing to run — all ${#ALL_TICKERS[@]} tickers already have a ${REPORT_GLOB} report."
  exit 0
fi
proxy_preflight || exit 1
echo "Pass 1: ${#TODO[@]} ticker(s) missing for ${DATE} ${MODEL_SLUG}, concurrency=${CONCURRENCY}"
echo "  ${TODO[*]}"
run_pass "$CONCURRENCY" "${TODO[@]}"

# --- final report ---------------------------------------------------------
read_into FAILED < <(missing_tickers)
DONE=$(( ${#ALL_TICKERS[@]} - ${#FAILED[@]} ))
echo "=== DONE: ${DONE}/${#ALL_TICKERS[@]} have a ${REPORT_GLOB} report ==="
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "STILL FAILING (check ${LOGDIR}/<TICKER>.log): ${FAILED[*]}"
  exit 1
fi
exit 0
}
