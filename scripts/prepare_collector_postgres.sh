#!/usr/bin/env bash
# Build a disposable PostgreSQL database with the collector-only integrity layer.
# This script is for local CI on trust-authenticated PostgreSQL; it never accepts
# or prints a production DSN.

set -euo pipefail

if [[ $# -ne 1 || ! $1 =~ ^ta_[a-z0-9_]{1,40}$ ]]; then
  echo "usage: $0 <ta_database_name>" >&2
  exit 64
fi

database_name=$1
: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PG_SUPERUSER:=postgres}"
: "${PYTHON:=python}"
export PGHOST PGPORT

psql -X -v ON_ERROR_STOP=1 -U "$PG_SUPERUSER" -d postgres <<'SQL'
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'schema_admin') THEN
        CREATE ROLE schema_admin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    ALTER ROLE schema_admin LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOREPLICATION NOBYPASSRLS;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-ingest-v2') THEN
        CREATE ROLE "tradingagents-ingest-v2" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
END
$roles$;
SQL

dropdb --if-exists --force --maintenance-db=postgres \
  -U "$PG_SUPERUSER" "$database_name"
createdb --maintenance-db=postgres -U "$PG_SUPERUSER" \
  --owner=schema_admin "$database_name"

admin_url="postgresql://schema_admin@${PGHOST}:${PGPORT}/${database_name}"
MEDIA_AUTO_MIGRATE=true TEST_DATABASE_URL="$admin_url" "$PYTHON" - <<'PY'
import os

from tradingagents.dataflows.media_store import open_store

store = open_store(os.environ["TEST_DATABASE_URL"], auto_migrate=True)
store.close()
PY

# These are the only historical migrations still exercised by the collector:
# receipt integrity, atomic item lineage, collection cycles, and server clocks.
for migration in \
  migrations/003_formal_source_integrity.sql \
  migrations/006_atomic_fetch_lineage.sql \
  migrations/007_collection_cycles.sql \
  migrations/009_server_observed_evidence.sql; do
  psql -X -v ON_ERROR_STOP=1 "$admin_url" -f "$migration"
done

psql -X -v ON_ERROR_STOP=1 "$admin_url" <<'SQL'
ALTER SCHEMA public OWNER TO schema_admin;
GRANT USAGE ON SCHEMA public TO "tradingagents-ingest-v2";
GRANT SELECT, INSERT ON media_posts, media_labels, media_observations, macro_odds,
    fetch_run_items, collection_cycle_slots TO "tradingagents-ingest-v2";
GRANT SELECT, INSERT, UPDATE ON fetch_runs, poll_state, collection_cycles
    TO "tradingagents-ingest-v2";
SQL

ingest_url="postgresql://tradingagents-ingest-v2@${PGHOST}:${PGPORT}/${database_name}"
if psql -X -v ON_ERROR_STOP=1 "$ingest_url" \
    -c 'CREATE TABLE collector_must_not_create_tables (id INTEGER)' \
    >/dev/null 2>&1; then
  echo "collector role unexpectedly has DDL authority" >&2
  exit 1
fi
if psql -X -v ON_ERROR_STOP=1 "$ingest_url" \
    -c 'DELETE FROM media_posts' >/dev/null 2>&1; then
  echo "collector role unexpectedly has delete authority" >&2
  exit 1
fi

echo "prepared disposable collector database ${database_name}"
