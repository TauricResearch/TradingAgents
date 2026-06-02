# Brief: Strategy Intake & Evaluation Pipeline

**Date:** 2026-05-30
**Status:** In Progress — Phase 1 active
**Epic:** `briefs/epic-strategy-intake-phase1.md` (STRAT-001)
**Source:** Ayrat Murtazin — "How Stealing Strategies Made Me $200,000" (Medium/DataDrivenInvestor)

---

## Objective

Build a lightweight strategy intake and evaluation pipeline that lets us capture strategy ideas from external sources (books, papers, podcasts), label them with a standard framework, backtest them against historical data, and track their performance over time — as a complement to the existing per-ticker LLM analysis.

The core insight from Murtazin's piece: **the edge is never in the idea; it's in what you do after you find it.** TradingAgents already does AI-powered per-ticker analysis. What it doesn't do is evaluate whether a *strategy rule set* — independent of any single ticker — has statistical merit. This brief closes that gap with a practical, low-ceremony addition.

---

## Operational Heuristic

**"If you can't write it as a set of IF statements, it's not a strategy. It's a vibe."**

Every intake must reduce to testable rules before it enters the pipeline. No sentiment, no narrative, no "looks oversold." This aligns with the existing TradingAgents workflow — the LLM agents produce qualitative reasoning, but strategy evaluation demands quantitative rigour.

---

## Background: What We Have vs. What's Missing

| Capability | Existing in TradingAgents | Gap |
|---|---|---|
| Per-ticker AI analysis | `trading analyze AAPL` — full multi-agent workflow | No strategy-level evaluation |
| Signal history | `signals` table, confidence + reasoning | Signals are per-ticker, not per-strategy |
| Watchlist screening | `trading screen run` — fundamental + sentiment filters | Screening is candidate discovery, not strategy validation |
| Price data | `prices` table, yfinance subprocess | Data exists; no backtesting harness |
| Benchmark comparison | `trading benchmark` — portfolio vs. VWCE.DE | No per-strategy benchmark |
| Governance | Risk rules, position limits, exit plans | No strategy-level risk evaluation |

**What's missing entirely:**
- A way to store a strategy as a first-class entity (not just a position or signal)
- A backtesting engine that evaluates strategy rules against historical data
- Overfitting guards: out-of-sample split, parameter sensitivity, walk-forward analysis
- A framework label: *risk premium* vs. *inefficiency* — tells you how long the edge should last
- Strategy decay tracking: does the edge degrade over time?

---

## Functional Requirements

### R01: Strategy Definition Store

A `strategies` table and associated schema to capture strategy definitions:

```sql
CREATE TABLE strategies (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  source          TEXT,              -- book, paper, podcast URL, tweet URL
  source_type     TEXT CHECK(source_type IN ('book','paper','podcast','twitter','onchain','manual')),
  edge_type       TEXT CHECK(edge_type IN ('risk_premium','inefficiency','unknown')),
  market          TEXT,              -- 'equities','futures','crypto','options','forex'
  behaviour       TEXT CHECK(behaviour IN ('trend_following','mean_reversion','momentum','carry','arbitrage','other')),
  entry_rules     TEXT NOT NULL,     -- JSON: structured conditions (indicator, threshold, confirmation)
  exit_rules      TEXT NOT NULL,     -- JSON: target, stop, time-based, signal reversal
  position_sizing TEXT,              -- JSON: fixed_fractional, volatility_scaled, equal_weight, kelly
  parameters      TEXT,              -- JSON: key parameters with defaults (e.g. {"rsi_period": 14, "rsi_threshold": 30})
  timeframe       TEXT,              -- '1d','1h','4h','1w'
  status          TEXT DEFAULT 'draft' CHECK(status IN ('draft','extracted','backtested','paper_trading','live','retired')),
  notes           TEXT,
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);
```

- [ ] **R01.1:** `strategies` table in schema.sql
- [ ] **R01.2:** CLI command `trading strategy add` with interactive prompts for the framework fields (market, edge type, entry/exit logic, behaviour)
- [ ] **R01.3:** CLI command `trading strategy list [--status backtested] [--edge-type risk_premium]`
- [ ] **R01.4:** CLI command `trading strategy show <id>` — displays full strategy definition with source attribution

