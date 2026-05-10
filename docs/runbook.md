# TradingAgents Runbook

**Date:** 2026-05-10
**Status:** Active
**Audience:** Human operator running the TradingAgents system

---

## What This System Does

TradingAgents is a CLI-driven trading workbench. It combines:
- **LLM analysis** — multi-agent research on a ticker via TradingAgents
- **Trade planning** — ATR-14 position sizing, bracket orders, stop/target calculation
- **IG demo execution** — place real orders (demo account only)
- **Portfolio tracking** — positions, P&L, watchlist, alerts
- **Dashboard** — web UI on port 3000

**Primary interface:** `just -f trading/justfile <recipe>`

All commands are executed from the project root (`/Users/petersmith/Dev/GitHub/TradingAgents`).

---

## Session Start Checklist

```bash
# 1. Confirm branch (never work on main)
git status && git branch -v

# 2. Set working directory
cd /Users/petersmith/Dev/GitHub/TradingAgents

# 3. Check system health
just -f trading/justfile status

# 4. Optional: start dashboard
just -f trading/justfile serve
# → http://localhost:3000
```

---

## CLI Reference

**Primary interface:** `just -f trading/justfile <recipe>`

Run from: `/Users/petersmith/Dev/GitHub/TradingAgents`

### Core Commands

| Recipe | What it does |
|--------|-------------|
| `just -f trading/justfile analyze <ticker>` | Run TradingAgents LLM analysis |
| `just -f trading/justfile plan <ticker>` | Generate trade plan (ATR, stop, targets, position size) |
| `just -f trading/justfile execute <ticker>` | Calculate plan + place IG demo order |
| `just -f trading/justfile research <ticker>` | Analyze + extract buylist values to watchlist |

### IG Trading (Demo)

| Recipe | What it does |
|--------|-------------|
| `ig-accounts` | List IG accounts with balances |
| `ig-search <query>` | Search IG markets by name/ticker |
| `ig-prices <epic>` | Fetch historical prices for an EPIC |
| `ig-positions` | List open IG positions |
| `ig-history` | IG activity and transaction history |
| `ig-buy <epic> <size> [stop] [limit]` | Place a market buy order |
| `ig-sell <deal-id>` | Close an open position by deal ID |

### Portfolio & Alerts

| Recipe | What it does |
|--------|-------------|
| `portfolio` | Holdings, P&L, cash summary |
| `alerts` | Exit plan alerts for all positions |
| `buylist` | Watchlist items with fair value targets |
| `buylist-fetch` | Fetch prices for buylist items |
| `watchlist` | Prospects being tracked but not owned |
| `signals [ticker]` | Latest AI-generated trading signals |
| `trades` | Trade history |

### Data & Config

| Recipe | What it does |
|--------|-------------|
| `sync <ticker>` | Sync prices from Yahoo Finance |
| `sync-all` | Sync prices for all open positions |
| `price <ticker>` | Quick price lookup |
| `backup` | Backup SQLite database |
| `config` | Show current config defaults |
| `config-set <key> <value>` | Set a config value |

### Key Flags

| Flag | Applies to | What |
|------|-----------|------|
| `--yes` | `execute` | Skip confirmation prompt |
| `--dry-run` | `execute` | Show plan + IG validation, no order |
| `--execute` | `analyze` | Chain analysis → execute after completion |
| `--debrief` | `analyze` | Save analysis output to debriefs/ |
| `--fetch` | `buylist`, `research` | Fetch prices from Yahoo Finance |

### Override Defaults

Recipes have sensible defaults. Override any parameter:

```bash
just -f trading/justfile plan AAPL account=50000 risk=0.02
just -f trading/justfile analyze NVDA debates=2
```

| Parameter | Default | Example |
|-----------|---------|---------|
| `ticker` | SPY | `analyze AAPL` |
| `account` | 75000 | `plan AAPL account=50000` |
| `risk` | 0.03 (3%) | `plan AAPL risk=0.02` |
| `debates` | 1 | `analyze AAPL debates=2` |

---

## End-to-End Workflow

### 1. Analyze → Plan → Execute

```bash
# Step 1: Run LLM analysis on a ticker
just -f trading/justfile analyze TKA.DE debates=2

# Step 2: Generate trade plan
just -f trading/justfile plan TKA.DE account=50000 risk=0.02

# Step 3: Preview the order (dry-run)
just -f trading/justfile plan-dry TKA.DE account=50000 risk=0.02

# Step 4: Execute on IG demo
just -f trading/justfile execute-yes TKA.DE account=50000 risk=0.02
```

### 2. Analyze + Execute in One Command

```bash
# Run analysis, parse decision, auto-execute on BUY/SELL signal
just -f trading/justfile analyze-exec-yes TKA.DE
```

If decision is `hold`, execution is skipped (use `execute-yes` to force it).

### 3. Check Portfolio + Alerts

```bash
just -f trading/justfile portfolio
just -f trading/justfile alerts
just -f trading/justfile buylist-fetch
just -f trading/justfile status
```

### 4. IG Demo Trading (Standalone)

```bash
# Authenticate and list accounts
just -f trading/justfile ig-accounts

# Search for a market
just -f trading/justfile ig-search FTSE

# Get current prices
just -f trading/justfile ig-prices IX.D.FTSE.CFD.IP

# Place a buy order (epic, size, stop points, limit points)
just -f trading/justfile ig-buy IX.D.FTSE.CFD.IP 0.5 50 100

# List open positions
just -f trading/justfile ig-positions

# Close a position
just -f trading/justfile ig-sell <deal-id>
```

