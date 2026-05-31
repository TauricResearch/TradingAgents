#!/usr/bin/env bash
set -o pipefail

LOG_DIR="back_test/logs"
mkdir -p "$LOG_DIR"

timestamp="$(date +%Y%m%d_%H%M%S)"
ticker="backtest"

for ((i = 1; i <= $#; i++)); do
  if [ "${!i}" = "--ticker" ] && [ "$((i + 1))" -le "$#" ]; then
    next=$((i + 1))
    ticker="${!next}"
    break
  fi
done

log_file="$LOG_DIR/${ticker}_${timestamp}.log"

if [ -z "${PYTHON:-}" ] && [ -x ".venv/bin/python" ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

"$PYTHON" -m back_test.run_backtest "$@" 2>&1 | tee "$log_file"
exit "${PIPESTATUS[0]}"
