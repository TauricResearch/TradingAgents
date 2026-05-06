# TradingAgents — Unified task runner
# Requires: just (https://github.com/casey/just), bun, uv
# See: playbooks/just-playbook.md

# Default: list all available recipes
default:
    @just --list

# Orient: what the project is and how to navigate it
[group("meta")]
help:
    @glow docs/help.md 2>/dev/null || cat docs/help.md

# State: current branch, env, DB counts, active tasks
[group("meta")]
info:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp=$(mktemp)
    python scripts/gen-info-md.py > "$tmp"
    glow - "$tmp" 2>/dev/null || cat "$tmp"
    rm -f "$tmp"

set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments := true
set dotenv-load := true

# Group navigation shortcuts — just <letter> to list that group's recipes
[group("nav")]
b:  # bun group
    @just --list --group bun

[group("nav")]
p:  # python group
    @just --list --group python

[group("nav")]
h:  # hledger group
    @just --list --group hledger

[group("nav")]
t:  # td group
    @just --list --group td

[group("nav")]
m:  # meta group
    @just --list --group meta

[group("nav")]
c:  # convenience group
    @just --list --group convenience

[group("nav")]
d:  # diagrams group
    @just --list --group diagrams

[group("nav")]
pr:  # pr group
    @just --list --group pr

# Type-check + lint the TypeScript server
[group("bun")]
check:
    bunx biome check .
    tsc --project tsconfig.server.json --noEmit

# Convert :root hex palette to oklch() (preserves original hex in comments)
[group("bun")]
convert-hex-oklch:
    bun scripts/color-tools/convert-hex-to-oklch.ts

# Format all files with Biome
[group("bun")]
format:
    bunx biome format . --write

# Lint code with Biome (exit 0 = clean)
[group("bun")]
lint:  # [alias: l]
    bunx biome check .

# Lint and auto-fix errors
[group("bun")]
lint-fix:
    bunx biome check . --write

# Start dashboard server (DEV mode, port 3000)
[group("bun")]
serve:
    pkill -9 -f bun 2>/dev/null || true
    bun run server/index.tsx

# Start dashboard server (TEST mode, uses test_portfolio.db)
[group("bun")]
serve-test:
    pkill -9 -f bun 2>/dev/null || true
    TEST_MODE=1 TEST_HLEDGER_FILE="${HOME}/.tradingagents/test_hledger.journal" bun run server/index.tsx

# Install Python dependencies
[group("python")]
install:
    uv sync

# Launch interactive CLI (tradingagents analyze)
[group("python")]
run:
    source .venv/bin/activate && tradingagents

# Launch CLI via python module
[group("python")]
run-cli:
    source .venv/bin/activate && python -m cli.main

# Run analysis on a ticker
[group("python")]
analyze TICKER="SPY" DATE="today" DEBATES="1":  # [alias: a]
    source .venv/bin/activate && python scripts/py/analyze.py '{{TICKER}}' --date '{{DATE}}' --debates {{DEBATES}}

# Generate LLM summary for a ticker (or all analyses)
[group("python")]
summarize TICKER="":
    {{if TICKER != '' { 'bun run scripts/summarize_analyses.ts --ticker ' + TICKER } else { 'bun run scripts/summarize_analyses.ts' }}}

# Regenerate all LLM summaries
[group("python")]
summarize-all:
    bun run scripts/summarize_analyses.ts --all

# Run pytest test suite
[group("python")]
test-smoke:
    uv run pytest tests/ -v

# Quick smoke test for structured output (openai, google, anthropic, deepseek)
[group("python")]
test-quick PROVIDER="openai":
    .venv/bin/python scripts/py/smoke_structured_output.py {{PROVIDER}}

# Start new td session
[group("td")]
td-new:
    td usage --new-session

# Show current td session and workspace
[group("td")]
td-status:
    td current
    td ws current

# Show next priority issue
[group("td")]
td-next:
    td next

# Get full context for a td issue
[group("td")]
td-context ID:
    td context {{ID}}

# Reset td database
[group("td")]
td-reset:
    rm -rf .todos
    td init

# Run analysis on TKA.DE (default test ticker)
[group("convenience")]
analyze-tka DEBATES="1":
    just analyze TKA.DE today {{DEBATES}}

# Generate test hLedger journal with 3 platforms
[group("convenience")]
seed-test-journal JOURNAL="${HOME}/.hledger.journal":
    bash scripts/seed_test_journal.sh "{{JOURNAL}}"

# Show portfolio holdings (DEV, uses hledger + SQLite)
[group("convenience")]
portfolio-intel:
    bun scripts/portfolio-intel.ts

# Show portfolio holdings (TEST mode)
[group("convenience")]
portfolio-intel-test:
    TA_DASHBOARD_PORT=3000 bun scripts/portfolio-intel.ts test

# Seed DEV SQLite database (positions, signals, analyses, watchlist, prices)
[group("convenience")]
seed-db:
    bun scripts/seed_database.ts

# Seed TEST SQLite database
[group("convenience")]
test-seed-db:
    TEST_MODE=1 bun scripts/seed_database.ts --db ./test_portfolio.db

