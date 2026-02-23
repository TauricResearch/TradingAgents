# TradeDog — Design Reference

*All architecture patterns, code snippets, schemas, and design decisions for TradeDog.
Referenced by [TradeDog_Roadmap.md](TradeDog_Roadmap.md) — use the roadmap for task tracking, use this doc for implementation details.*

---

## Table of Contents

- [Architecture Target](#architecture-target)
- [Data Source Strategy](#data-source-strategy)
- [Watchlist Design](#watchlist-design)
- [Market Hours and Scheduling](#market-hours-and-scheduling)
- [Execution Layer Architecture](#execution-layer-architecture)
- [Broker Interface](#broker-interface)
- [Position Sizing Formula](#position-sizing-formula)
- [Conviction Scoring Design](#conviction-scoring-design)
- [Auto-Buy Rules](#auto-buy-rules)
- [Agent Prompt Additions](#agent-prompt-additions)
- [Exit Conditions and Rules](#exit-conditions-and-rules)
- [Monitor Loop](#monitor-loop)
- [Trailing Stop Implementation](#trailing-stop-implementation)
- [Reversal Detection](#reversal-detection)
- [Portfolio Guard Design](#portfolio-guard-design)
- [Database Schema](#database-schema)
- [Dashboard Specs](#dashboard-specs)
- [Target File Structure](#target-file-structure)
- [Broker Setup Commands](#broker-setup-commands)
- [Cost Estimate](#cost-estimate)
- [US Regulatory Note](#us-regulatory-note)

---

## Architecture Target

```
[Watchlist Scanner]
       |
[Research Pipeline] <-- Fundamentals / Sentiment / News / Technical
       |
[Bull vs Bear Debate]
       |
[Trader -> Risk Manager -> Fund Manager]
       |
  Conviction Score
       |
[Auto-Buy Engine] <--> [Broker API: Alpaca / IBKR]
       |
[Position Monitor -- runs every N minutes]
  |-- Profit target hit -> SELL
  |-- Trailing stop triggered -> SELL
  |-- Reversal signal detected -> SELL
  |-- Time-based exit (optional)
       |
[Trade Logger + Dashboard]
```

---

## Data Source Strategy

| Source | Use Case | Cost | Notes |
|---|---|---|---|
| FinnHub | Real-time quotes, news, insider trades | Free tier | Already wired in |
| `yfinance` | OHLCV history, fundamentals fallback | Free | Add as secondary/fallback |
| Polygon.io | Higher-quality tick data if needed later | Paid | Skip for now |
| Alpha Vantage | Alternative fundamentals | Free tier | Keep as backup |

Both FinnHub and yfinance have excellent US coverage. yfinance is the primary fallback when FinnHub returns empty or errors.

---

## Watchlist Design

Starter watchlist (~36 quality tickers across sectors):

```json
{
  "large_cap": ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "JPM", "UNH", "V", "MA"],
  "growth": ["CRWD", "SNOW", "NET", "DDOG", "SMCI", "ARM", "PLTR"],
  "value": ["BRK-B", "JNJ", "PG", "KO", "WMT", "HD", "MCD"],
  "financials": ["GS", "MS", "BAC", "C", "WFC"],
  "energy": ["XOM", "CVX", "COP", "SLB"]
}
```

**Liquidity Filter** — only analyze stocks with sufficient volume to avoid slippage:

```python
MIN_AVG_DAILY_VOLUME = 1_000_000   # 1M shares/day minimum
MIN_MARKET_CAP = 2_000_000_000     # $2B market cap minimum
```

---

## Market Hours and Scheduling

- NYSE/NASDAQ: 9:30 AM - 4:00 PM ET
- Pre-market analysis run: 8:00-9:15 AM ET (agents analyze, build signals)
- Market open execution window: 9:30-10:30 AM ET (buy signals fire here)
- Monitoring loop: runs every 5 min during market hours
- After-hours: position review, log summary, prep next day's watchlist

---

## Execution Layer Architecture

New module: `execution/`

```
execution/
├── broker_interface.py    <-- Abstract base class
├── alpaca_broker.py       <-- Alpaca implementation
├── ibkr_broker.py         <-- IBKR implementation (Phase 7)
├── paper_broker.py        <-- Local simulation (no API needed)
└── order_manager.py       <-- Order lifecycle tracking
```

Start with `PaperBroker` — a pure Python simulation that tracks positions in a local SQLite database. This lets you test the full loop without any API dependency.

---

## Broker Interface

Define this first. All broker implementations (Paper, Alpaca, IBKR) implement this:

```python
class BrokerInterface:
    def place_market_buy(self, ticker: str, qty: int) -> Order: ...
    def place_market_sell(self, ticker: str, qty: int) -> Order: ...
    def get_positions(self) -> list[Position]: ...
    def get_account(self) -> AccountInfo: ...
    def cancel_order(self, order_id: str) -> bool: ...
```

---

## Position Sizing Formula

Start simple. Scale by conviction, cap at a percentage of account value:

```python
def calculate_position_size(account_value, conviction_score, price, max_position_pct=0.05):
    max_dollars = account_value * max_position_pct
    dollars_to_invest = max_dollars * conviction_score
    shares = int(dollars_to_invest / price)
    return max(1, shares)
```

---

## Conviction Scoring Design

The agents currently produce a BUY/SELL/HOLD decision with rationale. Extend this to produce a **conviction score (0-100)**.

**Weighted scoring approach:**

```python
CONVICTION_WEIGHTS = {
    "technical":    0.25,   # RSI, MACD, moving average signals
    "fundamental":  0.25,   # P/E, growth, financial health
    "sentiment":    0.20,   # Social/news mood
    "bull_bear":    0.30,   # Debate outcome (most decisive)
}

def calculate_conviction(agent_signals: dict) -> float:
    score = 0
    for agent, weight in CONVICTION_WEIGHTS.items():
        # Each agent returns -1.0 (strong sell) to +1.0 (strong buy)
        score += agent_signals[agent] * weight
    return score  # -1.0 to +1.0
```

---

## Auto-Buy Rules

```python
BUY_THRESHOLD = 0.65      # Must have >65% conviction to buy
MIN_AGENTS_AGREE = 3      # At least 3 of 4 analyst agents must agree direction
MAX_POSITIONS = 10        # Never hold more than 10 stocks at once
COOLDOWN_HOURS = 24       # Don't re-analyze same stock within 24h of last trade
```

---

## Agent Prompt Additions

Add to each analyst agent's system prompt for structured output parsing:

```
At the end of your analysis, always output a JSON block:
{"signal": "BUY|SELL|HOLD", "conviction": 0.85, "key_reason": "..."}
```

Then parse this structured output in the graph state.

---

## Exit Conditions and Rules

| Condition | Rule | Notes |
|---|---|---|
| Profit target | Exit when gain >= 15% | Hard target |
| Trailing stop | Exit when price drops 7% from highest point reached | Locks in gains |
| Stop loss | Exit when loss >= 8% from entry | Hard floor |
| Reversal signal | Exit when Technical Agent says strong SELL | Agent-driven exit |
| Time-based | Exit after 30 days if none of above triggered | Prevents zombie positions |

---

## Monitor Loop

New module: `monitoring/`

```
monitoring/
├── position_monitor.py    <-- Main loop
├── exit_rules.py          <-- All exit condition logic
├── price_feed.py          <-- Real-time price fetching
└── alert_manager.py       <-- Notifications
```

**Core loop pseudocode:**

```python
async def monitor_loop(interval_seconds=300):  # Check every 5 min
    while True:
        positions = broker.get_positions()
        for position in positions:
            current_price = price_feed.get_price(position.ticker)
            exit_rule = exit_rules.check(position, current_price)
            if exit_rule.should_exit:
                broker.place_market_sell(position.ticker, position.qty)
                log_exit(position, exit_rule.reason)
        await asyncio.sleep(interval_seconds)
```

---

## Trailing Stop Implementation

```python
class Position:
    ticker: str
    entry_price: float
    qty: int
    highest_price: float       # Track this, update every check
    entry_time: datetime

def check_trailing_stop(position, current_price, trail_pct=0.07):
    if current_price > position.highest_price:
        position.highest_price = current_price
        # Save updated high to DB

    trail_level = position.highest_price * (1 - trail_pct)
    if current_price <= trail_level:
        return ExitSignal(should_exit=True, reason="TRAILING_STOP")
    return ExitSignal(should_exit=False)
```

---

## Reversal Detection

Cost-effective approach: don't run the full 7-agent pipeline for monitoring. Only run the Technical Analyst:

```python
async def check_reversal(position):
    tech_signal = technical_agent.quick_check(position.ticker)
    if tech_signal.rsi > 75 and tech_signal.macd_cross == "BEARISH":
        return ExitSignal(should_exit=True, reason="REVERSAL_SIGNAL")
```

---

## Portfolio Guard Design

**Hard limits:**

```python
PORTFOLIO_RULES = {
    "max_positions": 10,              # Never hold more than 10 stocks
    "max_sector_exposure": 0.30,      # No single sector > 30% of portfolio
    "max_single_position": 0.08,      # No single stock > 8% of portfolio
    "max_single_exchange": 0.60,      # No more than 60% in NYSE or NASDAQ alone
    "daily_loss_limit": -0.03,        # Stop all buys if down 3% on the day
    "weekly_loss_limit": -0.07,       # Stop all activity if down 7% in a week
    "cash_reserve": 0.10,             # Always keep 10% cash
}
```

**Guard class:**

```python
class PortfolioGuard:
    def can_open_position(self, ticker, proposed_size) -> tuple[bool, str]:
        checks = [
            self._check_max_positions(),
            self._check_sector_exposure(ticker),
            self._check_daily_loss(),
            self._check_cash_reserve(proposed_size),
        ]
        failures = [r for r in checks if not r.passed]
        if failures:
            return False, failures[0].reason
        return True, "OK"
```

Insert `PortfolioGuard.can_open_position()` between Fund Manager approval and order execution.

---

## Database Schema

Use **SQLite** to start (zero infrastructure). Migrate to Postgres later if needed.

```sql
-- All positions (open and closed)
CREATE TABLE positions (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    exchange TEXT NOT NULL,        -- 'NYSE' or 'NASDAQ'
    entry_price REAL NOT NULL,
    entry_time DATETIME NOT NULL,
    qty INTEGER NOT NULL,
    highest_price REAL,            -- For trailing stop
    exit_price REAL,
    exit_time DATETIME,
    exit_reason TEXT,              -- 'PROFIT_TARGET', 'TRAILING_STOP', etc.
    status TEXT DEFAULT 'OPEN'     -- 'OPEN' or 'CLOSED'
);

-- All agent signals (for analysis and debugging)
CREATE TABLE signals (
    id INTEGER PRIMARY KEY,
    ticker TEXT NOT NULL,
    timestamp DATETIME NOT NULL,
    conviction_score REAL,
    agent_decision TEXT,           -- JSON of each agent's output
    action_taken TEXT,             -- 'BOUGHT', 'SKIPPED', 'REJECTED_BY_GUARD'
    skip_reason TEXT
);

-- Daily portfolio snapshots
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    snapshot_date DATE NOT NULL,
    total_value REAL,
    cash REAL,
    num_positions INTEGER,
    daily_pnl REAL,
    daily_pnl_pct REAL
);

-- System events and errors
CREATE TABLE system_log (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    level TEXT,                    -- 'INFO', 'WARNING', 'ERROR'
    component TEXT,
    message TEXT
);
```

---

## Dashboard Specs

Stack: **Streamlit** + Plotly + Pandas. Run locally.

```bash
pip install streamlit plotly pandas
```

**Page 1: Portfolio Overview**
- Current positions table (ticker, entry price, current price, P&L%, trailing stop level)
- Total portfolio value + daily P&L
- Cash available
- Sector exposure chart

**Page 2: Signal Feed**
- Live log of agent decisions (last 50)
- Conviction scores with color coding (green = strong buy, yellow = weak, gray = hold)
- Pending signals not yet executed

**Page 3: Trade History**
- All closed trades with entry/exit/reason/profit
- Win rate, average return, best/worst trade
- Monthly return chart

**Page 4: Agent Monitor**
- Which tickers were analyzed today
- Agent breakdown per analysis (which agents said BUY vs SELL)
- API costs tracker (LLM call count x estimated cost)

---

## Target File Structure

```
TradeDog/
├── tradingagents/              <-- Upstream framework (minimal changes)
│   ├── agents/
│   ├── dataflows/
│   │   ├── yfinance_fallback.py <-- NEW: Fallback when FinnHub fails
│   │   └── data_validator.py   <-- NEW: Validates data quality
│   ├── graph/trading_graph.py
│   └── default_config.py
│
├── execution/                  <-- NEW: Order execution
│   ├── broker_interface.py
│   ├── paper_broker.py
│   ├── alpaca_broker.py
│   ├── ibkr_broker.py
│   └── order_manager.py
│
├── monitoring/                 <-- NEW: Position monitoring
│   ├── position_monitor.py
│   ├── exit_rules.py
│   ├── price_feed.py
│   └── alert_manager.py
│
├── portfolio/                  <-- NEW: Risk management
│   ├── portfolio_guard.py
│   ├── conviction_gate.py
│   └── position_sizer.py
│
├── database/                   <-- NEW: Data persistence
│   ├── schema.sql
│   ├── db.py
│   └── models.py
│
├── dashboard/                  <-- NEW: Streamlit UI
│   └── app.py
│
├── watchlist/                  <-- NEW: Curated tickers
│   ├── watchlist.json          <-- NYSE/NASDAQ curated tickers
│   └── sector_map.json         <-- Ticker -> sector classification
│
├── scheduler/                  <-- NEW: Orchestrates daily run
│   └── main_loop.py
│
├── tests/
│   └── ...
│
├── docs/
│   ├── architecture.md
│   ├── agent_contracts.md
│   ├── design_reference.md
│   └── TradeDog_Roadmap.md
│
├── .env
├── main.py
└── requirements.txt
```

---

## Broker Setup Commands

**Alpaca (recommended for paper + live):**

```bash
pip install alpaca-py
```

Free paper trading API, full NYSE/NASDAQ coverage, no account minimums, clean REST API + Python SDK. Same SDK for paper and live — just swap credentials.

**IBKR (alternative for live trading):**

```bash
pip install ib_insync
# Requires IBKR TWS or Gateway running locally
```

Build `IBKRBroker` implementing the same `BrokerInterface`. Switching brokers is a config change — the rest of the system doesn't care.

---

## Cost Estimate

| Item | Cost |
|---|---|
| LLM API (Claude Sonnet for analysts, Opus for Trader/Risk) | ~$30-80/mo |
| FinnHub free tier | $0 |
| yfinance | $0 |
| Alpaca paper trading | $0 |
| IBKR live account | $0 (no monthly fee) |
| Hosting (run on your laptop) | $0 |

Keep costs low by: analyzing each ticker once per day (not per minute), using Claude Haiku for the analyst agents, and only using a more powerful model for the final Trader and Risk Manager decisions.

---

## US Regulatory Note

For personal automated trading in a US brokerage account, you operate under standard retail trading rules. If you make more than 3 day trades in a 5-day rolling window with under $25,000 in the account, you'll trigger **Pattern Day Trader** rules. Since TradeDog is a swing trading system (holding for days to weeks), this typically isn't an issue — but keep it in mind when sizing up.
