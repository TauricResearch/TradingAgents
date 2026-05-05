# TradingAgents 调用链 (Call Chain)

## 1. 总览：从入口到最终决策

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            ENTRY POINTS                                     │
│                                                                             │
│  CLI:  cli/main.py                 API:  main.py                            │
│  ├─ typer app.analyze()            └─ TradingAgentsGraph.propagate()        │
│  └─ run_analysis()                                                          │
│      ├─ get_user_selections()  ← 交互式问卷 (9步)                            │
│      └─ TradingAgentsGraph(...)                                              │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TradingAgentsGraph.__init__()                             │
│                    trading_graph.py:50                                       │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. set_config()          → dataflows/config.py  全局配置单例           │   │
│  │ 2. create_llm_client()   → llm_clients/factory.py                     │   │
│  │    ├─ deep_thinking_llm  (Research Manager + Portfolio Manager 用)    │   │
│  │    └─ quick_thinking_llm (其余 10 个 Agent 用)                        │   │
│  │ 3. TradingMemoryLog()    → agents/utils/memory.py  决策记忆/反思      │   │
│  │ 4. _create_tool_nodes()  → 4 个 ToolNode, 包装 @tool 函数             │   │
│  │ 5. ConditionalLogic()    → graph/conditional_logic.py  路由决策        │   │
│  │ 6. GraphSetup()          → graph/setup.py  构建 StateGraph             │   │
│  │ 7. Propagator()          → graph/propagation.py  状态创建              │   │
│  │ 8. Reflector()           → graph/reflection.py  结果反思               │   │
│  │ 9. SignalProcessor()     → graph/signal_processing.py  评级解析        │   │
│  │ 10. workflow.compile()   → 编译 LangGraph                             │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TradingAgentsGraph.propagate()                            │
│                    trading_graph.py:265                                      │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Phase B: _resolve_pending_entries() ← 对同股票上次决定的滞后反思       │   │
│  │   ├─ yfinance 获取实际收益率                                           │   │
│  │   ├─ Reflector.reflect_on_final_decision()  ← quick_thinking_llm      │   │
│  │   └─ TradingMemoryLog.batch_update_with_outcomes()                     │   │
│  │                                                                        │   │
│  │ _run_graph()                                                           │   │
│  │   ├─ propagator.create_initial_state()  → AgentState                  │   │
│  │   ├─ graph.stream(init_state)  → LangGraph 流式执行                    │   │
│  │   │   └─ (详见下方 "Agent 管道" 章节)                                  │   │
│  │   ├─ _log_state()  → JSON 写入磁盘                                     │   │
│  │   ├─ TradingMemoryLog.store_decision()  → Phase A 存储                 │   │
│  │   └─ signal_processor.process_signal()  → 提取 Buy/Hold/Sell 评级     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Agent 管道（LangGraph 节点图）

