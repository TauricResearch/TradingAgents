# TradingAgents Dashboard Fork

A **Bun/Hono web dashboard** wrapping [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) — the upstream multi-agent LLM trading framework.

This fork adds:
- **Web dashboard** (Bun/Hono, TypeScript, HTMX)
- **hLedger** as the single source of truth for positions and cash
- **Isolated test environment** (`TEST_MODE=1`)
- **TypeScript scripts** for all non-Python utilities
- **Playbooks** for project conventions (SQLite, hledger, td, diagrams)

> **This is a fork, not a feature branch.** The dashboard never modifies the upstream
> `tradingagents` Python package — communication is exclusively via subprocess bridge.

---

## Quick Start

```bash
# Prerequisites
bun --version        # v1.x
python --version     # 3.11+
hledger --version    # 1.x

# Install
bun install
just install         # Python venv + tradingagents deps

# Run
just serve           # Dashboard at http://localhost:3000
```

### First run

```bash
just seed-test-journal  # Seed hledger test journal
just seed-db            # Seed SQLite dev database
just diagrams           # Render SVG diagrams from .dot sources
just check             # Lint + type-check
```

---

## Architecture

```
Browser (HTMX + SSE)
    ↕ HTMX + SSE
Bun/Hono Server (Port 3000)              Python Subprocess
    ↕ SQLite WAL (portfolio.db)         ↕ TradingAgentsGraph
    ↕ hledger (read-only)                  ↕ yfinance
    ↕ exit plans (YAML)                    ↕ decision memory log
    ↕ post-mortems (Markdown)
```

Full diagram: [`docs/diagrams/system-overview.svg`](docs/diagrams/system-overview.svg)
Full docs: [`ARCHITECTURE.md`](ARCHITECTURE.md) · [`AGENTS.md`](AGENTS.md)

---

## What's different from upstream

| Feature | This fork | Upstream |
|---------|-----------|----------|
| Interface | Bun/Hono web dashboard | CLI only |
| Positions | hLedger journal (SSOT) | SQLite only |
| Testing | Isolated `TEST_MODE=1` | None |
| Scripts | TypeScript (Bun native) | Python only |
| Diagrams | DOT/Graphviz (SVG) | Mermaid (unreliable) |
| Docs | Playbooks, ARCHITECTURE.md | CHANGELOG |

---

## Key Commands

```bash
# Dashboard
just serve              # DEV mode  (port 3000)
just serve-test         # TEST mode (isolated DB + hledger)

# Database
just seed-db           # Seed dev SQLite
just seed-test-db      # Seed test SQLite
just reset-portfolio    # Reset dev state

# Scripts
just diagrams          # Render .dot → .svg (graphviz + mmdc)
bun scripts/get_price.ts AAPL        # Yahoo Finance price
just seed-db --exit-plans           # Exit plans (YAML) only

# Analysis
just analyze TKA.DE               # Run full analysis (TradingAgentsGraph)
just summarize-all                # LLM summarisation (OpenRouter)
just check                       # biome lint + tsc
just test-smoke PROVIDER=openai   # Smoke tests
```

Full command list: `just --list`

---

## Project Structure

```
TradingAgents/
├── server/                 # Bun/Hono dashboard
│   ├── index.tsx           # Entry point, routes, graceful shutdown
│   ├── routes/             # API endpoints (12 modules)
│   └── views/              # HTMX SSR views (12 .tsx)
├── tradingagents/          # Upstream Python package (DO NOT MODIFY)
├── scripts/                # Utilities
│   ├── *.ts               # TypeScript (Bun native) — see scripts/README.md
│   └── py/                # Python (tradingagents dep)
│       ├── analyze_stream.py  # Bun→Python bridge
│       └── smoke_structured_output.py
├── docs/diagrams/         # .dot source + committed .svg
├── playbooks/             # Project conventions
├── tests/                 # Python smoke tests + hledger gate tests
├── Justfile               # Unified task runner
└── ARCHITECTURE.md        # System architecture (canonical)
```

---

## Scripts

TypeScript scripts (`bun scripts/*.ts`):

| Script | Purpose |
|--------|---------|
| `seed_database.ts` | Seed SQLite + exit plans + post-mortems |
| `summarize_analyses.ts` | OpenRouter LLM summarisation |
| `get_price.ts` | Yahoo Finance price + history |
| `portfolio-intel.ts` | Portfolio summary via HTTP |
| `render_diagrams.ts` | DOT/MMD → SVG |
| `extract_mermaid.ts` | Strip YAML front matter from MMD |

Python scripts (`python scripts/py/*.py`):

| Script | Purpose |
|--------|---------|
| `analyze_stream.py` | Bun→Python bridge (TradingAgentsGraph) |
| `smoke_structured_output.py` | Agent output smoke tests |

See [`scripts/README.md`](scripts/README.md) for full docs.

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TA_DASHBOARD_PORT` | `3000` | Dashboard HTTP port |
| `PORTFOLIO_DB` | `./portfolio.db` | DEV SQLite path |
| `TEST_MODE` | `0` | Set `1` for isolated test environment |
| `TEST_PORTFOLIO_DB` | `./test_portfolio.db` | Test SQLite path |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | `~/.tradingagents/memory/trading_memory.md` | Decision memory |
| `HLEDGER_FILE` | `~/.hledger.journal` | DEV hledger journal |
| `TEST_HLEDGER_FILE` | `~/.tradingagents/test_hledger.journal` | TEST hledger journal |

---

## Upstream

This fork is built on [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents).
Upstream README archived at [`archive/upstream/tauric-readme.md`](archive/upstream/tauric-readme.md).