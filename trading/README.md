# TradingOperations

IG demo trading CLI. All operations run via `just -f trading/justfile <recipe>` from the project root.

```bash
# Full invocation
just -f trading/justfile <recipe>

# From project root (recommended)
cd /Users/petersmith/Dev/GitHub/TradingAgents
just -f trading/justfile <recipe>
```

---

## Quick Start

```bash
# Show all recipes
just -f trading/justfile

# Plan a trade
just -f trading/justfile plan AAPL

# Execute on IG demo
just -f trading/justfile execute AAPL --yes

# Portfolio + alerts
just -f trading/justfile portfolio
just -f trading/justfile alerts

# Run analysis
just -f trading/justfile analyze NVDA --debates 2

# Analyze + auto-execute on BUY signal
just -f trading/justfile analyze-exec NVDA --yes
```

---

## Recipe Groups

| Group | Recipes | Purpose |
|-------|---------|---------|
| `analyze` | `analyze`, `analyze-debrief`, `analyze-exec`, `analyze-exec-yes`, `research` | LLM analysis |
| `plan` | `plan`, `plan-dry`, `execute`, `execute-yes` | Trade planning + execution |
| `portfolio` | `portfolio`, `alerts`, `buylist`, `buylist-fetch`, `signals`, `trades`, `watchlist` | Portfolio management |
| `ig` | `ig-accounts`, `ig-search`, `ig-prices`, `ig-positions`, `ig-history`, `ig-buy`, `ig-sell`, `ig-login` | IG demo trading |
| `data` | `sync`, `sync-all`, `price`, `backup` | Price data + DB |
| `config` | `config`, `config-get`, `config-set` | CLI defaults |
| `status` | `status` | System health |
| `dashboard` | `serve`, `serve-test`, `serve-stop` | Web dashboard |

---

## Common Workflows

### Analyze → Plan → Execute

```bash
# Full pipeline with defaults (account=75000, risk=0.03)
just -f trading/justfile analyze NVDA --debates 2
just -f trading/justfile plan NVDA
just -f trading/justfile execute-yes NVDA

# Preview without executing
just -f trading/justfile plan-dry NVDA
```

### Analyze + Execute in One Command

```bash
# Runs analysis, parses decision, auto-executes on BUY/SELL
just -f trading/justfile analyze-exec-yes TKA.DE

# With debrief saved to debriefs/
just -f trading/justfile analyze-debrief TKA.DE --execute --yes
```

### Portfolio Check

```bash
just -f trading/justfile portfolio
just -f trading/justfile alerts
just -f trading/justfile buylist-fetch
just -f trading/justfile watchlist
```

### IG Demo Trading

```bash
just -f trading/justfile ig-accounts
just -f trading/justfile ig-search FTSE
just -f trading/justfile ig-buy IX.D.FTSE.CFD.IP 0.5 50 100   # epic, size, stop, limit
just -f trading/justfile ig-positions
just -f trading/justfile ig-sell <deal-id>
```

### Research Pipeline

```bash
# Analyze + extract buylist values (writes fair_value to watchlist)
just -f trading/justfile research NVDA --fetch
```

---

## Default Arguments

Recipes have sensible defaults — you can override any parameter:

| Parameter | Default | Example |
|-----------|---------|---------|
| `ticker` | SPY | `analyze AAPL` |
| `account` | 75000 | `plan AAPL account=50000` |
| `risk` | 0.03 (3%) | `plan AAPL risk=0.02` |
| `debates` | 1 | `analyze AAPL debates=2` |

```bash
# Override defaults
just -f trading/justfile plan AAPL account=50000 risk=0.02
just -f trading/justfile analyze NVDA debates=2
```

---

## Requirements

- `bun` (Bun runtime)
- `uv` (Python package manager — for TradingAgents analysis)
- IG demo credentials: `IG_DEMO_API_KEY`, `IG_DEMO_USERNAME`, `IG_DEMO_PASSWORD`
- `OPENROUTER_API_KEY` for LLM analysis

---

## Config Defaults

```bash
just -f trading/justfile config                    # show all
just -f trading/justfile config-get account         # get single value
just -f trading/justfile config-set risk 0.02        # set value
```

Config stored in: `~/.tradingagents/config.json`

---

## Dashboard

```bash
# Start → http://localhost:3000
just -f trading/justfile serve

# Test mode (uses test_portfolio.db)
just -f trading/justfile serve-test

# Stop stale processes
just -f trading/justfile serve-stop
```

See `docs/runbook.md` for full operations manual.