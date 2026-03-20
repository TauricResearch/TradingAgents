# Portfolio Manager Agent — Design Overview

<!-- Last verified: 2026-03-20 -->

## Feature Description

The Portfolio Manager Agent (PMA) is an autonomous agent that manages a simulated
investment portfolio end-to-end. It performs the following actions in sequence:

1. **Initiates market research** — triggers the existing `ScannerGraph` to produce a
   macro watchlist of top candidate tickers.
2. **Initiates per-ticker analysis** — feeds scan results into the existing
   `MacroBridge` / `TradingAgentsGraph` pipeline for high-conviction candidates.
3. **Loads current holdings** — queries the Supabase database for the active portfolio
   state (positions, cash balance, sector weights).
4. **Requests lightweight holding reviews** — for each existing holding, runs a
   quick `HoldingReviewerAgent` (quick_think) that checks price action and recent
   news — no full bull/bear debate needed.
5. **Computes portfolio-level risk metrics** — pure Python, no LLM:
   Sharpe ratio, Sortino ratio, beta, 95 % VaR, max drawdown, sector concentration,
   correlation matrix, and what-if buy/sell scenarios.
6. **Makes allocation decisions** — the Portfolio Manager Agent (deep_think +
   memory) reads all inputs and outputs a structured JSON with sells, buys, holds,
   target cash %, and detailed rationale.
7. **Executes mock trades** — validates decisions against constraints, records trades
   in Supabase, updates holdings, and takes an immutable snapshot.

---

## Architecture Decision: Supabase (PostgreSQL) + Filesystem

```
┌─────────────────────────────────────────────────┐
│                   Supabase (PostgreSQL)          │
│                                                  │
│  portfolios   holdings   trades   snapshots      │
│                                                  │
│  "What do I own right now?"                      │
│  "What trades did I make?"                       │
│  "What was my portfolio value on date X?"        │
└────────────────────┬────────────────────────────┘
                     │ report_path column
                     ▼
┌─────────────────────────────────────────────────┐
│              Filesystem  (reports/)              │
│                                                  │
│  reports/daily/{date}/                           │
│    market/          ← scan output                │
│    {TICKER}/        ← per-ticker analysis        │
│    portfolio/                                    │
│      holdings_review.json                        │
│      risk_metrics.json                           │
│      pm_decision.json                            │
│      pm_decision.md  (human-readable)            │
│                                                  │
│  "Why did I decide this?"                        │
│  "What was the macro context?"                   │
│  "What did the risk model say?"                  │
└─────────────────────────────────────────────────┘
```

**Rationale:**

| Concern | Storage | Why |
|---------|---------|-----|
| Transactional integrity (trades) | Supabase | ACID, foreign keys, row-level security |
| Fast portfolio queries (weights, cash) | Supabase | SQL aggregations |
| LLM reports (large text, markdown) | Filesystem | Avoids bloating the DB |
| Agent memory / rationale | Filesystem | Easy to inspect and version |
| Audit trail of decisions | Filesystem | Markdown readable by humans |

The `report_path` column in the `portfolios` table points to the daily portfolio
subdirectory on disk: `reports/daily/{date}/portfolio/`.

### Data Access Layer: raw `supabase-py` (no ORM)

The Python code talks to Supabase through the raw `supabase-py` client — **no
ORM** (Prisma, SQLAlchemy, etc.) is used.

**Why not Prisma?**
- `prisma-client-py` requires a Node.js runtime for code generation — an
  extra non-Python dependency in a Python-only project.
- Prisma's `prisma migrate` conflicts with Supabase's own SQL migration tooling
  (we use `.sql` files in `tradingagents/portfolio/migrations/`).
- 4 tables with straightforward CRUD don't benefit from a code-generated ORM.

**Why not SQLAlchemy?**
- Supabase is accessed via PostgREST (HTTP API), not a direct TCP database
  connection. SQLAlchemy is designed for direct connections and would bypass
  Supabase's Row Level Security.
- Extra dependency overhead for a non-DB-heavy feature.

**`supabase-py` is sufficient because:**
- Its builder-pattern API (`client.table("holdings").select("*").eq(...)`)
  covers all needed queries cleanly.
- Our own dataclasses handle type-safety via `to_dict()` / `from_dict()`.
- Plain SQL migration files are readable, versionable, and Supabase-native.

> Full rationale: `docs/agent/decisions/012-portfolio-no-orm.md`

---

## 5-Phase Workflow

