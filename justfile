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

# ── Modules ────────────────────────────────────────────────────────────────
mod hledger

# Group navigation shortcuts — just <letter> to list that group's recipes
[group("nav")]
b:  # Bun — TypeScript server tooling
    @echo ""
    @echo "=== Bun: TypeScript server tooling ==="
    @echo ""
    @just --list --group bun

[group("nav")]
p:  # Python — tradingagents package, tests, analysis
    @echo ""
    @echo "=== Python: tradingagents package, tests, analysis ==="
    @echo ""
    @just --list --group python

[group("nav")]
h:  # hLedger — plain-text accounting
    @echo ""
    @echo "=== hLedger: plain-text accounting ==="
    @echo ""
    @just --list hledger

[group("nav")]
t:  # td — task management
    @echo ""
    @echo "=== td: task management ==="
    @echo ""
    @just --list --group td

[group("nav")]
db:  # Database — backup, stats, maintenance
    @echo ""
    @echo "=== Database: backup, stats, maintenance ==="
    @echo ""
    @just --list --group db

[group("nav")]
m:  # Meta — project info, help, state
    @echo ""
    @echo "=== Meta: project info, help, state ==="
    @echo ""
    @just --list --group meta

[group("nav")]
r:  # Run — business operations (analyze, portfolio, sync, seed)
    @echo ""
    @echo "=== Run: business operations ==="
    @echo ""
    @just --list --group run

[group("nav")]
s:  # Seed — database seeding and partial resets
    @echo ""
    @echo "=== Seed: database seeding ==="
    @echo ""
    @just --list --group seed

[group("nav")]
x:  # Test — test DB and development tools
    @echo ""
    @echo "=== Test: test DB and development tools ==="
    @echo ""
    @just --list --group test

[group("nav")]
d:  # Diagrams — render .dot / .mmd to .svg
    @echo ""
    @echo "=== Diagrams: render .dot / .mmd to .svg ==="
    @echo ""
    @just --list --group diagrams

[group("nav")]
pr:  # PR — GitHub pull request helpers
    @echo ""
    @echo "=== PR: GitHub pull request helpers ==="
    @echo ""
    @just --list --group pr

[group("nav")]
hk:  # Hooks — git workflow automation
    @echo ""
    @echo "=== Hooks: git workflow automation ==="
    @echo ""
    @just --list --group hooks

# Aliases for common hledger recipes (backward compat)
alias hl := hledger::hl
alias hl-cash := hledger::hl-cash
alias hl-holdings := hledger::hl-holdings
alias hl-prices := hledger::hl-prices
alias hl-register := hledger::hl-register
alias hl-net-worth := hledger::hl-net-worth

# Type-check + lint + custom gates
[group("bun")]
check:
    bunx biome check .
    tsc --project tsconfig.server.json --noEmit
    bun scripts/check-database-usage.ts

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
    bun run src/server/index.tsx

# Start dashboard server (TEST mode, uses test_portfolio.db)
[group("bun")]
serve-test:
    pkill -9 -f bun 2>/dev/null || true
    TEST_MODE=1 TEST_HLEDGER_FILE="${HOME}/.tradingagents/test_hledger.journal" bun run src/server/index.tsx

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

# Run trade calculator unit tests
[group("bun")]
test-trade-calc:
    bun test tests/trade-calculator.test.ts

# Run trade calculator integration tests (real price data)
[group("bun")]
test-trade-calc-integration:
    bun test tests/trade-calculator-integration.test.ts

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

# ── Run: business operations ────────────────────────────────────────────────
#   Core day-to-day operations. Ordered by frequency of use.

# Run analysis on TKA.DE (default test ticker)
[group("run")]
analyze-tka DEBATES="1":
    just analyze TKA.DE today {{DEBATES}}

# Show portfolio holdings (DEV, uses hledger + SQLite)
[group("run")]
portfolio-intel:
    bun scripts/portfolio-intel.ts

# Show portfolio holdings (TEST mode)
[group("run")]
portfolio-intel-test:
    TA_DASHBOARD_PORT=3000 bun scripts/portfolio-intel.ts test

