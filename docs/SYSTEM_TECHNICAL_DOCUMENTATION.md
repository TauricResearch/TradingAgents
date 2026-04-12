# TradingAgents — Multi-Agent System Technical Documentation

> **Reverse-engineered from production code — 2026-04-04**
>
> Source of truth: `tradingagents/graph/`, `tradingagents/agents/`, `tradingagents/portfolio/`,
> `agent_os/backend/services/langgraph_engine.py`

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Agent Flow](#2-agent-flow)
3. [Agent Specifications](#3-agent-specifications)
4. [Data Contracts (Strict)](#4-data-contracts-strict)
5. [End-to-End Data Flow](#5-end-to-end-data-flow)
6. [Constraints](#6-constraints)

---

## 1. System Overview

### 1.1 Purpose

TradingAgents is a **LangGraph-based multi-agent trading research system** that automates the
complete investment decision lifecycle — from macro market scanning through per-ticker deep
analysis to portfolio-level trade execution. The system orchestrates 25+ specialized agents
across three compiled LangGraph graphs plus an imperative auto-orchestration layer.

### 1.2 Overall Agent Orchestration Flow

The system operates in four runtime phases:

| Phase | Graph | Purpose |
|-------|-------|---------|
| **Phase 1 — Scan** | `ScannerGraph` | Discovers investable candidates across geopolitical, sector, and market signals |
| **Phase 2 — Per-Ticker Pipeline** | `TradingAgentsGraph` | Deep-dives each candidate through analyst → debate → risk → decision stages |
| **Phase 3 — Portfolio** | `PortfolioGraph` | Manages holdings, synthesizes macro/micro briefs, generates structured trade orders |
| **Auto** | Imperative (`run_auto()`) | Orchestrates Phases 1–3 end-to-end with bounded concurrency and failure handling |

### 1.3 High-Level Execution Sequence

```
1. SCAN PHASE
   ├── Fan-out: gatekeeper, geopolitical, market_movers, sector scanners (parallel)
   ├── Follow-on: factor_alignment, smart_money, drift scanners
   ├── Fan-in: industry_deep_dive
   └── Synthesis: macro_synthesis → ranked candidate list (JSON)

2. PER-TICKER PIPELINE (repeated per candidate)
   ├── Instrument Preflight (unsupported instruments abort early)
   ├── Sequential Analysts: Market → Social → News → Fundamentals
   ├── Investment Debate: Bull ↔ Bear Researchers (alternating rounds)
   ├── Research Manager: synthesizes bull/bear into Buy/Sell/Hold
   ├── Trader: converts to precise entry/stop-loss/take-profit proposal
   ├── Risk Debate: Aggressive, Conservative, Neutral (2 parallel rounds + synthesis)
   └── Portfolio Manager: final BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL decision

3. PORTFOLIO PHASE
   ├── Load portfolio + compute risk metrics
   ├── Review existing holdings (inline tools)
   ├── Prioritize candidates from scan
   ├── Parallel: macro_summary + micro_summary
   ├── PM Decision: structured output with sells/buys/holds
   ├── Cash sweep (auto-buy SGOV for excess cash)
   └── Execute trades
```

### 1.4 Execution Primitives

| Pattern | Where Used | Description |
|---------|-----------|-------------|
| **Prefetch + LLM** | Market, Social, News, Fundamentals Analysts | Python calls tools upfront via `prefetch_tools_parallel()`, injects results into prompt |
| **Inline tool loop** | Scanner agents, Market Analyst, Fundamentals Analyst, Holding Reviewer | Node binds tools and resolves via `run_tool_loop()`; no separate LangGraph tool node |
| **Pure reasoning** | Debate agents, Risk agents, Research Manager, Macro Synthesis, PM Decision | LLM-only node with prompt context and optional memory |
| **Python closure** | load_portfolio, compute_risk, prioritize_candidates, cash_sweep, execute_trades | No LLM; state transformed deterministically in Python |

### 1.5 LLM Tier Model

| Tier | Default Model | Used By |
|------|--------------|---------|
| **Quick** | `gpt-5-mini` | Analysts, scanners, risk debaters |
| **Mid** | Falls back to Quick | Researchers, Trader, Holding Reviewer, Summary agents |
| **Deep** | `gpt-5.2` | Research Manager, Macro Synthesis, PM Decision |

---

## 2. Agent Flow

### 2.1 Scanner Graph

```
START ──┬── gatekeeper_scanner ──┬── summarize_gatekeeper ───────────────┬── drift_scanner
        │                        │                                       │
        ├── geopolitical_scanner ── summarize_geopolitical ──┐           │
        │                                                    │           │
        ├── market_movers_scanner ── summarize_market_movers ┤──────────┤
        │                                                    │           │
        └── sector_scanner ── summarize_sector ──┬── factor_alignment ──┤── industry_deep_dive
                                                 │                      │          │
                                                 └── smart_money_scanner┘          │
                                                                             macro_synthesis
                                                                                   │
                                                                                  END
```

**Execution phases:**

1. **Phase 1a (parallel):** `gatekeeper_scanner`, `geopolitical_scanner`, `market_movers_scanner`, `sector_scanner`
2. **Summarization:** Each Phase 1a node feeds its own `summarize_*` node
3. **Phase 1b (after sector):** `factor_alignment_scanner`, `smart_money_scanner`
4. **Phase 1c (multi-predecessor):** `drift_scanner` (needs gatekeeper + market_movers + sector summaries)
5. **Phase 2 (fan-in):** `industry_deep_dive` (all Phase 1 summaries)
6. **Phase 3:** `macro_synthesis` (all summaries) → `END`

### 2.2 Per-Ticker Trading Pipeline

```
START
  │
  ▼
Instrument Preflight ──[aborted]──► END
  │ [supported]
  ▼
Market Analyst → Msg Clear Market → Social Analyst → Msg Clear Social
  → News Analyst → Msg Clear News → News Fact Checker
  → Fundamentals Analyst → Msg Clear Fundamentals
  │
  │──[CRITICAL ABORT detected]──► Critical Abort Terminal → END
  │
  ▼
Bull Researcher ◄──────────────► Bear Researcher
  │                (alternating until max_debate_rounds)
  ▼
Research Manager
  │
  ▼
Trader
  │
  ├──► Aggressive R1 ──┐
  ├──► Conservative R1 ─┤──► Risk Round Barrier
  └──► Neutral R1 ──────┘         │
                            ├──► Aggressive R2 ──┐
                            ├──► Conservative R2 ─┤──► Risk Synthesis
                            └──► Neutral R2 ──────┘         │
                                                             ▼
                                                    Portfolio Manager → END
```

**Branching conditions:**

| Decision Point | Condition | Route |
|---------------|-----------|-------|
| After Instrument Preflight | `analysis_status == "aborted"` | → END |
| After any Msg Clear node | `market_report` or `fundamentals_report` contains `[CRITICAL ABORT]` | → Critical Abort Terminal |
| After Bull/Bear Researcher | `count >= 2 × max_debate_rounds` | → Research Manager |
| After Bull/Bear Researcher | `current_response` starts with "Bull" | → Bear Researcher |
| After Bull/Bear Researcher | `current_response` starts with "Bear" | → Bull Researcher |
| After Bull/Bear/Risk nodes | Any analyst report contains `[CRITICAL ABORT]` | → Portfolio Manager (short-circuit) |

### 2.3 Portfolio Graph

```
START
  │
  ▼
load_portfolio (Python)
  │
  ▼
compute_risk (Python)
  │
  ▼
review_holdings (LLM + inline tools)
  │
  ▼
prioritize_candidates (Python)
  │
  ├──► macro_summary (LLM + memory)  ──┐
  │                                     ├──► make_pm_decision (LLM structured output)
  └──► micro_summary (LLM + memory)  ──┘         │
                                                  ▼
                                            cash_sweep (Python)
                                                  │
                                                  ▼
                                           execute_trades (Python)
                                                  │
                                                 END
```

### 2.4 Auto Orchestration

```
run_auto()
  │
  ├──► Phase 1: run_scan() (or reuse existing scan)
  │
  ├──► Load scan summary from ReportStore
  │
  ├──► Merge scan candidates with portfolio holdings
  │
  ├──► Phase 2: run_pipeline() per ticker (bounded concurrency via TaskGroup)
  │
  ├──► Reload ticker analyses, classify terminal states
  │
  ├──[incomplete tickers exist & continue_on_ticker_failure=false]
  │    └──► Raise AwaitPhase3Decision → UI shows retry checkboxes
  │         └──► run_auto_phase3_decision(): retry selected, recheck
  │
  └──► Phase 3: run_portfolio() (or resume from saved PM decision)
```

---

## 3. Agent Specifications

### 3.1 Scanner Agents

#### 3.1.1 Gatekeeper Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Defines the investable stock universe boundary conditions (liquidity, market cap, profitability screens) |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop via `run_tool_loop()` |
| **Available Tools** | `get_gatekeeper_universe` → retrieves universe of US-listed liquid profitable mid-cap+ names |
| **Incoming Data** | `scan_date` (str), `messages` (list) |
| **Outgoing Data** | `gatekeeper_universe_report` (str), `messages` (list), `sender` = `"gatekeeper_scanner"` |

#### 3.1.2 Geopolitical Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Macro strategist performing geopolitical risk assessment with asset/FX validation |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_topic_news` (geopolitical events), `get_todays_sovereign_cds`, `get_gold_price`, `get_oil_prices`, `get_bitcoin_price`, `get_eur_usd_rate`, `get_jpy_usd_rate`, `get_cny_usd_rate` |
| **Incoming Data** | `scan_date` (str), `messages` (list) |
| **Outgoing Data** | `geopolitical_report` (str), `messages` (list), `sender` = `"geopolitical_scanner"` |

#### 3.1.3 Market Movers Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Assesses market regime and breadth conditions across major indices |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_market_indices` → retrieves index/breadth data |
| **Incoming Data** | `scan_date` (str), `messages` (list) |
| **Outgoing Data** | `market_movers_report` (str), `messages` (list), `sender` = `"market_movers_scanner"` |

#### 3.1.4 Sector Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Performs sector rotation analysis across 11 GICS sectors |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_sector_performance` → sector momentum rankings (1-day, 1-week, 1-month, YTD) |
| **Incoming Data** | `scan_date` (str), `messages` (list) |
| **Outgoing Data** | `sector_performance_report` (str), `messages` (list), `sender` = `"sector_scanner"` |

#### 3.1.5 Factor Alignment Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Quantifies analyst sentiment and earnings revision flow |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_topic_news` (analyst recommendations), `get_earnings_calendar` (earnings dates) |
| **Incoming Data** | `scan_date` (str), `sector_performance_report` (str), `messages` (list) |
| **Outgoing Data** | `factor_alignment_report` (str), `messages` (list), `sender` = `"factor_alignment_scanner"` |

#### 3.1.6 Smart Money Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Identifies institutional footprints — insider buying, volume anomalies, breakout accumulation |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_insider_buying_stocks`, `get_unusual_volume_stocks`, `get_breakout_accumulation_stocks` (all Finviz) |
| **Incoming Data** | `scan_date` (str), `sector_performance_report` (str), `messages` (list) |
| **Outgoing Data** | `smart_money_report` (str), `messages` (list), `sender` = `"smart_money_scanner"` |

#### 3.1.7 Drift Scanner

| Attribute | Value |
|-----------|-------|
| **Purpose** | Identifies 1–3 month continuation setups within the gatekeeper universe |
| **LLM Tier** | Quick |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_gap_candidates` (technical event filtering), `get_topic_news`, `get_earnings_calendar` |
| **Incoming Data** | `scan_date` (str), `gatekeeper_universe_report` (str), `market_movers_report` (str), `sector_performance_report` (str), `messages` (list) |
| **Outgoing Data** | `drift_opportunities_report` (str), `messages` (list), `sender` = `"drift_scanner"` |

#### 3.1.8 Industry Deep Dive

| Attribute | Value |
|-----------|-------|
| **Purpose** | Drills into the top 3 high-conviction sectors from Phase 1 with clinical analysis |
| **LLM Tier** | Mid |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_industry_performance` (top sectors), `get_topic_news` (industry themes) |
| **Incoming Data** | `scan_date` (str), all Phase 1 summaries (str), `messages` (list) |
| **Outgoing Data** | `industry_deep_dive_report` (str), `messages` (list), `sender` = `"industry_deep_dive"` |

#### 3.1.9 Macro Synthesis

| Attribute | Value |
|-----------|-------|
| **Purpose** | Synthesizes all scanner reports into a unified ranked candidate list; deterministic ranking before final LLM call |
| **LLM Tier** | Deep |
| **Execution Pattern** | Pure reasoning (no tools) |
| **Available Tools** | None. `_build_candidate_rankings()` provides deterministic ticker scoring before LLM invocation |
| **Incoming Data** | All scanner reports and summaries (str), `scan_date` (str), `messages` (list) |
| **Outgoing Data** | `macro_scan_summary` (JSON str — see §4.1.2), `messages` (list), `sender` = `"macro_synthesis"` |

#### 3.1.10 Scanner Summarizer (×8 instances)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Compresses raw scanner reports into clinical bullet-format summaries for token efficiency |
| **LLM Tier** | Quick |
| **Execution Pattern** | Pure reasoning |
| **Available Tools** | None |
| **Incoming Data** | `{report_key}` (str) — the raw scanner report field |
| **Outgoing Data** | `{summary_key}` (str), `sender` = `"summarizer_{report_key}"` |

---

### 3.2 Per-Ticker Pipeline Agents

#### 3.2.1 Instrument Preflight

| Attribute | Value |
|-----------|-------|
| **Purpose** | Validates that the instrument is supported for stock deep-dive analysis (equity pipeline); aborts for unsupported types |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | None |
| **Incoming Data** | `company_of_interest` (str) |
| **Outgoing Data** | `instrument_key` (str), `asset_class` (str), `instrument_type` (str), `is_etf` (bool), `is_inverse` (bool), `is_leveraged` (bool), `sender` = `"instrument_preflight"` — on abort: additionally sets `analysis_status` = `"aborted"`, `terminal_action` = `"UNSUPPORTED_INSTRUMENT_TYPE"`, `market_report` = `"[CRITICAL ABORT] ..."` |

#### 3.2.2 Market Analyst

| Attribute | Value |
|-----------|-------|
| **Purpose** | Analyzes macro regime, stock price data, and regime-specific technical indicators; produces quantitative market report |
| **LLM Tier** | Quick (with max_tokens=900) |
| **Execution Pattern** | Prefetch + LLM |
| **Available Tools** | **Prefetched:** `get_macro_regime`, `get_stock_data`, regime-specific `get_indicators` pack (8 indicators). **Inline (dormant):** `get_indicators` via `run_tool_loop()` |
| **Incoming Data** | `company_of_interest` (str), `trade_date` (str), `scanner_context_packet` (str), `messages` (list) |
| **Outgoing Data** | `market_report` (str), `macro_regime_report` (str), `market_report_structured` (dict — see §4.2.2), `messages` (list) |

#### 3.2.3 Social Analyst

| Attribute | Value |
|-----------|-------|
| **Purpose** | Analyzes headline sentiment signals — polarity shifts, coverage intensity, publisher diversity |
| **LLM Tier** | Quick |
| **Execution Pattern** | Prefetch + pure LLM |
| **Available Tools** | **Prefetched:** `get_social_sentiment` (7-day headline polarity). No post-prefetch tool loop |
| **Incoming Data** | `company_of_interest` (str), `trade_date` (str), `scanner_context_packet` (str), `macro_regime_report` (str), `messages` (list) |
| **Outgoing Data** | `sentiment_report` (str), `sentiment_report_structured` (dict), `messages` (list) |

#### 3.2.4 News Analyst

| Attribute | Value |
|-----------|-------|
| **Purpose** | Synthesizes company-specific and global macroeconomic news into structured claims with evidence IDs |
| **LLM Tier** | Quick |
| **Execution Pattern** | Prefetch + pure LLM (2-attempt validation with retry) |
| **Available Tools** | **Prefetched:** `get_news` (company-specific, 7d), `get_global_news` (macro, 7d). News evidence persisted via `NewsEvidenceStore` |
| **Incoming Data** | `company_of_interest` (str), `trade_date` (str), `run_id` (str), `scanner_context_packet` (str), `macro_regime_report` (str), `messages` (list) |
| **Outgoing Data** | `news_report` (str), `news_report_structured` (dict — see §4.2.4), `messages` (list) |

#### 3.2.5 Fundamentals Analyst

| Attribute | Value |
|-----------|-------|
| **Purpose** | Deep fundamental analysis over last 8 quarters — TTM trends, peer comparison, valuation anomalies |
| **LLM Tier** | Quick |
| **Execution Pattern** | Prefetch + inline tool loop |
| **Available Tools** | **Prefetched:** `get_ttm_analysis`, `get_fundamentals`, `get_peer_comparison`, `get_sector_relative`. **Iterative via `run_tool_loop()`:** `get_balance_sheet`, `get_cashflow`, `get_income_statement` |
| **Incoming Data** | `company_of_interest` (str), `trade_date` (str), `scanner_context_packet` (str), `macro_regime_report` (str), `messages` (list) |
| **Outgoing Data** | `fundamentals_report` (str), `fundamentals_report_structured` (dict — see §4.2.5), `messages` (list) |

#### 3.2.6 News Fact Checker

| Attribute | Value |
|-----------|-------|
| **Purpose** | Validates news claims against persisted evidence records; prunes hallucinated or unverifiable claims |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | None (reads from `NewsEvidenceStore`) |
| **Incoming Data** | `news_report_structured` (dict with `claims` array) |
| **Outgoing Data** | Updated `news_report_structured` (dict), `news_report` (str — re-rendered) |

#### 3.2.7 Bull Researcher

| Attribute | Value |
|-----------|-------|
| **Purpose** | Builds a clinical bullish investment thesis through structured debate; uses anonymization to prevent ticker bias |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `FinancialSituationMemory.get_memories(research_packet, n_matches=2)` — retrieves past similar situations |
| **Incoming Data** | `company_of_interest` (str), `investment_debate_state` (InvestDebateState), analyst reports via `build_research_packet()` |
| **Outgoing Data** | `investment_debate_state` (InvestDebateState — updated `history`, `bull_history`, `current_response`, `current_bull_summary`, `summary`, `count`) |

#### 3.2.8 Bear Researcher

| Attribute | Value |
|-----------|-------|
| **Purpose** | Builds a clinical bearish investment thesis — risk delta, competitive fragility, negative indicators |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `FinancialSituationMemory.get_memories(research_packet, n_matches=2)` |
| **Incoming Data** | Same as Bull Researcher |
| **Outgoing Data** | `investment_debate_state` (InvestDebateState — updated `history`, `bear_history`, `current_response`, `current_bear_summary`, `summary`, `count`) |

#### 3.2.9 Research Manager

| Attribute | Value |
|-----------|-------|
| **Purpose** | Debate judge: synthesizes bull/bear positions into a Buy/Sell/Hold decision with structured rationale |
| **LLM Tier** | Deep |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `FinancialSituationMemory.get_memories(curr_situation, n_matches=2)` |
| **Incoming Data** | `company_of_interest` (str), `investment_debate_state.history` (str), `market_report`, `sentiment_report`, `news_report`, `fundamentals_report` (all str), `macro_regime_report` (str), `scanner_context_packet` (str) |
| **Outgoing Data** | `investment_debate_state` (updated with `judge_decision`), `investment_plan` (str), `investment_plan_structured` (dict) |

#### 3.2.10 Trader

| Attribute | Value |
|-----------|-------|
| **Purpose** | Converts the Research Manager recommendation into a precise transaction proposal with entry price, stop-loss, take-profit, and catalyst timeline |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `FinancialSituationMemory.get_memories(curr_situation, n_matches=2)` |
| **Incoming Data** | `company_of_interest` (str), `investment_plan` (str), `market_report`, `sentiment_report`, `news_report`, `fundamentals_report` (all str), `scanner_context_packet` (str) |
| **Outgoing Data** | `trader_investment_plan` (str), `trader_plan_structured` (dict), `messages` (list), `sender` = `"Trader"` |

#### 3.2.11 Aggressive Risk Analyst (Round 1 & Round 2)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Analyzes high-reward, high-risk opportunities; focuses on growth deltas and moats |
| **LLM Tier** | Quick |
| **Execution Pattern** | Pure reasoning |
| **Available Tools** | None |
| **Incoming Data** | `company_of_interest` (str), `trader_investment_plan` (str), analyst reports, risk summary. Round 2 additionally reads `risk_r1_conservative`, `risk_r1_neutral` |
| **Outgoing Data** | Round 1: `risk_r1_aggressive` (str). Round 2: `risk_r2_aggressive` (str) |

#### 3.2.12 Conservative Risk Analyst (Round 1 & Round 2)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Identifies systemic risks, volatility threats, capital preservation requirements |
| **LLM Tier** | Quick |
| **Execution Pattern** | Pure reasoning |
| **Available Tools** | None |
| **Incoming Data** | Same as Aggressive; Round 2 reads `risk_r1_aggressive`, `risk_r1_neutral` |
| **Outgoing Data** | Round 1: `risk_r1_conservative` (str). Round 2: `risk_r2_conservative` (str) |

#### 3.2.13 Neutral Risk Analyst (Round 1 & Round 2)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Provides balanced risk/reward assessment — diversification efficacy, regime alignment |
| **LLM Tier** | Quick |
| **Execution Pattern** | Pure reasoning |
| **Available Tools** | None |
| **Incoming Data** | Same as Aggressive; Round 2 reads `risk_r1_aggressive`, `risk_r1_conservative` |
| **Outgoing Data** | Round 1: `risk_r1_neutral` (str). Round 2: `risk_r2_neutral` (str) |

#### 3.2.14 Risk Synthesis

| Attribute | Value |
|-----------|-------|
| **Purpose** | Consolidates 2 rounds (6 responses total) of risk debate into a unified risk assessment for Portfolio Manager |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning |
| **Available Tools** | None |
| **Incoming Data** | `risk_r1_aggressive`, `risk_r1_conservative`, `risk_r1_neutral`, `risk_r2_aggressive`, `risk_r2_conservative`, `risk_r2_neutral` (all str), `trader_investment_plan` (str), `company_of_interest` (str) |
| **Outgoing Data** | `risk_debate_state` (RiskDebateState — full populated), `risk_synthesis_structured` (dict), `sender` = `"risk_synthesis"` |

#### 3.2.15 Portfolio Manager (Per-Ticker)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Makes the final per-ticker trade decision: BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL |
| **LLM Tier** | Deep |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `FinancialSituationMemory.get_memories(curr_situation, n_matches=2)` |
| **Incoming Data** | `company_of_interest` (str), `risk_debate_state` (RiskDebateState), `trader_investment_plan` (str), analyst reports (str), `macro_regime_report` (str), critical abort signals |
| **Outgoing Data** | `risk_debate_state` (updated with `judge_decision`), `final_trade_decision` (str), `final_trade_decision_structured` (dict), `analysis_status` (str), `terminal_action` (str) |

#### 3.2.16 Critical Abort Terminal

| Attribute | Value |
|-----------|-------|
| **Purpose** | Terminal node for catastrophic abort paths — records which report triggered the abort and sets terminal status |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | None |
| **Incoming Data** | `market_report`, `news_report`, `fundamentals_report` (all str) |
| **Outgoing Data** | `analysis_status` = `"aborted"`, `terminal_action` = `"CRITICAL_ABORT"`, `critical_abort_reason` (str), `final_trade_decision` = `"SELL / AVOID — Critical risk event detected ..."` |

---

### 3.3 Portfolio Agents

#### 3.3.1 load_portfolio

| Attribute | Value |
|-----------|-------|
| **Purpose** | Loads portfolio data and current holdings from PostgreSQL via `PortfolioRepository` |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | `PortfolioRepository.get_portfolio_with_holdings()` |
| **Incoming Data** | `portfolio_id` (str), `prices` (dict) |
| **Outgoing Data** | `portfolio_data` (JSON str — `{"portfolio": {...}, "holdings": [...]}`), `sender` = `"load_portfolio"` |

#### 3.3.2 compute_risk

| Attribute | Value |
|-----------|-------|
| **Purpose** | Computes portfolio-level risk metrics (volatility, drawdown, concentration) |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | `compute_portfolio_risk()` from `risk_evaluator.py` |
| **Incoming Data** | `portfolio_data` (JSON str), `prices` (dict), `scan_summary` (dict) |
| **Outgoing Data** | `risk_metrics` (JSON str), `sender` = `"compute_risk"` |

#### 3.3.3 review_holdings (Holding Reviewer)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Reviews all open positions; recommends HOLD or SELL for each based on thesis validation |
| **LLM Tier** | Mid |
| **Execution Pattern** | Inline tool loop |
| **Available Tools** | `get_stock_data` (recent price history), `get_news` (sentiment check) |
| **Memory System** | None |
| **Incoming Data** | `portfolio_data` (JSON str), `analysis_date` (str), `ticker_analyses` (dict), `messages` (list) |
| **Outgoing Data** | `holding_reviews` (JSON str — `{ticker: {recommendation, confidence, rationale, key_risks}}`), `messages` (list), `sender` = `"holding_reviewer"` |

#### 3.3.4 prioritize_candidates

| Attribute | Value |
|-----------|-------|
| **Purpose** | Ranks scan candidates by conviction, filtering to only those with completed deep-dive analyses |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | `prioritize_candidates()`, `build_selection_memory()` from lesson store |
| **Incoming Data** | `portfolio_data` (JSON str), `scan_summary` (dict), `ticker_analyses` (dict), `prices` (dict) |
| **Outgoing Data** | `prioritized_candidates` (JSON str — list of ranked candidates), `sender` = `"prioritize_candidates"` |

#### 3.3.5 macro_summary

| Attribute | Value |
|-----------|-------|
| **Purpose** | Compresses macro scan output into a 1-page regime brief; persists macro state to memory |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `MacroMemory.build_macro_context(limit=3)` for retrieval, `MacroMemory.record_macro_state()` for persistence |
| **Incoming Data** | `scan_summary` (dict), `analysis_date` (str), `messages` (list) |
| **Outgoing Data** | `macro_brief` (str — formatted regime brief), `macro_memory_context` (str), `messages` (list), `sender` = `"macro_summary_agent"` |

#### 3.3.6 micro_summary

| Attribute | Value |
|-----------|-------|
| **Purpose** | Compresses holding reviews + ranked candidates into a 1-page micro brief with per-ticker memory |
| **LLM Tier** | Mid |
| **Execution Pattern** | Pure reasoning + memory |
| **Available Tools** | None |
| **Memory System** | `ReflexionMemory.build_context(ticker, limit=2)` — read-only per-ticker history |
| **Incoming Data** | `holding_reviews` (JSON str), `prioritized_candidates` (JSON str), `ticker_analyses` (dict), `analysis_date` (str), `messages` (list) |
| **Outgoing Data** | `micro_brief` (str), `micro_memory_context` (JSON str — ticker memory dict), `messages` (list), `sender` = `"micro_summary_agent"` |

#### 3.3.7 make_pm_decision (PM Decision Agent)

| Attribute | Value |
|-----------|-------|
| **Purpose** | Synthesizes macro and micro briefs into a final structured portfolio decision with sells/buys/holds |
| **LLM Tier** | Deep |
| **Execution Pattern** | LLM with `with_structured_output(PMDecisionSchema)` and raw fallback |
| **Available Tools** | None |
| **Incoming Data** | `macro_brief` (str), `micro_brief` (str), `prioritized_candidates` (JSON str), `portfolio_data` (JSON str), `analysis_date` (str), `messages` (list) |
| **Outgoing Data** | `pm_decision` (JSON str — see §4.3.7 `PMDecisionSchema`), `messages` (list), `sender` = `"pm_decision_agent"` |

#### 3.3.8 cash_sweep

| Attribute | Value |
|-----------|-------|
| **Purpose** | Automatically sweeps excess cash (above 5% threshold) into SGOV (cash-equivalent ETF) |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | None |
| **Incoming Data** | `portfolio_data` (JSON str), `pm_decision` (JSON str), `prices` (dict) |
| **Outgoing Data** | `pm_decision` (JSON str — with SGOV buy appended if applicable), `cash_sweep` (str — sweep details), `sender` = `"cash_sweep"` |

#### 3.3.9 execute_trades

| Attribute | Value |
|-----------|-------|
| **Purpose** | Executes the PM decision against the portfolio via `TradeExecutor` |
| **LLM Tier** | N/A (Python closure) |
| **Available Tools** | `TradeExecutor.execute_decisions()` |
| **Incoming Data** | `portfolio_id` (str), `analysis_date` (str), `prices` (dict), `pm_decision` (JSON str) |
| **Outgoing Data** | `execution_result` (JSON str — `{executed_trades: [], failed_trades: [], error?: str}`), `sender` = `"execute_trades"` |

---

## 4. Data Contracts (Strict)

### 4.1 Scanner Graph State

#### 4.1.1 `ScannerState` — Full State Schema

```python
class ScannerState(MessagesState):
    # Input (set once by caller)
    scan_date: str                              # REQUIRED — "YYYY-MM-DD"

    # Phase 1a: Raw scanner reports (one writer per field)
    gatekeeper_universe_report: str             # Written by gatekeeper_scanner
    geopolitical_report: str                    # Written by geopolitical_scanner
    market_movers_report: str                   # Written by market_movers_scanner
    sector_performance_report: str              # Written by sector_scanner

    # Phase 1b/c: Follow-on scanner reports
    factor_alignment_report: str                # Written by factor_alignment_scanner
    drift_opportunities_report: str             # Written by drift_scanner
    smart_money_report: str                     # Written by smart_money_scanner

    # Summarized outputs (written by scanner_summarizer instances)
    gatekeeper_summary: str                     # Written by summarize_gatekeeper
    geopolitical_summary: str                   # Written by summarize_geopolitical
    market_movers_summary: str                  # Written by summarize_market_movers
    sector_summary: str                         # Written by summarize_sector
    factor_alignment_summary: str               # Written by summarize_factor_alignment
    drift_opportunities_summary: str            # Written by summarize_drift
    smart_money_summary: str                    # Written by summarize_smart_money
    industry_deep_dive_summary: str             # Written by summarize_industry_deep_dive

    # Phase 2: Deep dive
    industry_deep_dive_report: str              # Written by industry_deep_dive

    # Phase 3: Final output
    macro_scan_summary: str                     # REQUIRED OUTPUT — Written by macro_synthesis (JSON)

    # Tracking
    sender: str                                 # Last node that wrote
    messages: list                              # LangGraph message list (inherited)
```

All `str` fields use `_last_value` reducer for concurrent-write safety.

#### 4.1.2 `macro_scan_summary` — Output JSON Schema

```json
{
  "timeframe": "string",                        // REQUIRED — "1 month" | "2 months" | "3 months"
  "executive_summary": "string",                // REQUIRED — 2-3 sentence macro overview
  "macro_context": {                            // REQUIRED
    "economic_cycle": "string",                 // REQUIRED — e.g., "late expansion"
    "central_bank_stance": "string",            // REQUIRED — e.g., "hawkish hold"
    "geopolitical_risks": ["string"]            // REQUIRED — list of risk factors
  },
  "key_themes": [                               // REQUIRED — array of 3-5 themes
    {
      "theme": "string",                        // REQUIRED
      "description": "string",                  // REQUIRED
      "conviction": "high|medium|low",          // REQUIRED
      "timeframe": "string"                     // REQUIRED
    }
  ],
  "stocks_to_investigate": [                    // REQUIRED — up to max_scan_tickers (default 10)
    {
      "ticker": "string",                       // REQUIRED — e.g., "AAPL"
      "name": "string",                         // REQUIRED
      "sector": "string",                       // REQUIRED
      "rationale": "string",                    // REQUIRED
      "thesis_angle": "string",                 // REQUIRED
      "conviction": "high|medium|low",          // REQUIRED
      "key_catalysts": ["string"],              // REQUIRED
      "risks": ["string"]                       // REQUIRED
    }
  ],
  "risk_factors": ["string"]                    // REQUIRED — global risk factors
}
```

---

### 4.2 Per-Ticker Pipeline State

#### 4.2.1 `AgentState` — Full State Schema

```python
class AgentState(MessagesState):
    # Identity and configuration (set at initialization)
    run_id: str                                 # REQUIRED — Canonical ULID run identifier
    company_of_interest: str                    # REQUIRED — Ticker symbol, e.g., "AAPL"
    trade_date: str                             # REQUIRED — "YYYY-MM-DD"
    portfolio_context: str                      # REQUIRED — "candidate" | "holding"
    instrument_key: str                         # REQUIRED — Canonical instrument identity
    asset_class: str                            # REQUIRED — e.g., "equity"
    instrument_type: str                        # REQUIRED — e.g., "common_stock"
    is_etf: bool                                # REQUIRED
    is_inverse: bool                            # REQUIRED
    is_leveraged: bool                          # REQUIRED

    # Scanner context (injected at initialization)
    scanner_context_packet: str                 # OPTIONAL — Consolidated scanner phase context

    # Tracking
    sender: str                                 # Last agent that wrote

    # Analyst reports
    market_report: str                          # Written by Market Analyst
    market_report_structured: dict              # Written by Market Analyst
    macro_regime_report: str                    # Written by Market Analyst
    sentiment_report: str                       # Written by Social Analyst
    sentiment_report_structured: dict           # Written by Social Analyst
    news_report: str                            # Written by News Analyst
    news_report_structured: dict                # Written by News Analyst
    fundamentals_report: str                    # Written by Fundamentals Analyst
    fundamentals_report_structured: dict        # Written by Fundamentals Analyst
    research_packet_summary: str                # Derived artifact (not in main path)

    # Investment debate
    investment_debate_state: InvestDebateState   # Written by Bull/Bear/Research Manager
    investment_plan: str                         # Written by Research Manager
    investment_plan_structured: dict             # Written by Research Manager

    # Trader plan
    trader_investment_plan: str                  # Written by Trader
    trader_plan_structured: dict                 # Written by Trader

    # Risk debate
    risk_debate_state: RiskDebateState           # Written by Risk Synthesis
    risk_r1_aggressive: str                      # Written by Aggressive R1
    risk_r1_conservative: str                    # Written by Conservative R1
    risk_r1_neutral: str                         # Written by Neutral R1
    risk_r2_aggressive: str                      # Written by Aggressive R2
    risk_r2_conservative: str                    # Written by Conservative R2
    risk_r2_neutral: str                         # Written by Neutral R2
    risk_synthesis_structured: dict              # Written by Risk Synthesis

    # Final decision
    final_trade_decision: str                    # Written by Portfolio Manager
    final_trade_decision_structured: dict        # Written by Portfolio Manager
    analysis_status: str                         # "pending" | "completed" | "aborted"
    terminal_action: str                         # e.g., "BUY", "SELL", "CRITICAL_ABORT"
    critical_abort_reason: str                   # Raw report text triggering abort
```

#### 4.2.2 `market_report_structured` — Market Analyst Output

```json
{
  "ticker": "string",                           // REQUIRED — e.g., "AAPL"
  "as_of_date": "string",                       // REQUIRED — "YYYY-MM-DD"
  "status": "completed|aborted|timeout_fallback|empty",  // REQUIRED
  "macro_regime": "risk_on|risk_off|transition|unknown",  // REQUIRED
  "summary_bullets": ["string"],                // OPTIONAL — key quantitative points
  "has_critical_abort": false                   // REQUIRED — boolean
}
```

#### 4.2.3 `sentiment_report_structured` — Social Analyst Output

```json
{
  "ticker": "string",                           // REQUIRED
  "as_of_date": "string",                       // REQUIRED
  "status": "completed|timeout_fallback|empty",  // REQUIRED
  "sentiment_direction": "bullish|bearish|mixed|neutral",  // REQUIRED
  "has_critical_abort": false                   // REQUIRED
}
```

#### 4.2.4 `news_report_structured` — News Analyst Output

```json
{
  "ticker": "string",                           // REQUIRED — company ticker symbol
  "as_of_date": "YYYY-MM-DD",                   // REQUIRED — report date
  "status": "completed|empty|invalid_structured_payload|missing_structured_payload|aborted",  // REQUIRED
  "contract_version": "news_report_v1",         // REQUIRED — canonical contract version
  "abort_reason": "string",                     // REQUIRED — error description for non-completed statuses
  "report_title": "string",                     // REQUIRED
  "claims": [                                   // REQUIRED — verified claims array
    {
      "claim": "string",                        // REQUIRED — one-sentence grounded claim
      "source": "string",                       // REQUIRED — exact source name
      "published_at": "YYYY-MM-DD",             // REQUIRED for article claims
      "evidence_id": "art_...",                 // REQUIRED for article claims — stable evidence handle
      "scan_date": "YYYY-MM-DD"                 // REQUIRED for Finviz scanner claims
    }
  ],
  "summary_table": [                            // REQUIRED — summary table rows
    {
      "date": "YYYY-MM-DD",                     // REQUIRED
      "event": "string",                        // REQUIRED — short label
      "metric": "string",                       // REQUIRED
      "value": "string",                        // REQUIRED — exact value
      "source": "string",                       // REQUIRED
      "evidence_id": "art_...",                 // REQUIRED for article rows
      "scan_date": "YYYY-MM-DD"                 // REQUIRED for scanner rows
    }
  ],
  "key_metrics": {                              // REQUIRED — computed metrics
    "claim_count": 0,                           // REQUIRED — number of claims
    "summary_rows": 0,                          // REQUIRED — number of summary table rows
    "evidence_ids": 0,                          // REQUIRED — count of unique evidence IDs
    "removed_claims": 0,                        // REQUIRED — claims removed during sanitization
    "below_min_claims": false                   // REQUIRED — flag for sparse output
  }
}
```

**Status Values:**
- `completed`: At least one verified claim remains after fact-checking
- `empty`: No validated claims available (successful run with no evidence)
- `invalid_structured_payload`: Malformed payload or all claims rejected
- `missing_structured_payload`: Analyst produced no structured payload
- `aborted`: Critical failure (analyst timeout or prefetch failure)

**Contract Version:** `news_report_v1` is the canonical news contract. Previous non-canonical statuses (`timeout_fallback`, `completed_sparse`) are no longer used for news.

**Downstream Usage:** Consumers should check `status == "completed"` and `key_metrics.claim_count > 0` before using news as evidence.

#### 4.2.5 `fundamentals_report_structured` — Fundamentals Analyst Output

```json
{
  "ticker": "string",                           // REQUIRED
  "as_of_date": "string",                       // REQUIRED
  "status": "completed|timeout_fallback|empty",  // REQUIRED
  "macro_regime": "string",                     // REQUIRED
  "has_critical_abort": false,                  // REQUIRED
  "ttm_highlights": {},                         // OPTIONAL — parsed TTM metrics
  "peer_comparison_summary": "string",          // OPTIONAL
  "sector_relative_summary": "string"           // OPTIONAL
}
```

#### 4.2.6 `InvestDebateState` — Investment Debate Schema

```json
{
  "bull_history": "string",                     // REQUIRED — cumulative bull arguments
  "bear_history": "string",                     // REQUIRED — cumulative bear arguments
  "history": "string",                          // REQUIRED — full debate transcript
  "summary": "string",                          // REQUIRED — rolling compressed summary
  "current_response": "string",                 // REQUIRED — latest response text
  "current_bull_summary": "string",             // REQUIRED — extracted bull summary points
  "current_bear_summary": "string",             // REQUIRED — extracted bear summary points
  "judge_decision": "string",                   // REQUIRED — Research Manager decision
  "count": 0                                    // REQUIRED — debate turn counter (int)
}
```

#### 4.2.7 `RiskDebateState` — Risk Debate Schema

```json
{
  "aggressive_history": "string",               // REQUIRED — cumulative aggressive arguments
  "conservative_history": "string",             // REQUIRED — cumulative conservative arguments
  "neutral_history": "string",                  // REQUIRED — cumulative neutral arguments
  "history": "string",                          // REQUIRED — full risk debate transcript
  "summary": "string",                          // REQUIRED — risk synthesis summary
  "latest_speaker": "string",                   // REQUIRED — last analyst who spoke
  "current_aggressive_response": "string",      // REQUIRED — latest aggressive position
  "current_conservative_response": "string",    // REQUIRED — latest conservative position
  "current_neutral_response": "string",         // REQUIRED — latest neutral position
  "judge_decision": "string",                   // REQUIRED — PM judge decision
  "count": 0                                    // REQUIRED — debate turn counter (int)
}
```

---

### 4.3 Portfolio Graph State

#### 4.3.1 `PortfolioManagerState` — Full State Schema

```python
class PortfolioManagerState(MessagesState):
    # Inputs (set once by caller, never written by nodes)
    portfolio_id: str                           # REQUIRED — portfolio UUID
    analysis_date: str                          # REQUIRED — "YYYY-MM-DD"
    prices: dict                                # REQUIRED — {ticker: float} live prices
    scan_summary: dict                          # REQUIRED — macro_scan_summary JSON
    ticker_analyses: dict                       # REQUIRED — {instrument_key: analysis_dict}

    # Processing fields (JSON-serialized strings, written by nodes)
    portfolio_data: str                         # Written by load_portfolio
    risk_metrics: str                           # Written by compute_risk
    holding_reviews: str                        # Written by review_holdings
    prioritized_candidates: str                 # Written by prioritize_candidates

    # Summary briefs (written by parallel summary agents)
    macro_brief: str                            # Written by macro_summary
    micro_brief: str                            # Written by micro_summary
    macro_memory_context: str                   # Written by macro_summary
    micro_memory_context: str                   # Written by micro_summary

    # Decision outputs
    pm_decision: str                            # Written by pm_decision / cash_sweep
    cash_sweep: str                             # Written by cash_sweep
    execution_result: str                       # Written by execute_trades

    # Tracking
    sender: str                                 # Last node that wrote
    messages: list                              # LangGraph message list (inherited)
```

#### 4.3.2 `portfolio_data` — load_portfolio Output

```json
{
  "portfolio": {                                // REQUIRED
    "portfolio_id": "string",                   // REQUIRED
    "name": "string",                           // REQUIRED
    "cash": 0.0,                                // REQUIRED — float
    "initial_cash": 0.0,                        // REQUIRED — float
    "total_value": null                         // OPTIONAL — float, enriched from prices
  },
  "holdings": [                                 // REQUIRED — may be empty
    {
      "ticker": "string",                       // REQUIRED
      "shares": 0.0,                            // REQUIRED — float
      "avg_cost": 0.0,                          // REQUIRED — float
      "current_value": null,                    // OPTIONAL — enriched from prices
      "weight": null                            // OPTIONAL — enriched from total_value
    }
  ],
  "error": "string"                             // OPTIONAL — present only on failure
}
```

#### 4.3.3 `holding_reviews` — Holding Reviewer Output

```json
{
  "AAPL": {                                     // Key = ticker symbol
    "recommendation": "HOLD|SELL",              // REQUIRED
    "confidence": "high|medium|low",            // REQUIRED
    "rationale": "string",                      // REQUIRED
    "key_risks": ["string"]                     // REQUIRED
  }
}
```

#### 4.3.4 `prioritized_candidates` — Candidate Prioritizer Output

```json
[
  {
    "ticker": "string",                         // REQUIRED
    "instrument_key": "string",                 // REQUIRED
    "sector": "string",                         // OPTIONAL
    "conviction": "high|medium|low",            // REQUIRED
    "thesis_angle": "string",                   // OPTIONAL
    "key_catalysts": ["string"],                // OPTIONAL
    "candidate_final_trade_decision_summary": "string"  // REQUIRED — from deep-dive
  }
]
```

#### 4.3.5 `risk_metrics` — compute_risk Output

```json
{
  "total_value": 0.0,                           // REQUIRED — float
  "cash_pct": 0.0,                              // REQUIRED — float (0-1)
  "equity_pct": 0.0,                            // REQUIRED — float (0-1)
  "concentration": {                            // REQUIRED
    "top_holding_pct": 0.0,                     // float
    "hhi": 0.0                                  // Herfindahl-Hirschman Index
  },
  "volatility": {                               // OPTIONAL — requires price histories
    "portfolio_vol": null,
    "max_drawdown": null
  },
  "error": "string"                             // OPTIONAL — present only on failure
}
```

#### 4.3.6 `macro_brief` — Macro Summary Output Format

```
MACRO REGIME: [risk-on|risk-off|neutral|transition]
KEY NUMBERS: [exact numeric values from scan]
TOP 3 THEMES: [with quantitative descriptions]
MACRO-ALIGNED TICKERS: [high-conviction candidates]
REGIME MEMORY NOTE: [lessons from past similar regimes]
```

#### 4.3.7 `pm_decision` — PM Decision Schema (Pydantic)

```json
{
  "macro_regime": "risk-on|risk-off|neutral|transition",  // REQUIRED
  "regime_alignment_note": "string",            // REQUIRED
  "sells": [                                    // REQUIRED — may be empty
    {
      "ticker": "string",                       // REQUIRED
      "shares": 0.0,                            // REQUIRED — float
      "rationale": "string",                    // REQUIRED
      "macro_driven": false                     // REQUIRED — boolean
    }
  ],
  "buys": [                                     // REQUIRED — may be empty
    {
      "ticker": "string",                       // REQUIRED
      "shares": 0.0,                            // REQUIRED — float
      "price_target": 0.0,                      // REQUIRED — float
      "stop_loss": 0.0,                         // REQUIRED — float (5-15% below entry)
      "take_profit": 0.0,                       // REQUIRED — float (10-30% above entry)
      "sector": "string",                       // REQUIRED
      "rationale": "string",                    // REQUIRED
      "thesis": "string",                       // REQUIRED
      "macro_alignment": "string",              // REQUIRED
      "memory_note": "string",                  // OPTIONAL
      "position_sizing_logic": "string"         // REQUIRED
    }
  ],
  "holds": [                                    // REQUIRED — may be empty
    {
      "ticker": "string",                       // REQUIRED
      "rationale": "string"                     // REQUIRED
    }
  ],
  "cash_reserve_pct": 0.05,                     // REQUIRED — float (0-1)
  "portfolio_thesis": "string",                 // REQUIRED
  "risk_summary": "string",                     // REQUIRED
  "forensic_report": {                          // REQUIRED
    "regime_alignment": "string",               // REQUIRED
    "key_risks": ["string"],                    // REQUIRED
    "decision_confidence": "high|medium|low",   // REQUIRED
    "position_sizing_rationale": "string"       // REQUIRED
  }
}
```

#### 4.3.8 `execution_result` — Trade Executor Output

```json
{
  "executed_trades": [                          // REQUIRED — may be empty
    {
      "ticker": "string",
      "action": "BUY|SELL",
      "shares": 0.0,
      "price": 0.0,
      "total": 0.0
    }
  ],
  "failed_trades": [                            // REQUIRED — may be empty
    {
      "ticker": "string",
      "action": "BUY|SELL",
      "shares": 0.0,
      "error": "string"
    }
  ],
  "error": "string"                             // OPTIONAL — top-level error
}
```

---

## 5. End-to-End Data Flow

### 5.1 Sample Input Tracking: "AAPL" from Scan to Execution

Below we trace a concrete example of how the ticker "AAPL" flows through the entire system,
showing the data transformations at each stage.

#### Stage 1 — Scanner Graph

**Input:**
```json
{"scan_date": "2026-03-31", "messages": []}
```

**Phase 1a — Parallel Scanners execute:**
- `gatekeeper_scanner` → `gatekeeper_universe_report`: "...AAPL: $220.50, Market Cap $3.4T, Avg Volume 65M..."
- `market_movers_scanner` → `market_movers_report`: "...S&P 500 +0.4%, Nasdaq +0.6%, Risk-On regime..."
- `sector_scanner` → `sector_performance_report`: "...Technology +1.2% 1W, +3.8% 1M, strongest rotation..."
- `geopolitical_scanner` → `geopolitical_report`: "...US-China tariff review deadline April 15..."

**Phase 1b — Smart Money detects insider accumulation:**
- `smart_money_scanner` → `smart_money_report`: "...AAPL: Unusual volume +180% avg, insider buy $2.1M..."

**Phase 2/3 — Industry Deep Dive and Synthesis:**
- `macro_synthesis` → `macro_scan_summary`:
```json
{
  "timeframe": "1 month",
  "executive_summary": "Risk-on regime with tech sector leadership...",
  "stocks_to_investigate": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc",
      "sector": "Technology",
      "rationale": "Smart money accumulation + sector leadership",
      "thesis_angle": "Momentum continuation with insider confirmation",
      "conviction": "high",
      "key_catalysts": ["Q2 earnings Apr 24", "WWDC keynote June"],
      "risks": ["China revenue exposure", "Tariff deadline Apr 15"]
    }
  ]
}
```

#### Stage 2 — Per-Ticker Pipeline for AAPL

**Initial State (via `Propagator.create_initial_state()`):**
```json
{
  "run_id": "01JQWX...",
  "company_of_interest": "AAPL",
  "trade_date": "2026-03-31",
  "portfolio_context": "candidate",
  "scanner_context_packet": "<consolidated scanner context with commodity prices, FX, calendar>",
  "instrument_key": "AAPL",
  "asset_class": "equity",
  "instrument_type": "common_stock",
  "is_etf": false,
  "analysis_status": "pending",
  "investment_debate_state": {"count": 0, "history": "", ...},
  "risk_debate_state": {"count": 0, "history": "", ...}
}
```

**Market Analyst output:**
```
State updates:
  market_report: "- AAPL trading at $220.50, +1.2% WoW\n- RSI: 62 (neutral-bullish)..."
  macro_regime_report: "Risk-On: SPX above 200 SMA, VIX at 14.2..."
  market_report_structured: {"ticker": "AAPL", "status": "completed", "macro_regime": "risk_on"}
```

**Social Analyst output:**
```
State updates:
  sentiment_report: "- 34 articles, 8 publishers; polarity improving +0.3→+0.6..."
  sentiment_report_structured: {"ticker": "AAPL", "status": "completed", "sentiment_direction": "improving"}
```

**News Analyst output:**
```
State updates:
  news_report_structured: {
    "ticker": "AAPL",
    "claims": [
      {"claim": "AAPL: iPhone 17 supply chain ramp confirmed...", "source": "Nikkei Asia", "evidence_id": "art_nikkei_001"}
    ]
  }
```

**Fundamentals Analyst output:**
```
State updates:
  fundamentals_report: "- Revenue TTM $407B, +6.2% YoY\n- Gross margin 46.8%, +120bps..."
  fundamentals_report_structured: {"ticker": "AAPL", "status": "completed", "macro_regime": "risk_on"}
```

**Bull/Bear Debate (2 rounds):**
```
Round 1: Bull argues momentum + insider buying + margin expansion
Round 1: Bear counters with China tariff risk + mature growth
Round 2: Bull rebuts with services growth 18% YoY + buyback program
Round 2: Bear rebuts with valuation at 31x forward P/E vs 5-year avg 27x

investment_debate_state.count = 4
```

**Research Manager decision:**
```
State updates:
  investment_plan: "BUY — Momentum continuation thesis with insider confirmation. Risk/reward favors upside..."
  investment_debate_state.judge_decision: "BUY with conviction HIGH"
```

**Trader proposal:**
```
State updates:
  trader_investment_plan: "Entry: $220.50 | Stop-loss: $198.45 (-10%) | Take-profit: $253.58 (+15%)
    Catalyst: Q2 earnings Apr 24 | Position size: 2% of portfolio"
```

**Risk Debate (2 parallel rounds + synthesis):**
```
Round 1 (parallel): Aggressive, Conservative, Neutral each write initial positions
Round 2 (parallel): Each reads others' R1, provides rebuttals
Risk Synthesis: Combines 6 responses into unified risk assessment
```

**Portfolio Manager final decision:**
```
State updates:
  final_trade_decision: "Rating: BUY | Conviction: HIGH | Entry $220.50..."
  analysis_status: "completed"
  terminal_action: "BUY"
```

#### Stage 3 — Portfolio Graph

**Initial State:**
```json
{
  "portfolio_id": "portfolio-uuid",
  "analysis_date": "2026-03-31",
  "prices": {"AAPL": 220.50, "MSFT": 420.00, "SGOV": 100.25},
  "scan_summary": {"stocks_to_investigate": [{"ticker": "AAPL", ...}]},
  "ticker_analyses": {"AAPL": {"final_trade_decision": "Rating: BUY...", "analysis_status": "completed"}}
}
```

**load_portfolio →** `portfolio_data`: `{"portfolio": {"cash": 50000}, "holdings": [{"ticker": "MSFT", "shares": 100}]}`

**compute_risk →** `risk_metrics`: `{"total_value": 92000, "cash_pct": 0.54, "concentration": {"hhi": 0.21}}`

**review_holdings →** `holding_reviews`: `{"MSFT": {"recommendation": "HOLD", "confidence": "high"}}`

**prioritize_candidates →** `prioritized_candidates`: `[{"ticker": "AAPL", "conviction": "high"}]`

**macro_summary + micro_summary (parallel) →** `macro_brief` + `micro_brief`

**make_pm_decision →**
```json
{
  "macro_regime": "risk-on",
  "sells": [],
  "buys": [{"ticker": "AAPL", "shares": 90, "stop_loss": 198.45, "take_profit": 253.58}],
  "holds": [{"ticker": "MSFT", "rationale": "Thesis intact"}],
  "cash_reserve_pct": 0.05
}
```

**cash_sweep →** Excess cash above 5%: buys 250 shares SGOV

**execute_trades →**
```json
{
  "executed_trades": [
    {"ticker": "AAPL", "action": "BUY", "shares": 90, "price": 220.50, "total": 19845.00},
    {"ticker": "SGOV", "action": "BUY", "shares": 250, "price": 100.25, "total": 25062.50}
  ],
  "failed_trades": []
}
```

---

## 6. Constraints

### 6.1 Schema Naming Conventions

| Convention | Rule |
|-----------|------|
| **State field naming** | `snake_case` for all state fields |
| **Report fields** | `{domain}_report` for prose, `{domain}_report_structured` for machine-readable dict |
| **Debate state fields** | `{perspective}_history`, `current_{perspective}_response`, `current_{perspective}_summary` |
| **Risk round fields** | `risk_r{round}_{perspective}` — e.g., `risk_r1_aggressive`, `risk_r2_conservative` |
| **Portfolio JSON fields** | Serialized as JSON strings in state; parsed inside each node |
| **Sender tracking** | Every node writes `sender` = `"{node_name}"` |

### 6.2 Field Compatibility Rules

| Output Agent | Output Field | Consumer Agent | Input Field |
|-------------|-------------|----------------|-------------|
| Market Analyst | `market_report` | Bull/Bear Researchers, Research Manager, Trader, Risk Agents, PM | `market_report` (via `build_research_packet()`) |
| Market Analyst | `macro_regime_report` | Social, News, Fundamentals Analysts + downstream | `macro_regime_report` |
| Market Analyst | `market_report_structured` | Downstream structured consumers | `market_report_structured` |
| Social Analyst | `sentiment_report` | Bull/Bear, Research Manager, Trader, PM | `sentiment_report` |
| News Analyst | `news_report` | Bull/Bear, Research Manager, Trader, PM | `news_report` |
| News Analyst | `news_report_structured` | News Fact Checker | `news_report_structured` |
| Fundamentals Analyst | `fundamentals_report` | Bull/Bear, Research Manager, Trader, PM | `fundamentals_report` |
| Bull/Bear Researchers | `investment_debate_state` | Research Manager | `investment_debate_state` |
| Research Manager | `investment_plan` | Trader | `investment_plan` |
| Trader | `trader_investment_plan` | Risk Agents, Risk Synthesis, PM | `trader_investment_plan` |
| Risk R1/R2 agents | `risk_r{n}_{perspective}` | Other R2 agents, Risk Synthesis | `risk_r{n}_{perspective}` |
| Risk Synthesis | `risk_debate_state` | Portfolio Manager | `risk_debate_state` |
| PM (per-ticker) | `final_trade_decision` | Portfolio `ticker_analyses` | `ticker_analyses[key]["final_trade_decision"]` |
| macro_synthesis | `macro_scan_summary` | Portfolio `scan_summary` | `scan_summary` |
| load_portfolio | `portfolio_data` | compute_risk, review_holdings, prioritize_candidates, cash_sweep | `portfolio_data` |
| review_holdings | `holding_reviews` | micro_summary | `holding_reviews` |
| prioritize_candidates | `prioritized_candidates` | micro_summary, pm_decision | `prioritized_candidates` |
| macro_summary | `macro_brief` | pm_decision | `macro_brief` |
| micro_summary | `micro_brief` | pm_decision | `micro_brief` |
| pm_decision | `pm_decision` | cash_sweep, execute_trades | `pm_decision` |

### 6.3 Critical Abort Protocol

- Any analyst can trigger `[CRITICAL ABORT]` by prepending the marker to its report
- `state_has_critical_abort()` checks `market_report`, `news_report`, `fundamentals_report`
- Abort routes immediately to `Critical Abort Terminal` (bypasses debate/risk)
- Critical Abort Terminal sets `analysis_status` = `"aborted"`, `terminal_action` = `"CRITICAL_ABORT"`
- Abort conditions: delisting, bankruptcy, SEC enforcement, market cap collapse >90%, regulatory shutdown

### 6.4 Ground Truth Propagation

All pipeline agents (4 analysts, Research Manager, Trader, 3 risk debaters × 2 rounds, risk synthesis) have explicit **GROUND TRUTH** instructions referencing the Scanner Context (Phase 1) section for:
- Commodity prices (gold, oil, bitcoin)
- FX rates (EUR/USD, JPY/USD, CNY/USD)
- Calendar dates (earnings, FOMC, CPI)

Agents must NOT deviate from these numbers or dates. Summary rules preserve ground-truth values through compression.

### 6.5 Data Integrity Rules

| Rule | Enforcement |
|------|------------|
| No undefined fields | All state fields are typed in `AgentState`, `ScannerState`, `PortfolioManagerState` |
| Reducer safety | Parallel-written fields use `_last_value` reducer; each field has exactly one writer |
| JSON serialization | Portfolio state fields (`portfolio_data`, `holding_reviews`, etc.) are JSON strings; each consumer calls `json.loads()` |
| Structured output validation | News Analyst uses 2-attempt validation with retry; PM Decision uses `with_structured_output()` with raw fallback |
| Memory isolation | Each memory system (`FinancialSituationMemory`, `MacroMemory`, `ReflexionMemory`) is scoped to its consumer; no cross-agent memory leakage |
| Run identity | Single canonical `run_id` (ULID) flows through all phases; persisted artifacts live under `reports/daily/{date}/{run_id}/` |

### 6.6 Timeout and Fallback Behavior

| Agent | Timeout Source | Fallback Behavior |
|-------|---------------|-------------------|
| Market Analyst | `quick_think_llm_timeout_cap` (default 45s) | Deterministic markdown report with macro regime from prefetched data |
| Social Analyst | `mid_think_llm_timeout_cap` (default 60s) | "Treat sentiment as neutral" AIMessage |
| News Analyst | `mid_think_llm_timeout_cap` (default 60s) | Timeout structured payload from persisted evidence records |
| Fundamentals Analyst | `run_tool_loop` internal timeout | Report with `status: "timeout_fallback"` |
| Scanner agents | `run_tool_loop` internal timeout | Fallback message with partial data |

---

*Document generated by reverse-engineering production code in `tradingagents/` and `agent_os/`.*
