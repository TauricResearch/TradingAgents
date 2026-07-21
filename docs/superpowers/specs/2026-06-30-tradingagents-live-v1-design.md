# TradingAgents Live v1 — Always-On Paper-Trading Agent

**Date:** 2026-06-30
**Status:** Design approved by user, ready for implementation plan
**Scope:** v1 of a larger always-on agentic trading system on top of `TauricResearch/TradingAgents`

## Summary

Build an always-on service that runs on the user's Mac, watches recent S&P 500 earnings reports, runs each candidate through the existing TradingAgents multi-agent pipeline, places **paper trades** through a guarded broker layer, and notifies the user of fills, stops, and kill-switch events. Live Robinhood execution is wired but gated off behind a config flag; v1 ships paper-only.

## Background

The user is extending `~/Code/TradingAgents` (fork of `TauricResearch/TradingAgents`, v0.3.0) to manage a small, higher-risk slice of their personal investments autonomously. They funded a dedicated Robinhood account with $250 and will add $100–$200 monthly. They want event-driven and options-income strategies eventually, but have hard constraints — never go negative, max 15% weekly loss, every position needs a stop. With $250, options strategies that fit those constraints are not viable; v1 therefore implements the most conservative deployable strategy (post-earnings momentum on liquid large-caps via fractional shares) and runs entirely in paper mode until empirical results justify graduation to live trading.

The upstream framework already provides a multi-agent decision pipeline (Analysts → Researchers debate → Trader → Risk Mgmt → Portfolio Manager) but executes against a simulated exchange. v1 adds the live-trading scaffolding around it: broker abstraction, guardrail engine, position guardian, scheduler, universe builder, strategy module, journal, notifications.

## Goals

- A working paper-trading system that runs continuously on macOS.
- Hard enforcement of every safety constraint at the order boundary — guardrails cannot be bypassed.
- Identical code path for paper and live execution; the only difference is which `Broker` implementation is wired in.
- Multi-LLM-provider support (including local Ollama) for cost control. Leverage the upstream's existing `TRADINGAGENTS_*` env-var configuration.
- A SQLite event journal so the future dashboard (v2) and post-hoc analysis have a complete record.
- Push + email notifications for fills, stops, and the weekly kill-switch trip-wire.

## Non-Goals (v1)

- Web/Streamlit dashboard — punted to v2 once we know what the journal data looks like.
- Options strategies — defer until account ≥ ~$2–3K.
- Multiple strategy modules — v1 ships exactly one: post-earnings momentum.
- Crypto, leveraged/inverse ETFs, micro-caps, shorting, margin — all permanently excluded.
- Automatic graduation from paper to live. Graduation is a manual, deliberate config flip with code-enforced first-N-trades guardrails.
- Optimization of the TradingAgents pipeline's decision quality. v1 tests verify plumbing safety; paper-trade results inform whether the strategy ships to live.

## Architecture

New code lives in a sibling Python package `ops/` at the repo root. The existing `tradingagents/` package is imported, never modified — upstream merges stay clean.

```
ops/
  broker/
    base.py             # Broker ABC
    paper.py            # PaperBroker (default)
    robinhood.py        # RobinhoodBroker (gated, MCP-backed)
    guarded.py          # GuardedBroker wraps any Broker
  guardrails/
    rules.py            # One class per rule
    engine.py           # Ordered rule chain; first failure aborts
  position_guardian.py  # Background thread: stop loss + kill switch
  scheduler/
    market_calendar.py  # NYSE hours via pandas_market_calendars
    orchestrator.py     # The always-on loop
  universe/
    sp500.py            # S&P 500 membership (cached weekly)
    earnings.py         # Recent-earnings filter via MCP
    filters.py          # Liquidity, ETF exclusions
  strategy/
    base.py             # Strategy ABC
    post_earnings_momentum.py
  pipeline_adapter.py   # Wraps tradingagents.TradingAgentsGraph
  journal.py            # SQLite event journal
  notify/
    push.py             # Pushover
    email.py            # SMTP
    events.py           # Event types + dispatcher
  config.py             # ops config (separate from TradingAgents config)
  cli.py                # Reporting commands
  main.py               # Service entrypoint
```