# Sync prices for all open positions (catch-up latest)
[group("run")]
sync-prices:
    bun run scripts/sync-prices.ts

# Full sync: gap fill + catch-up for all open positions
[group("run")]
sync-prices-all:
    bun run scripts/sync-prices.ts --all

# Sync prices for a single ticker: TICKER=AAPL just sync-prices-ticker
[group("run")]
sync-prices-ticker:
    @if [ -z "${TICKER}" ]; then echo "Usage: TICKER=AAPL just sync-prices-ticker"; exit 1; fi
    bun scripts/sync-prices.ts --ticker "${TICKER}"

# Seed DEV SQLite database (positions, signals, analyses, watchlist, prices)
[group("run")]
seed-db:
    bun scripts/seed_database.ts

# Unified trading CLI — generate trade plan for a ticker
[group("run")]
trading TICKER:
    bun run trading plan {{TICKER}} --platform ig --account 50000 --risk 0.02

# ── Database ───────────────────────────────────────────────────────────────
#   Backup, restore, and maintenance.

# Backup portfolio.db (timestamped copy in backups/)
[group("db")]
backup:
    bun scripts/db-backup.ts

# Backup test_portfolio.db
[group("db")]
backup-test:
    bun scripts/db-backup.ts --test

# List existing backups
[group("db")]
backups-list:
    bun scripts/db-backup.ts --list

# Prune backups older than N days (default: 30)
[group("db")]
backups-prune DAYS="30":
    bun scripts/db-backup.ts --prune {{DAYS}}

# Show which database is currently active (LIVE vs TEST)
[group("db")]
db-active:
    @echo "=== Active Database ==="
    @if [ -n "$$TEST_MODE" ] && [ "$$TEST_MODE" = "1" ]; then \
        echo "MODE: TEST"; \
        echo "DB:   $$TEST_PORTFOLIO_DB (default: ./test_portfolio.db)"; \
    else \
        echo "MODE: LIVE"; \
        echo "DB:   $$PORTFOLIO_DB (default: ./portfolio.db)"; \
    fi

# Show row counts for LIVE database
[group("db")]
db-stats:
    @echo "=== LIVE portfolio.db ==="
    @sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist UNION ALL SELECT 'prices', COUNT(*) FROM prices UNION ALL SELECT 'accounts', COUNT(*) FROM accounts UNION ALL SELECT 'trades', COUNT(*) FROM trades" 2>/dev/null || echo "portfolio.db not found"

# Show row counts for TEST database
[group("db")]
db-stats-test:
    @echo "=== TEST test_portfolio.db ==="
    @sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist UNION ALL SELECT 'prices', COUNT(*) FROM prices UNION ALL SELECT 'accounts', COUNT(*) FROM accounts UNION ALL SELECT 'trades', COUNT(*) FROM trades" 2>/dev/null || echo "test_portfolio.db not found"

# Reset TEST database (destroy and recreate)
[confirm("Destroy and recreate test_portfolio.db?")]
[group("db")]
db-reset-test:
    @echo "{{RED}}⚠{{NORMAL}}  Resetting test_portfolio.db..."
    TEST_MODE=1 bash scripts/init-test-db.sh --reset
    @echo "{{GREEN}}✓{{NORMAL}} TEST database reset. Run: just seed-db-test"

# ── Seed: database seeding variants ────────────────────────────────────────
#   Partial seeding for focused reset. Less frequently used than run recipes.

# Seed positions only (DEV)
[group("seed")]
seed-db-positions:
    bun scripts/seed_database.ts --positions

# Seed signals only (DEV)
[group("seed")]
seed-db-signals:
    bun scripts/seed_database.ts --signals

# Seed exit plans from YAML (DEV)
[group("seed")]
seed-db-exit-plans:
    bun scripts/seed_database.ts --exit-plans

# Seed prices from Yahoo Finance (backfill open positions)
[group("seed")]
seed-db-prices:
    bun scripts/seed_database.ts --prices

# Seed TEST SQLite database
[group("seed")]
test-seed-db:
    TEST_MODE=1 bun scripts/seed_database.ts --db ./test_portfolio.db

