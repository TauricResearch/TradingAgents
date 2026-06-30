#!/usr/bin/env bash
# Run the skill.md "heavy run" for every ticker that has NOT been analyzed
# today, with safe concurrency and an automatic retry pass for failures.
#
# GLM/Zhipu variant of run_missing_today_opus.sh. The repo loads .env from the
# project root at Python package import; provider "glm" reads ZHIPU_API_KEY.
#
# Usage:
#   bash scripts/run_missing_today_glm52.sh                  # all missing tickers, 10-wide
#   CONCURRENCY=8 bash scripts/run_missing_today_glm52.sh    # override concurrency
#   TRADINGAGENTS_DATE=2026-06-01 bash scripts/run_missing_today_glm52.sh
#   bash scripts/run_missing_today_glm52.sh NVDA AMD TSLA    # explicit ticker list
#
# Rate-limit pacing: export TRADINGAGENTS_LLM_RPM=$((QUOTA / CONCURRENCY)) to
# divide the provider's request quota across the parallel workers (each run
# paces itself; the limiter is per-process and cannot see its siblings).

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
DATE_SLUG="${DATE//-/}"                       # 2026-06-01 -> 20260601 (folder prefix)
PROVIDER="glm"
BACKEND_URL="https://api.z.ai/api/paas/v4/"
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-glm-5.2}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-glm-5.2}"
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
CONCURRENCY="${CONCURRENCY:-10}"               # keep conservative unless the Zhipu quota is known higher
LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs}"
mkdir -p "$LOGDIR"

DEFAULT_TICKERS=(SPY QQQ SOXX SPCX CRM MSFT META AAPL NVDA MU INTC AVGO GOOGL)
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
# Mirrors the skill.md "heavy run" one-liner, using the OpenAI-compatible GLM provider.
run_pass() {
  local conc="$1"; shift
  printf '%s\n' "$@" | xargs -n1 -P"$conc" -I{} bash -c '
      t="$1"; DATE="$2"; LOGDIR="$3"; PROVIDER="$4"; BACKEND_URL="$5"; DEEP_MODEL="$6"; QUICK_MODEL="$7"; ANALYSTS="$8"; DEPTH="$9"
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
        --checkpoint --clear-checkpoints \
        > "${LOGDIR}/${t}.log" 2>&1 \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR" "$PROVIDER" "$BACKEND_URL" "$DEEP_MODEL" "$QUICK_MODEL" "$ANALYSTS" "$DEPTH"
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
  echo "Nothing to run - all ${#ALL_TICKERS[@]} tickers already have a ${REPORT_GLOB} report."
  exit 0
fi
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
