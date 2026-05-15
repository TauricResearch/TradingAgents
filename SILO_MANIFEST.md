# TradingAgents Silo Manifest

**Purpose:** Single source of truth for agent orientation. When an agent spins up in this silo, all assets should be findable here.

**First step:** `just orient` — shows branch, git status, and current session tasks.

---

## Getting Started

1. `just orient` — branch, git status, session tasks
2. `just check` — run all quality gates (biome, tsc, db usage, import boundaries, registry sync)
3. `bun run src/server/index.tsx` — start dashboard on port 3000
4. `bun src/cli/main.ts --help` — list CLI commands

---

## Asset Map

| Asset | Location | Description | Owner |
|-------|----------|-------------|-------|
| **Project identity** | `AGENTS.md` | Edinburgh Protocol rules, Scottish Enlightenment identity, task management protocol | project |
| **Task runner** | `justfile` | 90 recipes for lint, serve, test, sync, registry, etc. Run `just --list --groups` for full list | project |
| **Task DB** | `~/.td/*.jsonl` | TD session data — tasks, handoffs, reviews, logs | system |
| **Architecture** | `ARCHITECTURE.md` | System design, two-system model (Python package + TS dashboard) | project |
| **Readme** | `README.md` | Project overview and quick start | project |
| **Briefs registry** | `briefs/INDEX.jsonl` | All briefs (open/done/active) — see `briefs/*.md` for details | project |
| **Playbooks registry** | `playbooks/REGISTRY.jsonl` | All playbooks — see `playbooks/*.md` for details | project |
| **Debriefs registry** | `debriefs/INDEX.jsonl` | All debriefs — see `debriefs/reviews/` for details | project |
| **Docs registry** | `docs/INDEX.jsonl` | All documentation | project |
| **Code registry** | `code/INDEX.jsonl` | All source files with descriptions | project |
| **CLI entry** | `src/cli/main.ts` | Unified trading CLI — `bun src/cli/main.ts --help` | project |
| **CLI commands** | `src/cli/commands/` | 42 commands: analyze, plan, execute, alerts, ig, etc. | project |
| **Server entry** | `src/server/index.tsx` | Bun/Hono dashboard server — HTMX + server-rendered HTML | project |
| **Server routes** | `src/server/routes/` | API routes: /api/positions, /api/analyze, /api/analyses, etc. | project |
| **Server views** | `src/server/views/` | HTMX-rendered page components | project |
| **Server lib** | `src/server/lib/` | Shared server utilities: alerts, benchmarks, governance, telegram | project |
| **Shared lib** | `src/lib/` | DatabaseFactory, IG client, trade calculator, settings, logger | project |
| **Python package** | `tradingagents/` | Multi-agent trading analysis pipeline (Python 3.13) | upstream |
| **Python bridge** | `scripts/py/analyze_stream.py` | SSE-streaming analysis runner — spawns Python subprocess | project |
| **Utility scripts** | `scripts/` | sync-prices, check-alerts, reg.ts, etc. | project |
| **Lab scripts** | `scripts/lab/` | Experimental utilities — not in CI gates | project |
| **Tests** | `tests/` | Bridge tests (TypeScript + Python) | project |
| **hledger journal** | `journal.hledger` | Accounting data — holdings, cash, transactions | user |
| **Dashboard DB** | `portfolio.db` (or `test_portfolio.db`) | SQLite: positions, prices, signals, analyses, alerts | project |
| **Settings** | `~/.tradingagents/` | User config, governance rules, positions YAML | user |

---

## Override Relationships

- `TradingAgents/AGENTS.md` **overrides** `~/.pi/agent/AGENTS.md` for all sessions in this repo
- Project-level brief files override the index — check `briefs/` directory
- `src/lib/` is the shared layer — CLI and server both import from here

---

## Key Conventions

| Convention | Location | Description |
|------------|----------|-------------|
| Database access | `src/lib/db.ts` | `DatabaseFactory` only — never `new Database()` |
| Import boundaries | `src/lib/*` → `src/` | CLI imports from `@lib/*` only, not `@server/*` |
| Logging | `src/lib/logger.ts` | Pino logger — use `cliLogger` for CLI, `logger` for server |
| CI gate | `just check` | All quality gates must pass before commit |
| Task management | `td` CLI | Use `td start`, `td log`, `td handoff`, `td review` workflow |
| Registry sync | `bun scripts/reg.ts sync` | Sync indexes after adding briefs/playbooks/debriefs |

---

## Quick Reference

```bash
# Orient
just orient

# Check quality
just check

# Serve dashboard
just serve

# Run analysis
trading analyze AAPL

# Plan trade
trading plan AAPL --risk 0.02

# Check alerts
trading alerts check

# Sync prices
bun scripts/sync-prices.ts --ticker AAPL

# Run tests
bun test
```