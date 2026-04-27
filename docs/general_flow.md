# General Flow - Analysis Nodes

## Tổng quan

Khi user chọn analysts (`market`, `social`, `news`, `fundamentals`), graph chạy tuần tự từng node. Mỗi node gọi LLM + tools, loop cho đến khi không còn tool_calls, rồi chuyển sang node tiếp theo.

**CLI entry:** `tradingagents analyze` -> `run_analysis()` -> `get_user_selections()` -> `TradingAgentsGraph()` -> `graph.stream()` -> `publish_to_notion()`

### Color Legend

```mermaid
flowchart LR
    E["Existing Component"]:::existing
    N["New Component"]:::new

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

> Hiện tại **tất cả** components đều là **existing** (đen đậm). Khi thêm component mới, đổi class sang `new` (xanh lá).

---

## 0. Full Pipeline: CLI → Graph → Notion

```mermaid
flowchart TD
    CLI["<b>CLI: tradingagents analyze</b><br/><i>cli/main.py :: analyze()</i>"]:::existing
    CLI --> RA["<b>run_analysis()</b><br/><i>Orchestrate toàn bộ pipeline</i>"]:::existing

    RA --> GUS["<b>get_user_selections()</b><br/><i>Thu thập input: market type, ticker,<br/>date, analysts, LLM provider, depth</i>"]:::existing

    GUS --> S1["Step 1: select_market_type()<br/><i>stock / crypto / forex</i>"]:::existing
    GUS --> S2["Step 2: get_ticker()<br/><i>VD: AAPL, BTCUSDT, EURUSD=X</i>"]:::existing
    GUS --> S3["Step 3: get_analysis_date()<br/><i>YYYY-MM-DD</i>"]:::existing
    GUS --> S4["Step 4: select_analysts()<br/><i>market, social, news, fundamentals</i>"]:::existing
    GUS --> S5["Step 5: select_research_depth()<br/><i>Số rounds debate</i>"]:::existing
    GUS --> S6["Step 6: select_llm_provider()<br/><i>openai / anthropic / gpt</i>"]:::existing

    GUS --> S7["Step 7: select_thinking_agents()<br/><i>shallow + deep thinker models</i>"]:::existing

    GUS --> CFG["<b>Build config dict</b><br/><i>Merge DEFAULT_CONFIG + user selections</i>"]:::existing
    CFG --> TAG["<b>TradingAgentsGraph(selected_analysts, config)</b><br/><i>Khởi tạo LLMs, tool nodes, compile graph</i>"]:::existing

    TAG --> INIT["<b>propagator.create_initial_state(ticker, date)</b><br/><i>Tạo AgentState ban đầu với empty reports</i>"]:::existing
    INIT --> STREAM["<b>graph.stream(init_state, **args)</b><br/><i>Chạy multi-agent workflow, stream chunks</i>"]:::existing

    STREAM --> CHUNKS["Process chunks loop:<br/><i>Track messages, tool calls, update UI</i>"]:::existing
    CHUNKS --> FINAL["<b>final_state = trace[-1]</b><br/><i>Lấy state cuối cùng</i>"]:::existing
    FINAL --> SIGNAL["<b>graph.process_signal(final_trade_decision)</b><br/><i>Xử lý tín hiệu BUY/HOLD/SELL</i>"]:::existing

    SIGNAL --> SAVE{"Save report?"}:::existing
    SAVE -->|Y| DISK["<b>save_report_to_disk()</b><br/><i>Lưu .md vào reports/TICKER/DATE/</i>"]:::existing
    SAVE -->|N| NOTION_Q

    DISK --> NOTION_Q{"Publish to Notion?"}:::existing
    NOTION_Q -->|Y| NOTION["<i>Ingress all reports</i>"]:::existing
    

    NOTION --> LLM_API["select_llm_provider()<br/><i>openai / anthropic / gpt-5.3-codex-high</i>"]:::existing
    NOTION_Q -->|N| DISPLAY
    DISPLAY -->|Y| SHOW["<b>display_complete_report(final_state)</b><br/><i>In report ra terminal</i>"]:::existing

    LLM_API -->GPT_CODEX["transform to JSON"]:::new
    GPT_CODEX --> Pilot["Draw chart"]:::new

    Pilot --> NOTION_API["<b>publish chart data to notion</b> <br/> <i>Handle fallback and expcetion</i> "]:::new    
    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