---

## Dashboard

**Start:** `just -f trading/justfile serve`
**URL:** `http://localhost:3000`

**Routes:**
- `/` — Portfolio intelligence (hledger cash + SQLite positions)
- `/analyses` — Analysis history and reports
- `/signals` — Signal history with accuracy metrics
- `/watchlist` — Prospect tracking with fair value targets

Dashboard uses HTMX + server-side rendering. No client-side framework.

**Test mode:** `just -f trading/justfile serve-test` (uses test_portfolio.db)

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `PORTFOLIO_DB` | `./portfolio.db` | SQLite database path |
| `TEST_MODE` | `0` | Set `1` to use `test_portfolio.db` |
| `TA_DASHBOARD_PORT` | `3000` | Dashboard HTTP port |
| `OPENROUTER_API_KEY` | — | LLM provider (analysis requires this) |
| `IG_DEMO_API_KEY` | — | IG demo API key |
| `IG_DEMO_USERNAME` | — | IG demo username |
| `IG_DEMO_PASSWORD` | — | IG demo password |
| `HLEDGER_FILE` | `~/.hledger.journal` | hLedger accounting journal |
| `TRADINGAGENTS_MEMORY_LOG_PATH` | `~/.tradingagents/memory/trading_memory.md` | Decision memory log |

---

## Config Defaults

```bash
# View all defaults
just -f trading/justfile config

# Set account balance default
just -f trading/justfile config-set account 50000

# Set risk per trade default
just -f trading/justfile config-set risk 0.02

# View single key
just -f trading/justfile config-get account
```

Config stored in: `~/.tradingagents/config.json`

---

## IG Demo Credentials

Requires three env vars (set in shell or `.env`):

```bash
export IG_DEMO_API_KEY=your_api_key
export IG_DEMO_USERNAME=your_username
export IG_DEMO_PASSWORD=your_password
```

Or via `.env` file in project root.

**Demo endpoint:** `https://demo-api.ig.com/gateway/deal`

See `docs/ig-trading-guide.md` for full API documentation.

---

## Database

**Dev:** `./portfolio.db` (seeded with test data)
**Test:** `./test_portfolio.db` (active when `TEST_MODE=1`)

**Seed the database:**
```bash
cd /Users/petersmith/Dev/GitHub/TradingAgents
bun run scripts/seed_database.ts          # full reset
bun run scripts/seed_database.ts --prices  # prices only
bun run scripts/seed_database.ts --signals # signals only
```

**Backup:**
```bash
just -f trading/justfile backup
```

---

## Exit Plan Alerts

Exit plans are stored as YAML files in: `~/.tradingagents/positions/`

Format:
```yaml
ticker: AAPL
entry_price: 180.00
stop_loss: 155.00
targets:
  - price: 230.00      # Target 1
    date: 2025-08-01
  - price: 280.00      # Target 2
    date: 2025-11-01
```

`just -f trading/justfile alerts` reads these plans + current prices from the `prices` table.

**Sync prices first:**
```bash
just -f trading/justfile sync AAPL           # single ticker
just -f trading/justfile sync-all            # all positions
```

---

## Known Limitations

1. **Demo only.** IG credentials connect to demo environment. No live trading.
2. **US stocks on IG demo.** IG demo may reject 24-hour US stocks (null bid/offer). Use UK shares/indices for testing.
3. **Memory log.** Decision memory (`~/.tradingagents/memory/trading_memory.md`) is primitive — plain text with prompt injection. Not real model training.
4. **LLM non-determinism.** Same inputs → different outputs on reruns.
5. **24-hour stocks.** Margin and availability vary. Check `just -f trading/justfile ig-search FTSE` for current status.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| IG commands say "Missing credentials" | Set `IG_DEMO_API_KEY`, `IG_DEMO_USERNAME`, `IG_DEMO_PASSWORD` |
| No price data for ticker | `just -f trading/justfile sync <ticker>` |
| Database locked | `just -f trading/justfile serve-stop` (kills zombie bun processes) |
| Port 3000 occupied | `just -f trading/justfile serve-stop` or set `TA_DASHBOARD_PORT=8080` |
| Analysis fails | Check `OPENROUTER_API_KEY` is set; check `~/.tradingagents/memory/` exists |
| Not working | Verify you're in the project root: `cd /Users/petersmith/Dev/GitHub/TradingAgents` |

---

## Quick Reference

```bash
# Navigate to project
cd /Users/petersmith/Dev/GitHub/TradingAgents

# Check system
just -f trading/justfile status
just -f trading/justfile portfolio

# Analysis workflow
just -f trading/justfile analyze NVDA debates=2
just -f trading/justfile plan NVDA account=50000 risk=0.02
just -f trading/justfile plan-dry NVDA
just -f trading/justfile execute-yes NVDA

# Combined
just -f trading/justfile analyze-exec-yes NVDA

# Portfolio
just -f trading/justfile alerts
just -f trading/justfile buylist-fetch

# Data
just -f trading/justfile sync NVDA
just -f trading/justfile backup

# IG
just -f trading/justfile ig-accounts
just -f trading/justfile ig-buy <epic> <size> <stop> <limit>
just -f trading/justfile ig-positions

# Dashboard
just -f trading/justfile serve    # → http://localhost:3000
```