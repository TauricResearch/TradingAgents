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

# ── Knowledge Registry: briefs, debriefs, playbook indexes ───────────────
#   Usage: just reg-list <briefs|debriefs|decisions|docs|lexicon>
#         just reg-sync [--fix]
#         just reg-mine [--apply]
#         just reg-import [--apply]

[group("kr")]
reg-list REGISTRY:
    bun scripts/reg.ts list "{{ REGISTRY }}"

[group("kr")]
reg-sync FIX="":
    bun scripts/reg.ts sync {{ FIX }}

[group("kr")]
reg-mine:
    bun scripts/reg-mine.ts

[group("kr")]
reg-import:
    bun scripts/reg-import.ts

set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments
set dotenv-load

# ── Modules ────────────────────────────────────────────────────────────────
mod hledger

# Aliases for common hledger recipes (backward compat)
alias hl := hledger::hl
alias hl-cash := hledger::hl-cash
alias hl-holdings := hledger::hl-holdings
alias hl-prices := hledger::hl-prices
alias hl-register := hledger::hl-register
alias hl-net-worth := hledger::hl-net-worth

# Bundle client-side scripts (tree explorer, etc.)
[group("bun")]
build-client:
    bun build --target=browser --format=esm --outfile=src/server/static/scripts/explorer-tree.bundle.js src/server/static/scripts/explorer-tree.ts# Type-check + lint + custom gates
[group("bun")]
check:
    just --unstable --fmt --check
    bunx biome check src cli scripts
    tsc --project tsconfig.server.json --noEmit
    bun scripts/check-database-usage.ts
    bun scripts/check-import-boundaries.ts
    bun scripts/reg.ts enrich --apply
    bun scripts/reg.ts sync --fix
    bun scripts/td-orphans.ts

# Type-check scripts tier (excludes scripts/lab/)
[group("bun")]
check-scripts:
    tsc --project tsconfig.scripts.json --noEmit

# Run all type-check gates: server + scripts
[group("bun")]
check-all:
    just check
    just check-scripts

# Convert :root hex palette to oklch() (preserves original hex in comments)
[group("bun")]
convert-hex-oklch:
    bun scripts/color-tools/convert-hex-to-oklch.ts

# Format all files with Biome
[group("bun")]
format:
    bunx biome format src cli scripts --write

# Lint code with Biome (exit 0 = clean)
[group("bun")]
lint:
    bunx biome check src cli scripts

# Lint and auto-fix errors
[group("bun")]
lint-fix:
    bunx biome check src cli scripts --write

# Show portfolio holdings (LIVE, uses hledger + SQLite via dashboard)
[group("bun")]
portfolio-intel:
    bun scripts/portfolio-intel.ts

# Show portfolio holdings (TEST mode)
[group("bun")]
portfolio-intel-test:
    TA_DASHBOARD_PORT=3000 bun scripts/portfolio-intel.ts test

# Start dashboard server (LIVE mode, port 3000)
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

# Generate LLM summary for a ticker (or all analyses)
[group("python")]
summarize:
    bun run scripts/summarize_analyses.ts

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

# Run CLI command smoke tests
[group("bun")]
test-cli:
    bun test tests/cli-commands.test.ts

# Quick smoke test for structured output (openai, google, anthropic, deepseek)
[group("python")]
test-quick:
    .venv/bin/python scripts/py/smoke_structured_output.py openai

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
    td context {{ ID }}

# Reset td database
[group("td")]
td-reset:
    rm -rf .todos
    td init

# ── Worktree: git worktree management ──────────────────────────────────────
#   Creates worktree + writes .td-root → shared .todos/ at repo root.
#   Each worktree uses the same td database (no copies, no merge needed).

# Create a worktree (sibling dir, new branch, .td-root written)
# Usage: just wt-create my-branch [base-branch] [task-id]
[group("worktree")]
wt-create NAME BASE="main":
    bun scripts/worktree-init.ts {{ NAME }} --base {{ BASE }}

# Create a worktree linked to a TD task
[group("worktree")]
wt-create-task NAME BASE="main" TASK="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{{ TASK }}" ]; then
        bun scripts/worktree-init.ts {{ NAME }} --base {{ BASE }} --task {{ TASK }}
    else
        bun scripts/worktree-init.ts {{ NAME }} --base {{ BASE }}
    fi

# List all worktrees (git worktree list + .td-root status)
[group("worktree")]
wt-list:
    bun scripts/worktree-init.ts --list