```
                             START
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Market Analyst                                                  │
│  agents/analysts/market_analyst.py                                       │
│  LLM: quick_thinking_llm                                                 │
│  Tools: [get_stock_data, get_indicators]                                │
│                                                                          │
│  prompt | llm.bind_tools(tools) | llm.invoke()                          │
│       │                                                                  │
│       ├─ 有 tool_calls ──→ [tools_market] ──→ 回到 Market Analyst       │
│       │                      │                                           │
│       │                      ├─ get_stock_data()                         │
│       │                      │   └─ dataflows/interface.py              │
│       │                      │       └─ route_to_vendor()                │
│       │                      │           ├─ yfinance → Yahoo Finance API  │
│       │                      │           └─ Alpha Vantage API             │
│       │                      │                                           │
│       │                      └─ get_indicators()                         │
│       │                          └─ dataflows/stockstats_utils.py        │
│       │                              └─ stockstats.wrap(ohlcv)            │
│       │                                                                  │
│       └─ 无 tool_calls ──→ 写入 state["market_report"]                  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                     ┌─────────────────┐
                     │  Msg Clear      │  ← create_msg_delete()
                     │  (清空消息列表)   │     清空 messages 并插入
                     └────────┬────────┘     HumanMessage("Continue")
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 2: Social Media Analyst                                            │
│  agents/analysts/social_media_analyst.py                                 │
│  LLM: quick_thinking_llm                                                 │
│  Tools: [get_news]                                                       │
│                                                                          │
│  (模式同上: prompt → llm.bind_tools → invoke → tool_calls 循环)          │
│                                                                          │
│  输出: state["sentiment_report"]                                         │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                     ┌─────────────────┐
                     │  Msg Clear      │
                     └────────┬────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 3: News Analyst                                                    │
│  agents/analysts/news_analyst.py                                         │
│  LLM: quick_thinking_llm                                                 │
│  Tools: [get_news, get_global_news, get_insider_transactions]           │
│                                                                          │
│  输出: state["news_report"]                                              │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                     ┌─────────────────┐
                     │  Msg Clear      │
                     └────────┬────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 4: Fundamentals Analyst                                            │
│  agents/analysts/fundamentals_analyst.py                                 │
│  LLM: quick_thinking_llm                                                 │
│  Tools: [get_fundamentals, get_balance_sheet, get_cashflow,              │
│          get_income_statement]                                           │
│                                                                          │
│  输出: state["fundamentals_report"]                                      │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                     ┌─────────────────┐
                     │  Msg Clear      │
                     └────────┬────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 5: Research Debate (牛熊辩论)  ← 最大 N 轮                         │
│                                                                          │
│      ┌────────────────────┐         ┌────────────────────┐              │
│      │  Bull Researcher   │ ──────→ │  Bear Researcher   │              │
│      │  (无 Tools)        │ ←────── │  (无 Tools)        │              │
│      │  quick_thinking_llm│         │  quick_thinking_llm│              │
│      └────────┬───────────┘         └────────┬───────────┘              │
│               │                              │                           │
│               │  读写:                       │  读写:                     │
│               │  invest_debate_state         │  invest_debate_state       │
│               │  ["bull_history"]            │  ["bear_history"]          │
│               │  ["current_response"]        │  ["current_response"]      │
│               │                              │                           │
│               └──────────┬───────────────────┘                           │
│                          │                                               │
│               ConditionalLogic.should_continue_debate()                  │
│               count >= 2*max_debate_rounds?                              │
│                          │                                               │
│                     YES  │  NO → 回到 Bull/Bear                          │
│                          ▼                                               │
│               ┌──────────────────────┐                                   │
│               │  Research Manager    │  ← deep_thinking_llm              │
│               │  结构化输出:          │                                   │
│               │  bind_structured(    │                                   │
│               │    llm,              │                                   │
│               │    ResearchPlan)     │                                   │
│               │                     │                                   │
│               │  输出 →              │                                   │
│               │  state["investment_  │                                   │
│               │  plan"]              │                                   │
│               └──────────────────────┘                                   │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 6: Trader                                                          │
│  agents/trader/trader.py                                                 │
│  LLM: quick_thinking_llm                                                 │
│  结构化输出: bind_structured(llm, TraderProposal)                        │
│                                                                          │
│  输入: Research Manager 的 investment_plan                                │
│  输出: state["trader_investment_plan"]                                   │
│        {action: Buy/Hold/Sell, entry_price, stop_loss, position_sizing}  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  STEP 7: Risk Debate (风险辩论)  ← 最大 N 轮                             │
│                                                                          │
│   Aggressive Analyst ──→ Conservative Analyst ──→ Neutral Analyst        │
│        ↑        ←────────────←─────────────────────┘  │                  │
│        └──────────────────────────────────────────────┘                  │
│                                                                          │
│  全部使用 quick_thinking_llm (无 Tools, f-string 提示词)                  │
│                                                                          │
│  ConditionalLogic.should_continue_risk_analysis()                        │
│  count >= 3*max_risk_discuss_rounds?                                     │
│                                                                          │
│                    YES                                                    │
│                     ▼                                                    │
│              ┌──────────────────────┐                                    │
│              │ Portfolio Manager    │  ← deep_thinking_llm               │
│              │ 结构化输出:           │                                    │
│              │ bind_structured(     │                                    │
│              │   llm,              │                                    │
│              │   PortfolioDecision) │                                    │
│              │                     │                                    │
│              │ 输入: 风险辩论历史    │                                    │
│              │   + research plan   │                                    │
│              │   + trader plan     │                                    │
│              │   + past_context    │ ← 来自 TradingMemoryLog             │
│              │                     │                                    │
│              │ 输出 →              │                                    │
│              │ state["final_trade_ │                                    │
│              │ decision"]          │                                    │
│              └──────────────────────┘                                    │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                               ▼
                              END
```