### Component responsibilities

**`Broker` (ABC).** The single interface that touches money. Methods: `place_market_order`, `place_limit_order`, `cancel`, `get_positions`, `get_quote`, `get_cash`, `get_equity`. Concrete impls: `PaperBroker` (in-memory book + SQLite ledger) and `RobinhoodBroker` (Python MCP client connecting to `https://agent.robinhood.com/mcp/trading`).

**`GuardedBroker`.** Wraps any `Broker` with an ordered rule chain. Every `place_*` call runs the rules; first failure short-circuits with a structured `OrderRejected` exception, journaled with which rule fired. This is *the* enforcement boundary — guardrails cannot be bypassed because the inner broker is never exposed outside `GuardedBroker`.

**`PositionGuardian`.** Background thread, polls quotes every 60 seconds during market hours. Enforces per-position software stop loss (Robinhood-side stops are unreliable on gaps), tracks daily and weekly P&L, fires the kill switch on the weekly cap.

**`Orchestrator`.** Always-on loop. Uses `MarketCalendar` to know when the market is open, ticks every 30 minutes during regular hours. Each tick: refreshes universe (cached if recent), asks strategy module which candidates to deep-analyze, runs each through `PipelineAdapter`, routes decisions to `GuardedBroker`.

**`UniverseBuilder`.** S&P 500 membership ∩ recent earnings beats ∩ liquidity filter, minus static deny-list (SPOT, leveraged/inverse ETFs).

**`PipelineAdapter`.** Thin wrapper around `TradingAgentsGraph.propagate(ticker, date)`. v1 depends only on the upstream public surface so version bumps don't break us.

**Division of responsibility between strategy and pipeline.** The strategy module (`post_earnings_momentum.py`) is responsible for **candidate selection and order construction**: filter universe → pick which tickers to deep-analyze → build orders with size and stop level if the pipeline says BUY. The upstream TradingAgents pipeline is responsible for the **BUY/HOLD/SELL decision** on a given ticker. v1 strategy never overrides a HOLD into a BUY; it only sizes and stops a BUY that the pipeline already produced.

**`Journal`.** One SQLite database with tables: `decisions`, `orders`, `fills`, `positions_snapshot`, `events`. Every state change is appended. Source of truth for state recovery after restart.

**`Notify`.** Small event dispatcher; push (Pushover) and email (SMTP) are subscribers. Event types: `fill`, `stop_hit`, `kill_switch`, `daily_halt`, `daily_summary`, `broker_unreachable`, `inconsistency`.

**LLM provider plumbing.** Use the upstream's existing `TRADINGAGENTS_LLM_PROVIDER`, `TRADINGAGENTS_DEEP_THINK_LLM`, `TRADINGAGENTS_QUICK_THINK_LLM`, and `TRADINGAGENTS_BACKEND_URL` env vars. Document the `.env` knobs in `ops/README.md`, including the local-Ollama recipe.

**Robinhood auth path.** `RobinhoodBroker` uses the Python MCP SDK to connect to `https://agent.robinhood.com/mcp/trading` (OAuth, no password storage). MCP knowledge is isolated to that one file.

## Guardrail rules (defaults in `ops/config.py`)

### Always-on hard rules (never disable)

| Rule | Default | Reason |
|---|---|---|
| `DenyListRule` | `["SPOT"]` + leveraged/inverse ETF list (TQQQ, SQQQ, UVXY, SOXL, etc.) | SPOT contractual compliance; leveraged ETFs decay |
| `NoMarginRule` | Reject any order that would require margin | "Never go negative" |
| `NoOptionsRule` | Reject options orders in v1 | Account too small; user apprehension |
| `NoCryptoRule` | Reject crypto orders | User apprehension |
| `LongOnlyRule` | Reject SELL_SHORT | Can't go negative |
| `StopAttachedRule` | Every BUY must carry an entry-relative stop level | Mandatory stop loss |

