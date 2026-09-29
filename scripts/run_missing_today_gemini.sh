#!/usr/bin/env bash
# Run missing Gemini reports through CLIProxyAPI (default) or Google directly.
# Usage:
#   bash scripts/run_missing_today_gemini.sh --check-only
#   bash scripts/run_missing_today_gemini.sh NVDA AMD
#   TRADINGAGENTS_MODE=direct bash scripts/run_missing_today_gemini.sh
# --check-only verifies model access with a small Gemini request.
#
# Proxy mode starts the Homebrew service and uses CLIPROXY_API_KEY or the
# client key in CLIPROXY_CONFIG (default /opt/homebrew/etc/cliproxyapi.conf).
# TRADINGAGENTS_LLM_BACKEND_URL overrides the server root (no /v1 suffix).
# Direct mode uses GOOGLE_API_KEY from the environment or project .env.
# TRADINGAGENTS_MODE defaults to proxy; TRADINGAGENTS_GEMINI_MODE overrides it.
# Direct mode defaults to gemini-3.8-flash; proxy mode uses its -high alias.
# Model overrides: TRADINGAGENTS_DEEP_MODEL / TRADINGAGENTS_QUICK_MODEL.
# TRADINGAGENTS_GOOGLE_THINKING_LEVEL defaults to high; CONCURRENCY to 10.
# Reports always go to this repository's docs/; TA_LOGDIR overrides logs.

# Parse the complete body before running; edits during a batch must not shift
# the file positions Bash reads after workers finish. Exit inside this block.
{
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

# Save where this launcher checks for completed reports, overriding .env.
export TRADINGAGENTS_REPORTS_DIR="$ROOT/docs"

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
DATE_SLUG="${DATE//-/}"                       # 2026-06-01 -> 20260601 (folder prefix)
PROVIDER="google"
MODE="${TRADINGAGENTS_GEMINI_MODE:-${TRADINGAGENTS_MODE:-proxy}}"
case "$MODE" in
  proxy)
    BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-http://127.0.0.1:8317}"
    DEFAULT_MODEL="gemini-3.8-flash-high" ;;
  direct)
    BACKEND_URL="${TRADINGAGENTS_LLM_BACKEND_URL:-https://generativelanguage.googleapis.com}"
    DEFAULT_MODEL="gemini-3.8-flash" ;;
  *) echo "TRADINGAGENTS_GEMINI_MODE/TRADINGAGENTS_MODE must be proxy or direct" >&2; exit 1 ;;
esac
PYTHON="${TRADINGAGENTS_PYTHON:-$ROOT/.venv/bin/python}"
export GOOGLE_GENAI_USE_VERTEXAI=false
CHECK_ONLY=0
if [ "${1:-}" = "--check-only" ]; then
  CHECK_ONLY=1
  shift
fi
model_preflight() {
  if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Python not found: $PYTHON; set TRADINGAGENTS_PYTHON." >&2
    return 1
  fi
  if [ "$MODE" = proxy ]; then
    local service_output
    if ! service_output="$(brew services start cliproxyapi 2>&1)"; then
      echo "Could not start CLIProxyAPI with Homebrew; proxy preflight aborted." >&2
      echo "$service_output" >&2
      return 1
    fi
    CLIPROXY_API_KEY="$("$PYTHON" scripts/claude_proxy.py --key)" || return 1
    export CLIPROXY_API_KEY
    export GOOGLE_API_KEY="$CLIPROXY_API_KEY"
    "$PYTHON" scripts/claude_proxy.py --provider gemini --base-url "$BACKEND_URL" "${MODELS[@]}" || return 1
  else
    echo "Direct Google API selected."
  fi
  unset GEMINI_API_KEY
  if ! "$PYTHON" -m scripts.gemini_model_probe --mode "$MODE" --base-url "$BACKEND_URL" \
    --thinking-level "$GOOGLE_THINKING_LEVEL" "${MODELS[@]}"; then
    if [ "$MODE" = proxy ]; then
      echo "To check your direct Google key: TRADINGAGENTS_GEMINI_MODE=direct bash scripts/run_missing_today_gemini.sh --check-only" >&2
    fi
    return 1
  fi
}
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-$DEFAULT_MODEL}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-$DEFAULT_MODEL}"
MODELS=("$DEEP_MODEL")
if [ "$QUICK_MODEL" != "$DEEP_MODEL" ]; then
  MODELS+=("$QUICK_MODEL")
fi
GOOGLE_THINKING_LEVEL="${TRADINGAGENTS_GOOGLE_THINKING_LEVEL:-high}"
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
CONCURRENCY="${CONCURRENCY:-10}"               # keep conservative unless the Google quota is known higher
case "$CONCURRENCY" in
  ''|*[!0-9]*) echo "CONCURRENCY must be a positive integer" >&2; exit 1 ;;
esac
if ! [ "$CONCURRENCY" -gt 0 ] 2>/dev/null; then
  echo "CONCURRENCY must be a positive integer" >&2
  exit 1
fi
if [ "$CHECK_ONLY" -eq 1 ]; then
  model_preflight
  exit $?
fi
LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs/gemini/$DATE_SLUG/$MODEL_SLUG}"
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
# Mirrors the skill.md "heavy run" one-liner, using the native Google provider.
run_pass() {
  local conc="$1"; shift
  printf '%s\n' "$@" | xargs -P"$conc" -I{} bash -c '
      t="$1"; DATE="$2"; LOGDIR="$3"; PROVIDER="$4"; DEEP_MODEL="$5"; QUICK_MODEL="$6"; GOOGLE_THINKING_LEVEL="$7"; ANALYSTS="$8"; DEPTH="$9"; BACKEND_URL="${10}"
      echo "[START $t] $(date +%T)"
      TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT="${TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT:-0}" \
      TRADINGAGENTS_LLM_PROVIDER="$PROVIDER" \
      TRADINGAGENTS_LLM_BACKEND_URL="$BACKEND_URL" \
      TRADINGAGENTS_DEEP_THINK_LLM="$DEEP_MODEL" \
      TRADINGAGENTS_QUICK_THINK_LLM="$QUICK_MODEL" \
      TRADINGAGENTS_GOOGLE_THINKING_LEVEL="$GOOGLE_THINKING_LEVEL" \
      uv run python -m cli.main run \
        --ticker "$t" --date "$DATE" \
        --analysts "$ANALYSTS" \
        --depth "$DEPTH" --language English \
        --provider "$PROVIDER" \
        --deep-model "$DEEP_MODEL" --quick-model "$QUICK_MODEL" \
        --google-thinking-level "$GOOGLE_THINKING_LEVEL" \
        --checkpoint --clear-checkpoints \
        > "${LOGDIR}/${t}.log" 2>&1 \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR" "$PROVIDER" "$DEEP_MODEL" "$QUICK_MODEL" "$GOOGLE_THINKING_LEVEL" "$ANALYSTS" "$DEPTH" "$BACKEND_URL"
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
model_preflight || exit 1
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
