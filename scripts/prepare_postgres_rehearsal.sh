#!/usr/bin/env bash
# Build one disposable, MPG-shaped PostgreSQL database at an exact migration head.
#
# This is intentionally limited to a local/CI PostgreSQL instance using trust
# authentication. It never accepts or prints a production DSN. The caller sets
# PGHOST/PGPORT (and optionally PG_SUPERUSER) and receives the non-secret test
# URL on stdout only when PRINT_DATABASE_URL=true.

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <database-name> <migration-head 1..13>" >&2
  exit 64
fi

database_name=$1
migration_head=$2

if [[ ! $database_name =~ ^ta_[a-z0-9_]{1,40}$ ]]; then
  echo "database name must match ta_[a-z0-9_]{1,40}" >&2
  exit 64
fi
if [[ ! $migration_head =~ ^([1-9]|1[0-3])$ ]]; then
  echo "migration head must be an integer from 1 through 13" >&2
  exit 64
fi

: "${PGHOST:=127.0.0.1}"
: "${PGPORT:=5432}"
: "${PG_SUPERUSER:=postgres}"
: "${PYTHON:=python}"

export PGHOST PGPORT

psql -X -v ON_ERROR_STOP=1 -U "$PG_SUPERUSER" -d postgres <<'SQL'
DO $roles$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'schema_admin') THEN
        CREATE ROLE schema_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reader') THEN
        CREATE ROLE reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-app-v2') THEN
        CREATE ROLE "tradingagents-app-v2" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-ingest') THEN
        CREATE ROLE "tradingagents-ingest" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-ingest-v2') THEN
        CREATE ROLE "tradingagents-ingest-v2" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-paper') THEN
        CREATE ROLE "tradingagents-paper" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
            NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-paper-decision'
    ) THEN
        CREATE ROLE "tradingagents-paper-decision" LOGIN NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'tradingagents-paper-marker'
    ) THEN
        CREATE ROLE "tradingagents-paper-marker" LOGIN NOSUPERUSER NOCREATEDB
            NOCREATEROLE NOREPLICATION NOBYPASSRLS;
    END IF;
END
$roles$;

GRANT schema_admin TO "tradingagents-app-v2";
GRANT reader TO "tradingagents-ingest", "tradingagents-ingest-v2",
    "tradingagents-paper", "tradingagents-paper-decision",
    "tradingagents-paper-marker";
-- The disposable test administrator may assume runtime identities for RLS
-- adversarial checks. The inverse memberships forbidden in production remain
-- absent, and release execution still connects without SET ROLE.
GRANT "tradingagents-ingest-v2", "tradingagents-paper-decision",
    "tradingagents-paper-marker" TO "tradingagents-app-v2";
SQL

dropdb --if-exists --force --maintenance-db=postgres \
  -U "$PG_SUPERUSER" "$database_name"
createdb --maintenance-db=postgres -U "$PG_SUPERUSER" \
  --owner=tradingagents-app-v2 "$database_name"

admin_url="postgresql://tradingagents-app-v2@${PGHOST}:${PGPORT}/${database_name}"

MEDIA_AUTO_MIGRATE=true PAPER_AUTO_MIGRATE=true TEST_DATABASE_URL="$admin_url" \
  "$PYTHON" - <<'PY'
import os

from tradingagents.dataflows.media_store import open_store
from tradingagents.paper_trading import PaperStore

url = os.environ["TEST_DATABASE_URL"]
media = open_store(url, auto_migrate=True)
media.close()
paper = PaperStore(url, auto_migrate=True)
paper.close()
PY

psql -X -v ON_ERROR_STOP=1 "$admin_url" <<'SQL'
ALTER SCHEMA public OWNER TO schema_admin;
GRANT USAGE ON SCHEMA public TO reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO reader;
ALTER DEFAULT PRIVILEGES FOR ROLE "tradingagents-app-v2" IN SCHEMA public
    GRANT SELECT ON TABLES TO reader;
SQL

applied=0
for migration in migrations/*.sql; do
  filename=${migration##*/}
  ordinal=${filename%%_*}
  ordinal=$((10#$ordinal))
  if (( ordinal > migration_head )); then
    continue
  fi
  # Every checked-in migration owns one exact BEGIN/COMMIT boundary.
  psql -X -v ON_ERROR_STOP=1 "$admin_url" -f "$migration"
  applied=$((applied + 1))
done

if (( applied != migration_head )); then
  echo "migration inventory is incomplete for requested head" >&2
  exit 1
fi

identity_ready=$(psql -X -v ON_ERROR_STOP=1 -At "$admin_url" <<'SQL'
SELECT current_user = 'tradingagents-app-v2'
   AND session_user = 'tradingagents-app-v2'
   AND pg_has_role(current_user, 'schema_admin', 'MEMBER');
SQL
)
if [[ $identity_ready != t ]]; then
  echo "direct schema-administrator identity check failed" >&2
  exit 1
fi

if (( migration_head == 13 )); then
  head_contract=$(psql -X -v ON_ERROR_STOP=1 -At "$admin_url" <<'SQL'
SELECT public.formal_role_policy_contract_matches()::TEXT || ':' ||
       (SELECT count(*)::TEXT FROM public.formal_trial_authorizations);
SQL
)
  if [[ $head_contract != true:0 ]]; then
    echo "migration-013 role policy or preauthorization state is invalid" >&2
    exit 1
  fi
fi

echo "prepared disposable PostgreSQL database ${database_name} at migration ${migration_head}"
if [[ ${PRINT_DATABASE_URL:-false} == true ]]; then
  echo "$admin_url"
fi