# Generate test hLedger journal with 3 platforms
[group("seed")]
seed-test-journal JOURNAL="${HOME}/.hledger.journal":
    bash scripts/seed_test_journal.sh "{{JOURNAL}}"

# ── Test: development and test DB tools ─────────────────────────────────
#   Test DB lifecycle, diagnostics, and cross-environment copying.

# Create fresh test_portfolio.db with schema
[group("test")]
test-init:
    bash scripts/init-test-db.sh

# Wipe and recreate test DB
[group("test")]
test-reset:
    bash scripts/init-test-db.sh --reset

# Seed test DB with E2E data (positions + signals)
[group("test")]
test-seed:
    bash scripts/init-test-db.sh --reset
    sqlite3 test_portfolio.db < scripts/seed-test-db.sql
    echo "TEST DB seeded: $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM positions') positions, $(sqlite3 test_portfolio.db 'SELECT COUNT(*) FROM signals') signals"

# Seed signals to TEST DB
[group("test")]
test-db-signal:
    bun scripts/seed_database.ts --db ./test_portfolio.db --signals

# Show row counts for DEV and TEST DB
[group("test")]
test-db-stats:
    @echo "=== DEV portfolio.db ==="
    sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"
    @echo ""
    @echo "=== TEST test_portfolio.db ==="
    sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"

# Copy TEST artefacts to DEV (dry-run, shows what would change)
[group("test")]
copy-test-to-dev:
    ./scripts/copy-test-to-dev.sh

# Copy TEST artefacts to DEV (apply changes)
[group("test")]
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

