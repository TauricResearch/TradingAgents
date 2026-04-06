# TradingAgents Architecture Overview

> **Purpose:** Reference document mapping the current TradingAgents architecture.
> **Status:** Informational (no changes proposed here)
> **Related:** [RFC_AUTORESEARCH_INTRADAY.md](./RFC_AUTORESEARCH_INTRADAY.md)
>
> This document is submitted as context for the auto-research RFC. It captures
> the current architecture to ground the proposal in existing code.

## Overview

TradingAgents is a **multi-agent LLM system** that analyzes stocks using 12 AI agents organized in 4 layers:
1. **Analysis Layer** - 4 analysts gather data using tools
2. **Investment Debate Layer** - Bull vs Bear researchers debate, judge decides
3. **Trading Layer** - Trader creates execution plan
4. **Risk Management Layer** - 3 risk analysts debate, portfolio manager makes final call

---

## Complete System Flow (High Level)

```mermaid
flowchart TD
    USER["User calls ta.propagate('NVDA', '2024-05-10')"]

    subgraph INIT["Initialization"]
        MAIN["main.py"] --> CONFIG["default_config.py"]
        CONFIG --> GRAPH["TradingAgentsGraph.__init__()"]
        GRAPH --> LLM_FACTORY["create_llm_client() - factory.py"]
        LLM_FACTORY --> DEEP["deep_thinking_llm"]
        LLM_FACTORY --> QUICK["quick_thinking_llm"]
        GRAPH --> MEM_INIT["Initialize Memories<br/>bull_memory, bear_memory, trader_memory"]
    end

    USER --> PROPAGATOR["Propagator<br/>Creates initial state"]

    subgraph ANALYSTS["Layer 1: Analysis (Sequential)"]
        MA["Market Analyst<br/>tools: get_stock_data, get_indicators"]
        SA["Social Media Analyst<br/>tools: get_news"]
        NA["News Analyst<br/>tools: get_news, get_global_news"]
        FA["Fundamentals Analyst<br/>tools: get_fundamentals,<br/>get_balance_sheet,<br/>get_cashflow,<br/>get_income_statement"]
        MA --> SA --> NA --> FA
    end

    subgraph DEBATE["Layer 2: Investment Debate"]
        BULL["Bull Researcher<br/>(BUY advocate + memory)"]
        BEAR["Bear Researcher<br/>(SELL advocate + memory)"]
        BULL <-->|"max_debate_rounds"| BEAR
        JUDGE["Research Manager<br/>(Judge: BUY/SELL/HOLD)"]
        BULL --> JUDGE
        BEAR --> JUDGE
    end

    subgraph TRADE["Layer 3: Trading"]
        TRADER["Trader<br/>(Execution strategy + memory)"]
    end

    subgraph RISK["Layer 4: Risk Management Debate"]
        AGG["Aggressive Analyst<br/>(High risk, high reward)"]
        CON["Conservative Analyst<br/>(Low risk, protect assets)"]
        NEU["Neutral Analyst<br/>(Balanced approach)"]
        AGG <-->|"max_risk_discuss_rounds"| CON
        CON <-->|"max_risk_discuss_rounds"| NEU
        PM["Portfolio Manager<br/>(Final Judge)"]
        AGG --> PM
        CON --> PM
        NEU --> PM
    end

    subgraph OUTPUT["Final Output"]
        SP["SignalProcessor<br/>Extracts: BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL"]
    end

    PROPAGATOR --> ANALYSTS
    FA --> DEBATE
    JUDGE --> TRADE
    TRADER --> RISK
    PM --> SP

    SP --> DECISION["Final Decision Returned to User"]

    style ANALYSTS fill:#e1f5fe,e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style DEBATE fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style TRADE fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style RISK fill:#fce4ec,stroke:#c2185b,stroke-width:2px,color:#880e4f
    style OUTPUT fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c
```

---

