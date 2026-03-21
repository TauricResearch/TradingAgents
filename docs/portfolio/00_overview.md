# Portfolio Manager Agent — Design Overview

<!-- Last verified: 2026-03-21 -->

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

### Data Access Layer: raw `psycopg2` (no ORM)

The Python code talks to Supabase PostgreSQL directly via `psycopg2` using the
**pooler connection string** (`SUPABASE_CONNECTION_STRING`). No ORM (Prisma,
SQLAlchemy) and no `supabase-py` REST client is used.

**Why `psycopg2` over `supabase-py`?**
- Direct SQL gives full control — transactions, upserts, `RETURNING *`, CTEs.
- No dependency on Supabase's PostgREST schema cache or API key types.
- `psycopg2-binary` is a single pip install with zero non-Python dependencies.
- 4 tables with straightforward CRUD don't benefit from an ORM or REST wrapper.

**Connection:**
- Uses `SUPABASE_CONNECTION_STRING` env var (pooler URI format).
- Passwords with special characters are auto-URL-encoded by `SupabaseClient._fix_dsn()`.
- Typical pooler URI: `postgresql://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:6543/postgres`

**Why not Prisma / SQLAlchemy?**
- Prisma requires Node.js runtime — extra non-Python dependency.
- SQLAlchemy adds dependency overhead for 4 simple tables.
- Plain SQL migration files are readable, versionable, and Supabase-native.

> Full rationale: `docs/agent/decisions/012-portfolio-no-orm.md`

---

## Implemented Workflow (6-Node Sequential Graph)

The portfolio manager runs as a **sequential LangGraph workflow** inside
`PortfolioGraph`. The scanner and price fetching happen **before** the graph
is invoked (handled by the CLI or calling code). The graph itself processes
6 nodes in strict sequence:

```
                      ┌──────────────────────────────────┐
                      │  PRE-GRAPH (CLI / caller)        │
                      │                                  │
                      │  • ScannerGraph.scan(date)       │
                      │    → scan_summary JSON            │
                      │  • yfinance price fetch           │
                      │    → prices dict {ticker: float}  │
                      └──────────────┬───────────────────┘
                                     │
                      ┌──────────────▼───────────────────┐
                      │ PortfolioGraph.run(               │
                      │   portfolio_id, date,             │
                      │   prices, scan_summary)           │
                      └──────────────┬───────────────────┘
                                     │
┌────────────────────────────────────▼───────────────────────────────────────┐
│  NODE 1: load_portfolio  (Python, no LLM)                                  │
│                                                                            │
│  • Queries Supabase for portfolio + holdings via PortfolioRepository       │
│  • Enriches holdings with current prices and computes weights              │
│  → portfolio_data (JSON string with portfolio + holdings dicts)            │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  NODE 2: compute_risk  (Python, no LLM)                                    │
│                                                                            │
│  • Computes portfolio risk metrics from enriched holdings                  │
│  • Sharpe ratio (annualised, rf = 0)                                       │
│  • Sortino ratio (downside deviation)                                      │
│  • Portfolio beta (vs SPY benchmark)                                       │
│  • 95 % VaR (historical simulation, 30-day window)                         │
│  • Max drawdown (peak-to-trough, 90-day window)                            │
│  • Sector concentration (weight per GICS sector)                           │
│  → risk_metrics (JSON string)                                              │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  NODE 3: review_holdings  (LLM — mid_think)                                │
│                                                                            │
│  HoldingReviewerAgent (create_holding_reviewer)                            │
│  • Tools: get_stock_data, get_news                                         │
│  • Uses run_tool_loop() for inline tool execution                          │
│  • Reviews each open position → HOLD or SELL recommendation                │
│  → holding_reviews (JSON string — ticker → review mapping)                 │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  NODE 4: prioritize_candidates  (Python, no LLM)                           │
│                                                                            │
│  • Scores scan_summary.stocks_to_investigate using:                        │
│    conviction × thesis × diversification × held_penalty                    │
│  • Ranks candidates by composite score                                     │
│  → prioritized_candidates (JSON string — sorted list)                      │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  NODE 5: pm_decision  (LLM — deep_think)                                   │
│                                                                            │
│  PM Decision Agent (create_pm_decision_agent)                              │
│  • Pure reasoning — no tools                                               │
│  • Reads: portfolio_data, risk_metrics, holding_reviews,                   │
│           prioritized_candidates, analysis_date                            │
│  • Outputs structured JSON:                                                │
│    {                                                                       │
│      "sells": [{"ticker": "X", "shares": 10, "rationale": "..."}],        │
│      "buys":  [{"ticker": "Y", "shares": 5,  "rationale": "..."}],        │
│      "holds": [{"ticker": "Z", "rationale": "..."}],                       │
│      "cash_reserve_pct": 0.10,                                             │
│      "portfolio_thesis": "...",                                            │
│      "risk_summary": "..."                                                 │
│    }                                                                       │
└───────────────────────────────────┬────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  NODE 6: execute_trades  (Python, no LLM)                                  │
│                                                                            │
│  TradeExecutor                                                             │
│  • SELLs first (frees cash), then BUYs                                     │
│  • Constraint pre-flight (position size, sector, cash)                     │
│  • Records trades in Supabase, updates holdings & cash                     │
│  • Takes immutable EOD portfolio snapshot                                   │
│  → execution_result (JSON string with executed/failed trades)              │
└────────────────────────────────────────────────────────────────────────────┘
```

