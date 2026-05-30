# TroddeAgents — Hedge Management Platform Specification

**Version:** 0.3  
**Status:** Approved for implementation  
**Last updated:** 2026-05-16

---

## Decisions Log

| # | Question | Decision |
|---|----------|----------|
| 1 | Single user or multi-user? | Single user (Troy) — no auth layer needed |
| 2 | Analysis threshold basis | **Per-position market value** (not total portfolio) |
| 3 | Sentiment score method | **LLM prompt-engineered** — final decision prompt asks for explicit 0–100 score |
| 4 | Live broker | **Alpaca Markets** (paper first, then live; free API, US equities) |
| 5 | LLM cost guardrails | **Hard daily budget cap** — configurable, queues overflow to next day |
| 6 | Sector taxonomy | **GICS 11 sectors** — user toggles which are active; scanner only runs active ones |
| 7 | Pre-IPO scanning | **Deferred** — removed from current scope, reserved as future extension (§10) |

---

## 1. Executive Summary

TroddeAgents expands from a manual stock-analysis tool into a full autonomous hedge management platform. The system continuously scans user-selected GICS industry sectors for public equity investment opportunities, routes candidates through AI-driven analysis, manages a live portfolio, and queues trade execution for human approval before touching real capital.

---

## 2. Current State — WebUI Wrapper Spec (`web/`)

### 2.1 Purpose
Single-page web application that wraps the TradingAgents LangGraph pipeline for interactive, on-demand stock analysis.

### 2.2 Technology
| Layer | Stack |
|-------|-------|
| Backend | FastAPI + Server-Sent Events (SSE) |
| Frontend | Vanilla JS SPA, no build step |
| Analysis engine | TradingAgents LangGraph (`tradingagents/`) |
| Persistence | `~/.tradingagents/logs/{TICKER}/{DATE}/` (markdown + JSON) |
| Config | `.env` loaded with `override=True` |

### 2.3 API Surface
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze` | Start analysis job; returns `job_id` |
| `GET`  | `/api/stream/{job_id}` | SSE stream of agent events |
| `GET`  | `/api/reports` | List all completed analyses |
| `GET`  | `/api/reports/{ticker}/{date}` | Parsed report for a single analysis |

### 2.4 Analysis Configuration (request body)
```json
{
  "ticker": "NVDA",
  "date": "2026-05-16",
  "analysts": ["market", "social", "news", "fundamentals"],
  "language": "English",
  "research_depth": 1,
  "llm_provider": "anthropic",
  "quick_llm": "claude-sonnet-4-6",
  "deep_llm": "claude-opus-4-7",
  "effort": "high"
}
```

### 2.5 SSE Event Schema
```
agent_update  { type, node, label, stage(1-5), msg_type, content, tokens_in, tokens_out }
done          { type, signal, decision, market_report, news_report, sentiment_report, fundamentals_report }
error         { type, message, detail }
heartbeat     { type }
complete      { type }
```

### 2.6 LLM Routing Rules
- `effort` parameter forwarded only when **both** quick and deep models are Opus-class (Haiku/Sonnet reject it with HTTP 400)
- Provider list: anthropic · openai · google · xai · deepseek · ollama (local)
- Quick LLM: low-latency agents (market, social, news, fundamentals)
- Deep LLM: reasoning-heavy agents (research team, risk, portfolio manager)

### 2.7 Five-Stage Pipeline
| Stage | Agents | Weight |
|-------|--------|--------|
| 1 — Analyst Team | Market, Social, News, Fundamentals | 35% |
| 2 — Research Team | Bull, Bear, Research Manager | 25% |
| 3 — Trader | Investment decision | 15% |
| 4 — Risk Management | Aggressive, Neutral, Conservative | 15% |
| 5 — Portfolio Manager | Final decision | 10% |

---

## 3. Platform Architecture — Full Hedge System

### 3.1 Component Overview

```
┌──────────────────────────────────────────────────────────────────┐
│  TroddeAgents Hedge Platform                                      │
│                                                                   │
│  ┌───────────────┐   ┌──────────────┐   ┌───────────────────┐   │
│  │ SectorScanner  │   │ TraderAgents  │   │  PortfolioManager │   │
│  │   Service      │──▶│   Engine     │──▶│    Service        │   │
│  └───────────────┘   └──────────────┘   └───────────────────┘   │
│          │                  ▲                      │              │
│          ▼                  │                      ▼              │
│  ┌───────────────┐          │            ┌───────────────────┐   │
│  │  Opportunity   │──────────┘            │   Action Queue    │   │
│  │    Queue       │  (send to analysis)   │  (human approval) │   │
│  └───────────────┘                       └───────────────────┘   │
│                                                    │              │
│          ┌─────────────────────────────────────────┘              │
│          ▼                                                        │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │  TradingBroker ABC  ·  MockBroker  →  AlpacaBroker        │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Component Specifications

