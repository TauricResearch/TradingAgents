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
    {{if TICKER != '' { 'python scripts/summarize_analyses.py --ticker ' + TICKER } else { 'python scripts/summarize_analyses.py' }}}

[group("python")]
summarize-all:                # Regenerate all LLM summaries
    source .venv/bin/activate && python scripts/summarize_analyses.py --all

[group("python")]
test-smoke:                 # Smoke tests only
    .venv/bin/python -m pytest tests/ -v -m smoke

[group("python")]
test-quick:                 # Quick structured output test
    .venv/bin/python scripts/smoke_structured_output.py

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

alias a := analyze
alias l := lint
