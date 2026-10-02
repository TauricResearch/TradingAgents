#!/usr/bin/env bash
# Run the skill.md "heavy run" for every ticker that has NOT been analyzed
# today, with safe concurrency and an automatic retry pass for failures.
#
# Learnings baked in (from the 2026-06-01 bulk run):
#   * Targets are the ticker folders under docs/ (minus stylesheets). A ticker
#     counts as done when the same date and deep-model report already exists.
#   * CONCURRENCY=10 is the default. CONCURRENCY=20 tripped the API key's
#     request rate limit (HTTP 429, "Current limit: 50") in a burst at launch
#     and silently dropped 2 tickers. Keep the default low; only raise it if
#     the gateway quota is known to be higher.
#   * Two tickers failed on that 429 and needed a manual re-run, so this script
#     does a second low-concurrency pass over whatever is still missing.
#   * `export -f` does NOT survive into `xargs -> bash -c`, so the run command
#     is inlined into the bash -c string below.
#
# Usage:
#   bash scripts/run_all_today.sh                  # all missing tickers, 10-wide
#   CONCURRENCY=8 bash scripts/run_all_today.sh    # override concurrency
#   TRADINGAGENTS_DATE=2026-06-01 bash scripts/run_all_today.sh
#   bash scripts/run_all_today.sh NVDA AMD TSLA    # explicit ticker list
#
# Rate-limit pacing: export TRADINGAGENTS_LLM_RPM=$((QUOTA / CONCURRENCY)) to
# divide the provider's request quota across the parallel workers (each run
# paces itself; the limiter is per-process and cannot see its siblings).

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
DEEP_MODEL="${TRADINGAGENTS_DEEP_MODEL:-claude-opus-4-8}"
QUICK_MODEL="${TRADINGAGENTS_QUICK_MODEL:-claude-sonnet-4-6}"
CONCURRENCY="${CONCURRENCY:-10}"               # 20 tripped HTTP 429 ("Current limit: 50")
LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs}"
mkdir -p "$LOGDIR"

# --- discover the target ticker universe ---------------------------------
if [ "$#" -gt 0 ]; then
  ALL_TICKERS=("$@")
else
  ALL_TICKERS=()
  for d in docs/*/; do
    [ -d "$d" ] || continue
    t="$(basename "$d")"
    [ "$t" = "stylesheets" ] && continue
    [ "$t" = "archive" ] && continue
    ALL_TICKERS+=("$t")
  done
fi

# --- check the same date, deep model, and ticker under docs/ --------------
missing_tickers() {
  python3 "$ROOT/scripts/report_guard.py" missing --reports-dir "$ROOT/docs" \
    --date "$DATE" --model "$DEEP_MODEL" -- "${ALL_TICKERS[@]}"
}

# --- run one heavy-run pass over a list of tickers ------------------------
# Mirrors the skill.md "heavy run" one-liner exactly.
run_pass() {
  local conc="$1"; shift
  printf '%s\n' "$@" | xargs -P"$conc" -I{} bash -c '
      t="$1"; DATE="$2"; LOGDIR="$3"; DEEP_MODEL="$4"; QUICK_MODEL="$5"
      TRADINGAGENTS_ANTHROPIC_CACHE=1 \
      python3 "$PWD/scripts/report_guard.py" run --reports-dir "$TRADINGAGENTS_REPORTS_DIR" \
        --date "$DATE" --model "$DEEP_MODEL" --ticker "$t" --log "${LOGDIR}/${t}.log" -- \
        uv run python -m cli.main run \
        --ticker "$t" --date "$DATE" \
        --analysts market,social,news,fundamentals \
        --depth 5 --language English \
        --provider anthropic \
        --deep-model "$DEEP_MODEL" --quick-model "$QUICK_MODEL" \
        --anthropic-effort low \
        --checkpoint \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR" "$DEEP_MODEL" "$QUICK_MODEL"
}

# Portable (bash 3.2 / macOS) array-from-lines; sets the named global array.
read_into() {  # read_into ARRAYNAME < input
  local __name="$1" __line
  eval "$__name=()"
  while IFS= read -r __line; do
    [ -n "$__line" ] && eval "$__name+=(\"\$__line\")"
  done
}

# Propagate discovery errors rather than treating a failed check as no work.
collect_missing() {
  local missing
  missing="$(missing_tickers)" || return 1
  read_into "$1" <<< "$missing"
  return 0
}

# Normalize and deduplicate arguments before scheduling parallel workers.
read_into ALL_TICKERS < <(printf '%s\n' "${ALL_TICKERS[@]}" | awk 'NF {t=toupper($0); if (!seen[t]++) print t}')

# --- pass 1: everything missing, at the safe concurrency ------------------
collect_missing TODO || exit 1
if [ "${#TODO[@]}" -eq 0 ]; then
  echo "Nothing to run — all ${#ALL_TICKERS[@]} tickers already have a ${DATE_SLUG} report."
  exit 0
fi
echo "Pass 1: ${#TODO[@]} ticker(s) missing for ${DATE}, concurrency=${CONCURRENCY}"
echo "  ${TODO[*]}"
run_pass "$CONCURRENCY" "${TODO[@]}"

# --- pass 2: retry whatever is still missing, at the safe concurrency -----
collect_missing STILL || exit 1
if [ "${#STILL[@]}" -gt 0 ]; then
  echo "Pass 2 (retry): ${#STILL[@]} still missing, concurrency=${CONCURRENCY}"
  echo "  ${STILL[*]}"
  run_pass "$CONCURRENCY" "${STILL[@]}"
fi

# --- final report ---------------------------------------------------------
collect_missing FAILED || exit 1
DONE=$(( ${#ALL_TICKERS[@]} - ${#FAILED[@]} ))
echo "=== DONE: ${DONE}/${#ALL_TICKERS[@]} have a ${DATE_SLUG} report ==="
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "STILL FAILING (check ${LOGDIR}/<TICKER>.log): ${FAILED[*]}"
  exit 1
fi
exit 0
}