### 4.1 SectorScanner Service

**Purpose:** Scan user-selected GICS sectors daily for public equity opportunities not already held in the portfolio.

**Trigger schedule:**
- Daily at 07:00 EST (pre-market)

**Inputs:**
- `sectors` table — user's active GICS sector selection
- `holdings` table — skip tickers already held
- `opportunities` table — skip tickers discovered in last 7 days

**Sector universe:** GICS 11 top-level sectors. User toggles active ones in Settings UI.

| GICS Code | Sector |
|-----------|--------|
| 10 | Energy |
| 15 | Materials |
| 20 | Industrials |
| 25 | Consumer Discretionary |
| 30 | Consumer Staples |
| 35 | Health Care |
| 40 | Financials |
| 45 | Information Technology |
| 50 | Communication Services |
| 55 | Utilities |
| 60 | Real Estate |

**Stock universe per active sector:** Top 50–200 tickers by market cap from that sector's GICS index (sourced from yfinance + static GICS mapping file). Updated monthly.

**Scoring → Investigation Depth mapping:**
| Score | Depth | Criteria |
|-------|-------|----------|
| 0–30 | Skip | Low volume, no news signal, negative momentum |
| 31–55 | Shallow | Basic momentum + volume screen passes |
| 56–79 | Medium | Multi-factor signal; sector trend aligns |
| 80–100 | Deep | Strong fundamental + technical convergence |

**Scoring factors (weighted):**
- Momentum: 20-day price vs 200-day MA: 25%
- Volume anomaly: 2σ above 90-day avg: 20%
- News sentiment: headline keyword scoring: 20%
- Fundamental screen: P/E, revenue growth, margins: 20%
- Sector momentum: sector ETF 20-day trend: 15%

**Output:** Inserts rows into `opportunities` with `status = 'new'`.

**Cost guard:** Scanner does not trigger TraderAgents analysis directly — it only populates the Opportunity Queue. Analysis is user-initiated or budget-permitting auto-queued.

#### 4.1.1 Market Data Sources
| Purpose | Provider | Notes |
|---------|----------|-------|
| Price / OHLCV | `yfinance` | Free, already in use |
| GICS sector membership | Static mapping + `yfinance` info | Refreshed monthly |
| News headlines | `newsapi.org` or RSS feeds | Requires API key |
| Social sentiment | Reddit API (`r/investing`, `r/stocks`) | Free tier |

---

### 4.2 Opportunity Queue UI

**Location:** "Opportunities" tab in TroddeAgents UI

**Daily Report View:**
- Table sorted by score descending
- Columns: Ticker · Name · Sector · Score · Depth Rec · Discovered · Status
- Per-row actions:
  - **Send to Analysis** → creates analysis job via `POST /api/analyze` with depth-mapped config; deducted from daily LLM budget
  - **Reject** → sets `status = 'rejected'`
  - **Snooze 7 days** → sets `snoozed_until`; re-surfaces after expiry