# Regenerate all diagrams: static + gitnexus graphs
[group("diagrams")]
regen-diagrams:
    @echo "=== Step 1: Clean old SVGs ==="
    rm -f docs/diagrams/*.svg
    @echo "=== Step 2: Generate GitNexus graphs ==="
    bun scripts/gitnexus-batch.ts --render
    @echo "=== Step 3: Render all DOT files to SVG ==="
    bun scripts/render_diagrams.ts
    @echo ""
    @echo "Done. All diagrams regenerated in docs/diagrams/"

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
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    defuddle parse --markdown "$url" > "$tmp"
    mv "$tmp" "$file"
    trap - EXIT
    echo "Saved: $file"

[group("pr")]
pr-fetch-all:  # fetch all open PRs as markdown
    bash scripts/pr-fetch-all.sh

[group("pr")]
pr-summarize NUM:  # summarize cached PR #NUM via LLM, prepend to file
    bun scripts/pr-summarize.ts {{NUM}} --write

# ── GitNexus: code knowledge graph ──────────────────────────────────────
#   Structural analysis via the indexed knowledge graph.
#   See: playbooks/gitnexus-playbook.md

# 360-degree view of a symbol: callers, callees, processes
[group("gn")]
gn-context SYM:
    gitnexus context "{{SYM}}" --repo TradingAgents

# Blast radius: what breaks if you change a symbol
[group("gn")]
gn-impact SYM DIRECTION="upstream":
    gitnexus impact "{{SYM}}" --direction {{DIRECTION}} --repo TradingAgents

# Map uncommitted changes to affected symbols and flows
[group("gn")]
gn-changes SCOPE="unstaged":
    gitnexus detect-changes --scope {{SCOPE}} --repo TradingAgents

# Raw Cypher query against the knowledge graph
[group("gn")]
gn-cypher QUERY:
    gitnexus cypher "{{QUERY}}" --repo TradingAgents

# Re-index the repo (run after significant code changes)
[group("gn")]
gn-analyze:
    gitnexus analyze --force .

# Export symbol impact graph to DOT/SVG (writes docs/diagrams/gn-impact-<SYM>.dot)
[group("gn")]
gn-graph-symbol SYM:
    bun scripts/gitnexus-to-dot.ts --symbol {{SYM}} --depth 1 --render

# Export file module graph to DOT/SVG (writes docs/diagrams/gn-file-<FILE>.dot)
[group("gn")]
gn-graph-file FILE:
    bun scripts/gitnexus-to-dot.ts --file {{FILE}} --render

# Generate key GitNexus graphs for the project (impact graphs for hotspots)
[group("gn")]
gn-diagrams:
    @echo "Generating GitNexus impact graphs..."
    bun scripts/gitnexus-batch.ts --render
    @echo ""
    @echo "Generated:"
    @ls -1 docs/diagrams/gn-impact-*.dot docs/diagrams/gn-file-*.dot 2>/dev/null || echo "  (no files yet)"

# Remove generated GitNexus diagrams
[group("gn")]
gn-diagrams-clean:
    rm -f docs/diagrams/gn-impact-* docs/diagrams/gn-file-*
    @echo "Cleaned GitNexus diagrams."

# ⚠️ BROKEN: gitnexus serve fails due to CSP on gitnexus.vercel.app
# Use gn-graph-symbol or gn-graph-file instead
[group("gn")]
gn-serve:
    @echo "⚠️  gitnexus serve is broken — CSP blocks localhost. Use:"
    @echo "   just gn-graph-symbol <SYMBOL>   # impact graph"
    @echo "   just gn-graph-file <FILE>       # module graph"
    @echo "   just gn-diagrams                # key project graphs"

# Show index status
[group("gn")]
gn-status:
    gitnexus list

[group("nav")]
gn:  # GitNexus — code knowledge graph
    @echo ""
    @echo "=== GitNexus: code knowledge graph ==="
    @echo ""
    @just --list --group gn

[group("nav")]
srv:  # Server — lifecycle management
    @echo ""
    @echo "=== Server: lifecycle management ==="
    @echo ""
    @just --list --group srv

# ── Server lifecycle ────────────────────────────────────────────────────────
#   Start, stop, restart, and monitor the dashboard server.

# Show all service status
[group("srv")]
status:
    @echo "{{CYAN}}●{{NORMAL}} Checking service status..."
    bun scripts/server-lifecycle.ts status

# Start dashboard server (background daemon)
[group("srv")]
start:
    @echo "{{GREEN}}▶{{NORMAL}} Starting dashboard server..."
    bun scripts/server-lifecycle.ts start

# Stop dashboard server
[confirm("Stop the dashboard server?")]
[group("srv")]
stop:
    @echo "{{RED}}■{{NORMAL}} Stopping dashboard server..."
    bun scripts/server-lifecycle.ts stop

# Restart dashboard server
[group("srv")]
restart:
    @echo "{{YELLOW}}↻{{NORMAL}} Restarting dashboard server..."
    bun scripts/server-lifecycle.ts restart

# Show listening ports
[group("srv")]
ports:
    bun scripts/server-lifecycle.ts ports

# Show recent server logs
[group("srv")]
logs:
    bun scripts/server-lifecycle.ts logs

# Show all available service commands
[group("srv")]
service-help:
    bun scripts/server-lifecycle.ts service-help

# ── Lab: terminal experiments ─────────────────────────────────────────────
#   Safe playground for testing CLI output, API calls, formatting.

[group("lab")]
lab-gum:
    @echo "=== Gum CLI output experiment ==="
    bun scripts/lab/gum.ts

[group("nav")]
lab:  # Lab — terminal experiments
    @echo ""
    @echo "=== Lab: terminal experiments ==="
    @echo ""
    @just --list --group lab

# ── Hooks: git workflow automation ─────────────────────────────────────────

# Install pre-push hook that auto-regenerates diagrams
[group("hooks")]
install-hooks:
    bash scripts/install-pre-push-hook.sh

# Explicit push with diagram regen (alternative to pre-push hook)
[group("hooks")]
push:
    @echo "=== Regenerating diagrams ==="
    just regen-diagrams
    @echo ""
    @echo "=== Checking for diagram changes ==="
    @if git diff --quiet docs/diagrams/gn-* docs/diagrams/*.svg 2>/dev/null; then \
        echo "No diagram changes."; \
    else \
        echo "Diagrams changed. Committing..."; \
        git add docs/diagrams/gn-*.dot docs/diagrams/gn-*.svg docs/diagrams/gn-*.png 2>/dev/null || true; \
        git add docs/diagrams/*.svg 2>/dev/null || true; \
        git commit -m "chore(diagrams): auto-regenerate before push" --no-verify || true; \
    fi
    @echo ""
    @echo "=== Pushing ==="
    git push

alias a := analyze
alias l := lint