---

## 0.1 CLI User Selections Detail

```mermaid
flowchart LR
    subgraph CLI ["cli/main.py :: get_user_selections()"]
        direction TB
        M["select_market_type()"]:::existing --> T["get_ticker()"]:::existing
        T --> D["get_analysis_date()"]:::existing
        D --> A["select_analysts()"]:::existing
        A --> R["select_research_depth()"]:::existing
        R --> P["select_llm_provider()"]:::existing
        P --> TH["select_thinking_agents()"]:::existing
        TH --> EF["ask_anthropic_effort()<br/><i>Chỉ khi provider = anthropic</i>"]:::existing
        EF --> KL["ask_kline_config()<br/><i>Chỉ khi market = crypto</i>"]:::existing
    end

    subgraph Config ["Config Assembly"]
        KL --> CFG["DEFAULT_CONFIG.copy()"]:::existing
        CFG --> |"merge"| FINAL["Final config dict"]:::existing
    end

    FINAL --> GRAPH["TradingAgentsGraph(analysts, config)"]:::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

| Step | Hàm | Mô tả |
|------|------|-------|
| 1 | `select_market_type()` | Chọn stock, crypto, hoặc forex |
| 2 | `get_ticker()` | Nhập ticker (AAPL, BTCUSDT, EURUSD=X) |
| 3 | `get_analysis_date()` | Nhập ngày phân tích, default = hôm nay |
| 4 | `select_analysts()` | Chọn analysts: market, social, news, fundamentals |
| 5 | `select_research_depth()` | Chọn số rounds debate (Bull vs Bear) |
| 6 | `select_llm_provider()` | Chọn openai hoặc anthropic |
| 7 | `select_thinking_agents()` | Chọn model cho shallow + deep thinking |
| 8 | `ask_anthropic_effort()` | Chỉ Anthropic: config effort level |
| 9 | `ask_kline_config()` | Chỉ crypto: interval + date range cho Binance klines |

---

## 0.2 Graph Initialization

```mermaid
flowchart TD
    TAG["TradingAgentsGraph.__init__(selected_analysts, config)"]:::existing
    TAG --> LLM1["create_llm_client(deep_think_llm)<br/><i>LLM cho Research Manager, Portfolio Manager</i>"]:::existing
    TAG --> LLM2["create_llm_client(quick_think_llm)<br/><i>LLM cho tất cả analysts, traders, debaters</i>"]:::existing
    TAG --> TN["_create_tool_nodes()<br/><i>Tạo ToolNode cho market, social, news, fundamentals</i>"]:::existing
    TAG --> CL["ConditionalLogic(max_debate, max_risk)<br/><i>Logic rẽ nhánh: tool loop vs next node</i>"]:::existing
    TAG --> GS["GraphSetup(quick_llm, deep_llm, tool_nodes, cond_logic)<br/><i>Setup và compile LangGraph workflow</i>"]:::existing
    GS --> WF["setup_graph(selected_analysts)<br/><i>Tạo StateGraph, add nodes + edges</i>"]:::existing
    WF --> COMPILE["workflow.compile()<br/><i>Compiled graph sẵn sàng stream</i>"]:::existing
    TAG --> PROP["Propagator()<br/><i>Tạo initial state</i>"]:::existing
    TAG --> REF["Reflector()<br/><i>Reflect on decisions</i>"]:::existing
    TAG --> SP["SignalProcessor()<br/><i>Xử lý BUY/HOLD/SELL signal</i>"]:::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

---

## 1. Flow tổng thể (Graph Execution)