### State Definition

The graph state is defined in `tradingagents/portfolio/portfolio_states.py`
as `PortfolioManagerState(MessagesState)`:

| Field | Type | Written By |
|-------|------|------------|
| `portfolio_id` | `str` | Caller (initial state) |
| `analysis_date` | `str` | Caller (initial state) |
| `prices` | `dict` | Caller (initial state) |
| `scan_summary` | `dict` | Caller (initial state) |
| `portfolio_data` | `Annotated[str, _last_value]` | Node 1 |
| `risk_metrics` | `Annotated[str, _last_value]` | Node 2 |
| `holding_reviews` | `Annotated[str, _last_value]` | Node 3 |
| `prioritized_candidates` | `Annotated[str, _last_value]` | Node 4 |
| `pm_decision` | `Annotated[str, _last_value]` | Node 5 |
| `execution_result` | `Annotated[str, _last_value]` | Node 6 |
| `sender` | `Annotated[str, _last_value]` | All nodes |

### Comparison: Original Design vs Implementation

| Aspect | Original Design (docs) | Current Implementation |
|--------|----------------------|------------------------|
| Phases 1a/1b | Parallel (scanner + load holdings) | Sequential — scanner runs in pre-graph step |
| Phases 2a/2b | Parallel (MacroBridge + HoldingReviewer) | Sequential — review_holdings then prioritize |
| Candidate analysis | MacroBridge per-ticker full pipeline | Pure Python scoring (no per-ticker LLM analysis) |
| Holding reviewer tier | `quick_think` | `mid_think` |
| Phase 3 risk metrics | Includes correlation matrix, what-if | Sharpe, Sortino, VaR, beta, drawdown, sector |
| Graph topology | Mixed parallel + sequential | Fully sequential (6 nodes) |

---

## Agent Specifications (as implemented)

### Portfolio Manager Decision Agent (`pm_decision_agent.py`)

| Property | Value |
|----------|-------|
| LLM tier | `deep_think` (default: `gpt-5.2`) |
| Pattern | `create_pm_decision_agent(llm)` → closure |
| Memory | Via context injection (portfolio_data, prior decisions) |
| Output format | Structured JSON (validated before trade execution) |
| Tools | None — pure reasoning agent |
| Invocation | Node 5 in the sequential graph, once per run |

**Prompt inputs (injected via state):**
- `portfolio_data` — Current holdings + portfolio state (JSON from Node 1)
- `risk_metrics` — Sharpe, Sortino, VaR, beta, drawdown, sector data (JSON from Node 2)
- `holding_reviews` — Per-ticker HOLD/SELL recommendations (JSON from Node 3)
- `prioritized_candidates` — Ranked candidate list with scores (JSON from Node 4)
- `analysis_date` — Date string for context

**Output schema:**
```json
{
  "sells": [{"ticker": "X", "shares": 10.0, "rationale": "..."}],
  "buys": [{"ticker": "Y", "shares": 5.0, "price_target": 200.0,
            "sector": "Technology", "rationale": "...", "thesis": "..."}],
  "holds": [{"ticker": "Z", "rationale": "..."}],
  "cash_reserve_pct": 0.10,
  "portfolio_thesis": "...",
  "risk_summary": "..."
}
```

### Holding Reviewer Agent (`holding_reviewer.py`)