# Delete a worktree (removes dir + branch)
[group("worktree")]
wt-delete NAME:
    bun scripts/worktree-init.ts {{ NAME }} --delete

# ── Agent: Session orientation (minimal — replaces full agent-ceremony) ────────
#   S08 brief: agent scripts archived. Use 'td --help' for task management.
#   (agent-*.ts scripts moved to archive/)

# Orientation: branch, git status, last commit, in-flight tasks, and upstream PR status
[group("agent")]
orient:
    #!/usr/bin/env bash
    set -euo pipefail
    branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD)
    echo "Branch: $branch"
    echo ""
    git status --short
    echo ""
    last=$(git log -1 --format="%cr (%ci)" 2>/dev/null || echo "unknown")
    echo "Last commit: $last"
    echo ""
    if command -v gh &> /dev/null; then
        echo "=== UPSTREAM PR STATUS ==="
        gh pr status 2>/dev/null | sed 's/^/  /' || echo "  (gh query failed/unauthenticated)"
        echo ""
    fi
    td current 2>/dev/null | head -5 || true
    echo ""
    td list --status in_progress 2>/dev/null | grep -E "^  td-" | head -10 || echo "  (no in-progress tasks)"

# ── Run: business operations ────────────────────────────────────────────────
#   Core day-to-day operations. Ordered by frequency of use.

# Show portfolio holdings via CLI (SQLite only, no server required)
[group("run")]
portfolio:
    bun run src/cli/main.ts portfolio

# Check exit plan alerts for all positions
[group("run")]
alerts:
    bun run src/cli/main.ts alerts

# Show contingency buylist — watchlist items with fair value targets
[group("run")]
buylist:
    bun run src/cli/main.ts buylist

# Run TradingAgents research pipeline and extract buylist values
[group("run")]
research:
    bun run src/cli/main.ts research SPY

# Unified trading CLI — generate trade plan for a ticker
[group("run")]
trading:
    bun run trading plan SPY --platform ig --account 50000 --risk 0.02

# Run analysis on a ticker (uses analyze_stream.py)
[group("run")]
analyze:
    source .venv/bin/activate && python scripts/py/analyze_stream.py 'SPY' --date today --debates 1

# Markov regime detection: state, transition matrix, and trading signal
[group("run")]
regime TICKER="AAPL":
    bun run src/cli/main.ts regime {{ TICKER }}

# Regime analysis + persist to DB
[group("run")]
regime-store TICKER="AAPL":
    bun run src/cli/main.ts regime {{ TICKER }} --store

# Regime analysis with N-day forecast (e.g. DAYS=2)
[group("run")]
regime-forecast TICKER="AAPL" DAYS="2":
    bun run src/cli/main.ts regime {{ TICKER }} --forecast {{ DAYS }}

# Regime analysis as JSON (for scripting)
[group("run")]
regime-json TICKER="AAPL":
    bun run src/cli/main.ts regime {{ TICKER }} --json

# Full regime pipeline: compute + forecast + persist
[group("run")]
regime-full TICKER="AAPL" DAYS="2":
    bun run src/cli/main.ts regime {{ TICKER }} --store --forecast {{ DAYS }}

# Run Markov regime detection unit tests
[group("bun")]
markov-test:
    bun --tsconfig=tsconfig.server.json -e "import { runAllTests, smokeTest } from './src/server/lib/markov/index.ts'; runAllTests(); smokeTest();"

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
backups-prune:
    bun scripts/db-backup.ts --prune 30

# Backup LIVE portfolio.db (timestamped copy in backups/)
[group("db")]
db-backup:
    bun scripts/db-backup.ts

# Reset LIVE portfolio.db from schema.sql (WIPES all data — use db-backup first)
[confirm("Destroy and recreate portfolio.db? All data will be lost. Run 'just db-backup' first.")]
[group("db")]
db-reset:
    @echo "{{ RED }}⚠{{ NORMAL }}  Backing up before reset..."
    bun scripts/db-backup.ts
    @echo "{{ RED }}⚠{{ NORMAL }}  Destroying portfolio.db..."
    rm -f portfolio.db portfolio.db-wal portfolio.db-shm
    sqlite3 portfolio.db < src/server/lib/schema.sql
    @echo "{{ GREEN }}✓{{ NORMAL }} portfolio.db reset from schema.sql"
    @echo "Run: just seed-db to repopulate data"