## Data Flow: From APIs to Agent Reports

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '20px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 140 }
}}%%
flowchart LR
    subgraph EXTERNAL["External Data Sources"]
        YF["yfinance API<br/>(Free, no key)"]
        AV["Alpha Vantage API<br/>(Needs API key)"]
    end

    subgraph DATAFLOWS["tradingagents/dataflows/"]
        YF_PY["y_finance.py<br/>get_YFin_data_online()"]
        YF_NEWS["yfinance_news.py<br/>get_news_yfinance()<br/>get_global_news_yfinance()"]
        AV_STOCK["alpha_vantage_stock.py"]
        AV_FUND["alpha_vantage_fundamentals.py"]
        AV_IND["alpha_vantage_indicator.py"]
        AV_NEWS["alpha_vantage_news.py"]

        ROUTER["interface.py<br/>route_to_vendor()<br/><br/>Decides: yfinance or alpha_vantage?<br/>Auto-fallback on rate limit"]
    end

    subgraph TOOLS["tradingagents/agents/utils/ (Tool Layer)"]
        T1["core_stock_tools.py<br/>get_stock_data()"]
        T2["technical_indicators_tools.py<br/>get_indicators()"]
        T3["fundamental_data_tools.py<br/>get_fundamentals()<br/>get_balance_sheet()<br/>get_cashflow()<br/>get_income_statement()"]
        T4["news_data_tools.py<br/>get_news()<br/>get_global_news()<br/>get_insider_transactions()"]
    end

    subgraph AGENTS["Analyst Agents"]
        MA2["Market Analyst"]
        SA2["Social Media Analyst"]
        NA2["News Analyst"]
        FA2["Fundamentals Analyst"]
    end

    YF --> YF_PY
    YF --> YF_NEWS
    AV --> AV_STOCK
    AV --> AV_FUND
    AV --> AV_IND
    AV --> AV_NEWS

    YF_PY --> ROUTER
    YF_NEWS --> ROUTER
    AV_STOCK --> ROUTER
    AV_FUND --> ROUTER
    AV_IND --> ROUTER
    AV_NEWS --> ROUTER

    ROUTER --> T1
    ROUTER --> T2
    ROUTER --> T3
    ROUTER --> T4

    T1 --> MA2
    T2 --> MA2
    T4 --> SA2
    T4 --> NA2
    T3 --> FA2

    style EXTERNAL fill:#ffecb3,stroke:#f9a825,stroke-width:2px,color:#f57f17
    style DATAFLOWS fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style TOOLS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style AGENTS fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c
```

---

## interface.py - The Router (Detailed)

```mermaid
flowchart TD
    CALL["Agent calls a tool<br/>e.g., get_stock_data('NVDA', ...)"]

    ROUTE["route_to_vendor('get_stock_data', *args)"]

    CAT["get_category_for_method()<br/>→ 'core_stock_apis'"]

    VENDOR["get_vendor(category, method)<br/>1. Check tool_vendors config (highest priority)<br/>2. Fall back to data_vendors config<br/>3. Fall back to 'default'"]

    PRIMARY["Try PRIMARY vendor<br/>(e.g., yfinance)"]

    SUCCESS{"Success?"}

    RATE_LIMIT{"Rate Limited?"}

    FALLBACK["Try FALLBACK vendor<br/>(e.g., alpha_vantage)"]

    RETURN["Return data to agent"]

    CALL --> ROUTE --> CAT --> VENDOR --> PRIMARY --> SUCCESS
    SUCCESS -->|"Yes"| RETURN
    SUCCESS -->|"No"| RATE_LIMIT
    RATE_LIMIT -->|"Yes"| FALLBACK
    RATE_LIMIT -->|"No (other error)"| ERROR["Raise Error"]
    FALLBACK --> RETURN

    style ROUTE fill:#bbdefb,stroke:#0277bd,stroke-width:2px,color:#01579b
    style VENDOR fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

---

## Tool Categories & Vendor Mapping