| Property | Value |
|----------|-------|
| LLM tier | `mid_think` (default: falls back to `gpt-5-mini`) |
| Pattern | `create_holding_reviewer(llm)` → closure |
| Memory | Disabled |
| Output format | Structured JSON |
| Tools | `get_stock_data`, `get_news` |
| Tool execution | `run_tool_loop()` inline (up to 5 rounds) |
| Invocation | Node 3 in the sequential graph, once per run |

**Output schema per holding:**
```json
{
  "AAPL": {
    "ticker": "AAPL",
    "recommendation": "HOLD",
    "confidence": "high",
    "rationale": "Strong momentum, no negative news.",
    "key_risks": ["Sector concentration", "Valuation stretch"]
  }
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

## Implementation Roadmap (Status)

| Phase | Deliverable | Status | Source |
|-------|-------------|--------|--------|
| 1 | Data foundation — models, DB, filesystem, repository | ✅ Done (PR #32) | `tradingagents/portfolio/models.py`, `repository.py`, etc. |
| 2 | Holding Reviewer Agent | ✅ Done | `tradingagents/agents/portfolio/holding_reviewer.py` |
| 3 | Risk metrics engine | ✅ Done | `tradingagents/portfolio/risk_evaluator.py`, `risk_metrics.py` |
| 4 | Portfolio Manager Decision Agent (LLM, structured output) | ✅ Done | `tradingagents/agents/portfolio/pm_decision_agent.py` |
| 5 | Trade execution engine | ✅ Done | `tradingagents/portfolio/trade_executor.py` |
| 6 | Full orchestration graph (LangGraph) | ✅ Done | `tradingagents/graph/portfolio_graph.py`, `portfolio_setup.py` |
| 7 | CLI commands (`portfolio`, `check-portfolio`, `auto`) | ✅ Done | `cli/main.py` |
| 8 | Candidate prioritizer | ✅ Done | `tradingagents/portfolio/candidate_prioritizer.py` |
| 9 | Portfolio state for LangGraph | ✅ Done | `tradingagents/portfolio/portfolio_states.py` |
| 10 | Tests (models, report_store, risk, trade, candidates) | ✅ Done | `tests/portfolio/` (588 tests total, 14 skipped) |

---

## Token Estimation per Model

Estimated token usage per model tier across all three workflows.  Numbers
assume default models (`quick_think` = gpt-5-mini, `deep_think` = gpt-5.2,
`mid_think` falls back to gpt-5-mini when not configured).

### Trading Workflow (`TradingAgentsGraph.propagate`)

| Agent | LLM Tier | Tools | LLM Calls | Est. Input Tokens | Est. Output Tokens |
|-------|----------|-------|-----------|-------------------|-------------------|
| Market Analyst | quick_think | get_stock_data, get_indicators, get_macro_regime | 3–5 | ~3,000–5,000 | ~1,500–3,000 |
| Social Media Analyst | quick_think | get_news | 1–2 | ~2,000–3,000 | ~1,000–2,000 |
| News Analyst | quick_think | get_news, get_global_news | 2–3 | ~2,000–4,000 | ~1,000–2,500 |
| Fundamentals Analyst | quick_think | get_ttm_analysis, get_fundamentals, etc. | 4–6 | ~4,000–8,000 | ~2,000–4,000 |
| Bull Researcher | mid_think | — | 1–2 per round | ~4,000–8,000 | ~1,500–3,000 |
| Bear Researcher | mid_think | — | 1–2 per round | ~4,000–8,000 | ~1,500–3,000 |
| Research Manager (Judge) | deep_think | — | 1 | ~6,000–12,000 | ~2,000–4,000 |
| Trader | mid_think | — | 1 | ~3,000–5,000 | ~1,000–2,000 |
| Aggressive Risk Analyst | quick_think | — | 1–2 per round | ~3,000–6,000 | ~1,000–2,000 |
| Neutral Risk Analyst | quick_think | — | 1–2 per round | ~3,000–6,000 | ~1,000–2,000 |
| Conservative Risk Analyst | quick_think | — | 1–2 per round | ~3,000–6,000 | ~1,000–2,000 |
| Risk Judge | deep_think | — | 1 | ~6,000–12,000 | ~2,000–4,000 |

**Trading workflow totals** (with `max_debate_rounds=2`):
- **LLM calls**: ~19–27
- **Tool calls**: ~15–25
- **quick_think tokens**: ~35,000–55,000 input, ~12,000–20,000 output
- **deep_think tokens**: ~12,000–24,000 input, ~4,000–8,000 output

### Scanner Workflow (`ScannerGraph.scan`)

| Agent | LLM Tier | Tools | LLM Calls | Est. Input Tokens | Est. Output Tokens |
|-------|----------|-------|-----------|-------------------|-------------------|
| Geopolitical Scanner | quick_think | get_topic_news | 2–3 | ~2,000–4,000 | ~1,000–2,500 |
| Market Movers Scanner | quick_think | get_market_movers, get_market_indices | 2–3 | ~2,000–4,000 | ~1,000–2,500 |
| Sector Scanner | quick_think | get_sector_performance | 1–2 | ~1,500–3,000 | ~800–2,000 |
| Industry Deep Dive | mid_think | get_industry_performance, get_topic_news | 5–7 | ~6,000–10,000 | ~3,000–5,000 |
| Macro Synthesis | deep_think | — | 1 | ~8,000–15,000 | ~3,000–5,000 |

**Scanner workflow totals**:
- **LLM calls**: ~9–13
- **Tool calls**: ~11–16
- **quick_think tokens**: ~5,500–11,000 input, ~2,800–7,000 output
- **deep_think tokens**: ~8,000–15,000 input, ~3,000–5,000 output

### Portfolio Workflow (`PortfolioGraph.run`)

| Node | LLM Tier | Tools | LLM Calls | Est. Input Tokens | Est. Output Tokens |
|------|----------|-------|-----------|-------------------|-------------------|
| load_portfolio | — | — | 0 | 0 | 0 |
| compute_risk | — | — | 0 | 0 | 0 |
| review_holdings | mid_think | get_stock_data, get_news | 1 call reviews all holdings (up to 5 tool rounds) | ~3,000–6,000 | ~1,500–3,000 |
| prioritize_candidates | — | — | 0 | 0 | 0 |
| pm_decision | deep_think | — | 1 | ~6,000–12,000 | ~2,000–4,000 |
| execute_trades | — | — | 0 | 0 | 0 |

**Portfolio workflow totals** (assuming 5 holdings):
- **LLM calls**: 2 (review + decision)
- **Tool calls**: ~10 (2 per holding)
- **mid_think tokens**: ~3,000–6,000 input, ~1,500–3,000 output
- **deep_think tokens**: ~6,000–12,000 input, ~2,000–4,000 output

### Full Auto Mode (`scan → pipeline → portfolio`)

| Workflow | quick_think | deep_think |
|----------|-------------|------------|
| Scanner | ~5K–11K in / ~3K–7K out | ~8K–15K in / ~3K–5K out |
| Trading (× 3 tickers — aggregate) | ~105K–165K in / ~36K–60K out | ~36K–72K in / ~12K–24K out |
| Portfolio | — | ~6K–12K in / ~2K–4K out |
| **Totals** | **~110K–176K in / ~39K–67K out** | **~50K–99K in / ~17K–33K out** |

> **Note:** `mid_think` defaults to `quick_think_llm` when not configured,
> so mid_think token counts are included under quick_think totals above.
> Actual token usage varies with portfolio size, number of candidates, and
> debate rounds.

---

## References

- `tradingagents/graph/portfolio_graph.py` — PortfolioGraph orchestrator
- `tradingagents/graph/portfolio_setup.py` — 6-node sequential workflow setup
- `tradingagents/portfolio/portfolio_states.py` — PortfolioManagerState definition
- `tradingagents/agents/portfolio/holding_reviewer.py` — Holding reviewer LLM agent
- `tradingagents/agents/portfolio/pm_decision_agent.py` — PM decision LLM agent
- `tradingagents/portfolio/risk_evaluator.py` — Pure-Python risk metrics
- `tradingagents/portfolio/candidate_prioritizer.py` — Candidate scoring/ranking
- `tradingagents/portfolio/trade_executor.py` — Trade execution with constraint checks
- `tradingagents/portfolio/models.py` — Portfolio, Holding, Trade, PortfolioSnapshot
- `tradingagents/portfolio/repository.py` — Unified data-access façade
- `tradingagents/portfolio/report_store.py` — Filesystem document storage
- `tradingagents/pipeline/macro_bridge.py` — Existing scan → per-ticker bridge
- `tradingagents/report_paths.py` — Filesystem path conventions
- `tradingagents/default_config.py` — Config pattern and LLM tier defaults
- `tradingagents/graph/scanner_graph.py` — Scanner pipeline (runs before portfolio)
- `cli/main.py` — CLI commands: `portfolio`, `check-portfolio`, `auto`