---

## 3. 数据流层 (Data Vendor 路由)

```
agent 调用 @tool 函数 (如 get_stock_data)
         │
         ▼
dataflows/interface.py: route_to_vendor(method_name, *args)
         │
         ├─ get_category_for_method(method_name)
         │   └─ TOOLS_CATEGORIES dict 映射
         │      ├─ "get_stock_data"       → "core_stock_apis"
         │      ├─ "get_indicators"       → "technical_indicators"
         │      ├─ "get_fundamentals"     → "fundamental_data"
         │      ├─ "get_balance_sheet"    → "fundamental_data"
         │      ├─ "get_cashflow"         → "fundamental_data"
         │      ├─ "get_income_statement" → "fundamental_data"
         │      ├─ "get_news"             → "news_data"
         │      ├─ "get_global_news"      → "news_data"
         │      └─ "get_insider_transactions" → "news_data"
         │
         ├─ 读取 config["data_vendors"][category] → 数据供应商
         ├─ 支持降级链: "alpha_vantage,yfinance"
         │
         └─ VENDOR_METHODS[category][vendor]["method"](*args)
                │
                ├─── yfinance ───→ dataflows/y_finance.py
                │                  ├─ get_YFin_data_online()
                │                  │   └─ yfinance.Ticker().history()
                │                  ├─ get_stock_stats_indicators_window()
                │                  │   └─ stockstats_utils.load_ohlcv()
                │                  │       └─ stockstats.wrap()
                │                  └─ dataflows/yfinance_news.py
                │                      └─ yfinance.Ticker().news
                │
                └─── alpha_vantage ───→ dataflows/alpha_vantage_*.py
                                       ├─ alpha_vantage_stock.py
                                       ├─ alpha_vantage_indicator.py
                                       ├─ alpha_vantage_fundamentals.py
                                       └─ alpha_vantage_news.py
                                           └─ https://www.alphavantage.co/query
```

---

## 4. LLM 客户端层 (Provider 路由)

```
create_llm_client(provider, model, base_url, **kwargs)
         │
         ▼
llm_clients/factory.py
         │
         ├─ "openai"     → OpenAIClient      → NormalizedChatOpenAI
         ├─ "xai"        → OpenAIClient      → NormalizedChatOpenAI
         ├─ "deepseek"   → OpenAIClient      → DeepSeekChatOpenAI
         │                                    (处理 thinking 模式往返)
         ├─ "qwen"       → OpenAIClient      → NormalizedChatOpenAI
         ├─ "glm"        → OpenAIClient      → NormalizedChatOpenAI
         ├─ "ollama"     → OpenAIClient      → NormalizedChatOpenAI
         ├─ "openrouter" → OpenAIClient      → NormalizedChatOpenAI
         ├─ "anthropic"  → AnthropicClient   → NormalizedChatAnthropic
         ├─ "google"     → GoogleClient      → NormalizedChatGoogleGenerativeAI
         │                                    (thinking_level / thinking_budget)
         └─ "azure"      → AzureOpenAIClient → NormalizedAzureChatOpenAI

所有 Normalized* 类重写 invoke() → normalize_content()
   将 list-based content (reasoning blocks) 压平为纯字符串
```

---

## 5. 结构化输出层

