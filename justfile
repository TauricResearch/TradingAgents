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

# Shortcut reference: just <letter> → group menu
[group("meta")]
shortcuts:
    #!/usr/bin/env bash
    echo ""
    echo "══════════════════════════════════════════════════════════════════════"
    echo "  NAVIGATION SHORTCUTS  —  just <letter> to see a group's recipes"
    echo "══════════════════════════════════════════════════════════════════════"
    echo ""
    printf "  %-6s  %-28s  %s\n" "Letter" "Group" "Purpose"
    echo "  ────────────────────────────────────────────────────────────────────"
    printf "  %-6s  %-28s  %s\n" "b"     "Bun"              "TypeScript server tooling"
    printf "  %-6s  %-28s  %s\n" "p"     "Python"           "tradingagents package, analysis"
    printf "  %-6s  %-28s  %s\n" "db"    "Database"         "SQLite backup, stats, maintenance"
    printf "  %-6s  %-28s  %s\n" "r"     "Run"              "Business operations (analyze, sync)"
    printf "  %-6s  %-28s  %s\n" "s"     "Seed"             "Database seeding"
    printf "  %-6s  %-28s  %s\n" "x"     "Test"             "Test DB, development tools"
    printf "  %-6s  %-28s  %s\n" "d"     "Diagrams"         "Render .dot / .mmd to .svg"
    printf "  %-6s  %-28s  %s\n" "pr"    "PR"               "GitHub pull request helpers"
    printf "  %-6s  %-28s  %s\n" "hk"    "Hooks"            "Git workflow automation"
    printf "  %-6s  %-28s  %s\n" "gn"    "GitNexus"         "Code knowledge graph"
    printf "  %-6s  %-28s  %s\n" "srv"   "Server"           "Dashboard lifecycle"
    printf "  %-6s  %-28s  %s\n" "t"     "td"               "Task management"
    printf "  %-6s  %-28s  %s\n" "m"     "Meta"             "Project info, help, state"
    printf "  %-6s  %-28s  %s\n" "h"     "hLedger"          "Plain-text accounting"
    printf "  %-6s  %-28s  %s\n" "lab"   "Lab"              "Terminal experiments"
    echo ""
    echo "  Also: just info  — full project state"
    echo "        just help  — project orientation guide"
    echo ""

# ── Registry: briefs, debriefs, playbook indexes (JSONL + jq) ────────────────
#   Query the project's knowledge base. All indexes are JSONL: one JSON object per line.
#   See: src/server/lib/registry-types.ts for schema definitions.

# List all decisions (human-readable)
[group("reg")]
reg-decisions:
    bun scripts/reg-list.ts decisions

# List all briefs (human-readable)
[group("reg")]
reg-briefs:
    bun scripts/reg-list.ts briefs

# List all debriefs (human-readable)
[group("reg")]
reg-debriefs:
    bun scripts/reg-list.ts debriefs

# List project playbooks that are mining candidates (portable patterns to extract)
[group("reg")]
reg-mining:
    @jq -r 'select(.meta.mining_candidate == true) | "\(.file) — \(.meta.mining_note)"' playbooks/REGISTRY.jsonl

# List all docs (human-readable)
[group("reg")]
reg-docs:
    bun scripts/reg-list.ts docs

# List conceptual lexicon (terms, heuristics, definitions)
[group("reg")]
reg-lexicon:
    bun scripts/reg-list.ts lexicon

# List CTX conceptual lexicon (converted to merged schema)
[group("reg")]
reg-lexicon-ctx:
    bun scripts/reg-list.ts lexicon-ctx

# Show consolidated project state (briefs, debriefs, tasks, docs)
[group("reg")]
reg-state:
    bun scripts/reg-state.ts

# Validate all registries (required fields, no duplicates)
[group("reg")]
reg-check:
    bun scripts/reg-check.ts

# Check all indexes are up-to-date (files vs entries)
[group("reg")]
reg-sync:
    bun scripts/reg-sync.ts --all

# Fix stale/missing index entries (regenerate from disk)
[group("reg")]
reg-sync-fix:
    bun scripts/reg-sync.ts --all --fix

# Mine a playbook from project to canonicals (dry-run by default, --apply to confirm)
[group("reg")]
reg-mine FILE:
    bun scripts/reg-mine.ts {{FILE}}

# Import a canonical playbook into the project (dry-run: add --apply to confirm)
[group("reg")]
reg-import FILE:
    bun scripts/reg-import.ts {{FILE}}

# Promote a playbook — see what would be stripped (add --apply to delegate to reg-mine)
[group("reg")]
reg-promote FILE *FLAGS="":
    bun scripts/reg-promote.ts {{FILE}} {{FLAGS}}

