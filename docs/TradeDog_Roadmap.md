# TradeDog — Solo Developer Roadmap

**From Research Framework to Autonomous Trading Platform**
*Built on TauricResearch/TradingAgents + LangGraph | NYSE + NASDAQ | Long-Only*

For code snippets, schemas, and architecture patterns see [design_reference.md](design_reference.md).

---

## What You Already Have


| Agent                | Role                               | Status |
| -------------------- | ---------------------------------- | ------ |
| Fundamentals Analyst | Financials, earnings, insider data | Done   |
| Sentiment Analyst    | Reddit/Twitter mood scoring        | Done   |
| News Analyst         | Macro/event impact                 | Done   |
| Technical Analyst    | Indicators, patterns               | Done   |
| Bull/Bear Researcher | Debate-based conviction            | Done   |
| Trader Agent         | Decision synthesis                 | Done   |
| Risk Manager         | Exposure checks                    | Done   |
| Fund Manager         | Final approval                     | Done   |


**What's missing:** Execution layer, auto-buy logic, exit/monitoring loop, position tracking, conviction scoring, dashboard.

---

## Phase Overview


| Phase | Focus                               | Duration  | Milestone |
| ----- | ----------------------------------- | --------- | --------- |
| **0** | Codebase audit and cleanup          | 1-2 weeks | v0.1      |
| **1** | Data layer hardening + watchlist    | 1-2 weeks | v0.1      |
| **2** | Paper trading execution layer       | 3-4 weeks | v0.1      |
| **3** | Conviction scoring + signal control | 2-3 weeks | v0.2      |
| **4** | Position monitoring and auto-exit   | 3-4 weeks | v0.2      |
| **5** | Portfolio-level risk controls       | 2-3 weeks | v0.3      |
| **6** | Dashboard and observability         | 2-3 weeks | v0.3      |
| **7** | Live trading (gradual)              | Ongoing   | v1.0      |


**Total realistic timeline: 5-7 months** at a sustainable pace.

---

# Milestone v0.1 — Minimal End-to-End Loop

*Manual trigger, single ticker analysis through to a paper trade execution.*

---

## Phase 0 — Codebase Audit and Foundation

**Goal:** Understand every file before adding anything. Establish a clean, documented, testable base.

**Duration:** 1-2 weeks

### Week 1 — Read and Map


| #   | Task                                                                         | ~Hours | Files                                                                        |
| --- | ---------------------------------------------------------------------------- | ------ | ---------------------------------------------------------------------------- |
| 0.1 | Read all files under `tradingagents/` top to bottom                          | 4h     | `tradingagents/`**                                                           |
| 0.2 | Draw a flow diagram of how `TradingAgentsGraph.propagate()` calls each agent | 2h     | `tradingagents/graph/trading_graph.py`, `tradingagents/graph/propagation.py` |
| 0.3 | Document what each agent returns (format, fields, meaning)                   | 3h     | `tradingagents/agents/`**                                                    |
| 0.4 | mm                                                                           | 2h     | `tradingagents/dataflows/**`                                                 |
| 0.5 | Review all config options in `default_config.py`                             | 1h     | `tradingagents/default_config.py`                                            |
| 0.6 | Run `main.py` and `test.py` end-to-end in your environment                   | 2h     | `main.py`, `test.py`                                                         |
| 0.7 | Set up `.env` with all required API keys                                     | 1h     | `.env`, `.env.example`                                                       |


- 0.1 — Read all source files under `tradingagents/`
- 0.2 — Draw propagation flow diagram
- 0.3 — Document each agent's input/output contract
- 0.4 — Map all data API calls and endpoints
- 0.5 — Review all config options
- 0.6 — Run `main.py` and `test.py` successfully
- 0.7 — Set up `.env` with all keys

### Week 2 — Clean and Prepare


| #    | Task                                                                             | ~Hours | Files                                       |
| ---- | -------------------------------------------------------------------------------- | ------ | ------------------------------------------- |
| 0.8  | Add type hints and docstrings to functions missing them                          | 4h     | `tradingagents/**`                          |
| 0.9  | Create `docs/agent_contracts.md` documenting each agent's I/O schema             | 2h     | `docs/agent_contracts.md`                   |
| 0.10 | Set up `pytest` with a conftest and one smoke test per agent                     | 3h     | `tests/conftest.py`, `tests/test_agents.py` |
| 0.11 | Create `dev` branch — all new work goes there, only tested code merges to `main` | 0.5h   | git                                         |
| 0.12 | Replace all `print()` with Python `logging` module calls                         | 3h     | `tradingagents/**`                          |
| 0.13 | Pin all dependency versions in `requirements.txt`                                | 1h     | `requirements.txt`                          |
| 0.14 | Update `docs/architecture.md` with your flow diagram from 0.2                    | 1h     | `docs/architecture.md`                      |


