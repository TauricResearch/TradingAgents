#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# reset-portfolio.sh
# Hard reset: zero out all portfolio data in both dev and test environments.
#
# Resets:
#   - Dev SQLite (./portfolio.db): open positions → zero
#   - Test SQLite (./test_portfolio.db): open positions → zero
#   - Dev hledger (~/.hledger.journal): wipe to clean account-openings template
#   - Test hledger (~/.tradingagents/test_hledger.journal): wipe to zero template
#   - Exit plans (~/.tradingagents/positions/): delete all active plans
#
# Preserves (AI artefacts — do not touch):
#   - signals, analyses, watchlist tables
#   - anything in ~/.tradingagents/positions/archive/
#
# Usage:
#   ./scripts/reset-portfolio.sh          # dry run (shows what will change)
#   ./scripts/reset-portfolio.sh --confirm  # actually do it
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DRY_RUN=true
if [[ "${1:-}" == "--confirm" ]]; then
  DRY_RUN=false
fi

DEV_DB="$PROJECT_ROOT/portfolio.db"
TEST_DB="$PROJECT_ROOT/test_portfolio.db"
DEV_HLEDGER="${HLEDGER_FILE:-$HOME/.hledger.journal}"
TEST_HLEDGER="${TEST_HLEDGER_FILE:-$HOME/.tradingagents/test_hledger.journal}"
POSITIONS_DIR="$HOME/.tradingagents/positions"

# ── Helpers ───────────────────────────────────────────────────────────────────

run() {
  if $DRY_RUN; then
    echo "  [DRY] $*"
  else
    echo "  [EXEC] $*"
    eval "$@"
  fi
}

header() {
  echo ""
  echo "━━ $1 ━━"
}

report() {
  local label="$1"
  local result="$2"
  if $DRY_RUN; then
    echo "  $label → $result (will change)"
  else
    echo "  $label → $result"
  fi
}

# ── Check env ─────────────────────────────────────────────────────────────────

header "Environment"
echo "  DEV_DB:    $DEV_DB"
echo "  TEST_DB:   $TEST_DB"
echo "  DEV_HL:    $DEV_HLEDGER"
echo "  TEST_HL:   $TEST_HLEDGER"
echo "  POSITIONS: $POSITIONS_DIR"

if $DRY_RUN; then
  echo ""
  echo "  ⚠️  DRY RUN — pass --confirm to actually execute"
fi

# ── SQLite: positions ─────────────────────────────────────────────────────────

header "SQLite: open positions"

DEV_POSITIONS=$(sqlite3 "$DEV_DB" "SELECT COUNT(*) FROM positions WHERE status='open'" 2>/dev/null || echo "N/A")
TEST_POSITIONS=$(sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM positions WHERE status='open'" 2>/dev/null || echo "N/A")

report "dev positions (status=open)" "$DEV_POSITIONS"
report "test positions (status=open)" "$TEST_POSITIONS"

if [[ "$DEV_POSITIONS" != "N/A" && "$DEV_POSITIONS" != "0" ]]; then
  run sqlite3 "$DEV_DB" "DELETE FROM positions WHERE status='open'"
fi

if [[ "$TEST_POSITIONS" != "N/A" && "$TEST_POSITIONS" != "0" ]]; then
  run sqlite3 "$TEST_DB" "DELETE FROM positions WHERE status='open'"
fi

# ── hledger: cash + holdings ──────────────────────────────────────────────────

header "hledger: account state"

if [[ -f "$DEV_HLEDGER" ]]; then
  DEV_ASSETS=$(hledger balance --file "$DEV_HLEDGER" assets 2>/dev/null | grep -E "(cash|holdings)" | head -5 || echo "no assets")
  echo "  dev hledger assets:"
  echo "$DEV_ASSETS" | sed 's/^/    /'
fi

if [[ -f "$TEST_HLEDGER" ]]; then
  TEST_ASSETS=$(hledger balance --file "$TEST_HLEDGER" assets 2>/dev/null | grep -E "(cash|holdings)" | head -10 || echo "no assets")
  echo "  test hledger assets:"
  echo "$TEST_ASSETS" | sed 's/^/    /'
fi

# Replace both hledgers with clean zero-balance account-openings template
HLEDGER_TEMPLATE='; ── TradingAgents Journal ────────────────────────────────────────
;
; Account convention: assets:<platform>:<account_type>
;
; Cash is zeroed until real broker statements confirm amounts.
; All positions are tracked in SQLite — hledger holds cash only.
;
; BASE CURRENCY: GBP
; All portfolio values in the UI are displayed in GBP.
; hledger holds native currencies (EUR, USD) — converted on display via live FX rates.

2026-04-01 * "Open unknown account"
  assets:unknown:cash         0.00 EUR
  equity:opening

2026-04-01 * "Open degiero account"
  assets:degiero:cash          0.00 EUR
  equity:opening

2026-04-01 * "Open ibkr account"
  assets:ibkr:cash             0.00 EUR
  equity:opening

2026-04-01 * "Open test account"
  assets:test:cash             0.00 EUR
  equity:opening
'

run "printf '%s' '$HLEDGER_TEMPLATE' > $DEV_HLEDGER"
run "printf '%s' '$HLEDGER_TEMPLATE' > $TEST_HLEDGER"

# ── Exit plans ────────────────────────────────────────────────────────────────

header "Exit plans"

PLAN_COUNT=0
for subdir in degiero ibkr test; do
  dir="$POSITIONS_DIR/$subdir"
  if [[ -d "$dir" ]]; then
    count=$(ls "$dir"/*.yaml 2>/dev/null | wc -l | tr -d ' ')
    PLAN_COUNT=$((PLAN_COUNT + count))
    echo "  $subdir/ → $count plan(s) to delete"
    if [[ "$count" -gt 0 ]]; then
      run "rm -f $dir/*.yaml"
    fi
  fi
done

if [[ "$PLAN_COUNT" -eq 0 ]]; then
  echo "  (no plans to delete)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

header "After-reset state (both envs)"
echo ""
echo "  SQLite positions (dev):"
sqlite3 "$DEV_DB" "SELECT COUNT(*) FROM positions WHERE status='open'" 2>/dev/null | sed 's/^/    /'
echo "  SQLite positions (test):"
sqlite3 "$TEST_DB" "SELECT COUNT(*) FROM positions WHERE status='open'" 2>/dev/null | sed 's/^/    /'
echo "  Dev hledger cash balances:"
hledger balance --file "$DEV_HLEDGER" assets 2>/dev/null | grep -v "^---\|^$" | sed 's/^/    /'
echo "  Test hledger cash balances:"
hledger balance --file "$TEST_HLEDGER" assets 2>/dev/null | grep -v "^---\|^$" | sed 's/^/    /'
echo ""
if $DRY_RUN; then
  echo "  ✅ Dry run complete. Run with --confirm to execute."
else
  echo "  ✅ Reset complete."
fi