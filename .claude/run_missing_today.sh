#!/usr/bin/env bash
# Run the skill.md "heavy run" for every ticker that has NOT been analyzed
# today, with safe concurrency and an automatic retry pass for failures.
#
# Learnings baked in (from the 2026-06-01 bulk run):
#   * Targets are the ticker folders under docs/ (minus stylesheets). A ticker
#     counts as "done today" when docs/<TICKER>/<YYYYMMDD>_*/ already exists.
#   * CONCURRENCY=5 ran clean end to end. CONCURRENCY=20 tripped the API key's
#     request rate limit (HTTP 429, "Current limit: 50") in a burst at launch
#     and silently dropped 2 tickers. Keep the default low; only raise it if
#     the gateway quota is known to be higher.
#   * Two tickers failed on that 429 and needed a manual re-run, so this script
#     does a second low-concurrency pass over whatever is still missing.
#   * `export -f` does NOT survive into `xargs -> bash -c`, so the run command
#     is inlined into the bash -c string below.
#
# Usage:
#   bash .claude/run_missing_today.sh                 # all missing tickers, 5-wide
#   CONCURRENCY=8 bash .claude/run_missing_today.sh    # override concurrency
#   TRADINGAGENTS_DATE=2026-06-01 bash .claude/run_missing_today.sh
#   bash .claude/run_missing_today.sh NVDA AMD TSLA    # explicit ticker list

set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
DATE_SLUG="${DATE//-/}"                       # 2026-06-01 -> 20260601 (folder prefix)
CONCURRENCY="${CONCURRENCY:-5}"               # 5 is the verified-safe default; >5 risks 429
LOGDIR="${TA_LOGDIR:-/tmp/ta_runlogs}"
mkdir -p "$LOGDIR"

# --- discover the target ticker universe ---------------------------------
if [ "$#" -gt 0 ]; then
  ALL_TICKERS=("$@")
else
  ALL_TICKERS=()
  for d in docs/*/; do
    t="$(basename "$d")"
    [ "$t" = "stylesheets" ] && continue
    ALL_TICKERS+=("$t")
  done
fi

# --- a ticker is "missing" if it has no docs/<T>/<DATESLUG>_*/ folder ------
missing_tickers() {
  for t in "${ALL_TICKERS[@]}"; do
    if [ -z "$(find "docs/$t" -maxdepth 1 -type d -name "${DATE_SLUG}_*" 2>/dev/null | head -1)" ]; then
      printf '%s\n' "$t"
    fi
  done
}

# --- run one heavy-run pass over a list of tickers ------------------------
# Mirrors the skill.md "heavy run" one-liner exactly.
run_pass() {
  local conc="$1"; shift
  printf '%s\n' "$@" | xargs -n1 -P"$conc" -I{} bash -c '
      t="$1"; DATE="$2"; LOGDIR="$3"
      echo "[START $t] $(date +%T)"
      uv run python -m cli.main run \
        --ticker "$t" --date "$DATE" \
        --analysts market,social,news,fundamentals \
        --depth 5 --language English \
        --provider anthropic \
        --deep-model claude-opus-4-8 --quick-model claude-sonnet-4-6 \
        --checkpoint --clear-checkpoints \
        > "${LOGDIR}/${t}.log" 2>&1 \
        && echo "[OK $t] $(date +%T)" || echo "[FAIL $t] $(date +%T)"
    ' _ {} "$DATE" "$LOGDIR"
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
  echo "Nothing to run — all ${#ALL_TICKERS[@]} tickers already have a ${DATE_SLUG} report."
  exit 0
fi
echo "Pass 1: ${#TODO[@]} ticker(s) missing for ${DATE}, concurrency=${CONCURRENCY}"
echo "  ${TODO[*]}"
run_pass "$CONCURRENCY" "${TODO[@]}"

# --- pass 2: retry whatever is still missing, serially (429-safe) ---------
read_into STILL < <(missing_tickers)
if [ "${#STILL[@]}" -gt 0 ]; then
  echo "Pass 2 (retry): ${#STILL[@]} still missing, concurrency=1"
  echo "  ${STILL[*]}"
  run_pass 1 "${STILL[@]}"
fi

# --- final report ---------------------------------------------------------
read_into FAILED < <(missing_tickers)
DONE=$(( ${#ALL_TICKERS[@]} - ${#FAILED[@]} ))
echo "=== DONE: ${DONE}/${#ALL_TICKERS[@]} have a ${DATE_SLUG} report ==="
if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "STILL FAILING (check ${LOGDIR}/<TICKER>.log): ${FAILED[*]}"
  exit 1
fi

# --- regenerate docs indices + build the static site (per skill.md) -------
if [ "${TA_BUILD_SITE:-1}" = "1" ]; then
  echo "Rebuilding reports site..."
  # Backfill complete_report.md for any run interrupted after its stages were
  # written but before consolidation; otherwise the index links a missing file
  # and `mkdocs build --strict` fails.
  uv run python scripts/reassemble_complete_reports.py \
    && uv run python scripts/build_reports_site.py \
    && uv run mkdocs build --clean
fi
