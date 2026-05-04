# TradingAgents — Unified task runner
# Requires: just (https://github.com/casey/just), bun, uv
# See: playbooks/just-playbook.md

set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments := true
set dotenv-load := true

[group("bun")]
lint:                       # Check code with Biome
    bunx biome check .

[group("bun")]
lint-fix:                   # Check and auto-fix
    bunx biome check . --write

[group("bun")]
format:                     # Format all files
    bunx biome format . --write

[group("bun")]
serve:                      # Start dashboard server (DEV mode)
    pkill -9 -f bun 2>/dev/null || true
    bun run server/index.tsx

[group("bun")]
serve-test:                  # Start dashboard server in TEST mode
    pkill -9 -f bun 2>/dev/null || true
    TEST_MODE=1 TEST_HLEDGER_FILE="${HOME}/.tradingagents/test_hledger.journal" bun run server/index.tsx

[group("bun")]
check:                      # Full CI gate: lint + type-check server
    bunx biome check .
    tsc --project tsconfig.server.json --noEmit

[group("python")]
install:                    # Install Python dependencies
    uv sync

[group("python")]
run:                        # Launch interactive CLI
    source .venv/bin/activate && tradingagents

[group("python")]
run-cli:                    # Launch CLI via python module
    source .venv/bin/activate && python -m cli.main

[group("python")]
analyze TICKER="SPY" DATE="today" DEBATES="1":  # Run analysis on a ticker
    source .venv/bin/activate && python scripts/py/analyze.py '{{TICKER}}' --date '{{DATE}}' --debates {{DEBATES}}

[group("python")]
summarize TICKER="":          # Generate LLM summaries (add --all to regenerate all)
    {{if TICKER != '' { 'bun run scripts/summarize_analyses.ts --ticker ' + TICKER } else { 'bun run scripts/summarize_analyses.ts' }}}

[group("python")]
summarize-all:                # Regenerate all LLM summaries
    bun run scripts/summarize_analyses.ts --all

[group("python")]
test-smoke:                 # Run test suite (all fast unit tests)
    uv run pytest tests/ -v

[group("python")]
test-quick PROVIDER="openai":  # Quick structured output test (openai, google, anthropic, deepseek)
    .venv/bin/python scripts/py/smoke_structured_output.py {{PROVIDER}}

[group("td")]
td-new:                     # Start new td session
    td usage --new-session

[group("td")]
td-status:                  # Show current status
    td current
    td ws current

[group("td")]
td-next:                    # Show next priority issue
    td next

[group("td")]
td-context ID:              # Get full context for an issue
    td context {{ID}}

[group("td")]
td-reset:                   # Reset td database
    rm -rf .todos
    td init

[group("convenience")]
analyze-tka DEBATES="1":    # Run analysis on TKA.DE (default test ticker)
    just analyze TKA.DE today {{DEBATES}}

[group("convenience")]
seed-test-journal JOURNAL="${HOME}/.hledger.journal":  # Generate test hLedger journal with 3 platforms
    bash scripts/seed_test_journal.sh "{{JOURNAL}}"

[group("convenience")]
portfolio-intel:              # Show portfolio intelligence (DEV mode)
    bun scripts/portfolio-intel.ts

[group("convenience")]
portfolio-intel-test:        # Show portfolio intelligence (TEST mode)
    TA_DASHBOARD_PORT=3000 bun scripts/portfolio-intel.ts test

[group("convenience")]
seed-db:                     # Seed DEV SQLite database (uses PORTFOLIO_DB env or default)
    bun scripts/seed_database.ts

[group("convenience")]
test-seed-db:                # Seed TEST SQLite database (uses TEST_MODE=1)
    TEST_MODE=1 bun scripts/seed_database.ts --db ./test_portfolio.db

[group("convenience")]
seed-db-positions:           # Seed positions only (DEV)
    bun scripts/seed_database.ts --positions

[group("convenience")]
seed-db-signals:             # Seed signals only (DEV)
    bun scripts/seed_database.ts --signals

