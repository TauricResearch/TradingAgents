# TradingAgents

Multi-agent LLM trading framework + web dashboard.

## Two systems in one repo

| Directory | System | Description |
|-----------|--------|-------------|
| `tradingagents/` | Python CLI | `tradingagents analyze`, LangGraph workflow |
| `src/server/` | Bun/Hono | Web dashboard on port 3000 |

## Quick start

```bash
just install      # Install Python deps (uv sync)
just seed-db      # Seed DEV SQLite database
just serve        # Start dashboard at http://localhost:3000
```

## Common workflows

| Command | What it does |
|---------|-------------|
| `just analyze TKA.DE` | Run analysis on a ticker (date=today, debates=1) |
| `just analyze AAPL today 3` | Full: ticker, date, debate rounds |
| `just check` | Full CI gate: lint + type check |
| `just lint-fix` | Auto-fix Biome lint errors |
| `just test-smoke` | Run pytest suite |
| `just portfolio-intel` | Portfolio holdings (hledger + SQLite) |
| `just sync-prices` | Sync prices for open positions |

## Key docs

| File | Purpose |
|------|---------|
| `./AGENTS.md` | Agent identity + rules (Scottish Enlightenment) |
| `./PLAYBOOK.md` | User guide for running analyses |
| `./ARCHITECTURE.md` | System design reference |
| `./CHANGELOG.md` | Release history |
| `./playbooks/` | Tool-specific conventions (sqlite, hledger, etc.) |
| `./debriefs/` | Post-work retrospectives |

## Troubleshooting

```bash
just test-reset                      # Wipe and recreate test DB
just lint-fix                        # Fix most Biome errors
just check                           # Reveal remaining lint + TS errors
bun run scripts/sync-prices.ts --all # Catch-up stale prices
```