### Sizing & exposure (tunable in `ops/config.py`)

| Rule | Default | Notes |
|---|---|---|
| `PerPositionCapRule` | 10% of account equity per position, evaluated at order time only | At $250 = $25; scales with account. No continuous rebalancing — once entered, positions are not trimmed for drift |
| `PerTradeDollarFloor` | Reject if trade < $5 | Avoid noise trades |
| `MaxOpenPositionsRule` | 5 | Concentration check |
| `CashReserveRule` | Keep 20% cash always | Guardian needs headroom |
| `FractionalSharesOnly` | All BUY orders use fractional share quantities, not whole shares | At $250, whole shares of most large-caps are unbuyable; Robinhood supports fractional. Sells of fractional positions go through the same path |

### Drawdown / kill switch (per-account)

| Rule | Threshold | Action |
|---|---|---|
| `DailyDrawdownRule` | −7% vs. start-of-day equity | Block new BUYs for the rest of the day; existing positions stay |
| `WeeklyDrawdownRule` | −15% vs. start-of-week (Monday open) equity | Kill switch (see below) |

**Per-position stop loss** — enforced by `PositionGuardian`, not at order placement. Default −8% from entry, polled every 60 seconds during market hours. On trigger: market-sell, journal `stop_hit`, push notification.

**Kill switch behavior** differs by broker mode (intentional):
- **Paper mode:** auto-close all positions at market, cancel pending orders, set `weekly_halt`, push + email.
- **Live mode:** do NOT auto-close. Cancel pending orders, halt orchestrator, leave positions for user to handle, immediate push + email. Human-in-the-loop the first time things go sideways with real money.

### Universe filters (enforced by `UniverseBuilder`)

- S&P 500 membership (refreshed weekly from a documented source).
- Exclude SPOT and the leveraged/inverse ETF deny-list.
- 20-day average dollar volume ≥ $50M.
- Share price ≥ $5.
- Earnings reported in last 2 trading days with EPS beat **and** revenue beat.

## Data flow (a day in the life)

**Startup (`ops/main.py`):**
1. Load config and `.env`.
2. Initialize SQLite journal, reconcile with broker positions if any pre-existing state.
3. Start `PositionGuardian` thread.
4. Start `Orchestrator` loop; idle until market hours.

**Pre-market (T−30 min before 9:30 ET):**
1. Refresh universe; cache result.
2. Journal `universe_built` with the candidate list.

**Every 30 min during regular hours:**
1. Pull open positions, equity, cash from broker.
2. Re-evaluate sizing/exposure caps → "remaining trading budget" snapshot.
3. For each candidate not already held, in rank order, call `PipelineAdapter.propagate(ticker, today)`.
4. If pipeline returns BUY and budget remains: build order with stop level (entry × 0.92), send to `GuardedBroker`.
5. Rule rejections journaled as `order_rejected` with the failed rule name.
6. Fills journaled as `fill`; position now tracked by `PositionGuardian`.

**Every 60s during market hours (`PositionGuardian`):**
1. Poll quotes for all open positions.
2. If position price ≤ entry × 0.92 → market-sell via `GuardedBroker`, journal `stop_hit`, push.
3. Recompute today's P&L; ≤ −7% trips `daily_halt`.
4. Recompute week's P&L; ≤ −15% trips kill switch (mode-dependent).

**Market close (4:00 ET):**
1. Orchestrator stops dispatching pipeline runs.
2. Guardian tracks AH quotes but does not trade. Any stop breached AH fires at next open.
3. Daily summary event → push (one-line) + email (full report).