[group("convenience")]
seed-db-exit-plans:          # Seed exit plans (YAML) only
    bun scripts/seed_database.ts --exit-plans

[group("convenience")]
seed-db-prices:               # Seed prices from Yahoo Finance (backfill all open positions)
    bun scripts/seed_database.ts --prices

[group("convenience")]
sync-prices:                  # Sync prices for all open positions (catch-up latest)
    bun run scripts/sync-prices.ts

[group("convenience")]
sync-prices-all:              # Full sync: gap fill + catch-up for all open positions
    bun run scripts/sync-prices.ts --all

[group("convenience")]
sync-prices-ticker:           # Sync prices for a single ticker: TICKER=AAPL just sync-prices-ticker
    @if [ -z "${TICKER}" ]; then echo "Usage: TICKER=AAPL just sync-prices-ticker"; exit 1; fi
    bun scripts/sync-prices.ts --ticker "${TICKER}"

[group("convenience")]
test-db-signal:              # Seed signals to TEST DB
    bun scripts/seed_database.ts --db ./test_portfolio.db --signals

[group("convenience")]
test-init:                   # Create fresh test_portfolio.db with schema
    bash scripts/init-test-db.sh

[group("convenience")]
test-reset:                  # Wipe and recreate test DB
    bash scripts/init-test-db.sh --reset

[group("convenience")]
test-seed:                   # Seed test DB with E2E data
    bash scripts/init-test-db.sh --reset
    sqlite3 test_portfolio.db < scripts/seed-test-db.sql
    echo "TEST DB seeded: $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM positions') positions, $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM signals') signals"

[group("convenience")]
test-db-stats:               # Show DEV and TEST DB row counts
    @echo "=== DEV portfolio.db ==="
    sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"
    @echo ""
    @echo "=== TEST test_portfolio.db ==="
    sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"

[group("convenience")]
copy-test-to-dev:            # Copy TEST artefacts to DEV (dry-run)
    ./scripts/copy-test-to-dev.sh

[group("convenience")]
copy-test-to-dev-apply:      # Copy TEST artefacts to DEV (apply)
    ./scripts/copy-test-to-dev.sh --apply

# [group("convenience")]
# seed-all:                    # Full seed: hLedger journal + DB + exit plans + post-mortems
#     just seed-test-journal
#     just seed-db

[group("diagrams")]
diagrams:                     # Render .dot and .mmd source files to .svg
    bun scripts/render_diagrams.ts

[group("diagrams")]
diagrams-clean:               # Remove all generated .svg files
    rm -f docs/diagrams/*.svg
    @echo "Cleaned SVG files."

[group("hledger")]
hl:                         # Holdings summary (market value)
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end

[group("hledger")]
hl-holdings:                # Holdings only (no cash)
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree

[group("hledger")]
hl-cash:                    # Cash balances per platform
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance assets: --tree | grep -E "(cash|EUR|USD)"

[group("hledger")]
hl-accounts:                # All accounts defined in journal
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" accounts

[group("hledger")]
hl-backup:                  # Backup hledger journal to ~/.tradingagents/backups/
    ~/.tradingagents/bin/backup-hledger.sh

[group("hledger")]
hl-backup-verify:           # Verify latest backup integrity
    ~/.tradingagents/bin/backup-hledger.sh --verify

[group("hledger")]
hl-backup-restore FILE:     # Restore hledger from a backup file
    ~/.tradingagents/bin/backup-hledger.sh --restore {{FILE}}

[group("hledger")]
hl-prices:                  # Price history
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices

[group("hledger")]
hl-update-prices:           # Fetch latest prices from Yahoo Finance
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" prices --auto

[group("hledger")]
hl-allocation:              # Allocation tree by account
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end --depth 3

[group("hledger")]
hl-register TICKER:         # Transaction history for a ticker
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" reg {{TICKER}}

[group("hledger")]
hl-net-worth:               # Net worth over time
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --equity --monthly

alias a := analyze
alias l := lint