```mermaid
%%{init: {'flowchart': {'nodeSpacing': 80, 'rankSpacing': 120}}}%%
flowchart TD
    subgraph CATEGORIES["Tool Categories (from config)"]
        C1["core_stock_apis"]
        C2["technical_indicators"]
        C3["fundamental_data"]
        C4["news_data"]
    end

    subgraph TOOLS_IN_CATS["Tools per Category"]
        C1 --> T_STOCK["get_stock_data"]
        C2 --> T_IND["get_indicators"]
        C3 --> T_FUND["get_fundamentals"]
        C3 --> T_BAL["get_balance_sheet"]
        C3 --> T_CASH["get_cashflow"]
        C3 --> T_INC["get_income_statement"]
        C4 --> T_NEWS["get_news"]
        C4 --> T_GNEWS["get_global_news"]
        C4 --> T_INSIDER["get_insider_transactions"]
    end

    subgraph VENDORS["Available Vendor Implementations"]
        V_YF["yfinance<br/>(Free, default)"]
        V_AV["Alpha Vantage<br/>(API key needed)"]
    end

    T_STOCK --> V_YF
    T_STOCK --> V_AV
    T_IND --> V_YF
    T_IND --> V_AV
    T_FUND --> V_YF
    T_FUND --> V_AV
    T_BAL --> V_YF
    T_BAL --> V_AV
    T_CASH --> V_YF
    T_CASH --> V_AV
    T_INC --> V_YF
    T_INC --> V_AV
    T_NEWS --> V_YF
    T_NEWS --> V_AV
    T_GNEWS --> V_YF
    T_GNEWS --> V_AV
    T_INSIDER --> V_YF

    style CATEGORIES fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style VENDORS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

---

## Agent Detail: Who Has What Tools

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '20px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 50 }
}}%%
flowchart LR
    subgraph WITH_TOOLS["Agents WITH Tools (4)"]
        MA3["Market Analyst"]
        SA3["Social Media Analyst"]
        NA3["News Analyst"]
        FA3["Fundamentals Analyst"]
    end

    subgraph NO_TOOLS["Agents WITHOUT Tools (8) - Pure LLM Reasoning"]
        BULL3["Bull Researcher"]
        BEAR3["Bear Researcher"]
        RM3["Research Manager"]
        TR3["Trader"]
        AG3["Aggressive Analyst"]
        CO3["Conservative Analyst"]
        NE3["Neutral Analyst"]
        PM3["Portfolio Manager"]
    end

    MA3 -->|uses| T_S["get_stock_data<br/>get_indicators"]
    SA3 -->|uses| T_N1["get_news"]
    NA3 -->|uses| T_N2["get_news<br/>get_global_news"]
    FA3 -->|uses| T_F["get_fundamentals<br/>get_balance_sheet<br/>get_cashflow<br/>get_income_statement"]

    BULL3 -->|reads| REPORTS["All 4 Analyst Reports<br/>+ Past Memories"]
    BEAR3 -->|reads| REPORTS
    RM3 -->|reads| DEBATE_HIST["Debate History"]
    TR3 -->|reads| INV_PLAN["Investment Plan"]
    AG3 -->|reads| TRADE_PLAN["Trader's Plan"]
    CO3 -->|reads| TRADE_PLAN
    NE3 -->|reads| TRADE_PLAN
    PM3 -->|reads| RISK_HIST["Risk Debate History"]

    style WITH_TOOLS fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
    style NO_TOOLS fill:#ffecb3,stroke:#f9a825,stroke-width:2px,color:#f57f17
```

---

## LangGraph Execution Flow (Detailed)

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '20px' },
  'flowchart': { 'nodeSpacing': 80, 'rankSpacing': 80 }
}}%%
stateDiagram-v2
    [*] --> Propagator: propagate(ticker, date)

    Propagator --> MarketAnalyst: Initial state created

    state "Analyst Phase" as AP {
        MarketAnalyst --> tools_market: Calls tools
        tools_market --> MarketAnalyst: Returns data
        MarketAnalyst --> MsgClearMarket: Report done
        MsgClearMarket --> SocialAnalyst
        SocialAnalyst --> tools_social: Calls tools
        tools_social --> SocialAnalyst: Returns data
        SocialAnalyst --> MsgClearSocial: Report done
        MsgClearSocial --> NewsAnalyst
        NewsAnalyst --> tools_news: Calls tools
        tools_news --> NewsAnalyst: Returns data
        NewsAnalyst --> MsgClearNews: Report done
        MsgClearNews --> FundAnalyst
        FundAnalyst --> tools_fund: Calls tools
        tools_fund --> FundAnalyst: Returns data
        FundAnalyst --> MsgClearFund: Report done
    }

    state "Investment Debate" as ID {
        BullResearcher --> BearResearcher: Bull case
        BearResearcher --> BullResearcher: Bear counter
        note right of BullResearcher: Loops max_debate_rounds times
        BearResearcher --> ResearchManager: Debate ends
        ResearchManager --> InvestmentPlan: BUY/SELL/HOLD
    }

    state "Trading" as TR {
        Trader --> TraderPlan: Execution strategy
    }

    state "Risk Debate" as RD {
        Aggressive --> Conservative: High-risk view
        Conservative --> Neutral: Low-risk view
        Neutral --> Aggressive: Balanced view
        note right of Aggressive: Loops max_risk_discuss_rounds times
        Neutral --> PortfolioManager: Debate ends
    }

    MsgClearFund --> BullResearcher
    InvestmentPlan --> Trader
    TraderPlan --> Aggressive
    PortfolioManager --> SignalProcessor
    SignalProcessor --> [*]: BUY/OVERWEIGHT/HOLD/UNDERWEIGHT/SELL
