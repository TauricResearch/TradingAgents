#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# init-test-db.sh
# Creates a fresh test portfolio SQLite DB with the correct schema.
# Run this once when starting a new test environment.
#
# Usage:
#   ./scripts/init-test-db.sh          — create test_portfolio.db from schema
#   ./scripts/init-test-db.sh --reset  — wipe and recreate
#   ./scripts/init-test-db.sh --seed   — add minimal test seed data
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_DIR="$PROJECT_ROOT"
SCHEMA="$PROJECT_ROOT/server/lib/schema.sql"
TEST_DB="$DB_DIR/test_portfolio.db"

mkdir -p "$DB_DIR"

if [[ "${1:-}" == "--reset" ]]; then
  echo "Wiping test DB..."
  rm -f "$TEST_DB"
fi

if [[ -f "$TEST_DB" && "${1:-}" != "--seed" ]]; then
  echo "test_portfolio.db already exists at $TEST_DB"
  echo "Run with --reset to recreate, or --seed to add test data"
  exit 0
fi

echo "Creating $TEST_DB..."
cp "$SCHEMA" /tmp/test_schema.sql

# Apply schema via sqlite3 (handles CREATE TABLE IF NOT EXISTS)
sqlite3 "$TEST_DB" < /tmp/test_schema.sql
rm /tmp/test_schema.sql

echo "[OK] test_portfolio.db created with schema from server/lib/schema.sql"
echo ""
echo "Tables:"
sqlite3 "$TEST_DB" ".tables"

if [[ "${1:-}" == "--seed" ]]; then
  echo ""
  echo "Seeding test data..."
  seed_test_db "$TEST_DB"
fi