- Filters: by sector, by depth, by date range, by status

**"Send to Analysis" depth → config mapping:**
| Depth | `research_depth` | `analysts` |
|-------|-----------------|------------|
| Shallow | 1 | market, news |
| Medium | 3 | market, social, news, fundamentals |
| Deep | 5 | all |

---

### 4.3 TraderAgents Engine (existing, enhanced)

**New capabilities needed:**
1. **Programmatic trigger** — Accept analysis requests from SectorScanner and PortfolioManager (not just UI); new `triggered_by` field in request
2. **Structured output** — Machine-readable fields alongside existing markdown reports
3. **LLM-scored sentiment** — Final decision prompt instructs the model to output a 0–100 sentiment score; extracted via regex/JSON from response
4. **Completion callback** — On job completion, push result to a callback queue consumed by PortfolioManager and Scheduler

**Sentiment score prompt addition** (appended to final portfolio manager prompt):
```
After your analysis, append a JSON block on the last line:
{"sentiment_score": <0-100>, "confidence": <0.0-1.0>,
 "recommended_entry": <price|null>, "stop_loss": <price|null>, "price_target": <price|null>}
Score guide: 0=extremely bearish, 50=neutral, 100=extremely bullish.
```

**Extended `done` event payload:**
```json
{
  "signal": "BUY",
  "confidence": 0.82,
  "sentiment_score": 74,
  "recommended_entry_price": 198.50,
  "stop_loss": 188.00,
  "price_target": 230.00
}
```

---

### 4.4 PortfolioManager Service

**Purpose:** Owns live portfolio state, schedules ongoing analysis, detects sentiment shifts, and generates action recommendations.

#### 4.4.1 Holdings Management
- Manual entry UI (ticker, shares, avg cost, date acquired)
- CSV import for bootstrapping
- `yfinance` auto-updates last price daily at 16:10 EST

#### 4.4.2 Scheduled Analysis Rules (per-position market value)

| Condition | Frequency | Depth | LLM budget |
|-----------|-----------|-------|-----------|
| All holdings | Daily | Shallow | Counts against daily cap |
| **Position market value > $100k** | Weekly (Mon) | Deep | Counts against daily cap |
| **Position market value > $1M** | Daily | Deep | Priority — runs even near cap |

> Threshold is **per-position market value** = `shares × last_price`.

#### 4.4.3 LLM Daily Budget Cap

Configured in `platform_config` table (editable in Settings UI):

| Key | Default | Description |
|-----|---------|-------------|
| `daily_llm_budget_usd` | `5.00` | Hard cap on LLM spend per day |
| `budget_reset_hour_est` | `0` | Hour budget resets (midnight EST) |
| `priority_override_threshold` | `1000000` | Positions above this run deep even if budget hit |

Estimated per-analysis cost used for budget accounting:
- Shallow: $0.05
- Medium: $0.30
- Deep: $1.50

When daily budget is exhausted: remaining scheduled analyses are queued with `status = 'budget_deferred'` and retried the following day. UI shows a budget indicator in the Settings tab.

#### 4.4.4 Sentiment Shift Detection

- `sentiment_score` stored per analysis in `analysis_history`
- Rolling 5-day average computed per ticker
- Comparison runs daily at 16:30 EST (post-close, after shallow analysis completes)

**Shift → Action mapping:**
| Delta | Trigger | Suggested Action | Urgency |
|-------|---------|-----------------|---------|
| Score drops ≥ 15 pts | vs 5-day avg | `SELL_PARTIAL` (50%) | Normal |
| Score drops ≥ 30 pts | vs 5-day avg | `SELL_ALL` | High |
| Score rises ≥ 15 pts | vs 5-day avg | `BUY_MORE` | Normal |
| Drops ≥ 15 AND position > $1M | — | `SELL_PARTIAL` | **Urgent** |

#### 4.4.5 Portfolio Summary (top of UI)
- Total portfolio value
- Today's P&L ($ and %)
- Sector allocation (GICS labels)
- Open action count (badge)
- Best / worst performer today

