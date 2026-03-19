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
   - [4.16 Industry Deep Dive](#416-industry-deep-dive)
   - [4.17 Macro Synthesis](#417-macro-synthesis)
5. [Tool → Data-Source Mapping](#5-tool--data-source-mapping)
6. [Memory System](#6-memory-system)

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
| 16 | Industry Deep Dive | **Mid** | ✅ | — | `run_tool_loop()` |
| 17 | Macro Synthesis | **Deep** | — | — | — |

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
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Geopolitical    │     │  Market Movers   │     │  Sector Scanner  │
│  Scanner         │     │  Scanner         │     │                  │
│  (quick_think)   │     │  (quick_think)   │     │  (quick_think)   │
│                  │     │                  │     │                  │
│ Tools:           │     │ Tools:           │     │ Tools:           │
│ • get_topic_news │     │ • get_market_    │     │ • get_sector_    │
│                  │     │   movers         │     │   performance    │
│ Output:          │     │ • get_market_    │     │                  │
│ geopolitical_rpt │     │   indices        │     │ Output:          │
│                  │     │                  │     │ sector_perf_rpt  │
│                  │     │ Output:          │     │                  │
│                  │     │ market_movers_rpt│     │                  │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                        │                         │
         └────────────────────────┼─────────────────────────┘
                                  │  (Phase 1 → Phase 2)
                                  ▼
                    ┌─────────────────────────────┐
                    │    Industry Deep Dive        │
                    │    (mid_think)               │
                    │                              │
                    │ Reads: all 3 Phase-1 reports │
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
                    │ Reads: all 4 prior reports   │
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
  neutral points. Emphasise downsides. Debate to
  demonstrate strength of low-risk strategy."
                          │
                          ▼
 Output:
  • risk_debate_state.conservative_history (appended)
  • risk_debate_state.current_conservative_response
  • risk_debate_state.count (incremented)
```

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

---

### 4.16 Industry Deep Dive

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
 │  • geopolitical_report     (Phase 1)                │
 │  • market_movers_report    (Phase 1)                │
 │  • sector_performance_report (Phase 1)              │
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

---

### 4.17 Macro Synthesis

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
 │  • geopolitical_report      (Phase 1)               │
 │  • market_movers_report     (Phase 1)               │
 │  • sector_performance_report (Phase 1)              │
 │  • industry_deep_dive_report (Phase 2)              │
 └────────────────────────┬────────────────────────────┘
                          │
                          ▼
 LLM Prompt (deep_think):
 "Synthesize all reports into final investment thesis.
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

 Context: all 4 prior reports concatenated
                          │
                          ▼
 Post-processing (Python, no LLM):
 extract_json() → strips markdown fences / <think> blocks
                          │
                          ▼
 Output: macro_scan_summary (JSON string)
```

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

> **Fallback rules** (ADR 011): Only 5 methods in `FALLBACK_ALLOWED` get
> cross-vendor fallback. All others fail-fast on error.

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