# Seed positions only (DEV)
[group("convenience")]
seed-db-positions:
    bun scripts/seed_database.ts --positions

# Seed signals only (DEV)
[group("convenience")]
seed-db-signals:
    bun scripts/seed_database.ts --signals

# Seed exit plans from YAML (DEV)
[group("convenience")]
seed-db-exit-plans:
    bun scripts/seed_database.ts --exit-plans

# Seed prices from Yahoo Finance (backfill open positions)
[group("convenience")]
seed-db-prices:
    bun scripts/seed_database.ts --prices

# Sync prices for all open positions (catch-up latest)
[group("convenience")]
sync-prices:
    bun run scripts/sync-prices.ts

# Full sync: gap fill + catch-up for all open positions
[group("convenience")]
sync-prices-all:
    bun run scripts/sync-prices.ts --all

# Sync prices for a single ticker: TICKER=AAPL just sync-prices-ticker
[group("convenience")]
sync-prices-ticker:
    @if [ -z "${TICKER}" ]; then echo "Usage: TICKER=AAPL just sync-prices-ticker"; exit 1; fi
    bun scripts/sync-prices.ts --ticker "${TICKER}"

# Seed signals to TEST DB
[group("convenience")]
test-db-signal:
    bun scripts/seed_database.ts --db ./test_portfolio.db --signals

# Create fresh test_portfolio.db with schema
[group("convenience")]
test-init:
    bash scripts/init-test-db.sh

# Wipe and recreate test DB
[group("convenience")]
test-reset:
    bash scripts/init-test-db.sh --reset

# Seed test DB with E2E data (positions + signals)
[group("convenience")]
test-seed:
    bash scripts/init-test-db.sh --reset
    sqlite3 test_portfolio.db < scripts/seed-test-db.sql
    echo "TEST DB seeded: $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM positions') positions, $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM signals') signals"

# Show row counts for DEV and TEST DB
[group("convenience")]
test-db-stats:
    @echo "=== DEV portfolio.db ==="
    sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"
    @echo ""
    @echo "=== TEST test_portfolio.db ==="
    sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"

# Copy TEST artefacts to DEV (dry-run, shows what would change)
[group("convenience")]
copy-test-to-dev:
    ./scripts/copy-test-to-dev.sh

# Copy TEST artefacts to DEV (apply changes)
[group("convenience")]
copy-test-to-dev-apply:
    ./scripts/copy-test-to-dev.sh --apply

# Render .dot and .mmd source files to .svg (graphviz + mmdc required)
[group("diagrams")]
diagrams:
    bun scripts/render_diagrams.ts

# Remove all generated .svg files
[group("diagrams")]
diagrams-clean:
    rm -f docs/diagrams/*.svg
    @echo "Cleaned SVG files."

# Holdings summary with market values
[group("hledger")]
hl:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end

# Holdings only (excludes cash)
[group("hledger")]
hl-holdings:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree

# Cash balances per platform
[group("hledger")]
hl-cash:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree | grep -E "(cash|EUR|USD)"

# All accounts defined in journal
[group("hledger")]
hl-accounts:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" accounts

# Backup hledger journal
[group("hledger")]
hl-backup:
    ~/.tradingagents/bin/backup-hledger.sh

# Verify latest backup integrity
[group("hledger")]
hl-backup-verify:
    ~/.tradingagents/bin/backup-hledger.sh --verify

# Restore hledger from a backup
[group("hledger")]
hl-backup-restore FILE:
    ~/.tradingagents/bin/backup-hledger.sh --restore {{FILE}}

# Price history
[group("hledger")]
hl-prices:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices

# Fetch latest prices from Yahoo Finance
[group("hledger")]
hl-update-prices:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices --auto

# Allocation tree by account
[group("hledger")]
hl-allocation:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end --depth 3

# Transaction history for a ticker
[group("hledger")]
hl-register TICKER:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" reg {{TICKER}}

# Net worth over time
[group("hledger")]
hl-net-worth:
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --equity --monthly

# ── PR review cache ─────────────────────────────────────────
# Persist PR reviews as markdown in debriefs/reviews/ for offline review.
# Run `just prs` to list open PRs, `just pr-fetch N` to save one,
# `just pr-fetch-all` to snapshot everything. Clear down merged PRs
# by deleting their files; the next `just pr-fetch-all` will skip them.

[group("pr")]
prs:  # list open PRs
    gh pr list --repo pjsvis/TradingAgents \
      --json number,title,updatedAt,reviewDecision,mergeStateStatus \
      --state open --limit 20

[group("pr")]
pr-fetch NUM:  # fetch PR #NUM as markdown via defuddle
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p debriefs/reviews
    url="https://github.com/pjsvis/TradingAgents/pull/{{NUM}}"
    file="debriefs/reviews/pr-{{NUM}}.md"
    defuddle parse --markdown "$url" > "$file"
    echo "Saved: $file"

[group("pr")]
pr-fetch-all:  # fetch all open PRs as markdown
    bash scripts/pr-fetch-all.sh

alias a := analyze
alias l := lint