# Sync script index: list all scripts with portability classification
[group("reg")]
reg-scripts:
    bun scripts/reg-sync-scripts.ts

# Sync script index — regenerate from disk
[group("reg")]
reg-scripts-fix:
    bun scripts/reg-sync-scripts.ts --fix

# Scan for barnacles (stale conventions, misdirecting docs)
[group("reg")]
barnacle-scan:
    bun scripts/barnacle-scan.ts

# Watch for barnacles (runs scan every N minutes, logs to ~/.tradingagents/barnacle-watch.log)
[group("reg")]
barnacle-watch MINUTES="60":
    @echo "{{YELLOW}}⏱{{NORMAL}} Starting barnacle watcher (interval: {{MINUTES}} min)"
    @echo "{{YELLOW}}⏱{{NORMAL}} Press Ctrl+C to stop. Logs: ~/.tradingagents/barnacle-watch.log"
    while true; do \
        echo "[$(date -Iseconds)] Scanning..." >> ~/.tradingagents/barnacle-watch.log; \
        bun scripts/barnacle-scan.ts --mechanical >> ~/.tradingagents/barnacle-watch.log 2>&1; \
        echo "---" >> ~/.tradingagents/barnacle-watch.log; \
        sleep $(({{MINUTES}} * 60)); \
    done

set shell := ["bash", "-o", "pipefail", "-c"]
set positional-arguments := true
set dotenv-load := true

# ── Modules ────────────────────────────────────────────────────────────────
mod hledger

# Group navigation shortcuts — just <letter> to list that group's recipes
# Uses scripts/just-group-menu.ts for formatted output with common-marker indicators.
[group("nav")]
b:  # Bun — TypeScript server tooling
    @bun scripts/just-group-menu.ts bun

[group("nav")]
p:  # Python — tradingagents package, tests, analysis
    @bun scripts/just-group-menu.ts python

[group("nav")]
h:  # hLedger — plain-text accounting
    @just hledger::default

[group("nav")]
t:  # td — task management
    @bun scripts/just-group-menu.ts td

[group("nav")]
db:  # Database — backup, stats, maintenance
    @bun scripts/just-group-menu.ts db

[group("nav")]
m:  # Meta — project info, help, state
    @bun scripts/just-group-menu.ts meta

[group("nav")]
r:  # Run — business operations (analyze, portfolio, sync, seed)
    @bun scripts/just-group-menu.ts run

[group("nav")]
s:  # Seed — database seeding and partial resets
    @bun scripts/just-group-menu.ts seed

[group("nav")]
x:  # Test — test DB and development tools
    @bun scripts/just-group-menu.ts test

[group("nav")]
d:  # Diagrams — render .dot / .mmd to .svg
    @bun scripts/just-group-menu.ts diagrams

[group("nav")]
pr:  # PR — GitHub pull request helpers
    @bun scripts/just-group-menu.ts pr

[group("nav")]
hk:  # Hooks — git workflow automation
    @bun scripts/just-group-menu.ts hooks

# Aliases for common hledger recipes (backward compat)
alias hl := hledger::hl
alias hl-cash := hledger::hl-cash
alias hl-holdings := hledger::hl-holdings
alias hl-prices := hledger::hl-prices
alias hl-register := hledger::hl-register
alias hl-net-worth := hledger::hl-net-worth

# Type-check + lint + custom gates
[group("bun")]
[doc("Run biome + tsc + db-usage gate. Must pass before commits.")]
check:
    bunx biome check .
    tsc --project tsconfig.server.json --noEmit
    bun scripts/check-database-usage.ts
    bun scripts/reg-sync.ts --all

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

# Run CLI command smoke tests
[group("bun")]
test-cli:
    bun test tests/cli-commands.test.ts

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

# ── Agent: Multi-Agent Coordination ─────────────────────────────────────────
#   Scripts live in scripts/agent-*.ts. These just recipes are the thin facade.
#   Full protocol: playbooks/td-playbook.md

# Full session startup: git state + td session + what's in flight
[group("agent")]
agent-orient:
    bun scripts/agent-orient.ts

# Compact orientation: one line per section
[group("agent")]
agent-orient-c:
    bun scripts/agent-orient.ts --compact

# What should I work on next?
[group("agent")]
agent-next:
    bun scripts/agent-orient.ts --next

# Claim a task before touching any files (checks collision, labels session)
[group("agent")]
agent-claim ID:
    bun scripts/agent-claim.ts {{ID}}