# Restore portfolio.db from a backup file
# Usage: just db-restore backups/portfolio-2026-05-15.db
[confirm("Restore portfolio.db from backup? Current DB will be overwritten.")]
[group("db")]
db-restore:
    @if [ -z "${BACKUP}" ]; then \
        echo "Usage: BACKUP=backups/portfolio-2026-05-15.db just db-restore"; \
        exit 1; \
    fi
    @if [ ! -f "${BACKUP}" ]; then \
        echo "{{ RED }}✗{{ NORMAL }} Backup file not found: ${BACKUP}"; \
        exit 1; \
    fi
    @echo "{{ RED }}⚠{{ NORMAL }}  Overwriting portfolio.db with ${BACKUP}..."
    cp "${BACKUP}" portfolio.db
    @echo "{{ GREEN }}✓{{ NORMAL }} Restored from ${BACKUP}"

# ── Screening: weekly cadence ──────────────────────────────────────────────────
#   Full screening cycle for weekly automation.
#   Usage: just screen-weekly
#   Cron: 0 18 * * 5 cd /path/to/repo && just screen-weekly >> ~/.tradingagents/logs/screen-weekly.log 2>&1

# Run full weekly screening cycle: backup → enrich → screen → history
# Cron: 0 18 * * 5 cd /path/to/repo && just screen-weekly >> ~/.tradingagents/logs/screen-weekly.log 2>&1
[confirm("Run weekly screening cycle? Fetches enrichment for all watchlist candidates and evaluates rules.")]
[group("screen")]
screen-weekly:
    @echo "{{ GREEN }}=== Weekly Screening Cycle ==={{ NORMAL }}"
    bun scripts/db-backup.ts
    @echo ""
    @echo "Enriching watchlist candidates..."
    bun src/cli/main.ts screen enrich --all
    @echo ""
    @echo "Running screening rules..."
    bun src/cli/main.ts screen run
    @echo ""
    @echo "Screening history:"
    bun src/cli/main.ts screen history
    @echo ""
    @echo "{{ GREEN }}=== Weekly cycle complete ==={{ NORMAL }}"

# ── Show which database is currently active (LIVE vs TEST)
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
    @echo "{{ RED }}⚠{{ NORMAL }}  Resetting test_portfolio.db..."
    TEST_MODE=1 bash scripts/init-test-db.sh --reset
    @echo "{{ GREEN }}✓{{ NORMAL }} TEST database reset. Run: just seed-db-test"

# Sync prices for all open positions (catch-up latest)
[group("db")]
sync-prices:
    bun run scripts/sync-prices.ts

# Full sync: gap fill + catch-up for all open positions
[group("db")]
sync-prices-all:
    bun run scripts/sync-prices.ts --all

# Sync prices for a single ticker: TICKER=AAPL just sync-prices-ticker
[group("db")]
sync-prices-ticker:
    @if [ -z "${TICKER}" ]; then echo "Usage: TICKER=AAPL just sync-prices-ticker"; exit 1; fi
    bun scripts/sync-prices.ts --ticker "${TICKER}"

# ── Seed: database seeding variants ────────────────────────────────────────
#   Partial seeding for focused reset. Less frequently used than run recipes.

# Seed positions only (LIVE)
[group("seed")]
seed-db-positions:
    bun scripts/seed_database.ts --positions

# Seed signals only (LIVE)
[group("seed")]
seed-db-signals:
    bun scripts/seed_database.ts --signals

# Seed exit plans from YAML (LIVE)
[group("seed")]
seed-db-exit-plans:
    bun scripts/seed_database.ts --exit-plans

# Seed prices from Yahoo Finance (backfill open positions)
[group("seed")]
seed-db-prices:
    bun scripts/seed_database.ts --prices

# Seed LIVE SQLite database (positions, signals, analyses, watchlist, prices)
[group("seed")]
seed-db:
    bun scripts/seed_database.ts

# Seed TEST SQLite database
[group("seed")]
test-seed-db:
    TEST_MODE=1 bun scripts/seed_database.ts --db ./test_portfolio.db

seed-test-journal:
    bash scripts/seed_test_journal.sh

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

# Show row counts for LIVE and TEST DB
[group("test")]
test-db-stats:
    @echo "=== LIVE portfolio.db ==="
    sqlite3 portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"
    @echo ""
    @echo "=== TEST test_portfolio.db ==="
    sqlite3 test_portfolio.db "SELECT 'positions', COUNT(*) FROM positions UNION ALL SELECT 'signals', COUNT(*) FROM signals UNION ALL SELECT 'analyses', COUNT(*) FROM analyses UNION ALL SELECT 'watchlist', COUNT(*) FROM watchlist"