```

---

## Memory System (BM25 Similarity Search)

```mermaid
%%{init: {
  'themeVariables': { 'fontSize': '20px' },
  'flowchart': { 'nodeSpacing': 100, 'rankSpacing': 120 }
}}%%
flowchart TD
    subgraph MEMORIES["5 Memory Instances"]
        M1["bull_memory<br/>FinancialSituationMemory"]
        M2["bear_memory<br/>FinancialSituationMemory"]
        M3["trader_memory<br/>FinancialSituationMemory"]
        M4["invest_judge_memory"]
        M5["portfolio_manager_memory"]
    end

    subgraph WRITE_PATH["Writing to Memory (after trade results)"]
        RESULT["Trade returns/losses"]
        REFLECT["Reflector<br/>reflection.py"]
        REFLECT -->|"What went right/wrong?"| LESSONS["Lessons learned<br/>(situation, recommendation) pairs"]
        LESSONS --> M1
        LESSONS --> M2
        LESSONS --> M3
        LESSONS --> M4
        LESSONS --> M5
    end

    subgraph READ_PATH["Reading from Memory (during analysis)"]
        CURRENT["Current market situation"]
        BM25["BM25Okapi Search<br/>memory.py"]
        CURRENT --> BM25
        BM25 -->|"Top N similar past situations"| CONTEXT["Past lessons + recommendations"]
        CONTEXT --> AGENTS2["Researchers & Managers<br/>use past experience"]
    end

    RESULT --> REFLECT
    M1 --> BM25
    M2 --> BM25

    style MEMORIES fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style WRITE_PATH fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style READ_PATH fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

---

## LLM Client Architecture

```mermaid
%%{init: {
  'themeVariables': { 
    'fontSize': '18px'
  },
  'flowchart': { 
    'nodeSpacing': 80, 
    'rankSpacing': 120 
  }
}}%%
flowchart TB

    %% Factory Layer
    subgraph FACTORY["Factory Layer"]
        CF["create_llm_client(provider, model)"]
    end

    %% Base Layer
    subgraph BASE["Base Class"]
        BLC["BaseLLMClient<br/>- get_llm()<br/>- validate_model()<br/>- warn_if_unknown_model()"]
    end

    %% Provider Layer
    subgraph CLIENTS["Provider Implementations"]
        direction LR
        OAI["OpenAIClient<br/>(openai, ollama, openrouter, xai)"]
        ANTH["AnthropicClient"]
        GOOG["GoogleClient"]
    end

    %% Flow (clean hierarchy)
    CF --> BLC
    BLC --> OAI
    BLC --> ANTH
    BLC --> GOOG

    %% Optional: show routing logic (lighter)
    CF -.->|"openai"| OAI
    CF -.->|"anthropic"| ANTH
    CF -.->|"google"| GOOG

    %% Styles (cleaner contrast)
    style FACTORY fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100
    style BASE fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b
    style CLIENTS fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20
```

---

## Complete File Structure

