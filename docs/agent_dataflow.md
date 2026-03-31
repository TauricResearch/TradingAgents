<!-- Last verified: 2026-03-31 -->

# Agent Data & Tool Flow

This is the compact companion to [`graph_execution_reference.md`](./graph_execution_reference.md).
Use this file when you need the current agent/tool/memory picture without the full node-by-node runtime detail.

## Reading Order

- Use [`graph_flows.md`](./graph_flows.md) for the shortest topology overview.
- Use [`graph_execution_reference.md`](./graph_execution_reference.md) for exact execution order and state writes.
- Use this file for role summaries, tool behavior, and memory usage.

## Execution Patterns

| Pattern | Where it is used | Meaning |
| --- | --- | --- |
| Prefetch before LLM call | Market, social, news, fundamentals analysts | Python fetches selected context before the LLM prompt is built. |
| Inline tool loop | Scanner agents, market analyst, fundamentals analyst, holding reviewer | Tools are bound and resolved inside the node via `run_tool_loop()`. |
| Pure reasoning node | Debate agents, risk agents, macro synthesis, summary agents, PM decision | No tools are bound. The node only reasons over state and memory context. |
| Plain Python closure | Portfolio loading, risk metrics, candidate ranking, cash sweep, trade execution | No LLM call. State is transformed deterministically in Python. |

## Trading Workflow

| Agent / node | Tier | Tool behavior | Memory behavior | Primary output |
| --- | --- | --- | --- | --- |
| Market Analyst | quick | Prefetches `get_macro_regime` and `get_stock_data`; may call `get_indicators` inline | none | `market_report`, `macro_regime_report` |
| Social Analyst | quick | Prefetches `get_news`; no post-prefetch tool loop | none | `sentiment_report` |
| News Analyst | quick | Prefetches `get_news` and `get_global_news`; no post-prefetch tool loop | none | `news_report` |
| Fundamentals Analyst | quick | Prefetches `get_ttm_analysis`, `get_fundamentals`, `get_peer_comparison`, `get_sector_relative`; may call statement tools inline | none | `fundamentals_report` |
| Bull Researcher | mid | no tools | `bull_memory.get_memories()` | debate update |
| Bear Researcher | mid | no tools | `bear_memory.get_memories()` | debate update |
| Research Manager | deep | no tools | `invest_judge_memory.get_memories()` | `investment_plan` |
| Trader | mid | no tools | `trader_memory.get_memories()` | `trader_investment_plan` |
| Aggressive / Conservative / Neutral | quick | no tools | none | `risk_debate_state` updates |
| Portfolio Manager | deep | no tools | `portfolio_manager_memory.get_memories()` | `final_trade_decision` |

## Scanner Workflow

| Agent / node | Tier | Tool behavior | Memory behavior | Primary output |
| --- | --- | --- | --- | --- |
| Gatekeeper Scanner | quick | `get_gatekeeper_universe` inline | none | `gatekeeper_universe_report` |
| Geopolitical Scanner | quick | `get_topic_news` inline | none | `geopolitical_report` |
| Market Movers Scanner | quick | `get_market_indices` inline | none | `market_movers_report` |
| Sector Scanner | quick | `get_sector_performance` inline | none | `sector_performance_report` |
| Factor Alignment Scanner | quick | `get_topic_news`, `get_earnings_calendar` inline | none | `factor_alignment_report` |
| Smart Money Scanner | quick | Finviz smart-money tools inline | none | `smart_money_report` |
| Drift Scanner | quick | `get_gap_candidates`, `get_topic_news`, `get_earnings_calendar` inline | none | `drift_opportunities_report` |
| Industry Deep Dive | mid | `get_industry_performance`, `get_topic_news` inline | none | `industry_deep_dive_report` |
| Macro Synthesis | deep | no tools; deterministic ranking before final LLM call | none | `macro_scan_summary` |

## Portfolio Workflow

| Agent / node | Tier | Tool behavior | Memory behavior | Primary output |
| --- | --- | --- | --- | --- |
| `load_portfolio` | n/a | no tools | none | `portfolio_data` |
| `compute_risk` | n/a | no tools | none | `risk_metrics` |
| `review_holdings` | mid | `get_stock_data`, `get_news` inline | none | `holding_reviews` |
| `prioritize_candidates` | n/a | no tools | selection memory from lesson store may enrich ranking | `prioritized_candidates` |
| `macro_summary` | mid | no tools | `MacroMemory.build_macro_context()` + persistence | `macro_brief`, `macro_memory_context` |
| `micro_summary` | mid | no tools | `ReflexionMemory.build_context()` | `micro_brief`, `micro_memory_context` |
| `make_pm_decision` | deep | no tools; structured-output path with raw fallback | brief-based only | `pm_decision` |
| `cash_sweep` | n/a | no tools | none | `cash_sweep`, updated `pm_decision` |
| `execute_trades` | n/a | no tools | none | `execution_result` |

## Tool Groups

| Group | Tools |
| --- | --- |
| Core market | `get_stock_data`, `get_market_indices`, `get_sector_performance`, `get_gap_candidates` |
| Technicals | `get_indicators`, `get_macro_regime` |
| Fundamentals | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_ttm_analysis`, `get_peer_comparison`, `get_sector_relative` |
| News | `get_news`, `get_global_news`, `get_topic_news`, `get_earnings_calendar` |
| Scanner-only | `get_gatekeeper_universe`, `get_industry_performance` |
| Smart money | `get_insider_buying_stocks`, `get_unusual_volume_stocks`, `get_breakout_accumulation_stocks` |

## Memory Surfaces

| Memory system | Used by | Purpose |
| --- | --- | --- |
| `FinancialSituationMemory` | bull, bear, trader, research manager, portfolio manager | Similar-situation retrieval for debate and decision refinement |
| `MacroMemory` | `macro_summary` | Regime-level lessons and context carryover |
| `ReflexionMemory` | `micro_summary` | Per-ticker historical lessons and prior outcomes |
| Selection lesson store | `prioritize_candidates` | Negative screening lessons applied during ranking |

## Current Runtime Notes

- The compiled trading graph still contains `tools_*` ToolNode nodes, but current analyst behavior mostly prefetches context or resolves tools inline before moving to the message-clear nodes.
- The trading analyst stage is sequential, not parallel.
- The scanner graph is a real fan-out/fan-in graph with reducer-protected shared state.
- The portfolio graph is mixed-mode: deterministic Python nodes, one inline-tool holding reviewer, parallel summary agents, then deterministic post-processing and execution.