# Copy TEST artefacts to LIVE (dry-run, shows what would change)
[group("test")]
copy-test-to-dev:
    ./scripts/copy-test-to-dev.sh

# Copy TEST artefacts to LIVE (apply changes)
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

# ── Prospect lists ──────────────────────────────────────────
# docs/prospects/ — canonical source for all stock prospect lists.
# Combined JSON feeds the Python tradingagents analysis pipeline.

# Build combined-prospects.json from source documents
[group("prospects")]
prospects-build:
    bun run scripts/prospects-build.ts

# Validate prospect documents without writing output
[group("prospects")]
prospects-check:
    bun run scripts/prospects-build.ts --check

# Show prospect summary with jq
[group("prospects")]
prospects-list:
    @echo "=== All Tickers ==="
    jq -r '.tickers[] | "\(.ticker) \(.source) \(.sector) \(.priority)"' docs/prospects/combined-prospects.json
    @echo ""
    @echo "=== Unique Tickers ==="
    jq -r '[.tickers[].ticker] | unique | .[]' docs/prospects/combined-prospects.json
    @echo ""
    @echo "=== By Sector ==="
    jq -r '.tickers | group_by(.sector) | .[] | "\(.[0].sector): \(length)"' docs/prospects/combined-prospects.json
    @echo ""
    @echo "=== High Priority ==="
    jq -r '.tickers[] | select(.priority=="high") | "  \(.ticker) — \(.name) — \(.thesis)"' docs/prospects/combined-prospects.json

# ── PR review cache ─────────────────────────────────────────
# Persist PR reviews as markdown in debriefs/reviews/ for offline review.
# Run `just prs` to list open PRs, `just pr-fetch N` to save one,
# `just pr-fetch-all` to snapshot everything. Clear down merged PRs
# by deleting their files; the next `just pr-fetch-all` will skip them.

[group("pr")]
prs:
    gh pr list --repo pjsvis/TradingAgents \
      --json number,title,updatedAt,reviewDecision,mergeStateStatus \
      --state open --limit 20

[group("pr")]
pr-fetch:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p debriefs/reviews
    NUM="${1:-1}"
    url="https://github.com/pjsvis/TradingAgents/pull/$NUM"
    file="debriefs/reviews/pr-$NUM.md"
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    defuddle parse --markdown "$url" > "$tmp"
    mv "$tmp" "$file"
    trap - EXIT
    echo "Saved: $file"

[group("pr")]
pr-fetch-all:
    bash scripts/pr-fetch-all.sh

# Check for new upstream commits (TauricResearch/TradingAgents)
[group("pr")]
check-upstream:
    @echo "Fetching upstream..."
    git fetch upstream
    @echo ""
    @echo "=== Upstream commits since last merge ==="
    @git log HEAD..upstream/main --oneline
    @echo ""
    @if git log HEAD..upstream/main --oneline | grep -q .; then \
      echo "💡 Run 'git merge upstream/main' to pull in changes"; \
    else \
      echo "✓ Up to date with upstream"; \
    fi

# Watch for new upstream releases (tag-based)
[group("pr")]
check-release:
    @echo "=== Latest upstream release tags ==="
    git fetch --tags upstream
    git tag -l "v*" --sort=-v:refname | head -5

# Run pytest before merging new upstream commits
# Usage: just test-upstream  (after git merge upstream/main)
[group("pr")]
test-upstream:
    @echo "=== Running Python tests ==="
    python3 -m pytest tests/ -q --tb=no

[group("pr")]
pr-summarize:
    bun scripts/pr-summarize.ts --write
#   Structural analysis via the indexed knowledge graph.
#   See: playbooks/gitnexus-playbook.md

# 360-degree view of a symbol: callers, callees, processes
[group("gn")]
gn-context SYM:
    gitnexus context "{{ SYM }}" --repo TradingAgents

# Blast radius: what breaks if you change a symbol
[group("gn")]
gn-impact SYM:
    gitnexus impact "{{ SYM }}" --direction upstream --repo TradingAgents

# Re-index the repo (run after significant code changes)
[group("gn")]
gn-analyze:
    gitnexus analyze --force .

