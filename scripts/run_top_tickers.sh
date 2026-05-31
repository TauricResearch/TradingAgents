#!/usr/bin/env bash
# Parallel max-power TradingAgents run, one docker container per ticker.
#
# Tickers below are deduped against the runs already in docs/ as of
# 2026-05-31. Concurrency defaults to 20 (one per ticker, all at once);
# override with `CONCURRENCY=8 bash scripts/run_top_tickers.sh`.
# Date defaults to today; override with `TRADINGAGENTS_DATE=YYYY-MM-DD ...`.

set -euo pipefail

TICKERS=(
  NVDA AMZN GOOGL AAPL ORCL HPE DELL ANET ASML TSLA
  AMAT LRCX TXN ADI CRWD PLTR COIN SNOW PANW NU
)

DATE="${TRADINGAGENTS_DATE:-$(date +%F)}"
CONCURRENCY="${CONCURRENCY:-20}"

cd "$(dirname "$0")/.."

# `--entrypoint python` overrides the Dockerfile's `tradingagents` entrypoint
# so we run the headless script. `-T` disables TTY allocation so xargs -P
# can multiplex containers without TTY contention. Each container picks up
# .env via docker-compose.yml `env_file` and writes to docs/ via the bind
# mount that already exists in docker-compose.yml.
printf '%s\n' "${TICKERS[@]}" | \
  xargs -n1 -P "$CONCURRENCY" -I{} \
  docker compose run --rm -T \
    --entrypoint python \
    tradingagents scripts/run_one.py --ticker {} --date "$DATE"