```
TradingAgents/
├── main.py                                    # Entry point
├── tradingagents/
│   ├── default_config.py                      # All default settings
│   │
│   ├── agents/
│   │   ├── analysts/
│   │   │   ├── market_analyst.py              # Tools: get_stock_data, get_indicators
│   │   │   ├── social_media_analyst.py        # Tools: get_news
│   │   │   ├── news_analyst.py                # Tools: get_news, get_global_news
│   │   │   └── fundamentals_analyst.py        # Tools: get_fundamentals, balance_sheet, cashflow, income
│   │   │
│   │   ├── researchers/
│   │   │   ├── bull_researcher.py             # BUY advocate (with memory)
│   │   │   └── bear_researcher.py             # SELL advocate (with memory)
│   │   │
│   │   ├── managers/
│   │   │   ├── research_manager.py            # Judge for Bull/Bear debate
│   │   │   └── portfolio_manager.py           # Judge for Risk debate (FINAL decision)
│   │   │
│   │   ├── trader/
│   │   │   └── trader.py                      # Execution strategy
│   │   │
│   │   ├── risk_mgmt/
│   │   │   ├── aggressive_debator.py          # High risk advocate
│   │   │   ├── conservative_debator.py        # Low risk advocate
│   │   │   └── neutral_debator.py             # Balanced advocate
│   │   │
│   │   └── utils/
│   │       ├── agent_states.py                # State definitions (AgentState)
│   │       ├── agent_utils.py                 # Helper utilities
│   │       ├── memory.py                      # BM25-based memory system
│   │       ├── core_stock_tools.py            # Tool: get_stock_data
│   │       ├── technical_indicators_tools.py  # Tool: get_indicators
│   │       ├── fundamental_data_tools.py      # Tools: fundamentals, balance sheet, etc.
│   │       └── news_data_tools.py             # Tools: news, global_news, insider_transactions
│   │
│   ├── graph/
│   │   ├── trading_graph.py                   # Main orchestrator class
│   │   ├── setup.py                           # LangGraph node/edge definitions
│   │   ├── conditional_logic.py               # Flow control (debate rounds, routing)
│   │   ├── propagation.py                     # State initialization
│   │   ├── reflection.py                      # Post-trade learning
│   │   └── signal_processing.py               # Extract final BUY/SELL/HOLD signal
│   │
│   ├── dataflows/
│   │   ├── interface.py                       # THE ROUTER: routes tools to vendors
│   │   ├── config.py                          # Data config getter/setter
│   │   ├── utils.py                           # Utility functions
│   │   ├── y_finance.py                       # yfinance data fetching
│   │   ├── yfinance_news.py                   # yfinance news fetching
│   │   ├── alpha_vantage_stock.py             # Alpha Vantage stock data
│   │   ├── alpha_vantage_fundamentals.py      # Alpha Vantage financials
│   │   ├── alpha_vantage_indicator.py         # Alpha Vantage indicators
│   │   ├── alpha_vantage_news.py              # Alpha Vantage news
│   │   ├── alpha_vantage_common.py            # Shared AV utilities
│   │   └── stockstats_utils.py                # Technical indicator calculations
│   │
│   └── llm_clients/
│       ├── factory.py                         # create_llm_client() factory function
│       ├── base_client.py                     # BaseLLMClient abstract class
│       ├── openai_client.py                   # OpenAI/Ollama/xAI/OpenRouter
│       ├── anthropic_client.py                # Anthropic Claude
│       ├── google_client.py                   # Google Gemini
│       ├── validators.py                      # Model name validation
│       └── model_catalog.py                   # Known model lists
```

---

## State Object: What Data Flows Between Agents

```mermaid
flowchart TD
    subgraph STATE["AgentState (shared state object)"]
        S1["messages: list - LLM conversation history"]
        S2["company_of_interest: str - 'NVDA'"]
        S3["trade_date: str - '2024-05-10'"]
        S4["market_report: str - Market Analyst output"]
        S5["sentiment_report: str - Social Analyst output"]
        S6["news_report: str - News Analyst output"]
        S7["fundamentals_report: str - Fundamentals Analyst output"]
        S8["investment_debate_state: dict - Bull/Bear debate history + judge decision"]
        S9["investment_plan: str - Research Manager's plan"]
        S10["trader_investment_plan: str - Trader's execution plan"]
        S11["risk_debate_state: dict - Risk debate history"]
        S12["final_trade_decision: str - Portfolio Manager's FINAL output"]
    end

    style STATE fill:#f5f5f5
```
