#!/usr/bin/env bash
# Run missing reports through CLIProxyAPI using its existing Codex login.
# Usage:
#   bash scripts/run_missing_today_gpt.sh --check-only
#   bash scripts/run_missing_today_gpt.sh NVDA AMD
#   CONCURRENCY=2 bash scripts/run_missing_today_gpt.sh
#
# CLIPROXY_API_KEY overrides the client key read from CLIPROXY_CONFIG
# (default: /opt/homebrew/etc/cliproxyapi.conf). This is the proxy client key,
# not the upstream OAuth token. TRADINGAGENTS_LLM_BACKEND_URL overrides
# http://127.0.0.1:8317/v1. Model overrides must be advertised by the proxy.
# --check-only checks access and model IDs without launching reports or locking.
# For the public OpenAI API, set TRADINGAGENTS_MODE=direct and
# OPENAI_API_KEY (which may also come from the project's .env).
# TRADINGAGENTS_MODE defaults to proxy; TRADINGAGENTS_GPT_MODE overrides it.
# TRADINGAGENTS_LLM_RPM controls per-worker request pacing.
# Logs default to /tmp/ta_runlogs/gpt/<DATE>/<MODEL>/; TA_LOGDIR overrides this.

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
# PROVIDER must be one `cli.main run` actually accepts ("cliproxyapi" isn't
# and fails --provider validation outright); "openai" plus a BACKEND_URL
# override is how you point it at a local OpenAI-compatible gateway instead
# of api.openai.com.
PROVIDER="openai"
MODE="${TRADINGAGENTS_GPT_MODE:-${TRADINGAGENTS_MODE:-proxy}}"
case "$MODE" in
  proxy) BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-http://127.0.0.1:8317/v1}" ;;
  direct) BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-https://api.openai.com/v1}" ;;
  *) echo "TRADINGAGENTS_GPT_MODE/TRADINGAGENTS_MODE must be proxy or direct" >&2; exit 1 ;;
esac
PYTHON="${TRADINGAGENTS_PYTHON:-$ROOT/.venv/bin/python}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON; set TRADINGAGENTS_PYTHON or install the project environment." >&2
  exit 1
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
    # Inherit the client key through the environment, never worker arguments.
    CLIPROXY_API_KEY="$("$PYTHON" scripts/claude_proxy.py --key)" || return 1
    export CLIPROXY_API_KEY
    export OPENAI_API_KEY="$CLIPROXY_API_KEY"
    "$PYTHON" scripts/claude_proxy.py --provider codex --base-url "$BACKEND_URL" "$DEEP_MODEL" "$QUICK_MODEL" || return 1
  else
    echo "Direct OpenAI API selected; proxy preflight does not apply."
  fi
}
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-gpt-6-astra}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-gpt-6-luna}"
REASONING_EFFORT="${TRADINGAGENTS_OPENAI_REASONING_EFFORT:-max}"
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
CONCURRENCY="${CONCURRENCY:-10}"
case "$CONCURRENCY" in
  ''|*[!0-9]*) echo "CONCURRENCY must be a positive integer" >&2; exit 1 ;;
esac
if ! [ "$CONCURRENCY" -gt 0 ] 2>/dev/null; then
  echo "CONCURRENCY must be a positive integer" >&2
  exit 1
fi
if [ "$CHECK_ONLY" -eq 1 ]; then
  proxy_preflight
  exit $?
fi

# Keep uv and TradingAgents runtime state inside the repository by default.
# This makes scheduled/sandboxed runs independent of access to ~/.cache and
# ~/.tradingagents while still honoring explicit caller overrides.
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.tradingagents/uv-cache}"
export TRADINGAGENTS_RESULTS_DIR="${TRADINGAGENTS_RESULTS_DIR:-$ROOT/.tradingagents/logs}"
export TRADINGAGENTS_CACHE_DIR="${TRADINGAGENTS_CACHE_DIR:-$ROOT/.tradingagents/cache}"
mkdir -p "$ROOT/.tradingagents" "$UV_CACHE_DIR" "$TRADINGAGENTS_RESULTS_DIR" "$TRADINGAGENTS_CACHE_DIR" || exit 1

# Refuse overlapping invocations: each invocation decides what is missing only
# once, so concurrent runs can otherwise generate duplicate timestamped reports.
LOCK_DIR="$ROOT/.tradingagents/run_missing_today_gpt.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Another run_missing_today_gpt.sh invocation is already running: $LOCK_DIR" >&2
  exit 1
fi
cleanup_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs/gpt/$DATE_SLUG/$MODEL_SLUG}"
mkdir -p "$LOGDIR" || exit 1

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
      t="$1"; DATE="$2"; LOGDIR="$3"; PROVIDER="$4"; BACKEND_URL="$5"; DEEP_MODEL="$6"; QUICK_MODEL="$7"; REASONING_EFFORT="$8"; ANALYSTS="$9"; DEPTH="${10}"
      echo "[START $t] $(date +%T)"
      TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT="${TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT:-0}" \
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
        --openai-reasoning-effort "$REASONING_EFFORT" \
        --checkpoint --clear-checkpoints \
        > "${LOGDIR}/${t}.log" 2>&1 \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR" "$PROVIDER" "$BACKEND_URL" "$DEEP_MODEL" "$QUICK_MODEL" "$REASONING_EFFORT" "$ANALYSTS" "$DEPTH"
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
echo "Logs: $LOGDIR"
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