### R02: Strategy Extraction via AI

Use the existing LLM infrastructure to extract strategy rules from unstructured text (similar to Murtazin's AI podcast/paper scraper but project-native):

- [ ] **R02.1:** `trading strategy extract --from-url <url>` — fetches content via `defuddle`, prompts LLM to extract: market, edge type, entry logic, exit logic, parameters, position sizing, expected behaviour
- [ ] **R02.2:** `trading strategy extract --from-file <path>` — same but for local PDF/text/Markdown
- [ ] **R02.3:** Extracted strategy is saved as `draft` status; human reviews and promotes to `extracted`
- [ ] **R02.4:** LLM prompt includes the framework template from R01 — ensures structured output
- [ ] **R02.5:** Extraction includes a confidence score and flags any fields the LLM couldn't determine

> **Guard:** Extraction is gated on human review. The LLM doesn't push anything to `backtested` or `live`. It populates `draft` only.

### R03: Backtesting Engine

A lightweight backtesting harness that evaluates a strategy against historical price data:

- [ ] **R03.1:** `scripts/py/backtest_strategy.py` — takes a strategy ID, loads historical data from `prices` table or yfinance, runs the entry/exit rules, and outputs a performance report
- [ ] **R03.2:** Store backtest results in `strategy_backtests` table: strategy_id, date_range, total_return, sharpe_ratio, max_drawdown, win_rate, num_trades, avg_hold_days
- [ ] **R03.3:** CLI command `trading strategy backtest <id> [--start YYYY-MM-DD] [--end YYYY-MM-DD]`
- [ ] **R03.4:** **Out-of-sample split:** `trading strategy backtest <id> --split 0.7` — trains on first 70% of date range, tests on last 30%. Reports both in-sample and out-of-sample metrics side by side
- [ ] **R03.5:** **Parameter sensitivity:** `trading strategy backtest <id> --sweep rsi_period=10..20` — varies one parameter across a range, reports stability
- [ ] **R03.6:** Performance decay check: compares first-half vs. second-half returns; flags degradation

### R04: Strategy Dashboard View

A new dashboard tab (`/strategies`) showing the strategy pipeline:

- [ ] **R04.1:** Cards for each strategy — name, edge type badge, status badge, source, last backtest metrics (Sharpe, drawdown, win rate)
- [ ] **R04.2:** Click-through to detailed strategy view: full rules, parameter sweep chart, equity curve (sparkline using Datatype font), out-of-sample vs. in-sample comparison
- [ ] **R04.3:** Status progression: drag/click to promote `draft → extracted → backtested → paper_trading → live → retired`
- [ ] **R04.4:** Correlation matrix view — shows correlation between strategies' daily returns (flag >0.7 as "double-counted risk premium")
- [ ] **R04.5:** Strategy decay indicator — arrow showing whether recent returns are above/below historical average

### R05: Strategy-to-Signal Bridge (Stretch)

Once a strategy is in `live` status, feed it into the analysis pipeline as context:

- [ ] **R05.1:** When running `trading analyze AAPL`, if any live strategies are tagged with `market='equities'`, inject them as "known edges" in the Analyst prompt
- [ ] **R05.2:** Signal table records `strategy_id` when a signal was influenced by a known strategy
- [ ] **R05.3:** Track per-strategy signal accuracy over time (hit rate, average return per signal)

> **R05 is stretch.** The core value is R01–R04: capture, test, and monitor strategies. Feeding them into the LLM analysis pipeline is a multiplier but not the first objective.

---

## Execution Workflow

```
Source → Extract → Label → Store → Backtest → Evaluate → Monitor
  │         │        │       │        │           │          │
  │    R02: AI    R01:     R01:    R03:       R03 out-   R04 decay
  │    extraction  framework  table   harness    of-sample   tracking
  │              (market,                        + sweep
  │              edge type,
  │              behaviour)
  │
  Books, papers,
  podcasts, tweets,
  on-chain data
```

**Phase 1 (this brief):** R01 + R02 — capture and extract. Get the table and CLI working.

**Phase 2 (follow-up brief):** R03 — backtesting engine. This is the heavy lift.

**Phase 3 (follow-up brief):** R04 — dashboard view. Make it visible.

**Phase 4 (stretch):** R05 — bridge to TradingAgents analysis.

---

## Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| Strategies captured | >10 in first month | Count of `strategies` rows with `status != 'draft'` |
| Extraction accuracy | >80% of fields correct | Human review of AI-extracted strategies |
| Strategies backtested | >5 with valid OOS results | Count of `strategy_backtests` rows with OOS metrics |
| Dashboard load time | <500ms | Page load of `/strategies` |
| Correlation detection | Flags strategies >0.7 corr | Visual indicator in dashboard |

---

## Constraints

- **Hard:** Never execute a strategy live without human approval (status gate: `backtested → paper_trading` requires manual promotion)
- **Hard:** Backtests must include realistic cost assumptions (commission, slippage, spread) — already a known gap in the Murtazin methodology
- **Hard:** All LLM-extracted strategies start as `draft` and require human review
- **Hard:** Use existing `prices` table for backtest data — no new data vendor dependency
- **Soft:** Datatype font for equity curve sparklines in dashboard (consistent with existing views)
- **Soft:** Keep Python backtest script under 500 lines — this is evaluation, not a production engine
- **Soft:** Alignment with governance engine — strategies producing signals should respect existing risk rules

---

## What This Is NOT

- **Not a live trading engine.** The backtester is for evaluation, not execution. Execution remains via `trading execute` on IG demo.
- **Not a strategy generator.** The LLM extracts from existing sources; it does not invent strategies. As Murtazin notes: AI is the extraction tool, not the idea generator.
- **Not a replacement for TradingAgents.** The multi-agent LLM analysis (analyst → research → trader → risk → PM) remains the primary decision engine. Strategy evaluation is a parallel, quantitative complement — not a replacement.
- **Not a machine learning pipeline.** Rule-based only in Phase 1–3. ML model evaluation is a separate conversation.
- **Not a high-frequency backtester.** Daily OHLCV data is sufficient. Tick-level or minute-level data is out of scope.

---

## Murtazin-Specific Insights to Embed

The following are methodological principles from the article that should inform implementation:

1. **"Label everything you steal."** Every strategy must carry `edge_type` (risk_premium vs. inefficiency) and `source_type`. Risk premiums persist for decades; inefficiencies decay fast. This label should influence the decay-check threshold.

2. **"If you can't write it as a set of IF statements, it's not a strategy."** The entry_rules and exit_rules JSON fields must be parseable as conditions. The backtester reads these as executable logic, not prose. This filters out ~50% of ideas at intake.

3. **"Most backtests are worthless."** Every backtest report must distinguish in-sample from out-of-sample performance. If OOS collapses, flag it prominently. Parameter sensitivity sweep is mandatory, not optional.

4. **"Know what you're stealing."** The source field isn't cosmetic — it's a durability heuristic. A trend-following rule from a 2010 book has different expected longevity than an arbitrage mention from last month's podcast.

5. **"Correlation is the silent killer."** The dashboard must compute a correlation matrix across all backtested strategies. Two strategies with >0.7 correlation over a full cycle are double-counting the same risk premium. This is the single most important portfolio-construction check, and Murtazin's article glaringly omits it.

---

## Related

- Source article: Ayrat Murtazin — "How Stealing Strategies Made Me $200,000" (Medium, May 2026)
- Brief: `briefs/2026-05-13-brief-curated-watch-lists.md` — screening engine pattern reference
- Brief: `briefs/brief-trading-benchmark.md` — benchmark comparison pattern reference
- Brief: `briefs/brief-portfolio-intelligence.md` — portfolio allocation / governance integration
- Brief: `briefs/epic-demo-execution-pipeline.md` — execution pipeline (strategy → signal → execute)
- Table: `prices` — historical price data for backtesting
- Table: `signals` — existing signal storage (extend with `strategy_id` FK in R05)
- Script: `scripts/py/analyze_stream.py` — Python bridge pattern for `backtest_strategy.py`
- Playbook: `playbooks/defuddle-playbook.md` — web content extraction for R02
- Playbook: `playbooks/database-lifecycle-playbook.md` — schema migration protocol
- Architecture: `ARCHITECTURE.md` — Dashboard server, CLI, and Python bridge architecture