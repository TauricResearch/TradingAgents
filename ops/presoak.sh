#!/usr/bin/env bash
#
# F3 pre-soak: exercise each sensing adapter in isolation for 1 hour and
# verify it (a) never restarts and (b) produces >= 1 event.
#
# Architecture note: adapters do NOT write the SQLite `events` table — they
# XADD envelopes to the Redis stream `sensing_ingest_stream`; the triage
# consumer (NOT started here) is what persists to SQLite. So a solo adapter's
# output is measured by the stream's XLEN delta over its window.
#
# Usage:
#   sudo -v                       # cache sudo creds first (avoids a mid-run prompt)
#   PRESOAK_SECONDS=120 ops/presoak.sh        # quick 2-min smoke of all five
#   nohup ops/presoak.sh > /tmp/presoak.log 2>&1 &   # full 1h each (~5h total)
#   tail -f /tmp/presoak.log
#
# Exits non-zero if any adapter failed its criteria.

set -uo pipefail

REPO=/home/ziwei-huang/TradingAgents/TradingAgents
PY=/home/ziwei-huang/miniconda3/bin/python
DURATION=${PRESOAK_SECONDS:-3600}
REDIS_CONTAINER=${REDIS_CONTAINER:-iic-redis}
UNITS=(iic-sense-polygon iic-sense-telegram iic-sense-rss iic-sense-gdelt iic-sense-macro)

cd "$REPO"

# Resolve the ingest stream name from config (don't hardcode it).
STREAM=$("$PY" -c "from tradingagents.default_config import DEFAULT_CONFIG as C; print(C['sensing_ingest_stream'])")
if [ -z "${STREAM:-}" ]; then
  echo "FATAL: could not resolve sensing_ingest_stream from config" >&2
  exit 2
fi

xlen() { docker exec "$REDIS_CONTAINER" redis-cli XLEN "$STREAM" 2>/dev/null | tr -d '\r'; }

# Confirm the Redis alias / container is reachable before we start.
if ! docker exec "$REDIS_CONTAINER" redis-cli ping 2>/dev/null | grep -q PONG; then
  echo "FATAL: $REDIS_CONTAINER not reachable (start redis-server.service)" >&2
  exit 2
fi

echo "F3 pre-soak  stream=$STREAM  per-adapter=${DURATION}s  start=$(date -u +%FT%TZ)"
echo "------------------------------------------------------------------"

fails=0
for unit in "${UNITS[@]}"; do
  before=$(xlen); before=${before:-0}
  sudo systemctl start "$unit.service"
  echo "$(date -u +%H:%M:%S)  started $unit  (stream@${before}) — soaking ${DURATION}s ..."
  sleep "$DURATION"

  restarts=$(systemctl show "$unit.service" --property=NRestarts --value 2>/dev/null)
  active=$(systemctl is-active "$unit.service" 2>/dev/null)
  after=$(xlen); after=${after:-0}
  sudo systemctl stop "$unit.service"

  produced=$(( after - before ))
  status="PASS"
  if [ "${restarts:-1}" != "0" ]; then status="FAIL(restarts=${restarts})"; fails=$((fails+1));
  elif [ "$active" != "active" ];  then status="FAIL(not active: ${active})"; fails=$((fails+1));
  elif [ "$produced" -lt 1 ];      then status="FAIL(0 events produced)"; fails=$((fails+1)); fi

  printf '%s  %-20s active=%-8s restarts=%-3s produced=%-5s -> %s\n' \
    "$(date -u +%H:%M:%S)" "$unit" "$active" "${restarts:-?}" "$produced" "$status"
done

echo "------------------------------------------------------------------"
if [ "$fails" -eq 0 ]; then
  echo "PRE-SOAK PASSED — all ${#UNITS[@]} adapters clean. end=$(date -u +%FT%TZ)"
  exit 0
else
  echo "PRE-SOAK FAILED — $fails adapter(s) did not meet criteria. end=$(date -u +%FT%TZ)"
  exit 1
fi