```mermaid
flowchart TD
    START([START]):::existing --> FirstAnalyst

    subgraph Analysts ["Analyst Nodes (tuần tự theo selected_analysts)"]
        FirstAnalyst["Market Analyst<br/><i>hoặc analyst đầu tiên được chọn</i>"]:::existing
        FirstAnalyst -->|tool_calls?| ToolLoop1{"should_continue_*()"}:::existing
        ToolLoop1 -->|Yes| Tools1["tools_market / tools_*"]:::existing
        Tools1 --> FirstAnalyst
        ToolLoop1 -->|No| MsgClear1["Msg Clear *<br/><i>Xóa messages, thêm placeholder</i>"]:::existing
        MsgClear1 --> NextAnalyst["Analyst tiếp theo..."]:::existing
        NextAnalyst -->|"Analyst cuối cùng"| BullResearcher
    end

    subgraph Debate ["Investment Debate"]
        BullResearcher["Bull Researcher"]:::existing <-->|max_debate_rounds| BearResearcher["Bear Researcher"]:::existing
        BullResearcher --> ResearchManager["Research Manager"]:::existing
        BearResearcher --> ResearchManager
    end

    subgraph Risk ["Risk Analysis"]
        ResearchManager --> Trader["Trader"]:::existing
        Trader --> Aggressive["Aggressive Analyst"]:::existing
        Aggressive <--> Conservative["Conservative Analyst"]:::existing
        Conservative <--> Neutral["Neutral Analyst"]:::existing
        Neutral <--> Aggressive
        Aggressive --> PM["Portfolio Manager"]:::existing
        Conservative --> PM
        Neutral --> PM
    end

    PM --> END([END]):::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

---

## 2. Market Analyst Node

**Parent function:** `create_market_analyst(llm)` -> `market_analyst_node(state)`
**Conditional:** `should_continue_market()` -> `tools_market` hoặc `Msg Clear Market`
**Output key:** `market_report`

```mermaid
flowchart LR
    subgraph MarketNode ["Market Analyst"]
        MA["market_analyst_node()"]:::existing -->|bind_tools| LLM["LLM invoke"]:::existing
        LLM -->|tool_calls| TC{"has tool_calls?"}:::existing
        TC -->|Yes| TN["ToolNode: tools_market"]:::existing
        TN --> MA
        TC -->|No| OUT["market_report = result.content"]:::existing
    end

    subgraph Tools ["Tools & Endpoints"]
        T1["get_stock_data(symbol, start, end)<br/><i>Lấy dữ liệu OHLCV giá cổ phiếu</i>"]:::existing
        T2["get_indicators(symbol, indicator, date, lookback)<br/><i>Tính technical indicators: SMA, RSI, MACD, Bollinger, ATR, VWMA</i>"]:::existing
        T3["get_fibonacci_retracement(symbol, start, end)<br/><i>Tính Fibonacci levels cho support/resistance</i>"]:::existing
    end

    subgraph Vendors ["Vendor Routing: route_to_vendor()"]
        V1["yfinance: yf.Ticker().history()"]:::existing
        V2["alpha_vantage: TIME_SERIES_DAILY"]:::existing
        V3["binance: get_binance_klines()"]:::existing
    end

    TN --> T1
    TN --> T2
    TN --> T3
    T1 --> Vendors
    T2 --> Vendors
    T3 --> Vendors

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

| Tool | Hàm | Mô tả |
|------|------|-------|
| `get_stock_data` | `core_stock_tools.py:get_stock_data()` | Lấy OHLCV qua `route_to_vendor()`. Primary: yfinance, fallback: alpha_vantage, binance |
| `get_indicators` | `technical_indicators_tools.py:get_indicators()` | Tính SMA/RSI/MACD/Bollinger/ATR/VWMA qua vendor routing |
| `get_fibonacci_retracement` | `core_stock_tools.py:get_fibonacci_retracement()` | Tính Fibonacci retracement levels (0, 0.236, 0.382, 0.5, 0.618, 1.0) |

---

## 3. Social Analyst Node

**Parent function:** `create_social_media_analyst(llm)` -> `social_media_analyst_node(state)`
**Conditional:** `should_continue_social()` -> `tools_social` hoặc `Msg Clear Social`
**Output key:** `sentiment_report`