# Export symbol/file impact graph to DOT/SVG (--symbol or --file required)
[group("gn")]
gn-graph SYM-or-FILE:
    bun scripts/gitnexus-to-dot.ts --symbol {{ SYM-or-FILE }} --depth 1 --render || \
    bun scripts/gitnexus-to-dot.ts --file {{ SYM-or-FILE }} --render

# Generate key GitNexus graphs for the project (impact graphs for hotspots)
[group("gn")]
gn-diagrams:
    @echo "Generating GitNexus impact graphs..."
    bun scripts/gitnexus-batch.ts --render
    @echo ""
    @echo "Generated:"
    @ls -1 docs/diagrams/gn-impact-*.dot docs/diagrams/gn-file-*.dot 2>/dev/null || echo "  (no files yet)"

# ── Server lifecycle ────────────────────────────────────────────────────────
#   Start, stop, restart, and monitor the dashboard server.

# Show all service status
[group("srv")]
status:
    @echo "{{ CYAN }}●{{ NORMAL }} Checking service status..."
    bun scripts/server-lifecycle.ts status

# Start dashboard server (background daemon)
[group("srv")]
start:
    @echo "{{ GREEN }}▶{{ NORMAL }} Starting dashboard server..."
    bun scripts/server-lifecycle.ts start

# Stop dashboard server
[confirm("Stop the dashboard server?")]
[group("srv")]
stop:
    @echo "{{ RED }}■{{ NORMAL }} Stopping dashboard server..."
    bun scripts/server-lifecycle.ts stop

# Restart dashboard server
[group("srv")]
restart:
    @echo "{{ YELLOW }}↻{{ NORMAL }} Restarting dashboard server..."
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

# ── Hooks: git workflow automation ─────────────────────────────────────────

# Install pre-push hook that auto-regenerates diagrams
[group("hooks")]
install-hooks:
    bash scripts/install-pre-push-hook.sh

# Explicit push with diagram regen (alternative to pre-push hook)
[group("hooks")]
push:
    bun scripts/push-with-diagrams.ts

# ── Barnacle Scrubber ──────────────────────────────────────────────────────
#   Barnacle removal: mechanical + LLM semantic scan, drydock quarantine,
#   slim condensation, anomaly escalation, and restore.
#   See: playbooks/conventions-playbook.md (barnacle section)

# Mechanical scan only (no LLM), print report, no writes
[group("barnacle")]
bs-scan:
    bun scripts/barnacle-scrubber.ts --report

# Show what would change, no file modifications
[group("barnacle")]
bs-dry-run:
    bun scripts/barnacle-scrubber.ts --dry-run

# Interactive: confirm each action before applying (mechanical only)
[group("barnacle")]
bs-scrub:
    bun scripts/barnacle-scrubber.ts

# Non-interactive: apply all mechanical fixes without prompting
[group("barnacle")]
bs-auto:
    bun scripts/barnacle-scrubber.ts --auto

# LLM semantic scan + mechanical, dry-run (requires OPENROUTER_API_KEY)
[group("barnacle")]
bs-llm-dry-run:
    bun scripts/barnacle-scrubber.ts --llm --dry-run

# LLM semantic scan + mechanical, interactive apply
[group("barnacle")]
bs-llm-scrub:
    bun scripts/barnacle-scrubber.ts --llm

# Full scrub: mechanical + LLM scan + slim, interactive
[group("barnacle")]
bs-full-dry-run:
    bun scripts/barnacle-scrubber.ts --llm --slim --dry-run

# Full scrub: mechanical + LLM scan + slim, auto-apply
[group("barnacle")]
bs-full:
    bun scripts/barnacle-scrubber.ts --llm --slim --auto

# Restore a barnacle from drydock (interactive)
# Usage: just bs-restore decisions/drydock/2026-05-24/playbooks/foo.md/BR-001/block.md
[group("barnacle")]
bs-restore PATH:
    bun scripts/barnacle-scrubber.ts --restore "{{ PATH }}"

# Auto-restore a barnacle from drydock
[group("barnacle")]
bs-restore-auto PATH:
    bun scripts/barnacle-scrubber.ts --restore "{{ PATH }}" --auto

# Show deletion log
[group("barnacle")]
bs-log:
    @if [ -f decisions/drydock/DELETION_LOG.md ]; then \
        cat decisions/drydock/DELETION_LOG.md; \
    else \
        echo "No deletion log found at decisions/drydock/DELETION_LOG.md"; \
    fi
