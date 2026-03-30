# Agent Data & Tool Flow Summary

This document is the short companion to [graph_execution_reference.md](./graph_execution_reference.md).
Use the reference doc for exact node order and state transitions.
Use this file when you only need the agent/tool/memory summary.

## LLM Tier Summary

| Tier | Config key | Default role |
| --- | --- | --- |
| Quick | `quick_think_llm` | analysts, scanners, risk debaters |
| Mid | `mid_think_llm` | bull/bear researchers, trader, industry deep dive, holding review, summary agents |
| Deep | `deep_think_llm` | research manager, portfolio manager, macro synthesis, portfolio PM decision |

## Per-Agent Summary

| Agent / node | Tier | Tool behavior | Memory behavior | Primary output |
| --- | --- | --- | --- | --- |
| Market Analyst | quick | Prefetches `get_macro_regime` and `get_stock_data`; may call `get_indicators` inline | none | `market_report`, `macro_regime_report` |
| Social Analyst | quick | Prefetches `get_news`; no tool loop after prefetch | none | `sentiment_report` |
| News Analyst | quick | Prefetches `get_news` and `get_global_news`; no tool loop after prefetch | none | `news_report` |
| Fundamentals Analyst | quick | Prefetches `get_ttm_analysis`, `get_fundamentals`, `get_peer_comparison`, `get_sector_relative`; may call raw statements inline | none | `fundamentals_report` |
| Bull Researcher | mid | no tools | `bull_memory.get_memories()` | debate update |
| Bear Researcher | mid | no tools | `bear_memory.get_memories()` | debate update |
| Research Manager | deep | no tools | `invest_judge_memory.get_memories()` | `investment_plan` |
| Trader | mid | no tools | `trader_memory.get_memories()` | `trader_investment_plan` |
| Aggressive / Conservative / Neutral risk analysts | quick | no tools | none | risk debate update |
| Portfolio Manager | deep | no tools | `portfolio_manager_memory.get_memories()` | `final_trade_decision` |
| Gatekeeper Scanner | quick | `get_gatekeeper_universe` inline | none | `gatekeeper_universe_report` |
| Geopolitical Scanner | quick | `get_topic_news` inline | none | `geopolitical_report` |
| Market Movers Scanner | quick | `get_market_indices` inline | none | `market_movers_report` |
| Sector Scanner | quick | `get_sector_performance` inline | none | `sector_performance_report` |
| Factor Alignment Scanner | quick | `get_topic_news`, `get_earnings_calendar` inline | none | `factor_alignment_report` |
| Drift Scanner | quick | `get_gap_candidates`, `get_topic_news`, `get_earnings_calendar` inline | none | `drift_opportunities_report` |
| Smart Money Scanner | quick | Finviz smart-money tools inline | none | `smart_money_report` |
| Industry Deep Dive | mid | `get_industry_performance`, `get_topic_news` inline | none | `industry_deep_dive_report` |
| Macro Synthesis | deep | no tools | none | `macro_scan_summary` |
| Holding Reviewer | mid | `get_stock_data`, `get_news` inline | none | `holding_reviews` |
| Macro Summary | mid | no tools | `MacroMemory` context + persistence | `macro_brief` |
| Micro Summary | mid | no tools | `ReflexionMemory.build_context()` | `micro_brief` |
| PM Decision | deep | no tools; structured-output LLM path with raw fallback | brief-based only | `pm_decision` |

## Tool Groups

| Group | Tools |
| --- | --- |
| Core stock | `get_stock_data` |
| Technicals | `get_indicators` |
| Fundamentals | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_ttm_analysis`, `get_peer_comparison`, `get_sector_relative`, `get_macro_regime` |
| News | `get_news`, `get_global_news`, `get_insider_transactions` |
| Scanner | `get_gatekeeper_universe`, `get_market_indices`, `get_sector_performance`, `get_gap_candidates`, `get_topic_news`, `get_earnings_calendar`, `get_industry_performance` |
| Smart money | `get_insider_buying_stocks`, `get_unusual_volume_stocks`, `get_breakout_accumulation_stocks` |

## Non-LLM Workflow Nodes

These nodes are part of runtime flow but are not agents:

- `Msg Clear *` nodes in the trading graph
- `load_portfolio`
- `compute_risk`
- `prioritize_candidates`
- `cash_sweep`
- `execute_trades`

## Important Current-State Notes

- The compiled trading graph still includes `tools_*` ToolNode nodes, but current analyst implementations already resolve their tools internally. In practice those graph-level tool nodes are mostly dormant.
- Older docs that describe parallel analysts are stale. The current compiled trading graph runs analysts sequentially.
- `auto` is orchestrated in `LangGraphEngine.run_auto()`, not in a standalone graph builder.