---

### 4.5 Action Queue

**Location:** "Actions" tab — badge count in header when pending

**Action types:**
| Type | Description |
|------|-------------|
| `BUY` | New position recommended |
| `BUY_MORE` | Add to existing position |
| `SELL_ALL` | Exit full position |
| `SELL_PARTIAL` | Sell X% of position |
| `HOLD` | Explicit hold (clears alert without trade) |

**Per-action display:**
- Ticker · Position size · Current P&L · Urgency badge
- Recommended: Order type · Price · Quantity
- Reasoning (1–2 sentences extracted from analysis)
- 7-day sentiment sparkline
- **[Approve]** → routes to TradingBroker → records `trades` row
- **[Modify]** → edit price/quantity before approving
- **[Reject]** → dismisses, logs reason

**Order types:**
- `MARKET` — execute at current market price
- `LIMIT` — execute at specified price or better
- `STOP_LOSS` — trigger sell at floor price

---

### 4.6 TradingBroker Abstraction Layer

**Module path:** `tradingagents/broker/`

**Interface (Python ABC):**
```python
class TradingBroker(ABC):
    @abstractmethod
    def place_order(self, order: Order) -> OrderResult: ...

    @abstractmethod
    def get_account(self) -> AccountInfo: ...

    @abstractmethod
    def get_positions(self) -> list[Position]: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...
```

**Order dataclass:**
```python
@dataclass
class Order:
    ticker: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop"]
    quantity: float
    limit_price: float | None = None
    stop_price:  float | None = None
    time_in_force: str = "day"
```

**Implementations:**

| Class | Phase | Notes |
|-------|-------|-------|
| `MockBroker` | **Phase 0 — build now** | Executes at yfinance close; logs to SQLite |
| `AlpacaBroker` | **Phase 2** | Alpaca Markets API; paper trading first, then live |
| `IBKRBroker` | Phase 3 | Interactive Brokers TWS/Gateway; wider coverage |

**MockBroker behaviour:**
- Market orders fill at last yfinance close price
- Limit orders fill immediately if within 2% of market (simulated slippage)
- Updates `holdings` and inserts `trades` row on fill

**AlpacaBroker notes:**
- Free API key; paper trading environment available immediately
- Supports fractional shares, extended hours
- Live trading enabled via separate config flag + modal confirmation
- API docs: `https://docs.alpaca.markets`

---

### 4.8 Telegram Notification Service

**Purpose:** Push real-time alerts and daily digests to the user's Telegram account so critical signals are surfaced even when the UI is not open.

**Implementation:** `python-telegram-bot` (async) — thin wrapper service that receives events from PortfolioManager, Scheduler, and Action Queue and dispatches formatted messages.

**Notification triggers:**

| Event | Trigger source | Urgency | Timing |
|-------|---------------|---------|--------|
| Daily opportunity digest | Scheduler `sector_scan` | Normal | 07:05 EST (5 min after scan) |
| Analysis complete (deep only) | TraderAgents callback | Normal | Immediate on completion |
| Sentiment shift alert | PortfolioManager `sentiment_check` | High | Immediate after 16:30 run |
| Urgent sell signal (position > $1M) | PortfolioManager | **Urgent** | Immediate |
| New Action Queue item (urgent) | Action Queue | High | Immediate |
| Action pending > 48 hours | Scheduler daily check | Normal | Daily 09:00 EST |
| LLM budget warning (> 80% used) | Budget tracker | Normal | On threshold breach |
| Budget exhausted — analyses deferred | Budget tracker | High | On hard cap hit |

**Message format (example — sentiment shift):**
```
🔴 URGENT: NVDA Sentiment Shift
Score: 82 → 47  (−35 pts vs 5-day avg)
Position: 1,200 shares @ $918.50 = $1.1M
Suggested: SELL_PARTIAL (50%)
→ Open TroddeAgents to review Action Queue
```

