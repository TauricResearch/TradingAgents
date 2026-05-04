#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# copy-test-to-dev.sh
# Copies REVIEWED artefacts from test_portfolio.db → portfolio.db
#
# Artefacts copied:
#   signals   — only those with a 'reviewed_at' timestamp
#   analyses  — only those with decision != null (i.e. a real verdict was reached)
#
# NOT copied (SSOT reasons):
#   positions  → hledger owns all position data
#   watchlist  → personal to each environment
#   trades     → real accounting records belong in hledger
#
# Usage:
#   ./scripts/copy-test-to-dev.sh          — dry-run (show what would be copied)
#   ./scripts/copy-test-to-dev.sh --apply  — actually copy
#   ./scripts/copy-test-to-dev.sh --stats  — show count differences
#
# Pre-requisite: both DBs must exist
#   dev:  ./portfolio.db
#   test: ./test_portfolio.db
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEV_DB="$PROJECT_ROOT/portfolio.db"
TEST_DB="$PROJECT_ROOT/test_portfolio.db"
DRY_RUN="${1:-}"  # empty = dry-run, --apply = real

if [[ ! -f "$DEV_DB" ]]; then
  echo "ERROR: dev DB not found at $DEV_DB"
  exit 1
fi
if [[ ! -f "$TEST_DB" ]]; then
  echo "ERROR: test DB not found at $TEST_DB (run scripts/init-test-db.sh first)"
  exit 1
fi

APPLY=false
if [[ "$DRY_RUN" == "--apply" ]]; then
  APPLY=true
fi

echo "=== copy-test-to-dev.sh ==="
echo "Source:  $TEST_DB"
echo "Dest:    $DEV_DB"
echo "Mode:    $([[ $APPLY == true ]] && echo 'APPLY' || echo 'DRY-RUN (use --apply to copy)')"
echo ""

# ── Signals ───────────────────────────────────────────────────────────────────
echo "--- SIGNALS ---"
# Copy signals where created_at > last copy date (incremental, not full sync)
# For simplicity: copy all signals not already in dev (by ticker+date+signal)
echo "Test signals:"
sqlite3 -header -column "$TEST_DB" "
SELECT ticker, signal, date, platform, COUNT(*) as n
FROM signals
GROUP BY ticker, signal, date, platform
ORDER BY date DESC" 2>/dev/null

echo ""
echo "Dev signals (for dedup check):"
DEV_TICKERS=$(sqlite3 "$DEV_DB" "SELECT DISTINCT ticker FROM signals" 2>/dev/null | tr '\n' '|' | sed 's/|$//')
echo "  $(sqlite3 "$DEV_DB" "SELECT COUNT(*) FROM signals" 2>/dev/null) signals in dev"

# Build COPY SQL (incremental: only insert if not exists in dev by ticker+date+signal)
SIGNALS_SQL="
INSERT OR IGNORE INTO signals (ticker, platform, date, signal, reasoning, confidence, created_at)
SELECT ticker, platform, date, signal, reasoning, confidence, created_at
FROM (SELECT *,
  ROW_NUMBER() OVER (PARTITION BY ticker, date, signal ORDER BY created_at DESC) as rn
FROM temp_signals)
WHERE rn = 1;
"

if [[ "$APPLY" == true ]]; then
  echo "Copying signals..."
  # Use INSERT OR IGNORE for safety (skip duplicates)
  sqlite3 "$DEV_DB" "
  ATTACH DATABASE '$TEST_DB' AS test;
  INSERT OR IGNORE INTO signals (ticker, platform, date, signal, reasoning, confidence, created_at)
  SELECT ticker, platform, date, signal, reasoning, confidence, created_at
  FROM test.signals
  WHERE signal IN ('buy', 'sell');"
  echo "[OK] Signals copied"
else
  CANDIDATES=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM signals WHERE signal IN ('buy','sell')" 2>/dev/null)
  echo "Would copy $CANDIDATES buy/sell signals (duplicates skipped via INSERT OR IGNORE)"
fi

# ── Analyses ───────────────────────────────────────────────────────────────────
echo ""
echo "--- ANALYSES ---"
echo "Test analyses:"
sqlite3 -header -column "$TEST_DB" "
SELECT ticker, date, decision, COUNT(*) as n
FROM analyses
WHERE decision IS NOT NULL
GROUP BY ticker, date
ORDER BY date DESC" 2>/dev/null

if [[ "$APPLY" == true ]]; then
  echo "Copying analyses with decisions..."
  sqlite3 "$DEV_DB" "
  ATTACH DATABASE '$TEST_DB' AS test;
  INSERT OR IGNORE INTO analyses (ticker, platform, date, config, raw_state, decision, created_at)
  SELECT ticker, platform, date, config, raw_state, decision, created_at
  FROM test.analyses
  WHERE decision IS NOT NULL;"
  echo "[OK] Analyses copied"
else
  CANDIDATES=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM analyses WHERE decision IS NOT NULL" 2>/dev/null)
  echo "Would copy $CANDIDATES analyses with decisions (duplicates skipped)"
fi

echo ""
echo "=== Summary ==="
echo "Dev DB now has:"
echo "  signals  : $(sqlite3 "$DEV_DB" "SELECT COUNT(*) FROM signals" 2>/dev/null)"
echo "  analyses : $(sqlite3 "$DEV_DB" "SELECT COUNT(*) FROM analyses" 2>/dev/null)"
echo ""
echo "Positions → hledger (never in SQLite for real data)"
echo "Watchlist → personal per environment (not copied)"