- 0.8 — Add type hints and docstrings
- 0.9 — Create `docs/agent_contracts.md`
- 0.10 — Set up pytest with smoke tests
- 0.11 — Create `dev` branch
- 0.12 — Replace print statements with logging
- 0.13 — Pin dependency versions
- 0.14 — Update architecture doc with flow diagram

### Decision Points (resolve before moving on)

- Choose LLM provider for production (recommendation: Claude Sonnet for analysts, reasoning model for Trader/Risk Manager)
- Choose broker for paper trading (recommendation: Alpaca — free paper API, full NYSE/NASDAQ)

### Definition of Done

- You can run `main.py` cleanly and get a trading decision for any ticker
- `pytest` passes with at least one test per agent
- `docs/architecture.md` and `docs/agent_contracts.md` exist and are accurate
- All dependencies are pinned
- Logging works (no raw print statements)

---

## Phase 1 — Data Layer Hardening + Watchlist

**Goal:** Make the data layer robust and production-grade. Reliable, clean OHLCV and fundamental data before any money touches the system.

**Duration:** 1-2 weeks

**Prereqs:** Phase 0 complete


| #    | Task                                                                                        | ~Hours | Files                                     |
| ---- | ------------------------------------------------------------------------------------------- | ------ | ----------------------------------------- |
| 1.1  | Add yfinance as a fallback in `dataflows/` — if primary source errors, fall through         | 3h     | `tradingagents/dataflows/interface.py`    |
| 1.2  | Add rate limit handling and retry logic for API calls                                       | 2h     | `tradingagents/dataflows/interface.py`    |
| 1.3  | Create a `MarketData` dataclass — standardized OHLCV format used by all agents              | 2h     | `tradingagents/dataflows/models.py` (new) |
| 1.4  | Add data validation — reject and log any ticker returning incomplete data                   | 2h     | `tradingagents/dataflows/interface.py`    |
| 1.5  | Add disk caching for API responses (pickle or SQLite) so re-runs don't re-hit APIs          | 3h     | `tradingagents/dataflows/`                |
| 1.6  | Create `watchlist/watchlist.json` with starter tickers (~36 across sectors)                 | 1h     | `watchlist/watchlist.json` (new)          |
| 1.7  | Implement liquidity filter (min volume + min market cap)                                    | 2h     | `watchlist/filters.py` (new)              |
| 1.8  | Test: run `propagate()` on 10 tickers, verify clean data with no empty fields or NaN prices | 2h     | `tests/test_data_layer.py` (new)          |
| 1.9  | Test: simulate API failure and verify fallback activates                                    | 1h     | `tests/test_data_layer.py`                |
| 1.10 | Log API call counts per run to estimate monthly costs                                       | 1h     | `tradingagents/dataflows/`                |


- 1.1 — yfinance fallback in dataflows
- 1.2 — Rate limit handling and retry logic
- 1.3 — `MarketData` dataclass
- 1.4 — Data validation step
- 1.5 — Disk caching for API responses
- 1.6 — Create watchlist JSON
- 1.7 — Liquidity filter
- 1.8 — Test: propagate on 10 tickers, verify clean data
- 1.9 — Test: API failure fallback
- 1.10 — Log API call counts per run