**Configuration** (stored in `platform_config`, editable in Settings UI):

| Key | Default | Description |
|-----|---------|-------------|
| `telegram_bot_token` | `''` | BotFather token; blank = notifications disabled |
| `telegram_chat_id` | `''` | Target chat ID (DM to bot, or group) |
| `telegram_digest_enabled` | `'true'` | Send daily opportunity digest |
| `telegram_notify_deep_complete` | `'true'` | Notify on deep analysis completion |

**Setup flow:**
1. User creates bot via @BotFather → copies token into Settings UI
2. User sends `/start` to bot → system captures chat ID
3. Notifications go live; can mute per-category in Settings

---

### 4.7 Scheduler Service

**Implementation:** APScheduler with SQLAlchemy jobstore (SQLite) — survives restarts

**Jobs:**
| Job ID | Schedule (EST) | Description |
|--------|---------------|-------------|
| `sector_scan` | Daily 07:00 | SectorScanner full run for active GICS sectors |
| `price_update` | Daily 16:10 | Refresh `last_price` for all holdings |
| `portfolio_shallow` | Daily 16:20 | Shallow analysis — all holdings (budget permitting) |
| `sentiment_check` | Daily 16:30 | Compute sentiment deltas; generate Action items |
| `portfolio_deep_weekly` | Mon 07:30 | Deep analysis — positions with market value > $100k |
| `portfolio_deep_daily` | Daily 07:30 | Deep analysis — positions with market value > $1M |

All jobs log start/end/status to `scheduler_log`.

---

## 5. Database Schema

**Engine:** SQLite  
**Location:** `~/.tradingagents/platform.db`