**On Mac wake/restart:**
1. Rebuild in-memory state from SQLite journal.
2. Reconcile with broker positions; any divergence → `inconsistency` event for manual review.

### Failure modes

- **Broker timeout / MCP outage:** orchestrator skips the tick (`broker_unreachable`), retries next cycle. Guardian still runs; if guardian is blind for >5 minutes, defensive state — no new orders, push alert.
- **Pipeline error on a ticker:** that ticker is skipped for the day, journaled, others continue.
- **Stop-loss can't fill** (e.g., halted stock): journal `stop_unfilled`, retry every 30s, escalate to email after 5 min.
- **Kill switch in live mode:** halts only; never auto-closes. See above.

## Testing strategy

### Unit tests
- Every rule in `ops/guardrails/rules.py` paired with `tests/ops/guardrails/test_<rule>.py`. Each rule: at least one allow, one block, one edge case.
- `GuardedBroker` order-of-rules tests — confirm first-failure short-circuits and inner-broker is not called on rejection.
- `PositionGuardian` with a fake quote feed: stop fires at exactly −8%, does not fire at −7.9%, kill switch fires at −15% weekly.

### Integration tests
- End-to-end paper lifecycle with `PaperBroker`, stubbed pipeline (deterministic BUY), stubbed universe (one ticker), stubbed quote feed.
- Reconciliation test: kill orchestrator mid-day, restart, verify state rebuilds from journal.
- Notification dispatch test using a fake transport.

### Manual smoke (gates v1 merge)
- Run orchestrator on a real trading day with `BROKER=paper`. Eyes-on-glass: scheduled agent runs, decisions journaled, forced test BUY passes guardrails to the paper book, forced stop hits, push + email arrive. Capture screenshots/logs for the PR.

### Live-broker plumbing (without trading)
- `RobinhoodBroker` integration suite runs against the MCP using **read-only** methods only (`get_positions`, `get_quote`, `get_cash`, account info). No `place_order` in tests.
- Order-placement tests for `RobinhoodBroker` use recorded fixtures.

### What v1 explicitly does NOT test
The quality of the TradingAgents pipeline's decisions. Paper-trade data answers that empirically.

## Graduation criteria (paper → live)

Documented now, not implemented in v1 — sets the bar before we get tempted to lower it.

1. Paper-trading uptime ≥ 8 calendar weeks continuous from first orchestrator start; orchestrator ran without errors on ≥ 80% of trading days in that window.
2. Cumulative paper P&L > 0 over those 8 weeks.
3. No more than 1 kill-switch trigger across the 8 weeks.
4. Manual flip: `BROKER=robinhood` in `.env`, `LIVE_MAX_POSITION=$10` set, CLI prompt requiring the user to type the account value verbatim.
5. First 20 live fills capped at `LIVE_MAX_POSITION=$10` regardless of the configured per-position cap; code-enforced. After 20 fills, normal `PerPositionCapRule` applies.

## Tech stack

- Python 3.12 (matches existing).
- APScheduler — scheduling.
- pandas-market-calendars — NYSE calendar.
- SQLite (via `sqlite3` stdlib + light wrapper) — journal.
- Python MCP SDK — Robinhood broker.
- Pushover — push notifications.
- `smtplib` (stdlib) — email.
- Existing TradingAgents deps for the pipeline.

## Out of scope for v1 (recap)

- Streamlit/web dashboard (v2).
- Options strategies (account-size gated).
- Additional strategy modules.
- Crypto, leveraged/inverse ETFs, shorting, margin (permanently excluded).
- Auto-graduation paper → live.

## Open items deferred to the implementation plan

- Exact APScheduler cron expressions and timezone handling.
- SQLite schema migrations approach (simple Alembic-lite or hand-rolled).
- Pushover API key handling in `.env`.
- Source of S&P 500 membership list (Wikipedia scrape vs. a vendor) — decide in plan.
- Whether to vendor a pinned MCP SDK or take the latest at install time.
