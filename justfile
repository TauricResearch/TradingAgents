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
check:                      # Full CI gate: lint + type-check server
    bunx biome check .
    tsc --project tsconfig.server.json --noEmit

[group("bun")]
serve:                      # Start dashboard server
    pkill -9 -f bun 2>/dev/null || true
    bun run server/index.tsx

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
    source .venv/bin/activate && python scripts/analyze.py '{{TICKER}}' --date '{{DATE}}' --debates {{DEBATES}}

[group("python")]
summarize TICKER="":          # Generate LLM summaries for analyses (add --all to regenerate)
    {{if TICKER != '' { '.venv/bin/python scripts/summarize_analyses.py --ticker ' + TICKER } else { '.venv/bin/python scripts/summarize_analyses.py' }}}

[group("python")]
summarize-all:                # Regenerate all LLM summaries
    source .venv/bin/activate && python scripts/summarize_analyses.py --all

[group("python")]
test-smoke:                 # Run test suite (all fast unit tests)
    uv run pytest tests/ -v

[group("python")]
test-quick PROVIDER="openai":  # Quick structured output test (openai, google, anthropic, deepseek)
    .venv/bin/python scripts/smoke_structured_output.py {{PROVIDER}}

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
seed-db:                     # Seed SQLite database with simulation data (all tables)
    .venv/bin/python scripts/seed_database.py

[group("convenience")]
seed-db-positions:           # Seed positions only
    .venv/bin/python scripts/seed_database.py --positions

[group("convenience")]
seed-db-signals:             # Seed signals only
    .venv/bin/python scripts/seed_database.py --signals

[group("convenience")]
seed-db-exit-plans:          # Seed exit plans (YAML) only
    .venv/bin/python scripts/seed_database.py --exit-plans

[group("convenience")]
seed-db-post-mortems:        # Seed post-mortems only
    .venv/bin/python scripts/seed_database.py --post-mortems

[group("convenience")]
seed-all:                    # Full seed: hLedger journal + DB + exit plans + post-mortems
    just seed-test-journal
    just seed-db

[group("hledger")]
hl:                         # Holdings summary
    hledger -f "${HLEDGER_FILE:-~/.hledger.journal}" balance --tree --value end

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