# Force-claim (bypass collision check — use when taking over from another agent)
[group("agent")]
agent-claim-force ID:
    bun scripts/agent-claim.ts {{ID}} --force

# Log progress to a task
[group("agent")]
agent-log ID *MSG:
    bun scripts/agent-log.ts {{ID}} {{MSG}}

# Log a blocker
[group("agent")]
agent-blocked ID *MSG:
    bun scripts/agent-log.ts {{ID}} {{MSG}} --blocked

# Structured handoff: done/remaining/decisions captured before closing
[group("agent")]
agent-handoff ID *MSG="handoff":
    bun scripts/agent-handoff.ts {{ID}} --note "{{MSG}}"

# Full handoff with explicit done/remaining
[group("agent")]
agent-handoff-full ID:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Enter done items (one per line, empty to finish):"
    done_file=$(mktemp)
    while read -r line; do [[ -z "$line" ]] && break; echo "$line" >> "$done_file"; done
    echo "Enter remaining items (one per line, empty to finish):"
    remaining_file=$(mktemp)
    while read -r line; do [[ -z "$line" ]] && break; echo "$line" >> "$remaining_file"; done
    bun scripts/agent-handoff.ts {{ID}} --done @"$done_file" --remaining @"$remaining_file"
    rm -f "$done_file" "$remaining_file"

# Sync state: git vs main + file collisions
[group("agent")]
agent-sync:
    bun scripts/agent-sync.ts

# Show file collisions only
[group("agent")]
agent-collisions:
    bun scripts/agent-sync.ts --collisions

# End session cleanly: handoff all in-progress tasks, clear claims
[group("agent")]
agent-end:
    @echo "Checking in-progress tasks..."
    @td list --status in_progress 2>/dev/null | head -20
    @echo ""
    @echo "Run handoffs manually, then: td ws handoff && td ws end"
    @echo "Full guide: playbooks/td-playbook.md"

# ── Run: business operations ────────────────────────────────────────────────
#   Core day-to-day operations. Ordered by frequency of use.

# Run analysis on TKA.DE (default test ticker)
[group("run")]
analyze-tka DEBATES="1":
    just analyze TKA.DE today {{DEBATES}}

# Show portfolio holdings via CLI (SQLite only, no server required)
[group("run")]
portfolio:
    bun run src/cli/main.ts portfolio

# Check exit plan alerts for all positions
[group("run")]
alerts:
    bun run src/cli/main.ts alerts

check-alerts FIRE="":
    bun scripts/check-alerts.ts {{FIRE}}


# Show contingency buylist — watchlist items with fair value targets
[group("run")]
buylist:
    bun run src/cli/main.ts buylist

# Run TradingAgents research pipeline and extract buylist values
[group("run")]
research TICKER:
    bun run src/cli/main.ts research {{TICKER}}

# Show portfolio holdings (LIVE, uses hledger + SQLite via dashboard)
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

# Seed LIVE SQLite database (positions, signals, analyses, watchlist, prices)
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
    @bun scripts/just-group-menu.ts gn

[group("nav")]
srv:  # Server — lifecycle management
    @bun scripts/just-group-menu.ts srv

# ── Server lifecycle ────────────────────────────────────────────────────────
#   Start, stop, restart, and monitor the dashboard server.

# Show all service status
[group("srv")]
[doc("Gum-formatted status table for Dashboard, SQLite, GitNexus.")]
status:
    @echo "{{CYAN}}●{{NORMAL}} Checking service status..."
    bun scripts/server-lifecycle.ts status

# Start dashboard server (background daemon)
[group("srv")]
[doc("Start dashboard as daemon. Writes PID to ~/.tradingagents/server.pid")]
start:
    @echo "{{GREEN}}▶{{NORMAL}} Starting dashboard server..."
    bun scripts/server-lifecycle.ts start

# Stop dashboard server
[confirm("Stop the dashboard server?")]
[group("srv")]
[doc("Graceful stop (SIGTERM → wait → SIGKILL fallback).")]
stop:
    @echo "{{RED}}■{{NORMAL}} Stopping dashboard server..."
    bun scripts/server-lifecycle.ts stop

# Restart dashboard server
[group("srv")]
[doc("Rotate logs, stop, start.")]
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
    @bun scripts/just-group-menu.ts lab

# ── Hooks: git workflow automation ─────────────────────────────────────────

# Install pre-push hook that auto-regenerates diagrams
[group("hooks")]
install-hooks:
    bash scripts/install-pre-push-hook.sh

# Explicit push with diagram regen (alternative to pre-push hook)
[group("hooks")]
push:
    bun scripts/push-with-diagrams.ts

alias a := analyze
alias l := lint
alias sc := shortcuts