```sql
-- GICS sector toggles (seeded with all 11 at first run)
CREATE TABLE sectors (
  id          INTEGER PRIMARY KEY,
  gics_code   INTEGER NOT NULL UNIQUE,  -- e.g. 45 = Information Technology
  name        TEXT    NOT NULL,         -- GICS display name
  active      BOOLEAN DEFAULT 0,        -- user toggles
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Discovered opportunities from scanner
CREATE TABLE opportunities (
  id              INTEGER PRIMARY KEY,
  ticker          TEXT NOT NULL,
  company_name    TEXT,
  gics_code       INTEGER REFERENCES sectors(gics_code),
  score           REAL,
  depth_rec       TEXT CHECK(depth_rec IN ('shallow','medium','deep','skip')),
  source          TEXT DEFAULT 'scanner',  -- 'scanner' | 'manual'
  status          TEXT DEFAULT 'new'
                  CHECK(status IN ('new','queued','analyzing','analyzed','rejected','snoozed')),
  discovered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
  snoozed_until   DATETIME,
  notes           TEXT
);

-- Current portfolio holdings
CREATE TABLE holdings (
  id            INTEGER PRIMARY KEY,
  ticker        TEXT NOT NULL UNIQUE,
  company_name  TEXT,
  shares        REAL    NOT NULL,
  avg_cost      REAL    NOT NULL,   -- per share cost basis
  last_price    REAL,
  last_updated  DATETIME,
  gics_code     INTEGER,
  acquired_at   DATE,
  notes         TEXT
);

-- Every analysis run (manual or automated)
CREATE TABLE analysis_history (
  id               INTEGER PRIMARY KEY,
  ticker           TEXT NOT NULL,
  trade_date       DATE NOT NULL,
  depth            TEXT,              -- shallow | medium | deep
  signal           TEXT,              -- BUY | SELL | HOLD
  confidence       REAL,              -- 0.0–1.0 (LLM-scored)
  sentiment_score  REAL,              -- 0–100   (LLM-scored)
  recommended_price REAL,
  stop_loss         REAL,
  price_target      REAL,
  estimated_cost_usd REAL,            -- LLM cost charged against daily budget
  report_path      TEXT,
  triggered_by     TEXT,             -- manual | scheduler | scanner
  created_at       DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Human-approval action queue
CREATE TABLE actions (
  id                INTEGER PRIMARY KEY,
  action_type       TEXT NOT NULL,   -- BUY|SELL_ALL|SELL_PARTIAL|BUY_MORE|HOLD
  ticker            TEXT NOT NULL,
  shares            REAL,
  recommended_price REAL,
  order_type        TEXT DEFAULT 'limit',
  reasoning         TEXT,
  urgency           TEXT DEFAULT 'normal',  -- normal | high | urgent
  status            TEXT DEFAULT 'pending'
                    CHECK(status IN ('pending','approved','rejected','executed','cancelled')),
  analysis_id       INTEGER REFERENCES analysis_history(id),
  created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
  resolved_at       DATETIME,
  resolved_by       TEXT             -- user | system
);

-- Executed trades
CREATE TABLE trades (
  id              INTEGER PRIMARY KEY,
  action_id       INTEGER REFERENCES actions(id),
  ticker          TEXT NOT NULL,
  side            TEXT,              -- buy | sell
  order_type      TEXT,
  quantity        REAL,
  limit_price     REAL,
  execution_price REAL,
  broker          TEXT DEFAULT 'mock',  -- mock | alpaca | ibkr
  broker_order_id TEXT,
  status          TEXT,              -- filled | partial | rejected | cancelled
  executed_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Platform config (key/value, editable in Settings UI)
CREATE TABLE platform_config (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL,
  description TEXT,
  updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Default config rows (inserted at first run):
-- daily_llm_budget_usd           = '5.00'
-- budget_reset_hour_est          = '0'
-- priority_override_threshold    = '1000000'
-- active_broker                  = 'mock'
-- alpaca_paper_mode              = 'true'
-- telegram_bot_token             = ''
-- telegram_chat_id               = ''
-- telegram_digest_enabled        = 'true'
-- telegram_notify_deep_complete  = 'true'

-- Scheduler job log
CREATE TABLE scheduler_log (
  id          INTEGER PRIMARY KEY,
  job_name    TEXT NOT NULL,
  started_at  DATETIME,
  finished_at DATETIME,
  status      TEXT,   -- success | error | skipped_budget
  detail      TEXT
);
```

---

## 6. LLM Cost Model

Daily analysis costs scale with portfolio size. Estimated at Anthropic pricing (mid-2026):

| Scenario | Analyses/day | Est. cost/day |
|----------|-------------|---------------|
| 5 holdings, all shallow | 5 shallow | ~$0.25 |
| 10 holdings, all shallow | 10 shallow | ~$0.50 |
| 10 holdings, 2 deep daily | 8 shallow + 2 deep | ~$3–8 |
| 20 holdings, 5 deep daily | 15 shallow + 5 deep | ~$10–25 |

**Default daily budget cap: $5.00** — covers all-shallow portfolios up to ~100 positions; adjust upward for deep-analysis-heavy portfolios.

Budget accounting:
- Shallow: ~$0.05 estimated cost
- Medium: ~$0.30 estimated cost
- Deep: ~$1.50 estimated cost
- Actual cost tracked via `usage_metadata` token counts in `estimated_cost_usd`

---

## 7. Phased Implementation Plan

### Phase 0 — Foundation (1–2 weeks)
- [ ] SQLite schema + seed script (sectors seeded with all 11 GICS, default config rows)
- [ ] `TradingBroker` ABC + `MockBroker` implementation (`tradingagents/broker/`)
- [ ] APScheduler service skeleton with SQLite jobstore
- [ ] Extend `POST /api/analyze` with `triggered_by`, `callback_url`, `estimated_cost_usd`
- [ ] LLM sentiment score extraction — prompt addition + regex parser in `app.py`
- [ ] Daily budget tracking (read/write `platform_config`, `estimated_cost_usd` in `analysis_history`)
- [ ] Telegram notification service skeleton (`tradingagents/notifications/telegram.py`) — bot token + chat ID wired to Settings UI; sends test ping on save