```mermaid
flowchart LR
    subgraph SocialNode ["Social Analyst"]
        SA["social_media_analyst_node()"]:::existing -->|bind_tools| LLM["LLM invoke"]:::existing
        LLM -->|tool_calls| TC{"has tool_calls?"}:::existing
        TC -->|Yes| TN["ToolNode: tools_social"]:::existing
        TN --> SA
        TC -->|No| OUT["sentiment_report = result.content"]:::existing
    end

    subgraph Tools ["Tools & Endpoints"]
        T1["get_news(ticker, start_date, end_date)<br/><i>Lấy tin tức company-specific + social sentiment</i>"]:::existing
    end

    subgraph Vendors ["Vendor Routing: route_to_vendor()"]
        V1["yfinance: yf.Ticker().news"]:::existing
        V2["alpha_vantage: NEWS_SENTIMENT endpoint"]:::existing
    end

    TN --> T1
    T1 --> Vendors

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

| Tool | Hàm | Mô tả |
|------|------|-------|
| `get_news` | `news_data_tools.py:get_news()` | Lấy tin company-specific qua `route_to_vendor()`. Phân tích sentiment từ social media |

---

## 4. News Analyst Node

**Parent function:** `create_news_analyst(llm)` -> `news_analyst_node(state)`
**Conditional:** `should_continue_news()` -> `tools_news` hoặc `Msg Clear News`
**Output key:** `news_report`

```mermaid
flowchart LR
    subgraph NewsNode ["News Analyst"]
        NA["news_analyst_node()"]:::existing -->|bind_tools| LLM["LLM invoke"]:::existing
        LLM -->|tool_calls| TC{"has tool_calls?"}:::existing
        TC -->|Yes| TN["ToolNode: tools_news"]:::existing
        TN --> NA
        TC -->|No| OUT["news_report = result.content"]:::existing
    end

    subgraph Tools ["Tools & Endpoints"]
        T1["get_news(ticker, start_date, end_date)<br/><i>Lấy tin tức targeted theo company</i>"]:::existing
        T2["get_global_news(curr_date, look_back_days, limit)<br/><i>Lấy tin macro từ S&P500, Dow Jones, NASDAQ</i>"]:::existing
    end

    subgraph Vendors ["Vendor Routing: route_to_vendor()"]
        V1["yfinance: yf.Ticker().news + _fetch_index_news()"]:::existing
        V2["alpha_vantage: NEWS_SENTIMENT endpoint"]:::existing
    end

    TN --> T1
    TN --> T2
    T1 --> Vendors
    T2 --> Vendors

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

| Tool | Hàm | Mô tả |
|------|------|-------|
| `get_news` | `news_data_tools.py:get_news()` | Lấy tin tức targeted theo ticker qua vendor routing |
| `get_global_news` | `news_data_tools.py:get_global_news()` | Lấy tin macro từ indices (^GSPC, ^DJI, ^IXIC), deduplicate |

---

## 5. Fundamentals Analyst Node

**Parent function:** `create_fundamentals_analyst(llm)` -> `fundamentals_analyst_node(state)`
**Conditional:** `should_continue_fundamentals()` -> `tools_fundamentals` hoặc `Msg Clear Fundamentals`
**Output key:** `fundamentals_report`

```mermaid
flowchart LR
    subgraph FundNode ["Fundamentals Analyst"]
        FA["fundamentals_analyst_node()"]:::existing -->|bind_tools| LLM["LLM invoke"]:::existing
        LLM -->|tool_calls| TC{"has tool_calls?"}:::existing
        TC -->|Yes| TN["ToolNode: tools_fundamentals"]:::existing
        TN --> FA
        TC -->|No| OUT["fundamentals_report = result.content"]:::existing
    end

    subgraph Tools ["Tools & Endpoints"]
        T1["get_fundamentals(ticker, curr_date)<br/><i>Lấy company overview: profile, financials cơ bản</i>"]:::existing
        T2["get_balance_sheet(ticker, freq, curr_date)<br/><i>Lấy bảng cân đối kế toán quarterly/annual</i>"]:::existing
        T3["get_cashflow(ticker, freq, curr_date)<br/><i>Lấy báo cáo lưu chuyển tiền tệ</i>"]:::existing
        T4["get_income_statement(ticker, freq, curr_date)<br/><i>Lấy báo cáo kết quả kinh doanh</i>"]:::existing
    end

    subgraph Vendors ["Vendor Routing: route_to_vendor()"]
        V1["yfinance: yf.Ticker().info / .balance_sheet / .cashflow / .financials"]:::existing
        V2["alpha_vantage: OVERVIEW / BALANCE_SHEET / CASH_FLOW / INCOME_STATEMENT"]:::existing
    end

    TN --> T1
    TN --> T2
    TN --> T3
    TN --> T4
    T1 --> Vendors
    T2 --> Vendors
    T3 --> Vendors
    T4 --> Vendors

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

| Tool | Hàm | Mô tả |
|------|------|-------|
| `get_fundamentals` | `fundamental_data_tools.py:get_fundamentals()` | Lấy company overview, profile, basic financials |
| `get_balance_sheet` | `fundamental_data_tools.py:get_balance_sheet()` | Lấy balance sheet quarterly hoặc annual |
| `get_cashflow` | `fundamental_data_tools.py:get_cashflow()` | Lấy cash flow statement quarterly hoặc annual |
| `get_income_statement` | `fundamental_data_tools.py:get_income_statement()` | Lấy income statement quarterly hoặc annual |

---

## 6. Vendor Routing

Tất cả tool calls đều đi qua `route_to_vendor()` tại `dataflows/interface.py`.

```mermaid
flowchart TD
    Tool["Tool call (vd: get_stock_data)"]:::existing --> RTV["route_to_vendor(method, *args)"]:::existing
    RTV --> Cat["get_category_for_method()"]:::existing
    Cat --> Vendor["get_vendor(category, method)"]:::existing
    Vendor --> Chain["Build fallback chain:<br/>primary vendors + remaining"]:::existing

    Chain --> Try1["Try vendor 1 (primary)"]:::existing
    Try1 -->|Success + non-empty| Return["Return result"]:::existing
    Try1 -->|Fail / empty / rate-limit| Try2["Try vendor 2 (fallback)"]:::existing
    Try2 -->|Success| Return
    Try2 -->|Fail| Try3["Try vendor 3..."]:::existing
    Try3 -->|All fail| Error["RuntimeError: All vendors exhausted"]:::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

