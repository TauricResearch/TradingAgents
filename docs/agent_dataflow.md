# Agent Data & Information Flows

This document describes how each agent in the TradingAgents framework collects
data, processes it, and sends it to an LLM for analysis or decision-making.
It also records the default model and **thinking modality** (quick / mid / deep)
used by every agent.

> **Source of truth** for LLM tier defaults: `tradingagents/default_config.py`

---

## Table of Contents

1. [Thinking-Modality Overview](#1-thinking-modality-overview)
2. [Trading Pipeline Flow](#2-trading-pipeline-flow)
3. [Scanner Pipeline Flow](#3-scanner-pipeline-flow)
4. [Per-Agent Data Flows](#4-per-agent-data-flows)
   - [4.1 Market Analyst](#41-market-analyst)
   - [4.2 Fundamentals Analyst](#42-fundamentals-analyst)
   - [4.3 News Analyst](#43-news-analyst)
   - [4.4 Social Media Analyst](#44-social-media-analyst)
   - [4.5 Bull Researcher](#45-bull-researcher)
   - [4.6 Bear Researcher](#46-bear-researcher)
   - [4.7 Research Manager](#47-research-manager)
   - [4.8 Trader](#48-trader)
   - [4.9 Aggressive Debator](#49-aggressive-debator)
   - [4.10 Conservative Debator](#410-conservative-debator)
   - [4.11 Neutral Debator](#411-neutral-debator)
   - [4.12 Risk Manager](#412-risk-manager)
   - [4.13 Geopolitical Scanner](#413-geopolitical-scanner)
   - [4.14 Market Movers Scanner](#414-market-movers-scanner)
   - [4.15 Sector Scanner](#415-sector-scanner)
   - [4.16 Smart Money Scanner](#416-smart-money-scanner)
   - [4.17 Industry Deep Dive](#417-industry-deep-dive)
   - [4.18 Macro Synthesis](#418-macro-synthesis)
5. [Tool → Data-Source Mapping](#5-tool--data-source-mapping)
6. [Memory System](#6-memory-system)
7. [Tool Data Formats & Sizes](#7-tool-data-formats--sizes)
8. [Context Window Budget](#8-context-window-budget)
9. [End-to-End Token Estimates](#9-end-to-end-token-estimates)

---

## 1. Thinking-Modality Overview

The framework uses a **3-tier LLM system** so that simple extraction tasks run
on fast, cheap models while critical judgment calls use the most capable model.

| Tier | Config Key | Default Model | Purpose |
|------|-----------|---------------|---------|
| **Quick** | `quick_think_llm` | `gpt-5-mini` | Fast extraction, summarization, debate positions |
| **Mid** | `mid_think_llm` | *None* → falls back to quick | Balanced reasoning with memory |
| **Deep** | `deep_think_llm` | `gpt-5.2` | Complex synthesis, final judgments |

Each tier can have its own `_llm_provider` and `_backend_url` overrides.
All are overridable via `TRADINGAGENTS_<KEY>` env vars.

### Agent → Tier Assignment

| # | Agent | Tier | Has Tools? | Has Memory? | Tool Execution |
|---|-------|------|-----------|-------------|----------------|
| 1 | Market Analyst | **Quick** | ✅ | — | LangGraph ToolNode |
| 2 | Fundamentals Analyst | **Quick** | ✅ | — | LangGraph ToolNode |
| 3 | News Analyst | **Quick** | ✅ | — | LangGraph ToolNode |
| 4 | Social Media Analyst | **Quick** | ✅ | — | LangGraph ToolNode |
| 5 | Bull Researcher | **Mid** | — | ✅ | — |
| 6 | Bear Researcher | **Mid** | — | ✅ | — |
| 7 | Research Manager | **Deep** | — | ✅ | — |
| 8 | Trader | **Mid** | — | ✅ | — |
| 9 | Aggressive Debator | **Quick** | — | — | — |
| 10 | Conservative Debator | **Quick** | — | — | — |
| 11 | Neutral Debator | **Quick** | — | — | — |
| 12 | Risk Manager | **Deep** | — | ✅ | — |
| 13 | Geopolitical Scanner | **Quick** | ✅ | — | `run_tool_loop()` |
| 14 | Market Movers Scanner | **Quick** | ✅ | — | `run_tool_loop()` |
| 15 | Sector Scanner | **Quick** | ✅ | — | `run_tool_loop()` |
| 16 | Smart Money Scanner | **Quick** | ✅ | — | `run_tool_loop()` |
| 17 | Industry Deep Dive | **Mid** | ✅ | — | `run_tool_loop()` |
| 18 | Macro Synthesis | **Deep** | — | — | — |

---

## 2. Trading Pipeline Flow

```
                         ┌─────────────────────────┐
                         │         START            │
                         │  (ticker + trade_date)   │
                         └────────────┬─────────────┘
                                      │
              ┌───────────────────────┬┴┬───────────────────────┐
              ▼                       ▼ ▼                       ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │  Market Analyst   │  │  News Analyst     │  │  Social Analyst   │  │  Fundamentals    │
   │  (quick_think)    │  │  (quick_think)    │  │  (quick_think)    │  │  Analyst          │
   │                   │  │                   │  │                   │  │  (quick_think)    │
   │ Tools:            │  │ Tools:            │  │ Tools:            │  │ Tools:            │
   │ • get_macro_regime│  │ • get_news        │  │ • get_news        │  │ • get_ttm_analysis│
   │ • get_stock_data  │  │ • get_global_news │  │   (sentiment)     │  │ • get_fundamentals│
   │ • get_indicators  │  │ • get_insider_txn │  │                   │  │ • get_peer_comp.  │
   │                   │  │                   │  │                   │  │ • get_sector_rel. │
   │ Output:           │  │ Output:           │  │ Output:           │  │ • get_balance_sh. │
   │ market_report     │  │ news_report       │  │ sentiment_report  │  │ • get_cashflow    │
   │ macro_regime_rpt  │  │                   │  │                   │  │ • get_income_stmt │
   └────────┬─────────┘  └────────┬──────────┘  └────────┬──────────┘  │ Output:           │
            │                     │                       │             │ fundamentals_rpt  │
            └─────────────────────┼───────────────────────┘             └────────┬──────────┘
                                  │                                              │
                                  ▼                                              │
                    ┌─────────────────────────┐◄─────────────────────────────────┘
                    │     4 analyst reports    │
                    │  feed into debate below  │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │       Investment Debate Phase        │
              │                                      │
              │  ┌───────────┐      ┌───────────┐   │
              │  │   Bull     │◄────►│   Bear     │  │
              │  │ Researcher │      │ Researcher │  │
              │  │ (mid_think)│      │ (mid_think)│  │
              │  │ + memory   │      │ + memory   │  │
              │  └───────────┘      └───────────┘   │
              │        (max_debate_rounds = 2)       │
              └──────────────────┬───────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Research Manager       │
                    │   (deep_think + memory)  │
                    │                          │
                    │   Reads: debate history, │
                    │   4 analyst reports,     │
                    │   macro regime           │
                    │                          │
                    │   Output:                │
                    │   investment_plan        │
                    │   (BUY / SELL / HOLD)    │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │       Trader             │
                    │   (mid_think + memory)   │
                    │                          │
                    │   Reads: investment_plan,│
                    │   4 analyst reports      │
                    │                          │
                    │   Output:                │
                    │   trader_investment_plan │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              │         Risk Debate Phase            │
              │                                      │
              │  ┌────────────┐  ┌───────────────┐  │
              │  │ Aggressive  │  │ Conservative   │ │
              │  │ (quick)     │  │ (quick)        │ │
              │  └──────┬─────┘  └───────┬────────┘ │
              │         │    ┌───────────┐│          │
              │         └───►│  Neutral   │◄─────────┘
              │              │  (quick)   │           │
              │              └───────────┘            │
              │   (max_risk_discuss_rounds = 2)       │
              └──────────────────┬────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    Risk Manager          │
                    │   (deep_think + memory)  │
                    │                          │
                    │   Reads: risk debate,    │
                    │   trader plan, 4 reports,│
                    │   macro regime           │
                    │                          │
                    │   Output:                │
                    │   final_trade_decision   │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                         ┌───────────────┐
                         │      END      │
                         └───────────────┘
```

---

## 3. Scanner Pipeline Flow

```
                              ┌─────────────────────────┐
                              │         START            │
                              │      (scan_date)         │
                              └────────────┬─────────────┘
                                           │
         ┌─────────────────────────────────┼──────────────────────────────────┐
         ▼                                 ▼                                  ▼
┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
│  Geopolitical    │          │  Market Movers   │          │  Sector Scanner  │
│  Scanner         │          │  Scanner         │          │                  │
│  (quick_think)   │          │  (quick_think)   │          │  (quick_think)   │
│                  │          │                  │          │                  │
│ Tools:           │          │ Tools:           │          │ Tools:           │
│ • get_topic_news │          │ • get_market_    │          │ • get_sector_    │
│                  │          │   movers         │          │   performance    │
│ Output:          │          │ • get_market_    │          │                  │
│ geopolitical_rpt │          │   indices        │          │ Output:          │
│                  │          │                  │          │ sector_perf_rpt  │
│                  │          │ Output:          │          │                  │
│                  │          │ market_movers_rpt│          │        │         │
└────────┬─────────┘          └────────┬─────────┘          └────────┼─────────┘
         │                             │                              │
         │                             │              ┌───────────────┘
         │                             │              ▼  (sector data available)
         │                             │   ┌──────────────────────────┐
         │                             │   │   Smart Money Scanner    │
         │                             │   │   (quick_think)          │
         │                             │   │                          │
         │                             │   │ Context: sector_perf_rpt │
         │                             │   │                          │
         │                             │   │ Tools (no params):       │
         │                             │   │ • get_insider_buying_    │
         │                             │   │   stocks                 │
         │                             │   │ • get_unusual_volume_    │
         │                             │   │   stocks                 │
         │                             │   │ • get_breakout_          │
         │                             │   │   accumulation_stocks    │
         │                             │   │                          │
         │                             │   │ Output:                  │
         │                             │   │ smart_money_report       │
         │                             │   └──────────┬───────────────┘
         │                             │              │
         └─────────────────────────────┼──────────────┘
                                       │  (Phase 1 → Phase 2, all 4 reports)
                                       ▼
                       ┌─────────────────────────────┐
                       │    Industry Deep Dive        │
                       │    (mid_think)               │
                       │                              │
                       │ Reads: all 4 Phase-1 reports │
                       │ Auto-extracts top 3 sectors  │
                       │                              │
                       │ Tools:                       │
                       │ • get_industry_performance   │
                       │   (called per top sector)    │
                       │ • get_topic_news             │
                       │   (sector-specific searches) │
                       │                              │
                       │ Output:                      │
                       │ industry_deep_dive_report    │
                       └──────────────┬───────────────┘
                                      │  (Phase 2 → Phase 3)
                                      ▼
                       ┌─────────────────────────────┐
                       │     Macro Synthesis          │
                       │     (deep_think)             │
                       │                              │
                       │ Reads: all 5 prior reports   │
                       │ Golden Overlap: cross-refs   │
                       │ smart money tickers with     │
                       │ top-down macro thesis        │
                       │ No tools – pure LLM reasoning│
                       │                              │
                       │ Output:                      │
                       │ macro_scan_summary (JSON)    │
                       │ Top 8-10 stock candidates    │
                       │ with conviction & catalysts  │
                       └──────────────┬───────────────┘
                                      │
                                      ▼
                              ┌───────────────┐
                              │      END      │
                              └───────────────┘
```

**Graph Topology Notes:**
- **Phase 1a** (parallel from START): geopolitical, market_movers, sector scanners
- **Phase 1b** (sequential after sector): smart_money_scanner — runs after sector data is available so it can use sector rotation context when interpreting Finviz signals
- **Phase 2** (fan-in from all 4 Phase 1 nodes): industry_deep_dive
- **Phase 3**: macro_synthesis with Golden Overlap strategy

---

## 4. Per-Agent Data Flows

Each subsection follows the same structure:

> **Data sources → Tool calls → Intermediate processing → LLM prompt → Output**

---

### 4.1 Market Analyst

| | |
|---|---|
| **File** | `agents/analysts/market_analyst.py` |
| **Factory** | `create_market_analyst(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | LangGraph `ToolNode` (graph conditional edge) |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input: company_of_interest, trade_date        │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ 1. get_macro_regime(curr_date)                      │
 │    → Fetches VIX, credit spreads, yield curve,      │
 │      SPY breadth, sector rotation signals            │
 │    → Classifies: risk-on / risk-off / transition     │
 │    → Returns: Markdown regime report                 │
 │    Data source: yfinance (VIX, SPY, sector ETFs)     │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ 2. get_stock_data(symbol, start_date, end_date)     │
 │    → Fetches OHLCV price data                        │
 │    → Returns: formatted CSV string                   │
 │    Data source: yfinance / Alpha Vantage              │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ 3. get_indicators(symbol, indicator, curr_date)     │
 │    → Up to 8 indicators chosen by LLM:               │
 │      SMA, EMA, MACD, RSI, Bollinger, ATR, VWMA, OBV │
 │    → Returns: formatted indicator values              │
 │    Data source: yfinance / Alpha Vantage              │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ LLM Prompt (quick_think):                           │
 │ "You are a Market Analyst. Classify macro            │
 │  environment, select complementary indicators,       │
 │  frame analysis based on regime context.             │
 │  Provide fine-grained analysis with summary table."  │
 │                                                      │
 │ Context sent to LLM:                                 │
 │  • Macro regime classification                       │
 │  • OHLCV price data                                  │
 │  • Technical indicator values                        │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Output:                                              │
 │  • market_report (technical analysis text)           │
 │  • macro_regime_report (risk-on/off classification)  │
 └─────────────────────────────────────────────────────┘
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions + indicator list | ~2.1 KB | ~525 |
| `get_macro_regime` result | Markdown | Tables (regime + 6 signals) | ~0.8 KB | ~200 |
| `get_stock_data` result (30 days) | CSV | Header + OHLCV rows | ~5 KB | ~1,250 |
| `get_indicators` × 8 calls | Markdown | Daily values + description | ~7.2 KB | ~1,800 |
| **Total prompt** | | | **~15–20 KB** | **~3,750–5,000** |

---

### 4.2 Fundamentals Analyst

| | |
|---|---|
| **File** | `agents/analysts/fundamentals_analyst.py` |
| **Factory** | `create_fundamentals_analyst(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | LangGraph `ToolNode` |

**Data Flow:**

```
 State Input: company_of_interest, trade_date
                          │
                          ▼
 1. get_ttm_analysis(ticker, curr_date)
    → Internally calls: get_income_statement, get_balance_sheet, get_cashflow
    → Computes: 8-quarter trailing metrics (revenue growth QoQ/YoY,
      gross/operating/net margins, ROE trend, debt/equity, FCF)
    → Returns: Markdown TTM trend report
    Data source: yfinance / Alpha Vantage
                          │
                          ▼
 2. get_fundamentals(ticker, curr_date)
    → Fetches: P/E, PEG, P/B, beta, 52-week range, market cap
    → Returns: formatted fundamentals report
    Data source: yfinance / Alpha Vantage
                          │
                          ▼
 3. get_peer_comparison(ticker, curr_date)
    → Ranks company vs sector peers (1W, 1M, 3M, 6M, YTD returns)
    → Returns: ranked comparison table
    Data source: yfinance
                          │
                          ▼
 4. get_sector_relative(ticker, curr_date)
    → Computes alpha vs sector ETF benchmark
    → Returns: alpha report (1W, 1M, 3M, 6M, YTD)
    Data source: yfinance
                          │
                          ▼
 5. (Optional) get_balance_sheet / get_cashflow / get_income_statement
    → Raw financial statements
    Data source: yfinance / Alpha Vantage
                          │
                          ▼
 LLM Prompt (quick_think):
 "Call tools in prescribed sequence. Write comprehensive report
  with multi-quarter trends, TTM metrics, relative valuation,
  sector outperformance. Identify inflection points. Append
  Markdown summary table with key metrics."
                          │
                          ▼
 Output: fundamentals_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Sequence instructions + metric list | ~1.4 KB | ~350 |
| `get_ttm_analysis` result | Markdown | Tables (TTM summary + 8-quarter history) | ~1.6 KB | ~400 |
| `get_fundamentals` result | Markdown | Key ratios table (~15 metrics) | ~1.5 KB | ~375 |
| `get_peer_comparison` result | Markdown | Ranked table (~10 peers × 6 horizons) | ~1.2 KB | ~300 |
| `get_sector_relative` result | Markdown | Alpha table (5–6 time periods) | ~0.8 KB | ~200 |
| `get_balance_sheet` (optional) | CSV | Quarterly rows (up to 8) | ~2.5 KB | ~625 |
| `get_cashflow` (optional) | CSV | Quarterly rows (up to 8) | ~2.5 KB | ~625 |
| `get_income_statement` (optional) | CSV | Quarterly rows (up to 8) | ~2.5 KB | ~625 |
| **Total prompt (core)** | | | **~6.5 KB** | **~1,625** |
| **Total prompt (with optionals)** | | | **~14 KB** | **~3,500** |

---

### 4.3 News Analyst

| | |
|---|---|
| **File** | `agents/analysts/news_analyst.py` |
| **Factory** | `create_news_analyst(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | LangGraph `ToolNode` |

**Data Flow:**

```
 State Input: company_of_interest, trade_date
                          │
                          ▼
 1. get_news(ticker, start_date, end_date)
    → Fetches company-specific news articles (past week)
    → Returns: formatted article list (title, summary, source, date)
    Data source: yfinance / Finnhub / Alpha Vantage
                          │
                          ▼
 2. get_global_news(curr_date, look_back_days=7, limit=5)
    → Fetches broader macroeconomic / market news
    → Returns: formatted global news list
    Data source: yfinance / Alpha Vantage
                          │
                          ▼
 3. get_insider_transactions(ticker)
    → Fetches recent insider buy/sell activity
    → Returns: insider transaction report
    Data source: Finnhub (primary) / Alpha Vantage
                          │
                          ▼
 LLM Prompt (quick_think):
 "Analyze recent news and trends over the past week.
  Provide fine-grained analysis. Append Markdown table
  organising key points."
                          │
                          ▼
 Output: news_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.75 KB | ~187 |
| `get_news` result | Markdown | Article list (≤ 20 articles) | ~7 KB | ~1,750 |
| `get_global_news` result | Markdown | Article list (5 articles) | ~1.75 KB | ~437 |
| `get_insider_transactions` result | Markdown | Transaction table (10–50 rows) | ~1.5 KB | ~375 |
| **Total prompt** | | | **~11 KB** | **~2,750** |

---

### 4.4 Social Media Analyst

| | |
|---|---|
| **File** | `agents/analysts/social_media_analyst.py` |
| **Factory** | `create_social_media_analyst(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | LangGraph `ToolNode` |

**Data Flow:**

```
 State Input: company_of_interest, trade_date
                          │
                          ▼
 1. get_news(query, start_date, end_date)
    → Searches for company-related social media mentions & sentiment
    → Returns: formatted news articles related to sentiment
    Data source: yfinance / Finnhub / Alpha Vantage
                          │
                          ▼
 LLM Prompt (quick_think):
 "Analyze social media posts, recent news, public sentiment
  over the past week. Look at all sources. Provide
  fine-grained analysis. Append Markdown table."
                          │
                          ▼
 Output: sentiment_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.85 KB | ~212 |
| `get_news` result | Markdown | Article list (≤ 20 articles) | ~7 KB | ~1,750 |
| **Total prompt** | | | **~8 KB** | **~2,000** |

---

### 4.5 Bull Researcher

| | |
|---|---|
| **File** | `agents/researchers/bull_researcher.py` |
| **Factory** | `create_bull_researcher(llm, memory)` |
| **Thinking Modality** | **Mid** (`mid_think_llm`, falls back to `quick_think_llm`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input:                                         │
 │  • market_report (from Market Analyst)               │
 │  • sentiment_report (from Social Media Analyst)      │
 │  • news_report (from News Analyst)                   │
 │  • fundamentals_report (from Fundamentals Analyst)   │
 │  • investment_debate_state.history (debate transcript)│
 │  • investment_debate_state.current_response           │
 │    (latest Bear argument to counter)                 │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Memory Retrieval (BM25):                            │
 │  memory.get_memories(current_situation, n_matches=2) │
 │  → Retrieves 2 most similar past trading situations  │
 │  → Returns: matched situation + recommendation       │
 │  (Offline, no API calls)                             │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ LLM Prompt (mid_think):                             │
 │ "You are a Bull Researcher. Build evidence-based     │
 │  case FOR investing. Focus on growth potential,      │
 │  competitive advantages, positive indicators.        │
 │  Counter Bear's arguments with specific data.        │
 │  Use past reflections."                              │
 │                                                      │
 │ Context sent:                                        │
 │  • 4 analyst reports (concatenated)                  │
 │  • Full debate history                               │
 │  • Bear's latest argument                            │
 │  • 2 memory-retrieved past situations & lessons      │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Output:                                              │
 │  • investment_debate_state.bull_history (appended)   │
 │  • investment_debate_state.current_response (latest) │
 │  • investment_debate_state.count (incremented)       │
 └─────────────────────────────────────────────────────┘
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size (Rd 1) | Avg Size (Rd 2) | Avg Tokens (Rd 2) |
|-----------|-----------|--------|-----------------|-----------------|-------------------|
| Prompt template | Text | f-string with instructions | ~1.2 KB | ~1.2 KB | ~300 |
| 4 analyst reports | Text | Concatenated Markdown | ~13 KB | ~13 KB | ~3,250 |
| Debate history | Text | Accumulated transcript | ~0 KB | ~6 KB | ~1,500 |
| Last Bear argument | Text | Debate response | ~0 KB | ~2 KB | ~500 |
| Memory (2 matches) | Text | Past situations + advice | ~4 KB | ~4 KB | ~1,000 |
| **Total prompt** | | | **~18 KB** | **~26 KB** | **~6,550** |

> Prompt grows ~8 KB per debate round as history accumulates.

---

### 4.6 Bear Researcher

| | |
|---|---|
| **File** | `agents/researchers/bear_researcher.py` |
| **Factory** | `create_bear_researcher(llm, memory)` |
| **Thinking Modality** | **Mid** (`mid_think_llm`, falls back to `quick_think_llm`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 State Input:
  • 4 analyst reports
  • investment_debate_state.history
  • investment_debate_state.current_response (Bull's latest argument)
                          │
                          ▼
 Memory Retrieval:
  memory.get_memories(situation, n_matches=2)
  → 2 most relevant past situations
                          │
                          ▼
 LLM Prompt (mid_think):
 "You are a Bear Researcher. Build well-reasoned case
  AGAINST investing. Focus on risks, competitive
  weaknesses, negative indicators. Critically expose
  Bull's over-optimism. Use past reflections."

 Context: 4 reports + debate history + Bull's argument + 2 memories
                          │
                          ▼
 Output:
  • investment_debate_state.bear_history (appended)
  • investment_debate_state.current_response (latest)
  • investment_debate_state.count (incremented)
```

**Prompt Size Budget:** Same structure as Bull Researcher (see 4.5).
Round 1 ≈ 18 KB (~4,500 tokens), Round 2 ≈ 26 KB (~6,550 tokens).
Grows ~8 KB per round.

---

### 4.7 Research Manager

| | |
|---|---|
| **File** | `agents/managers/research_manager.py` |
| **Factory** | `create_research_manager(llm, memory)` |
| **Thinking Modality** | **Deep** (`deep_think_llm`, default `gpt-5.2`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input:                                         │
 │  • investment_debate_state (full Bull vs Bear debate) │
 │  • market_report, sentiment_report, news_report,     │
 │    fundamentals_report (4 analyst reports)            │
 │  • macro_regime_report (risk-on / risk-off)          │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Memory Retrieval:                                    │
 │  memory.get_memories(situation, n_matches=2)         │
 │  → 2 past similar investment decisions & outcomes    │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ LLM Prompt (deep_think):                            │
 │ "Evaluate Bull vs Bear debate. Make definitive       │
 │  decision: BUY / SELL / HOLD. Avoid defaulting to    │
 │  HOLD. Account for macro regime. Summarize key       │
 │  points. Provide rationale and strategic actions."    │
 │                                                      │
 │ Context:                                             │
 │  • Full debate transcript (all rounds)               │
 │  • 4 analyst reports                                 │
 │  • Macro regime classification                       │
 │  • 2 memory-retrieved past outcomes                  │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Output:                                              │
 │  • investment_debate_state.judge_decision            │
 │  • investment_plan (BUY/SELL/HOLD + detailed plan)   │
 └─────────────────────────────────────────────────────┘
```

**Prompt Size Budget (after 2 debate rounds):**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~1.2 KB | ~300 |
| 4 analyst reports | Text | Concatenated Markdown | ~13 KB | ~3,250 |
| Full debate transcript | Text | Bull + Bear history (2 rounds) | ~20 KB | ~5,000 |
| Macro regime report | Markdown | Regime + signals table | ~0.8 KB | ~200 |
| Memory (2 matches) | Text | Past decisions + outcomes | ~4 KB | ~1,000 |
| **Total prompt** | | | **~39 KB** | **~9,750** |

> This is the **largest single-prompt agent** in the trading pipeline.
> With 3 debate rounds, prompt can reach ~50 KB (~12,500 tokens).

---

### 4.8 Trader

| | |
|---|---|
| **File** | `agents/trader/trader.py` |
| **Factory** | `create_trader(llm, memory)` |
| **Thinking Modality** | **Mid** (`mid_think_llm`, falls back to `quick_think_llm`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 State Input:
  • company_of_interest
  • investment_plan (from Research Manager)
  • 4 analyst reports
                          │
                          ▼
 Memory Retrieval:
  memory.get_memories(situation, n_matches=2)
  → 2 past similar trading decisions
                          │
                          ▼
 LLM Prompt (mid_think):
 "Analyze investment plan. Make strategic decision:
  BUY / SELL / HOLD. Must end with
  'FINAL TRANSACTION PROPOSAL: BUY/HOLD/SELL'.
  Leverage past decisions."

 Context: investment_plan + 4 reports + 2 memories
                          │
                          ▼
 Output:
  • trader_investment_plan (decision + reasoning)
  • sender = "Trader"
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System message | Text | Instructions + memory | ~0.6 KB | ~150 |
| Investment plan | Text | Research Manager output | ~3 KB | ~750 |
| 4 analyst reports | Text | Concatenated Markdown | ~13 KB | ~3,250 |
| Memory (2 matches) | Text | Past decisions + outcomes | ~4 KB | ~1,000 |
| **Total prompt** | | | **~21 KB** | **~5,150** |

---

### 4.9 Aggressive Debator

| | |
|---|---|
| **File** | `agents/risk_mgmt/aggressive_debator.py` |
| **Factory** | `create_aggressive_debator(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 State Input:
  • risk_debate_state.history (debate transcript)
  • risk_debate_state.current_conservative_response
  • risk_debate_state.current_neutral_response
  • 4 analyst reports
  • trader_investment_plan
                          │
                          ▼
 LLM Prompt (quick_think):
 "Champion high-reward, high-risk opportunities.
  Counter conservative and neutral analysts' points.
  Highlight where caution misses critical opportunities.
  Debate and persuade."

 Context: trader plan + 4 reports + conservative/neutral arguments
                          │
                          ▼
 Output:
  • risk_debate_state.aggressive_history (appended)
  • risk_debate_state.current_aggressive_response
  • risk_debate_state.count (incremented)
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size (Rd 1) | Avg Size (Rd 2) | Avg Tokens (Rd 2) |
|-----------|-----------|--------|-----------------|-----------------|-------------------|
| Prompt template | Text | f-string with instructions | ~1.2 KB | ~1.2 KB | ~300 |
| 4 analyst reports | Text | Concatenated Markdown | ~13 KB | ~13 KB | ~3,250 |
| Trader investment plan | Text | Decision + reasoning | ~3 KB | ~3 KB | ~750 |
| Risk debate history | Text | Accumulated transcript | ~0 KB | ~10 KB | ~2,500 |
| Conservative/Neutral args | Text | Debate responses | ~0 KB | ~4 KB | ~1,000 |
| **Total prompt** | | | **~17 KB** | **~31 KB** | **~7,800** |

---

### 4.10 Conservative Debator

| | |
|---|---|
| **File** | `agents/risk_mgmt/conservative_debator.py` |
| **Factory** | `create_conservative_debator(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 State Input:
  • risk_debate_state.history
  • risk_debate_state.current_aggressive_response
  • risk_debate_state.current_neutral_response
  • 4 analyst reports + trader_investment_plan
                          │
                          ▼
 LLM Prompt (quick_think):
 "Protect assets, minimize volatility. Critically
  examine high-risk elements. Counter aggressive and
  neutral points. Emphasize downsides. Debate to
  demonstrate strength of low-risk strategy."
                          │
                          ▼
 Output:
  • risk_debate_state.conservative_history (appended)
  • risk_debate_state.current_conservative_response
  • risk_debate_state.count (incremented)
```

**Prompt Size Budget:** Same structure as Aggressive Debator (see 4.9).
Round 1 ≈ 17 KB (~4,250 tokens), Round 2 ≈ 31 KB (~7,800 tokens).

---

### 4.11 Neutral Debator

| | |
|---|---|
| **File** | `agents/risk_mgmt/neutral_debator.py` |
| **Factory** | `create_neutral_debator(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 State Input:
  • risk_debate_state.history
  • risk_debate_state.current_aggressive_response
  • risk_debate_state.current_conservative_response
  • 4 analyst reports + trader_investment_plan
                          │
                          ▼
 LLM Prompt (quick_think):
 "Provide balanced perspective. Challenge both
  aggressive (overly optimistic) and conservative
  (overly cautious). Support moderate, sustainable
  strategy. Debate to show balanced view."
                          │
                          ▼
 Output:
  • risk_debate_state.neutral_history (appended)
  • risk_debate_state.current_neutral_response
  • risk_debate_state.count (incremented)
```

**Prompt Size Budget:** Same structure as Aggressive Debator (see 4.9).
Round 1 ≈ 17 KB (~4,250 tokens), Round 2 ≈ 31 KB (~7,800 tokens).

---

### 4.12 Risk Manager

| | |
|---|---|
| **File** | `agents/managers/risk_manager.py` |
| **Factory** | `create_risk_manager(llm, memory)` |
| **Thinking Modality** | **Deep** (`deep_think_llm`, default `gpt-5.2`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input:                                         │
 │  • risk_debate_state (Aggressive + Conservative +    │
 │    Neutral debate history)                           │
 │  • 4 analyst reports                                 │
 │  • investment_plan (Research Manager's plan)         │
 │  • trader_investment_plan (Trader's refinement)      │
 │  • macro_regime_report                               │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 Memory Retrieval:
  memory.get_memories(situation, n_matches=2)
  → 2 past risk decisions & outcomes
                          │
                          ▼
 LLM Prompt (deep_think):
 "Evaluate risk debate between Aggressive, Conservative,
  Neutral analysts. Make clear decision: BUY / SELL / HOLD.
  Account for macro regime. Learn from past mistakes.
  Refine trader's plan. Provide detailed reasoning."

 Context: full risk debate + trader plan + 4 reports +
          macro regime + 2 memories
                          │
                          ▼
 Output:
  • risk_debate_state.judge_decision
  • final_trade_decision (the system's final answer)
```

**Prompt Size Budget (after 2 risk-debate rounds):**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~1.3 KB | ~325 |
| 4 analyst reports | Text | Concatenated Markdown | ~13 KB | ~3,250 |
| Trader investment plan | Text | Decision + reasoning | ~3 KB | ~750 |
| Full risk debate transcript | Text | Aggressive + Conservative + Neutral (2 rds) | ~30 KB | ~7,500 |
| Macro regime report | Markdown | Regime + signals table | ~0.8 KB | ~200 |
| Memory (2 matches) | Text | Past risk decisions + outcomes | ~4 KB | ~1,000 |
| **Total prompt** | | | **~52 KB** | **~13,025** |

> **Largest prompt in the entire framework.** With 3 risk-debate rounds,
> this can reach ~70 KB (~17,500 tokens).

---

### 4.13 Geopolitical Scanner

| | |
|---|---|
| **File** | `agents/scanners/geopolitical_scanner.py` |
| **Factory** | `create_geopolitical_scanner(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | `run_tool_loop()` (inline, up to 5 rounds) |

**Data Flow:**

```
 State Input: scan_date
                          │
                          ▼
 Tool calls via run_tool_loop():

 1. get_topic_news("geopolitics", limit=10)
    → Fetches geopolitical news articles
    Data source: yfinance / Alpha Vantage

 2. get_topic_news("trade policy sanctions", limit=10)
    → Trade & sanctions news

 3. get_topic_news("central bank monetary policy", limit=10)
    → Central bank signals

 4. get_topic_news("energy oil commodities", limit=10)
    → Energy & commodity supply risks

 (LLM decides which topics to search — up to 5 rounds)
                          │
                          ▼
 LLM Prompt (quick_think):
 "Scan global news for risks and opportunities affecting
  financial markets. Cover: major geopolitical events,
  central bank signals, trade/sanctions, energy/commodity
  risks. Include risk assessment table."

 Context: all retrieved news articles
                          │
                          ▼
 Output: geopolitical_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.6 KB | ~150 |
| `get_topic_news` × 3–4 calls | Markdown | Article lists (10 articles each) | ~8 KB | ~2,000 |
| **Total prompt** | | | **~9 KB** | **~2,150** |

---

### 4.14 Market Movers Scanner

| | |
|---|---|
| **File** | `agents/scanners/market_movers_scanner.py` |
| **Factory** | `create_market_movers_scanner(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | `run_tool_loop()` |

**Data Flow:**

```
 State Input: scan_date
                          │
                          ▼
 Tool calls via run_tool_loop():

 1. get_market_movers("day_gainers")
    → Top gaining stocks (symbol, price, change%, volume, market cap)
    Data source: yfinance / Alpha Vantage

 2. get_market_movers("day_losers")
    → Top losing stocks

 3. get_market_movers("most_actives")
    → Highest-volume stocks

 4. get_market_indices()
    → Major indices: SPY, DJI, NASDAQ, VIX, Russell 2000
      (price, daily change, 52W high/low)
    Data source: yfinance
                          │
                          ▼
 LLM Prompt (quick_think):
 "Scan for unusual activity and momentum signals.
  Cover: unusual movers & catalysts, volume anomalies,
  index trends & breadth, sector concentration.
  Include summary table."

 Context: gainers + losers + most active + index data
                          │
                          ▼
 Output: market_movers_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.6 KB | ~150 |
| `get_market_movers` × 3 calls | Markdown | Tables (15 stocks each) | ~4.5 KB | ~1,125 |
| `get_market_indices` result | Markdown | Table (5 indices) | ~1 KB | ~250 |
| **Total prompt** | | | **~6 KB** | **~1,525** |

---

### 4.15 Sector Scanner

| | |
|---|---|
| **File** | `agents/scanners/sector_scanner.py` |
| **Factory** | `create_sector_scanner(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | `run_tool_loop()` |

**Data Flow:**

```
 State Input: scan_date
                          │
                          ▼
 Tool calls via run_tool_loop():

 1. get_sector_performance()
    → All 11 GICS sectors with 1-day, 1-week, 1-month, YTD returns
    Data source: yfinance (sector ETF proxies) / Alpha Vantage
                          │
                          ▼
 LLM Prompt (quick_think):
 "Analyze sector rotation across all 11 GICS sectors.
  Cover: momentum rankings, rotation signals (money flows),
  defensive vs cyclical positioning, acceleration/deceleration.
  Include ranked performance table."

 Context: sector performance data
                          │
                          ▼
 Output: sector_performance_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.5 KB | ~125 |
| `get_sector_performance` result | Markdown | Table (11 sectors × 4 horizons) | ~0.9 KB | ~220 |
| **Total prompt** | | | **~1.4 KB** | **~345** |

> Smallest prompt of any scanner agent.

---

### 4.16 Smart Money Scanner

| | |
|---|---|
| **File** | `agents/scanners/smart_money_scanner.py` |
| **Factory** | `create_smart_money_scanner(llm)` |
| **Thinking Modality** | **Quick** (`quick_think_llm`, default `gpt-5-mini`) |
| **Tool Execution** | `run_tool_loop()` |
| **Graph position** | Sequential after `sector_scanner` (Phase 1b) |

**Data Flow:**

```
 State Input: scan_date
 + sector_performance_report  ← injected from sector_scanner (available
                                because this node runs after it)
                          │
                          ▼
 Tool calls via run_tool_loop():
 (All three tools have NO parameters — filters are hardcoded.
  The LLM calls each tool by name; nothing to hallucinate.)

 1. get_insider_buying_stocks()
    → Mid/Large cap stocks with positive insider purchases, volume > 1M
    → Filters: InsiderPurchases=Positive, MarketCap=+Mid, Volume=Over 1M
    Data source: Finviz screener (web scraper, graceful fallback on error)

 2. get_unusual_volume_stocks()
    → Stocks trading at 2x+ normal volume today, price > $10
    → Filters: RelativeVolume=Over 2, Price=Over $10
    Data source: Finviz screener

 3. get_breakout_accumulation_stocks()
    → Stocks at 52-week highs on 2x+ volume (O'Neil CAN SLIM pattern)
    → Filters: Performance2=52-Week High, RelativeVolume=Over 2, Price=Over $10
    Data source: Finviz screener
                          │
                          ▼
 LLM Prompt (quick_think):
 "Hunt for Smart Money institutional footprints. Call all three tools.
  Use sector rotation context to prioritize tickers from leading sectors.
  Flag signals that confirm or contradict sector trends.
  Report: 5-8 tickers with scan source, sector, and anomaly explanation."

 Context: sector_performance_report + 3 Finviz tool results
                          │
                          ▼
 Output: smart_money_report
```

**Hallucination Safety:** Each Finviz tool is a zero-parameter `@tool`. Filters
are hardcoded inside the helper `_run_finviz_screen()`. If Finviz is unavailable
(rate-limited, scraped HTML changed), each tool returns
`"Smart money scan unavailable (Finviz error): <reason>"` — the pipeline never fails.

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions | ~0.7 KB | ~175 |
| Sector performance report (injected) | Markdown | Table (11 sectors) | ~0.9 KB | ~220 |
| `get_insider_buying_stocks` result | Markdown | 5-row ticker list | ~0.3 KB | ~75 |
| `get_unusual_volume_stocks` result | Markdown | 5-row ticker list | ~0.3 KB | ~75 |
| `get_breakout_accumulation_stocks` result | Markdown | 5-row ticker list | ~0.3 KB | ~75 |
| **Total prompt** | | | **~2.5 KB** | **~620** |

---

### 4.17 Industry Deep Dive

| | |
|---|---|
| **File** | `agents/scanners/industry_deep_dive.py` |
| **Factory** | `create_industry_deep_dive(llm)` |
| **Thinking Modality** | **Mid** (`mid_think_llm`, falls back to `quick_think_llm`) |
| **Tool Execution** | `run_tool_loop()` |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input:                                         │
 │  • scan_date                                         │
 │  • geopolitical_report     (Phase 1a)               │
 │  • market_movers_report    (Phase 1a)               │
 │  • sector_performance_report (Phase 1a)             │
 │  • smart_money_report      (Phase 1b)               │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 ┌─────────────────────────────────────────────────────┐
 │ Pre-processing (Python, no LLM):                    │
 │ _extract_top_sectors(sector_performance_report)      │
 │ → Parses Markdown table from Sector Scanner         │
 │ → Ranks sectors by absolute 1-month move            │
 │ → Returns top 3 sector keys                         │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 Tool calls via run_tool_loop():

 1. get_industry_performance("technology")
    → Top companies in sector: rating, market weight,
      1D/1W/1M returns
    Data source: yfinance / Alpha Vantage

 2. get_industry_performance("energy")
    (repeated for each top sector)

 3. get_industry_performance("healthcare")
    (up to 3 sector calls)

 4. get_topic_news("semiconductor industry", limit=10)
    → Sector-specific news for context

 5. get_topic_news("renewable energy", limit=10)
    (at least 2 sector-specific news searches)
                          │
                          ▼
 LLM Prompt (mid_think):
 "Drill into the most interesting sectors from Phase 1.
  MUST call tools before writing. Explain why these
  industries selected. Identify top companies, catalysts,
  risks. Cross-reference geopolitical events and sectors."

 Context: Phase 1 reports + industry data + sector news
                          │
                          ▼
 Output: industry_deep_dive_report
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions + sector list | ~1 KB | ~250 |
| Phase 1 context (4 reports) | Text | Concatenated Markdown | ~8 KB | ~2,000 |
| `get_industry_performance` × 3 | Markdown | Tables (10–15 companies each) | ~7.5 KB | ~1,875 |
| `get_topic_news` × 2 | Markdown | Article lists (10 articles each) | ~5 KB | ~1,250 |
| **Total prompt** | | | **~21.5 KB** | **~5,375** |

---

### 4.18 Macro Synthesis

| | |
|---|---|
| **File** | `agents/scanners/macro_synthesis.py` |
| **Factory** | `create_macro_synthesis(llm)` |
| **Thinking Modality** | **Deep** (`deep_think_llm`, default `gpt-5.2`) |
| **Tool Execution** | None — pure LLM reasoning |

**Data Flow:**

```
 ┌─────────────────────────────────────────────────────┐
 │ State Input:                                         │
 │  • geopolitical_report      (Phase 1a)              │
 │  • market_movers_report     (Phase 1a)              │
 │  • sector_performance_report (Phase 1a)             │
 │  • smart_money_report       (Phase 1b)  ← NEW       │
 │  • industry_deep_dive_report (Phase 2)              │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 LLM Prompt (deep_think):
 "Synthesize all reports into final investment thesis.
  GOLDEN OVERLAP: Cross-reference Smart Money tickers with macro thesis.
  If a Smart Money ticker fits the top-down narrative (e.g., Energy stock
  with heavy insider buying during an oil shortage) → label conviction 'high'.
  If no Smart Money tickers fit → select best from other reports.
  Output ONLY valid JSON (no markdown, no preamble).
  Structure:
  {
    executive_summary, macro_context,
    key_themes (with conviction levels),
    stocks_to_investigate (8-10 picks with
      ticker, sector, rationale, thesis_angle,
      conviction, key_catalysts, risks),
    risk_factors
  }"

 Context: all 5 prior reports concatenated
                          │
                          ▼
 Post-processing (Python, no LLM):
 extract_json() → strips markdown fences / <think> blocks
                          │
                          ▼
 Output: macro_scan_summary (JSON string)
```

**Prompt Size Budget:**

| Component | Data Type | Format | Avg Size | Avg Tokens |
|-----------|-----------|--------|----------|------------|
| System prompt | Text | Instructions + JSON schema + Golden Overlap | ~1.5 KB | ~375 |
| Geopolitical report (Phase 1a) | Text | Markdown report | ~3 KB | ~750 |
| Market movers report (Phase 1a) | Text | Markdown report | ~3 KB | ~750 |
| Sector performance report (Phase 1a) | Text | Markdown report | ~2 KB | ~500 |
| Smart money report (Phase 1b) | Text | Markdown report | ~2 KB | ~500 |
| Industry deep dive report (Phase 2) | Text | Markdown report | ~8 KB | ~2,000 |
| **Total prompt** | | | **~19.5 KB** | **~4,875** |

**Output:** Valid JSON (~3–5 KB, ~750–1,250 tokens).

---

## 5. Tool → Data-Source Mapping

Every tool routes through `dataflows/interface.py:route_to_vendor()` which
dispatches to the configured vendor.

### Trading Tools

| Tool | Category | Default Vendor | Fallback | Returns |
|------|----------|---------------|----------|---------|
| `get_stock_data` | core_stock_apis | yfinance | Alpha Vantage | OHLCV string |
| `get_indicators` | technical_indicators | yfinance | Alpha Vantage | Indicator values |
| `get_macro_regime` | *(composed)* | yfinance | — | Regime report |
| `get_fundamentals` | fundamental_data | yfinance | Alpha Vantage | Fundamentals |
| `get_balance_sheet` | fundamental_data | yfinance | Alpha Vantage | Balance sheet |
| `get_cashflow` | fundamental_data | yfinance | Alpha Vantage | Cash flow |
| `get_income_statement` | fundamental_data | yfinance | Alpha Vantage | Income stmt |
| `get_ttm_analysis` | *(composed)* | yfinance | — | TTM metrics |
| `get_peer_comparison` | *(composed)* | yfinance | — | Peer ranking |
| `get_sector_relative` | *(composed)* | yfinance | — | Alpha report |
| `get_news` | news_data | yfinance | Alpha Vantage | News articles |
| `get_global_news` | news_data | yfinance | Alpha Vantage | Global news |
| `get_insider_transactions` | *(tool override)* | **Finnhub** | Alpha Vantage | Insider txns |

### Scanner Tools

| Tool | Category | Default Vendor | Fallback | Returns |
|------|----------|---------------|----------|---------|
| `get_market_movers` | scanner_data | yfinance | Alpha Vantage | Movers table |
| `get_market_indices` | scanner_data | yfinance | — | Index table |
| `get_sector_performance` | scanner_data | yfinance | Alpha Vantage | Sector table |
| `get_industry_performance` | scanner_data | yfinance | — | Industry table |
| `get_topic_news` | scanner_data | yfinance | — | Topic news |
| `get_earnings_calendar` | calendar_data | **Finnhub** | — | Earnings cal. |
| `get_economic_calendar` | calendar_data | **Finnhub** | — | Econ cal. |
| `get_insider_buying_stocks` | *(Finviz direct)* | **Finviz** | graceful string | Insider buys |
| `get_unusual_volume_stocks` | *(Finviz direct)* | **Finviz** | graceful string | Vol anomalies |
| `get_breakout_accumulation_stocks` | *(Finviz direct)* | **Finviz** | graceful string | Breakouts |

> **Fallback rules** (ADR 011): Only 5 methods in `FALLBACK_ALLOWED` get
> cross-vendor fallback. All others fail-fast on error.
>
> **Finviz tools** bypass `route_to_vendor()` — they call `finvizfinance` directly
> via the shared `_run_finviz_screen()` helper. Errors return a graceful string
> starting with `"Smart money scan unavailable"` so the pipeline never hard-fails.
> `finvizfinance` is a web scraper, not an official API — treat it as best-effort.

---

## 6. Memory System

The framework uses **BM25-based lexical similarity** (offline, no API calls)
to retrieve relevant past trading situations.

### Memory Instances

| Instance | Used By | Purpose |
|----------|---------|---------|
| `bull_memory` | Bull Researcher | Past bullish analyses & outcomes |
| `bear_memory` | Bear Researcher | Past bearish analyses & outcomes |
| `trader_memory` | Trader | Past trading decisions & results |
| `invest_judge_memory` | Research Manager | Past investment judgments |
| `risk_manager_memory` | Risk Manager | Past risk decisions |

### How Memory Works

```
 Agent builds "current situation" string from:
  • company ticker + trade date
  • analyst report summaries
  • debate context
                          │
                          ▼
 memory.get_memories(current_situation, n_matches=2)
  → BM25 tokenises situation and scores against stored documents
  → Returns top 2 matches:
    { matched_situation, recommendation, similarity_score }
                          │
                          ▼
 Injected into LLM prompt as "Past Reflections"
  → Agent uses past lessons to avoid repeating mistakes
```

### Memory Data Flow

```
 After trading completes → outcomes stored back:
  add_situations([(situation_text, recommendation_text)])
  → Appends to document store
  → Rebuilds BM25 index for future retrieval
```

---

## 7. Tool Data Formats & Sizes

All tools return **strings** to the LLM. The table below shows the format,
typical size, and any truncation limits for each tool.

> **Token estimate rule of thumb:** 1 token ≈ 4 characters for English text.

### Trading Tools

| Tool | Return Format | Typical Size | Tokens | Items | Truncation / Limits |
|------|---------------|-------------|--------|-------|---------------------|
| `get_stock_data` | CSV (header + OHLCV rows) | 5–20 KB | 1,250–5,000 | 30–250 rows | None; all requested days returned |
| `get_indicators` | Markdown (daily values + description) | ~0.9 KB per indicator | ~225 | 30 daily values | 30-day lookback (configurable) |
| `get_macro_regime` | Markdown (regime table + 6 signal rows) | ~0.8 KB | ~200 | 1 regime + 6 signals | Fixed signal set |
| `get_fundamentals` | Markdown (key ratios table) | ~1.5 KB | ~375 | ~15 metrics | None |
| `get_ttm_analysis` | Markdown (TTM summary + 8-quarter table) | ~1.6 KB | ~400 | 15 metrics + 8 quarters | Last 8 quarters |
| `get_balance_sheet` | CSV (quarterly columns) | ~2.5 KB | ~625 | Up to 8 quarters | Last 8 quarters |
| `get_income_statement` | CSV (quarterly columns) | ~2.5 KB | ~625 | Up to 8 quarters | Last 8 quarters |
| `get_cashflow` | CSV (quarterly columns) | ~2.5 KB | ~625 | Up to 8 quarters | Last 8 quarters |
| `get_peer_comparison` | Markdown (ranked table) | ~1.2 KB | ~300 | ~10 peers | Top 10 sector peers |
| `get_sector_relative` | Markdown (alpha table) | ~0.8 KB | ~200 | 5–6 time periods | Fixed periods |
| `get_news` | Markdown (article list) | ~7 KB | ~1,750 | ≤ 20 articles | First 20 from API, filtered by date |
| `get_global_news` | Markdown (article list) | ~1.75 KB | ~437 | 5 articles (default) | Configurable limit; deduplicated |
| `get_insider_transactions` | Markdown (transaction table) | ~1.5 KB | ~375 | 10–50 transactions | API-dependent |

### Scanner Tools

| Tool | Return Format | Typical Size | Tokens | Items | Truncation / Limits |
|------|---------------|-------------|--------|-------|---------------------|
| `get_market_movers` | Markdown (table) | ~1.5 KB per category | ~375 | 15 stocks | Hard limit: top 15 |
| `get_market_indices` | Markdown (table) | ~1 KB | ~250 | 5 indices | Fixed set (SPY, DJI, NASDAQ, VIX, RUT) |
| `get_sector_performance` | Markdown (table) | ~0.9 KB | ~220 | 11 sectors × 4 horizons | Fixed 11 GICS sectors |
| `get_industry_performance` | Markdown (table) | ~2.5 KB | ~625 | 10–15 companies | Top companies by market weight |
| `get_topic_news` | Markdown (article list) | ~2.5 KB | ~625 | 10 articles (default) | Configurable limit |
| `get_earnings_calendar` | Markdown (table) | ~3 KB | ~750 | 20–50+ events | All events in date range |
| `get_economic_calendar` | Markdown (table) | ~2.5 KB | ~625 | 5–15 events | All events in date range |
| `get_insider_buying_stocks` | Markdown (list) | ~0.3 KB | ~75 | Top 5 stocks | Hard limit: top 5 by volume; returns error string on Finviz failure |
| `get_unusual_volume_stocks` | Markdown (list) | ~0.3 KB | ~75 | Top 5 stocks | Hard limit: top 5 by volume; returns error string on Finviz failure |
| `get_breakout_accumulation_stocks` | Markdown (list) | ~0.3 KB | ~75 | Top 5 stocks | Hard limit: top 5 by volume; returns error string on Finviz failure |

### Non-Tool Data Injected into Prompts

| Data | Format | Avg Size | Tokens | Notes |
|------|--------|----------|--------|-------|
| Memory match (× 2) | Text (situation + recommendation) | ~2 KB each | ~500 each | BM25 retrieval; injected as "Past Reflections" |
| Debate history (per round) | Text (accumulated transcript) | ~3–4 KB per turn | ~750–1,000 | Grows linearly with debate rounds |
| Analyst report (each) | Text (Markdown) | ~3 KB | ~750 | Output from analyst agents |
| Macro regime report | Markdown (tables) | ~0.8 KB | ~200 | Shared across multiple agents |

---

## 8. Context Window Budget

This section compares each agent's **estimated prompt size** against
the context windows of popular models to identify potential overflow risks.

### Model Context Windows (Reference)

| Model | Context Window | Input Limit (approx) | Notes |
|-------|---------------|---------------------|-------|
| gpt-4o-mini | 128K tokens | ~100K usable | Default quick-think candidate |
| gpt-4o | 128K tokens | ~100K usable | Alternative quick/mid |
| gpt-5-mini | 128K tokens | ~100K usable | Default `quick_think_llm` |
| gpt-5.2 | 128K tokens | ~100K usable | Default `deep_think_llm` |
| claude-3.5-sonnet | 200K tokens | ~180K usable | Anthropic option |
| claude-4-sonnet | 200K tokens | ~180K usable | Anthropic option |
| gemini-2.5-pro | 1M tokens | ~900K usable | Google option |
| deepseek-r1 | 128K tokens | ~100K usable | OpenRouter / Ollama option |
| llama-3.1-70b | 128K tokens | ~100K usable | Ollama local option |
| mistral-large | 128K tokens | ~100K usable | OpenRouter option |

### Per-Agent Prompt Size vs Context Budget

| # | Agent | Tier | Avg Prompt | Peak Prompt† | % of 128K | Risk |
|---|-------|------|-----------|-------------|-----------|------|
| 1 | Market Analyst | Quick | ~5,000 tok | ~6,000 tok | 4–5% | ✅ Safe |
| 2 | Fundamentals Analyst | Quick | ~1,600 tok | ~3,500 tok | 1–3% | ✅ Safe |
| 3 | News Analyst | Quick | ~2,750 tok | ~3,200 tok | 2–3% | ✅ Safe |
| 4 | Social Media Analyst | Quick | ~2,000 tok | ~2,500 tok | 1–2% | ✅ Safe |
| 5 | Bull Researcher (Rd 2) | Mid | ~6,550 tok | ~10,000 tok | 5–8% | ✅ Safe |
| 6 | Bear Researcher (Rd 2) | Mid | ~6,550 tok | ~10,000 tok | 5–8% | ✅ Safe |
| 7 | **Research Manager** | **Deep** | **~9,750 tok** | **~15,000 tok** | **8–12%** | ✅ Safe |
| 8 | Trader | Mid | ~5,150 tok | ~6,500 tok | 4–5% | ✅ Safe |
| 9 | Aggressive Debator (Rd 2) | Quick | ~7,800 tok | ~14,000 tok | 6–11% | ✅ Safe |
| 10 | Conservative Debator (Rd 2) | Quick | ~7,800 tok | ~14,000 tok | 6–11% | ✅ Safe |
| 11 | Neutral Debator (Rd 2) | Quick | ~7,800 tok | ~14,000 tok | 6–11% | ✅ Safe |
| 12 | **Risk Manager** | **Deep** | **~13,000 tok** | **~17,500 tok** | **10–14%** | ✅ Safe |
| 13 | Geopolitical Scanner | Quick | ~2,150 tok | ~3,000 tok | 2% | ✅ Safe |
| 14 | Market Movers Scanner | Quick | ~1,525 tok | ~2,000 tok | 1–2% | ✅ Safe |
| 15 | Sector Scanner | Quick | ~345 tok | ~500 tok | <1% | ✅ Safe |
| 16 | Smart Money Scanner | Quick | ~620 tok | ~900 tok | <1% | ✅ Safe |
| 17 | Industry Deep Dive | Mid | ~5,375 tok | ~7,500 tok | 4–6% | ✅ Safe |
| 18 | Macro Synthesis | Deep | ~4,875 tok | ~7,000 tok | 4–5% | ✅ Safe |

> **†Peak Prompt** = estimate with `max_debate_rounds=3` or maximum optional
> tool calls. All agents are well within the 128K context window.

### When to Watch Context Limits

Even though individual agents fit comfortably, be aware of these scenarios:

| Scenario | Estimated Total | Risk |
|----------|----------------|------|
| Default config (2 debate rounds) | Max single prompt ≈ 17.5K tokens | ✅ No risk |
| `max_debate_rounds=5` | Risk Manager prompt ≈ 30K tokens | ✅ Low risk |
| `max_debate_rounds=10` | Risk Manager prompt ≈ 55K tokens | ⚠️ Monitor |
| Small context model (8K window) | Risk Manager default already 13K | ❌ **Will overflow** |
| Ollama local (small model, 4K ctx) | Most debate agents exceed 4K | ❌ **Will overflow** |

> **Recommendation:** For local Ollama models with small context windows
> (e.g., 4K–8K), set `max_debate_rounds=1` and `max_risk_discuss_rounds=1`.

---

## 9. End-to-End Token Estimates

### Trading Pipeline (Single Company Analysis)

```
Phase                          Calls   Avg Tokens (per call)   Subtotal
─────────────────────────────────────────────────────────────────────────
1. ANALYST PHASE (parallel)
   Market Analyst              1       ~5,000                  ~5,000
   Fundamentals Analyst        1       ~1,600–3,500            ~2,500
   News Analyst                1       ~2,750                  ~2,750
   Social Media Analyst        1       ~2,000                  ~2,000
                                                     Phase 1: ~12,250

2. INVESTMENT DEBATE (2 rounds)
   Bull Researcher             2       ~4,500 → ~6,550         ~11,050
   Bear Researcher             2       ~4,500 → ~6,550         ~11,050
                                                     Phase 2: ~22,100

3. RESEARCH MANAGER
   Research Manager            1       ~9,750                  ~9,750
                                                     Phase 3: ~9,750

4. TRADER
   Trader                      1       ~5,150                  ~5,150
                                                     Phase 4: ~5,150

5. RISK DEBATE (2 rounds × 3 agents)
   Aggressive Debator          2       ~4,250 → ~7,800         ~12,050
   Conservative Debator        2       ~4,250 → ~7,800         ~12,050
   Neutral Debator             2       ~4,250 → ~7,800         ~12,050
                                                     Phase 5: ~36,150

6. RISK MANAGER
   Risk Manager                1       ~13,000                 ~13,000
                                                     Phase 6: ~13,000

═══════════════════════════════════════════════════════════════════════════
TOTAL INPUT TOKENS (single company):                          ~98,400
═══════════════════════════════════════════════════════════════════════════
```

> Each agent also produces **output tokens** (~500–3,000 per call).
> Total output across all agents ≈ 15,000–25,000 tokens.
> **Grand total (input + output) ≈ 115,000–125,000 tokens per company.**

### Scanner Pipeline (Market-Wide Scan)

```
Phase                          Calls   Avg Tokens (per call)   Subtotal
─────────────────────────────────────────────────────────────────────────
1a. PHASE 1 SCANNERS (parallel from START)
   Geopolitical Scanner        1       ~2,150                  ~2,150
   Market Movers Scanner       1       ~1,525                  ~1,525
   Sector Scanner              1       ~345                    ~345
                                                    Phase 1a: ~4,020

1b. SMART MONEY (sequential after Sector Scanner)
   Smart Money Scanner         1       ~620                    ~620
                                                    Phase 1b: ~620

2. PHASE 2
   Industry Deep Dive          1       ~5,375                  ~5,375
                                                     Phase 2: ~5,375

3. PHASE 3
   Macro Synthesis             1       ~4,875                  ~4,875
                                                     Phase 3: ~4,875

═══════════════════════════════════════════════════════════════════════════
TOTAL INPUT TOKENS (market scan):                             ~14,890
═══════════════════════════════════════════════════════════════════════════
```

> Scanner output tokens ≈ 6,000–9,000 additional.
> **Grand total (input + output) ≈ 21,000–24,000 tokens per scan.**

### Full Pipeline (Scan → Per-Ticker Deep Dives)

When running the `pipeline` command (scan + per-ticker analysis for top picks):

```
Scanner pipeline:                          ~14,890 input tokens
+ N company analyses (N = 8–10 picks):     ~98,400 × N input tokens
───────────────────────────────────────────────────────────────────
Example (10 companies):                    ~998,890 input tokens
                                           ≈ 1.0M total tokens (input + output)
```

### Key Observations

1. **No automatic truncation**: The framework concatenates all tool output
   and debate history into prompts without truncation. Context usage grows
   linearly with debate rounds.

2. **Debate history is the main driver**: In a 2-round debate, history adds
   ~8 KB per round per debater. The Risk Manager sees all three debaters'
   accumulated history.

3. **All prompts fit 128K models**: Even the largest prompt (Risk Manager
   at peak) uses only ~14% of a 128K context window.

4. **Small-context models are at risk**: Models with ≤ 8K context windows
   cannot accommodate debate agents beyond round 1. Use
   `max_debate_rounds=1` for such models.

5. **Cost optimization**: The scanner pipeline uses ~15K tokens total —
   roughly 6-7× cheaper than a single company analysis.
