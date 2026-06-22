#!/usr/bin/env bash
# Submit one Anthropic Message Batch run for tickers missing today's report.
#
# The submitted run is asynchronous. Use the printed run id with:
#   uv run python -m cli.main batch status <RUN_ID>
#   uv run python -m cli.main batch collect <RUN_ID>

set -uo pipefail

cd "$(dirname "$0")/.."

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
DATE_SLUG="${DATE//-/}"
PROVIDER="anthropic"
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-claude-opus-4-8}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-claude-sonnet-4-6}"
ANTHROPIC_EFFORT="${TRADINGAGENTS_ANTHROPIC_EFFORT:-low}"
ANALYSTS="${TRADINGAGENTS_ANALYSTS:-market,social,news,fundamentals}"
DEPTH="${TRADINGAGENTS_DEPTH:-5}"

model_slug() {
  local slug="$1"
  slug="${slug//\//-}"
  slug="${slug//:/-}"
  slug="${slug//./-}"
  printf '%s\n' "$slug"
}

REPORT_GLOB="${DATE_SLUG}_$(model_slug "$DEEP_MODEL")_*"
DEFAULT_TICKERS=(SPY QQQ SOXX SPCX CRM MSFT META AAPL NVDA MU INTC AVGO GOOGL)
ALL_TICKERS=()
if [ "$#" -gt 0 ]; then
  for t in "$@"; do
    ALL_TICKERS+=("$(printf '%s' "$t" | tr '[:lower:]' '[:upper:]')")
  done
else
  ALL_TICKERS=("${DEFAULT_TICKERS[@]}")
fi

TODO=()
for t in "${ALL_TICKERS[@]}"; do
  if [ -z "$(find "docs/$t" -maxdepth 1 -type d -name "$REPORT_GLOB" 2>/dev/null | head -1)" ]; then
    TODO+=("$t")
  fi
done

if [ "${#TODO[@]}" -eq 0 ]; then
  echo "Nothing to submit — all ${#ALL_TICKERS[@]} tickers already have a ${REPORT_GLOB} report."
  exit 0
fi

TICKERS_CSV="$(IFS=,; echo "${TODO[*]}")"
echo "Submitting Anthropic Message Batch run for ${#TODO[@]} ticker(s): ${TICKERS_CSV}"
TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT="${TRADINGAGENTS_SENTIMENT_INCLUDE_REDDIT:-0}" \
uv run python -m cli.main batch submit \
  --provider "$PROVIDER" \
  --tickers "$TICKERS_CSV" \
  --date "$DATE" \
  --analysts "$ANALYSTS" \
  --depth "$DEPTH" \
  --language English \
  --deep-model "$DEEP_MODEL" \
  --quick-model "$QUICK_MODEL" \
  --anthropic-effort "$ANTHROPIC_EFFORT"