**Vendor mặc định theo category:**

| Category | Primary | Fallback |
|----------|---------|----------|
| `core_stock_apis` | yfinance | alpha_vantage, binance |
| `technical_indicators` | yfinance | alpha_vantage, binance |
| `fundamental_data` | yfinance | alpha_vantage |
| `news_data` | yfinance | alpha_vantage |

---

## 7. Conditional Logic

Mỗi analyst node có 1 hàm conditional tại `graph/conditional_logic.py`:

| Hàm | Logic |
|-----|-------|
| `should_continue_market(state)` | Nếu `last_message.tool_calls` -> `tools_market`, ngược lại -> `Msg Clear Market` |
| `should_continue_social(state)` | Nếu `last_message.tool_calls` -> `tools_social`, ngược lại -> `Msg Clear Social` |
| `should_continue_news(state)` | Nếu `last_message.tool_calls` -> `tools_news`, ngược lại -> `Msg Clear News` |
| `should_continue_fundamentals(state)` | Nếu `last_message.tool_calls` -> `tools_fundamentals`, ngược lại -> `Msg Clear Fundamentals` |

---

## 8. Notion Export Flow

**File:** `cli/notion_publisher.py`
**Trigger:** User chọn "Y" khi CLI hỏi "Publish to Notion?"
**Requires:** `NOTION_API_KEY` + `NOTION_PARENT_PAGE_ID` trong `.env`