```
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1  (parallel)                                                       │
│                                                                            │
│  1a. ScannerGraph.scan(date)          1b. Load Holdings + Fetch Prices     │
│      → macro_scan_summary.json            → List[Holding] with             │
│        watchlist of top candidates          current_price, current_value   │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2  (parallel)                                                       │
│                                                                            │
│  2a. New Candidate Analysis           2b. Holding Re-evaluation             │
│      MacroBridge.run_all_tickers()        HoldingReviewerAgent (quick_think)│
│      Full bull/bear pipeline per          7-day price + 3-day news          │
│      HIGH/MEDIUM conviction               → JSON: signal/confidence/reason  │
│      candidates that are NOT             urgency per holding                │
│      already held                                                           │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 3  (Python, no LLM)                                                 │
│                                                                            │
│  Risk Metrics Computation                                                  │
│  • Sharpe ratio (annualised, rf = 0)                                       │
│  • Sortino ratio (downside deviation)                                      │
│  • Portfolio beta (vs SPY)                                                 │
│  • 95 % VaR (historical simulation, 30-day window)                         │
│  • Max drawdown (peak-to-trough, 90-day window)                            │
│  • Sector concentration (weight per GICS sector)                           │
│  • Correlation matrix (all holdings)                                       │
│  • What-if scenarios (buy X, sell Y → new weights)                         │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 4  Portfolio Manager Agent (deep_think + memory)                    │
│                                                                            │
│  Reads:  macro context, holdings, candidate signals, re-eval signals,      │
│          risk metrics, budget constraint, past decisions (memory)           │
│                                                                            │
│  Outputs structured JSON:                                                  │
│  {                                                                         │
│    "sells": [{"ticker": "X", "shares": 10, "reason": "..."}],              │
│    "buys":  [{"ticker": "Y", "shares": 5,  "reason": "..."}],              │
│    "holds": ["Z"],                                                         │
│    "target_cash_pct": 0.08,                                                │
│    "rationale": "...",                                                     │
│    "risk_summary": "..."                                                   │
│  }                                                                         │
└───────────────────────────────────┬───────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  PHASE 5  Trade Execution (Mock)                                           │
│                                                                            │
│  • Validate decisions against constraints (position size, sector, cash)    │
│  • Record each trade in Supabase (trades table)                            │
│  • Update holdings (avg cost basis, shares)                                │
│  • Deduct / credit cash balance                                            │
│  • Take immutable portfolio snapshot                                       │
│  • Save PM decision + risk report to filesystem                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Agent Specifications

### Portfolio Manager Agent (PMA)

| Property | Value |
|----------|-------|
| LLM tier | `deep_think` |
| Memory | Enabled — reads previous PM decision files from filesystem |
| Output format | Structured JSON (validated before trade execution) |
| Invocation | Once per run, after Phases 1–3 |

**Prompt inputs:**
- Macro scan summary (top candidates + context)
- Current holdings list (ticker, shares, avg cost, current price, weight, sector)
- Candidate analysis signals (BUY/SELL/HOLD per ticker from Phase 2a)
- Holding review signals (signal, confidence, reason, urgency per holding from Phase 2b)
- Risk metrics report (Phase 3 output)
- Budget constraint (available cash)
- Portfolio constraints (see below)
- Previous decision (last PM decision file for memory continuity)

### Holding Reviewer Agent

| Property | Value |
|----------|-------|
| LLM tier | `quick_think` |
| Memory | Disabled |
| Output format | Structured JSON |
| Tools | `get_stock_data` (7-day window), `get_news` (3-day window), RSI, MACD |
| Invocation | Once per existing holding (parallelisable) |

**Output schema per holding:**
```json
{
  "ticker": "AAPL",
  "signal": "HOLD",
  "confidence": 0.72,
  "reason": "Price action neutral; no material news. RSI 52, MACD flat.",
  "urgency": "LOW"
}
```

---

## PM Agent Constraints

These constraints are **hard limits** enforced during Phase 5 (trade execution).
The PM Agent is also instructed to respect them in its prompt.

| Constraint | Value |
|------------|-------|
| Max position size | 15 % of portfolio value |
| Max sector exposure | 35 % of portfolio value |
| Min cash reserve | 5 % of portfolio value |
| Max number of positions | 15 |

---

## PM Risk Management Rules

These rules trigger specific actions and are part of the PM Agent's system prompt:

| Trigger | Action |
|---------|--------|
| Portfolio beta > 1.3 | Reduce cyclical / high-beta positions |
| Sector exposure > 35 % | Diversify — sell smallest position in that sector |
| Sharpe ratio < 0.5 | Raise cash — reduce overall exposure |
| Max drawdown > 15 % | Go defensive — reduce equity allocation |
| Daily 95 % VaR > 3 % | Reduce position sizes to lower tail risk |

---

## 10-Phase Implementation Roadmap

| Phase | Deliverable | Effort |
|-------|-------------|--------|
| 1 | Data foundation (this PR) — models, DB, filesystem, repository | ~2–3 days |
| 2 | Holding Reviewer Agent | ~1 day |
| 3 | Risk metrics engine (Phase 3 of workflow) | ~1–2 days |
| 4 | Portfolio Manager Agent (LLM, structured output) | ~2 days |
| 5 | Trade execution engine (Phase 5 of workflow) | ~1 day |
| 6 | Full orchestration graph (LangGraph) tying all phases | ~2 days |
| 7 | CLI command `pm run` | ~0.5 days |
| 8 | End-to-end integration tests | ~1 day |
| 9 | Performance tuning + concurrency (Phase 2 parallelism) | ~1 day |
| 10 | Documentation, memory system update, PR review | ~0.5 days |

**Total estimate: ~15–22 days**

---

## References

- `tradingagents/pipeline/macro_bridge.py` — existing scan → per-ticker bridge
- `tradingagents/report_paths.py` — filesystem path conventions
- `tradingagents/default_config.py` — config pattern to follow
- `tradingagents/agents/scanners/` — scanner agent examples
- `tradingagents/graph/scanner_setup.py` — parallel graph node patterns