See [design_reference.md — Watchlist Design](design_reference.md#watchlist-design) and [Data Source Strategy](design_reference.md#data-source-strategy) for details.

### Definition of Done

- `propagate()` works on 10+ tickers with no data errors
- API failure gracefully falls back to yfinance
- Watchlist JSON exists with ~36 tickers
- API calls are cached so a second run is instant

---

## Phase 2 — Paper Trading Execution Layer

**Goal:** Connect the agent decision to an actual order. Paper trading only, no real money. This is the most critical phase.

**Duration:** 3-4 weeks

**Prereqs:** Phase 1 complete


| #    | Task                                                                            | ~Hours | Files                                                                      |
| ---- | ------------------------------------------------------------------------------- | ------ | -------------------------------------------------------------------------- |
| 2.1  | Create `database/schema.sql` and `database/db.py` with SQLite setup             | 3h     | `database/schema.sql`, `database/db.py` (new)                              |
| 2.2  | Create `database/models.py` with `Position`, `Order`, `AccountInfo` dataclasses | 2h     | `database/models.py` (new)                                                 |
| 2.3  | Define `BrokerInterface` abstract base class                                    | 2h     | `execution/broker_interface.py` (new)                                      |
| 2.4  | Build `PaperBroker` implementing `BrokerInterface` with SQLite backend          | 4h     | `execution/paper_broker.py` (new)                                          |
| 2.5  | Wire Fund Manager agent approval to `BrokerInterface.place_market_buy()`        | 3h     | `tradingagents/graph/trading_graph.py`, `execution/order_manager.py` (new) |
| 2.6  | Test: run `propagate()` on AAPL and NVDA, confirm position records are created  | 2h     | `tests/test_execution.py` (new)                                            |
| 2.7  | Add position sizing logic (use formula from design ref)                         | 2h     | `portfolio/position_sizer.py` (new)                                        |
| 2.8  | Build `AlpacaBroker` implementing `BrokerInterface`                             | 4h     | `execution/alpaca_broker.py` (new)                                         |
| 2.9  | Add Alpaca paper credentials to `.env` and config                               | 1h     | `.env`, `tradingagents/default_config.py`                                  |
| 2.10 | Switch config to use `AlpacaBroker` with paper mode                             | 1h     | `tradingagents/default_config.py`                                          |
| 2.11 | Run 10 paper trades end-to-end, inspect results in DB                           | 3h     | manual                                                                     |


- 2.1 — SQLite database setup
- 2.2 — Data models (Position, Order, AccountInfo)
- 2.3 — BrokerInterface abstract class
- 2.4 — PaperBroker with SQLite backend
- 2.5 — Wire Fund Manager to broker execution
- 2.6 — Test: propagate creates position records
- 2.7 — Position sizing logic
- 2.8 — AlpacaBroker implementation
- 2.9 — Alpaca paper credentials in config
- 2.10 — Switch to AlpacaBroker in paper mode
- 2.11 — Run 10 paper trades, inspect results

See [design_reference.md — Execution Layer Architecture](design_reference.md#execution-layer-architecture), [Broker Interface](design_reference.md#broker-interface), [Position Sizing Formula](design_reference.md#position-sizing-formula), and [Database Schema](design_reference.md#database-schema) for implementation details.

### Definition of Done

- Running `propagate()` on a ticker results in a paper trade being recorded in SQLite
- `PaperBroker` and `AlpacaBroker` both pass the same test suite
- 10 paper trades executed end-to-end with no errors
- Position records visible in the database

---

# Milestone v0.2 — Conviction + Profit Guardian

*Only buy when confident. Auto-exit when conditions are met.*

---

## Phase 3 — Conviction Scoring and Auto-Buy Control

**Goal:** Not every agent decision should trigger a buy. Add conviction scoring so the platform only buys when multiple agents agree strongly.

**Duration:** 2-3 weeks

**Prereqs:** Phase 2 complete


| #    | Task                                                                                 | ~Hours | Files                                                                                |
| ---- | ------------------------------------------------------------------------------------ | ------ | ------------------------------------------------------------------------------------ |
| 3.1  | Add `conviction_score: float` field to `TradingAgentsGraph` output state             | 2h     | `tradingagents/agents/utils/agent_states.py`, `tradingagents/graph/trading_graph.py` |
| 3.2  | Update each analyst agent prompt to return structured JSON with signal + conviction  | 3h     | `tradingagents/agents/analysts/*.py`                                                 |
| 3.3  | Parse structured conviction output from each agent in the graph state                | 2h     | `tradingagents/graph/signal_processing.py`                                           |
| 3.4  | Implement `calculate_conviction()` weighted scoring function                         | 2h     | `portfolio/conviction_gate.py` (new)                                                 |
| 3.5  | Build `ConvictionGate` — checks threshold, min agents agree, cooldown, max positions | 3h     | `portfolio/conviction_gate.py`                                                       |
| 3.6  | Add `signals` database table for logging all decisions                               | 2h     | `database/schema.sql`, `database/db.py`                                              |
| 3.7  | Wire ConvictionGate between graph output and execution                               | 2h     | `execution/order_manager.py`                                                         |
| 3.8  | Test: force high-conviction scenario, verify buy fires                               | 1h     | `tests/test_conviction.py` (new)                                                     |
| 3.9  | Test: force low-conviction scenario, verify buy is blocked                           | 1h     | `tests/test_conviction.py`                                                           |
| 3.10 | Add dry-run mode flag — logs what would have happened without executing              | 2h     | `tradingagents/default_config.py`, `execution/order_manager.py`                      |


- 3.1 — Add conviction_score to graph output
- 3.2 — Update analyst prompts for structured JSON output
- 3.3 — Parse conviction output in graph state
- 3.4 — Implement weighted conviction scoring function
- 3.5 — Build ConvictionGate with all buy rules
- 3.6 — Add signals table to database
- 3.7 — Wire ConvictionGate into execution pipeline
- 3.8 — Test: high conviction triggers buy
- 3.9 — Test: low conviction blocks buy
- 3.10 — Dry-run mode

See [design_reference.md — Conviction Scoring Design](design_reference.md#conviction-scoring-design), [Auto-Buy Rules](design_reference.md#auto-buy-rules), and [Agent Prompt Additions](design_reference.md#agent-prompt-additions) for implementation details.

### Definition of Done

- Every `propagate()` call outputs a conviction score
- Trades only fire when conviction exceeds threshold AND 3+ agents agree
- All signals are logged to the `signals` table (bought, skipped, or rejected)
- Dry-run mode works

---

## Phase 4 — Position Monitoring and Auto-Exit

**Goal:** Once a position is open, a monitoring loop checks it on a schedule and auto-exits based on predefined rules (profit target, trailing stop, stop loss, reversal, time-based).

**Duration:** 3-4 weeks

**Prereqs:** Phase 3 complete


| #    | Task                                                                                      | ~Hours  | Files                                   |
| ---- | ----------------------------------------------------------------------------------------- | ------- | --------------------------------------- |
| 4.1  | Ensure `positions` table has `highest_price` column for trailing stop tracking            | 1h      | `database/schema.sql`, `database/db.py` |
| 4.2  | Build `PriceFeed` class using yfinance for near-real-time quotes                          | 2h      | `monitoring/price_feed.py` (new)        |
| 4.3  | Implement profit target exit rule (>= 15% gain)                                           | 1h      | `monitoring/exit_rules.py` (new)        |
| 4.4  | Implement trailing stop exit rule (7% drop from peak)                                     | 2h      | `monitoring/exit_rules.py`              |
| 4.5  | Implement stop loss exit rule (>= 8% loss from entry)                                     | 1h      | `monitoring/exit_rules.py`              |
| 4.6  | Implement time-based exit rule (30 days max hold)                                         | 1h      | `monitoring/exit_rules.py`              |
| 4.7  | Implement reversal detection using only Technical Analyst (lightweight, no full pipeline) | 3h      | `monitoring/exit_rules.py`              |
| 4.8  | Build the async monitor loop — checks all positions every 5 min                           | 3h      | `monitoring/position_monitor.py` (new)  |
| 4.9  | Wire exit signals to `broker.place_market_sell()` and log exit reason                     | 2h      | `monitoring/position_monitor.py`        |
| 4.10 | Build alert manager — log exits + send Telegram notification                              | 2h      | `monitoring/alert_manager.py` (new)     |
| 4.11 | Test each exit rule in isolation with mocked prices                                       | 3h      | `tests/test_exit_rules.py` (new)        |
| 4.12 | Run paper trading for 2 weeks, verify exits fire correctly                                | ongoing | manual                                  |


- 4.1 — Ensure positions table has highest_price column
- 4.2 — PriceFeed class
- 4.3 — Profit target exit rule
- 4.4 — Trailing stop exit rule
- 4.5 — Stop loss exit rule
- 4.6 — Time-based exit rule
- 4.7 — Reversal detection (lightweight Technical Analyst only)
- 4.8 — Async monitor loop (5 min interval)
- 4.9 — Wire exits to broker sell + logging
- 4.10 — Alert manager (Telegram notifications)
- 4.11 — Test each exit rule in isolation
- 4.12 — 2-week paper trading validation

See [design_reference.md — Exit Conditions and Rules](design_reference.md#exit-conditions-and-rules), [Monitor Loop](design_reference.md#monitor-loop), [Trailing Stop Implementation](design_reference.md#trailing-stop-implementation), and [Reversal Detection](design_reference.md#reversal-detection) for implementation details.

### Definition of Done

- Monitor loop runs continuously during market hours
- Each exit rule fires correctly when its condition is met
- All exits are logged with reason
- Telegram alerts work
- 2 weeks of paper trading with no missed exits

---

# Milestone v0.3 — Portfolio Risk + Dashboard

*Protect the whole portfolio. See what's happening in real time.*

---

## Phase 5 — Portfolio-Level Risk Controls

**Goal:** Protect the portfolio as a whole, not just individual positions. Enforce hard limits on exposure, concentration, and drawdown.

**Duration:** 2-3 weeks

**Prereqs:** Phase 4 complete


| #    | Task                                                                                          | ~Hours | Files                                   |
| ---- | --------------------------------------------------------------------------------------------- | ------ | --------------------------------------- |
| 5.1  | Create `watchlist/sector_map.json` mapping each ticker to its sector                          | 1h     | `watchlist/sector_map.json` (new)       |
| 5.2  | Implement `PortfolioGuard` class with `can_open_position()` method                            | 4h     | `portfolio/portfolio_guard.py` (new)    |
| 5.3  | Implement max positions check (10 max)                                                        | 1h     | `portfolio/portfolio_guard.py`          |
| 5.4  | Implement sector exposure check (no sector > 30%)                                             | 2h     | `portfolio/portfolio_guard.py`          |
| 5.5  | Implement single position size check (no stock > 8%)                                          | 1h     | `portfolio/portfolio_guard.py`          |
| 5.6  | Implement daily loss limit (stop buys if down 3% on the day)                                  | 2h     | `portfolio/portfolio_guard.py`          |
| 5.7  | Implement cash reserve check (always keep 10%)                                                | 1h     | `portfolio/portfolio_guard.py`          |
| 5.8  | Insert `PortfolioGuard.can_open_position()` between Fund Manager approval and order execution | 2h     | `execution/order_manager.py`            |
| 5.9  | Add `portfolio_snapshots` table for daily P&L tracking                                        | 2h     | `database/schema.sql`, `database/db.py` |
| 5.10 | Create `portfolio_summary()` function (needed for dashboard)                                  | 2h     | `portfolio/portfolio_guard.py`          |
| 5.11 | Test: 10 positions open, verify 11th is blocked                                               | 1h     | `tests/test_portfolio_guard.py` (new)   |
| 5.12 | Test: simulate 3% daily loss, verify no new buys                                              | 1h     | `tests/test_portfolio_guard.py`         |


- 5.1 — Sector map JSON
- 5.2 — PortfolioGuard class skeleton
- 5.3 — Max positions check
- 5.4 — Sector exposure check
- 5.5 — Single position size check
- 5.6 — Daily loss limit
- 5.7 — Cash reserve check
- 5.8 — Wire PortfolioGuard into execution pipeline
- 5.9 — Portfolio snapshots table
- 5.10 — portfolio_summary() function
- 5.11 — Test: max positions enforcement
- 5.12 — Test: daily loss limit enforcement

See [design_reference.md — Portfolio Guard Design](design_reference.md#portfolio-guard-design) for implementation details.

### Definition of Done

- All guard rules pass tests
- 11th position attempt is blocked when 10 are open
- Daily loss limit halts buying
- Portfolio snapshots are recorded daily

---

## Phase 6 — Dashboard and Observability

**Goal:** See what's happening in real time. A simple web dashboard is far more practical than debugging log files.

**Duration:** 2-3 weeks

**Prereqs:** Phase 5 complete


| #    | Task                                                                                     | ~Hours | Files                                |
| ---- | ---------------------------------------------------------------------------------------- | ------ | ------------------------------------ |
| 6.1  | Install Streamlit, Plotly, Pandas dependencies                                           | 0.5h   | `requirements.txt`                   |
| 6.2  | Set up Streamlit app shell with sidebar navigation                                       | 2h     | `dashboard/app.py` (new)             |
| 6.3  | Connect app to SQLite database                                                           | 1h     | `dashboard/app.py`                   |
| 6.4  | Build Page 1: Portfolio Overview (positions table, total value, daily P&L, sector chart) | 4h     | `dashboard/app.py`                   |
| 6.5  | Build Page 2: Signal Feed (agent decisions log, conviction scores, pending signals)      | 3h     | `dashboard/app.py`                   |
| 6.6  | Build Page 3: Trade History (closed trades, win rate, monthly returns)                   | 3h     | `dashboard/app.py`                   |
| 6.7  | Build Page 4: Agent Monitor (tickers analyzed, agent breakdown, API costs)               | 3h     | `dashboard/app.py`                   |
| 6.8  | Add auto-refresh every 60 seconds                                                        | 1h     | `dashboard/app.py`                   |
| 6.9  | Add "pause trading" toggle that sets a flag in the DB                                    | 2h     | `dashboard/app.py`, `database/db.py` |
| 6.10 | Test: run dashboard locally alongside paper trading loop                                 | 1h     | manual                               |


- 6.1 — Install dashboard dependencies
- 6.2 — Streamlit app shell with navigation
- 6.3 — Connect to SQLite database
- 6.4 — Page 1: Portfolio Overview
- 6.5 — Page 2: Signal Feed
- 6.6 — Page 3: Trade History
- 6.7 — Page 4: Agent Monitor
- 6.8 — Auto-refresh
- 6.9 — Pause trading toggle
- 6.10 — Test: dashboard alongside paper trading

See [design_reference.md — Dashboard Specs](design_reference.md#dashboard-specs) for page layouts.

### Definition of Done

- Dashboard runs locally and shows live portfolio data
- All 4 pages render correctly
- Auto-refresh works
- Pause toggle actually stops the trading loop

---

# Milestone v1.0 — Live Trading

*Real money. Small size. Scaled carefully.*

---

## Phase 7 — Live Trading (Gradual Rollout)

**Goal:** Graduate from paper to live trading. Never rush this phase.

**Duration:** Ongoing

**Prereqs:** All previous phases complete + graduation criteria met

### Graduation Criteria (all must be true before using real money)

- 60+ consecutive days of paper trading with no critical bugs
- All exit rules have fired correctly at least 5 times each
- Portfolio guard rules verified under stress scenarios
- Trade log showing positive expectancy (avg win > avg loss)
- Manual review of every paper trade's entry/exit reasoning

### Go-Live Steps


| #   | Task                                                                                          | ~Hours  | Files                            |
| --- | --------------------------------------------------------------------------------------------- | ------- | -------------------------------- |
| 7.1 | Build `IBKRBroker` implementing `BrokerInterface` (optional, if using IBKR instead of Alpaca) | 4h      | `execution/ibkr_broker.py` (new) |
| 7.2 | Set up Alpaca live account (or IBKR), add live credentials to `.env`                          | 1h      | `.env`                           |
| 7.3 | Deploy Week 1: $2,000 max, 2 positions max, $200-300 per trade, monitor hourly                | ongoing | config                           |
| 7.4 | After Week 1 with no execution errors: scale to $10,000, 5 max positions                      | ongoing | config                           |
| 7.5 | Month 3+: increase to target capital, weekly agent review, monthly threshold recalibration    | ongoing | config                           |


- 7.1 — IBKRBroker implementation (if needed)
- 7.2 — Live broker credentials
- 7.3 — Week 1: $2K deployment
- 7.4 — Month 2: scale to $10K
- 7.5 — Month 3+: full operation

See [design_reference.md — Broker Setup Commands](design_reference.md#broker-setup-commands) and [US Regulatory Note](design_reference.md#us-regulatory-note) for broker details and PDT rules.

### Definition of Done

- Live trades execute and match paper trading behavior
- No execution errors in first week
- Profitable or at least not losing beyond daily limits

---

## Weekly Rhythm

**Every week:**

- Monday: Review last week's signal log — did the agents call it right?
- Tuesday-Thursday: Build next feature from this roadmap
- Friday: Write tests, review paper trades, update docs

**Every month:**

- Recalibrate conviction thresholds based on data
- Review which agents are adding value vs noise
- Upgrade watchlist based on what's been performing

---

## Risks and Mitigations


| Risk                                 | Mitigation                                               |
| ------------------------------------ | -------------------------------------------------------- |
| LLM hallucination drives a bad trade | Conviction gate + portfolio guard as hard stops          |
| API outage during market hours       | Retry logic + fallback to cached data                    |
| Broker API failure                   | Always log intent before execution; reconcile on startup |
| Runaway losses                       | Daily loss limit halts all activity automatically        |
| Overfitting to paper trading         | Paper trade on different time periods before going live  |
| Low liquidity stocks                 | Volume filter on watchlist (>1M shares/day avg)          |


---

*Finish each phase completely before starting the next. The order matters.*