```
Research Manager / Trader / Portfolio Manager 需要结构化输出
         │
         ▼
agents/utils/structured.py
         │
         ├─ bind_structured(llm, schema, agent_name)
         │   └─ llm.with_structured_output(schema)
         │      ├─ 成功 → 返回结构化 LLM
         │      └─ 失败 → 返回 None (deepseek-reasoner 等不支持)
         │
         └─ invoke_structured_or_freetext(structured_llm, plain_llm, prompt)
             ├─ structured_llm 存在 → structured_llm.invoke(prompt) → Pydantic Model
             └─ structured_llm 为 None → plain_llm.invoke(prompt) → 原始文本
                                             └─ 内容作为 result.response.content 返回

Schemas (agents/schemas.py):
  ├─ ResearchPlan:     recommendation (PortfolioRating), rationale, strategic_actions
  ├─ TraderProposal:   action (TraderAction), reasoning, entry_price, stop_loss
  └─ PortfolioDecision: rating, executive_summary, investment_thesis, price_target
```

---

## 6. 记忆 / 反思系统 (Memory & Reflection)

```
┌─────────────────────────────────────────────────────────────────┐
│                    TradingMemoryLog                              │
│                    agents/utils/memory.py                        │
│                                                                 │
│  存储位置: ~/.tradingagents/memory/trading_memory.md            │
│  (追加式 Markdown 日志)                                         │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Phase A (本次运行结束时)                                    │  │
│  │   store_decision(ticker, date, final_decision, rating)     │  │
│  │   → 追加一条 [pending] 条目                                │  │
│  │                                                            │  │
│  │ Phase B (下次同股票运行时)                                  │  │
│  │   _resolve_pending_entries(ticker)                         │  │
│  │   1. yfinance 获取实际收益率                                │  │
│  │   2. Reflector.reflect_on_final_decision()                 │  │
│  │      → quick_thinking_llm 生成 2-4 句反思                  │  │
│  │   3. batch_update_with_outcomes() → 原子更新               │  │
│  │                                                            │  │
│  │ Read Path (Portfolio Manager 提示词注入)                   │  │
│  │   get_past_context() + get_cross_ticker_context()          │  │
│  │   → 同股票最近 5 条 + 跨股票反思 3 条                      │  │
│  │   → 注入 Portfolio Manager 作为 past_context               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. 完整调用顺序总结

```
1. CLI 入口 cli/main.py:app.analyze()
2. 交互式问卷 get_user_selections() (股票/日期/语言/分析师/深度/LLM/数据源)
3. TradingAgentsGraph.__init__()
   ├─ 配置 → set_config()
   ├─ LLM 客户端 ×2 → create_llm_client() → factory dispatch
   ├─ 记忆日志 → TradingMemoryLog()
   ├─ 工具节点 ×4 → _create_tool_nodes()
   ├─ 路由逻辑 → ConditionalLogic()
   ├─ 图构建 → GraphSetup.setup_graph()
   │   ├─ 创建 12 个 Agent 节点 (工厂函数)
   │   └─ 构建 LangGraph StateGraph + 编译
   ├─ 状态创建器 → Propagator()
   ├─ 反思器 → Reflector()
   └─ 信号处理器 → SignalProcessor()
4. TradingAgentsGraph.propagate(ticker, date)
   ├─ Phase B: 解析之前待定条目的实际收益 + 反思
   └─ _run_graph()
       ├─ 创建初始状态 → propagator.create_initial_state()
       └─ graph.stream() → LangGraph 节点管道:
           ├─ Market Analyst ⇄ tools_market → market_report
           ├─ Social Analyst ⇄ tools_social → sentiment_report
           ├─ News Analyst ⇄ tools_news → news_report
           ├─ Fundamentals Analyst ⇄ tools_fundamentals → fundamentals_report
           ├─ Bull ⇄ Bear (辩论循环) → Research Manager → investment_plan
           ├─ Trader → trader_investment_plan
           ├─ Aggressive → Conservative → Neutral (风险辩论) → Portfolio Manager
           │   └─ past_context 注入 (来自 Memory)
           └─ final_trade_decision
       ├─ 日志写入 JSON → _log_state()
       ├─ Phase A → TradingMemoryLog.store_decision()
       └─ 评级解析 → SignalProcessor.process_signal()
5. CLI 后处理:
   ├─ 流式输出分析过程 (Rich Live Display)
   ├─ 保存报告到磁盘
   └─ 显示完整报告
```
