# Koral Equities V3 - Fail-Closed Autonomous Paper Trading Foundation

**Current release: staged offline PAPER infrastructure, not an autonomous market-connected trading bot.** This version cannot connect to a broker, obtain live prices on its own, generate a machine-approved AI investment plan or trade real money.

## What is implemented

- Separate V3 portfolio, isolated from `~/.tradingagents/paper/portfolio.json` (V1) and `~/.tradingagents/paper/v2/portfolio.json` (V2).
- Strict daily JSON feed format containing original provider source, captured UTC timestamp, market OHLC, SPY benchmark close, GBP/USD open and close rates, and separate issuer-earnings snapshots for pre-open versus after-close evaluation.
- Existing V2 deterministic conditional engine is reused. It cannot turn a plain Buy/Overweight rating into an executable order.
- Preview mode computes a simulated session without writing to disk.
- One-date-only, chronological, atomic book replacement, exclusive same-process lock and hash-linked journal that detects uncommitted or tampered state. In case of a process crash between journal and book commits, the next run stops and requires reconciliation; no blind retry.
- Failed market data, FX sanity or earnings verification rejects the entire session, with the portfolio unchanged. Earnings timestamps in the supplied fixture are validated by the V2 engine, but **vendor authenticity is not yet verified by the V3 orchestration code**.

## Getting started (Windows)

After deploying the new source files, without reinstalling pip:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_auto_v3.py tests/test_conditional_v2.py tests/test_paper_engine.py
.\.venv\Scripts\python.exe -m tradingagents.paper.auto_v3 --help
```

Create a *separate* offline V3 account **once**, and only if you want a new experimental ledger:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.auto_v3 init --start 2026-10-22
.\.venv\Scripts\python.exe -m tradingagents.paper.auto_v3 status
```

Simulate a day using an independent, complete, date-stamped data JSON fixture:

```powershell
.\.venv\Scripts\python.exe -m tradingagents.paper.auto_v3 advance-day --feed "PATH_TO_VALIDATED_SESSION.json" --preview
.\.venv\Scripts\python.exe -m tradingagents.paper.auto_v3 advance-day --feed "PATH_TO_VALIDATED_SESSION.json"
```

A fixture is a test input, not a verified actual stock-market quote. **Never invent one to infer investment performance.** No such feed fixture is supplied in this release. The JSON schema requires exactly `day`, `source`, `captured_at_utc`, `bars` (ticker to Bar with open/high/low/close), `gbp_per_usd_open`, `gbp_per_usd_close`, `spy_close_usd`, `earnings_preopen` and `earnings_afterclose`.

## What still blocks authentic autonomous AI forward-paper trading

**Gate A — independent as-of data:** Implement an exchange-calendar-aware adapter with actual vendor timestamps, corporate action/split/ADR currency normalization, per-session OHLC validation, audited SPY total return and FX, and source-backed issuer earnings schedules. Avoid using after-close news as if it was available before the market open. Failed or stale data cannot permit a fill.

**Gate B — typed AI trading proposal:** Extend the Investment Committee's original structured output with a complete TradeIntent at the source. Separate the 3-20-session Swing Alpha strategy from the 3-10-year Compounder Discovery thesis. Do not extract executable prices, stops or expiry from ambiguous prose. Reconcile portfolio manager's final conditions with the structured contract. Keep operator sign-off or a separately risk-approved research policy; no LLM order permissions by default.

**Gate C — durable scheduler:** Implement New York exchange holiday/half-day rules, transactional daily checkpoints, job recovery and resumption of all missed sessions, deduplication, separate process locks, automatic P&L monitoring and operator notifications. A full unattended schedule is not part of this V3 staging release.

**Gate D — statistical acceptance:** Run adverse test cases, historical out-of-sample validation, model-provenance replay, transaction costs, real currency/sector/position risk, and a **genuine forward comparison** of V1, V3, simple momentum/quality and SPY. The user's goal of at least six months and 100 completed trades is a research target, not a guaranteed demonstration of alpha.

## Risk controls

- 2% intended initial stop-risk budget and 6% aggregate planned risk; a stop does NOT cap realised losses in a gap.
- Maximum five simultaneous holdings; 30% maximum per name; no leverage; maximum 100% gross exposure.
- 10% drawdown lockout for new entries in the existing V2 risk accounting.
- Pre-open earnings veto and completed-close confirmation rules in V2, if correctly timestamped and independently verified.

The V3 runner adds **no real brokerage execution**. It is not a live trading strategy, and no 10x return or positive expectancy has been established.

## Provenance

See `AUDIT_FIRST_RESEARCH_CYCLE.md`, `AUDIT_DISCOVERY_ERO_2026-10-22.md`, `AUDIT_DISCOVERY_HMY_CURRENCY_2026-10-22.md` and the Apache 2.0 original framework attribution.