### Phase 1 — Portfolio Manager (2–3 weeks)
- [ ] Holdings CRUD UI (manual entry + CSV import)
- [ ] Portfolio summary dashboard (total value, P&L, GICS sector allocation, open actions badge)
- [ ] Scheduled daily shallow analysis + weekly/daily deep rules wired to TraderAgents
- [ ] Sentiment shift detector (rolling 5-day, Action generation)
- [ ] Action Queue UI (approve/modify/reject with per-action sentiment sparkline)
- [ ] MockBroker trade execution → holdings update → trade record
- [ ] Telegram notifications: sentiment shift alerts, urgent sell signals, action pending > 48h, budget warnings

### Phase 2 — Sector Scanner + Alpaca (3–4 weeks)
- [ ] GICS sector toggle UI in Settings tab
- [ ] GICS sector → ticker universe mapping file (top 50–200 by market cap per sector)
- [ ] Scanner service: yfinance screener + news headline scoring + scoring engine
- [ ] Opportunity Queue UI with Send to Analysis flow + budget guard
- [ ] AlpacaBroker implementation (paper mode; `alpaca-trade-api` or `alpaca-py`)
- [ ] Broker switcher in Settings UI (mock → alpaca-paper → alpaca-live)
- [ ] Paper trading validation period before live unlock

### Phase 3 — Hardening
- [ ] IBKR broker adapter (optional, post-Alpaca)
- [ ] Portfolio analytics: Sharpe ratio, beta, max drawdown, sector exposure
- [ ] Stop-loss monitoring: alert if holding price approaches configured stop
- [ ] Settings UI: budget display, budget history chart, config editor
- [ ] Monthly GICS universe refresh job

---

## 8. Remaining Open Questions

1. **Notification channel** — ~~Deferred~~ **Resolved: Telegram** (§4.8). Telegram Bot via `python-telegram-bot`; bot token + chat ID configured in Settings UI. Covers all alert types.

2. **Portfolio bootstrap** — Import existing holdings via CSV at Phase 1 launch? If yes, what format (brokerage export, manual CSV)?

3. **Trade types scope** — Market + Limit orders for Phase 1. Options and short-selling are substantially more complex — scope to Phase 3 or beyond?

4. **Multi-user** — Single user confirmed for now. If multi-user is added later, the main impact is adding a `user_id` FK to holdings/actions/trades and a session layer. Design is not yet multi-user-safe.

---

## 10. Future Extensions (Out of Scope — Current)

### 10.1 Pre-IPO / Private Round Scanning
Scanning private companies requires a dedicated data provider and is not included in current scope.

**When ready to add:**
- Create `PreIPODataProvider` ABC alongside `TradingBroker` ABC
- Implement first adapter against chosen provider API (Crunchbase, Dealroom, or Pitchbook)
- Add `source = 'preipo'` to `opportunities` table `source` CHECK constraint
- Add weekly Sunday 20:00 EST scan job to Scheduler
- UI: add "Pre-IPO" filter toggle in Opportunity Queue

**Candidate providers:**
| Provider | Coverage | Pricing |
|----------|----------|---------|
| Crunchbase API | Global, strong US | Paid tiers |
| Dealroom | European focus | Paid |
| Pitchbook | Institutional | Expensive |
| Manual entry | Any | Free |

### 10.2 Options and Short-Selling
Substantially more complex than equity orders. Requires separate order types, expiry management, margin accounting. Scope to a dedicated phase after Alpaca live trading is validated.

### 10.3 Multi-Sector News Digest
Daily email/Slack summary of new opportunities across all active sectors. Low priority vs building the core loop.

### 10.4 Portfolio Analytics Dashboard
- Sharpe ratio, Sortino ratio, max drawdown
- Beta vs SPY/sector ETF
- Correlation matrix across holdings
- P&L attribution by sector