```mermaid
flowchart TD
    PROMPT{"CLI: Publish to Notion? (Y/N)"}:::existing
    PROMPT -->|Y| IMPORT["from cli.notion_publisher import publish_to_notion"]:::existing
    PROMPT -->|N| SKIP["Bỏ qua"]:::existing

    IMPORT --> CALL["<b>publish_to_notion(final_state, ticker, date)</b>"]:::existing

    CALL --> VALIDATE["Validate env vars:<br/>NOTION_API_KEY, NOTION_PARENT_PAGE_ID"]:::existing
    VALIDATE -->|Missing| ERR["Raise EnvironmentError"]:::existing

    VALIDATE -->|OK| TITLE["Tạo title:<br/>'Trading Analysis: TICKER — DATE'"]:::existing
    TITLE --> CREATE["<b>POST /v1/pages</b><br/><i>Tạo Notion page trống với title + timestamp</i>"]:::existing

    CREATE -->|Response| PID["Lấy page_id + page_url từ response"]:::existing
    PID --> BUILD["<b>_build_blocks(final_state, ticker, date)</b><br/><i>Convert state → Notion blocks</i>"]:::existing

    BUILD --> APPEND["<b>_append_blocks(page_id, blocks, api_key)</b><br/><i>PATCH /v1/blocks/{page_id}/children<br/>Batch 100 blocks/request</i>"]:::existing

    APPEND --> URL["Return page_url"]:::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

### Notion Page Structure (_build_blocks)

```mermaid
flowchart TD
    BS["_build_blocks(final_state)"]:::existing

    BS --> S1["<b>I. Analyst Team Reports</b>"]:::existing
    S1 --> S1A["Market Analyst → market_report"]:::existing
    S1 --> S1B["Social Analyst → sentiment_report"]:::existing
    S1 --> S1C["News Analyst → news_report"]:::existing
    S1 --> S1D["Fundamentals Analyst → fundamentals_report"]:::existing

    BS --> S2["<b>II. Research Team Decision</b>"]:::existing
    S2 --> S2A["Bull Researcher → bull_history"]:::existing
    S2 --> S2B["Bear Researcher → bear_history"]:::existing
    S2 --> S2C["Research Manager → judge_decision"]:::existing

    BS --> S3["<b>III. Trading Team Plan</b>"]:::existing
    S3 --> S3A["Trader → trader_investment_plan"]:::existing

    BS --> S4["<b>IV. Risk Management Team</b>"]:::existing
    S4 --> S4A["Aggressive Analyst → aggressive_history"]:::existing
    S4 --> S4B["Conservative Analyst → conservative_history"]:::existing
    S4 --> S4C["Neutral Analyst → neutral_history"]:::existing

    BS --> S5["<b>V. Portfolio Manager Decision</b>"]:::existing
    S5 --> S5A["Portfolio Manager → judge_decision"]:::existing

    BS --> S6["<b>VI. Investment Plan</b>"]:::existing
    BS --> S7["<b>VII. Final Trade Decision</b>"]:::existing

    classDef existing fill:#1a1a2e,stroke:#16213e,color:#fff,font-weight:bold
    classDef new fill:#00C853,stroke:#00962b,color:#fff,font-weight:bold
```

### Notion API Endpoints

| Hàm | HTTP Method | Endpoint | Mô tả |
|-----|-------------|----------|-------|
| `publish_to_notion()` | `POST` | `/v1/pages` | Tạo page mới dưới parent page |
| `_append_blocks()` | `PATCH` | `/v1/blocks/{page_id}/children` | Thêm blocks vào page, tối đa 100/request |

### Notion Block Helpers

| Hàm | Mô tả |
|-----|-------|
| `_heading2(text)` | Tạo heading_2 block cho section title |
| `_heading3(text)` | Tạo heading_3 block cho agent name |
| `_paragraph(text)` | Tạo paragraph block |
| `_divider()` | Tạo divider block giữa các sections |
| `_text_to_blocks(text)` | Split text dài thành nhiều paragraph blocks |
| `_chunks(text, 1900)` | Cắt text thành chunks ≤1900 chars (Notion limit 2000) |

---

## 9. Key Files

| File | Vai trò |
|------|---------|
| `cli/main.py` | CLI entry point: `analyze()`, `run_analysis()`, `get_user_selections()` |
| `cli/notion_publisher.py` | Notion export: `publish_to_notion()`, `_build_blocks()` |
| `cli/models.py` | Enum definitions: `AnalystType`, etc. |
| `cli/stats_handler.py` | Callback handler tracking LLM/tool call stats |
| `tradingagents/default_config.py` | Default config dict cho graph |
| `graph/setup.py` | Dựng graph, nối edges giữa các nodes |
| `graph/conditional_logic.py` | Quyết định loop tool hay chuyển node tiếp |
| `graph/trading_graph.py` | `TradingAgentsGraph` class, compile graph |
| `graph/propagation.py` | `Propagator`: tạo initial state, graph args |
| `agents/analysts/market_analyst.py` | Market node: OHLCV + indicators + Fibonacci |
| `agents/analysts/social_media_analyst.py` | Social node: sentiment + company news |
| `agents/analysts/news_analyst.py` | News node: targeted + global macro news |
| `agents/analysts/fundamentals_analyst.py` | Fundamentals node: financials + balance sheet |
| `agents/utils/agent_utils.py` | Re-export tất cả tools, helper functions |
| `dataflows/interface.py` | Vendor routing: yfinance -> alpha_vantage -> binance |
