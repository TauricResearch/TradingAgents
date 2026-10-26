---
name: research
description: Research stocks and crypto with TradingAgents. Use when the user asks about a ticker, market data, technicals, fundamentals, news, insider activity, macro indicators, prediction markets, or a structured investment analysis or backtest.
---

# TradingAgents research

The TradingAgents MCP server has three modes.

## 1. Quick data lookup

Use the data tools directly and synthesize the answer yourself:

- `get_stock_data`
- `get_technical_indicators`
- `get_fundamentals`
- `get_financial_statement`
- `get_news`
- `get_global_news`
- `get_insider_transactions`
- `get_macro_indicators`
- `get_prediction_markets`

Always state the ticker, date range, and data source. Do not invent prices or
dates. If a tool fails, report the failure instead of guessing.

## 2. Claude-driven research

This mode uses Claude Code's own model and your Claude subscription; the
TradingAgents server only supplies data. When the user wants an analysis, call
`get_server_info` first. If `analysis_ready` is false, run this workflow
yourself with the data tools:

1. **Market:** price trend, volume, moving averages, RSI/MACD, support and
   resistance.
2. **News and sentiment:** company news, global news, and prediction-market
   odds where relevant.
3. **Fundamentals:** valuation, margins, growth, and balance sheet for stocks.
4. **Macro:** rates, inflation, growth, and sector context.
5. **Bull and bear cases:** each with evidence, catalysts, and what would
   invalidate it.
6. **Risk review:** aggressive, neutral, and conservative perspectives.
7. **Decision:** Buy, Hold, or Sell, with confidence, time horizon, and the
   evidence that would change the call.

Use only the data the tools return. Say what is missing. End with "This is
research, not financial, investment, or trading advice."

## 3. Full multi-agent analysis

`analyze_ticker` and `run_backtest` run TradingAgents' own multi-agent graph.
They need a provider for that graph: an API key in the environment or `.env`, a
ChatGPT plan sign-in, or Ollama. They cannot reuse Claude Code's subscription.

If `analysis_ready` is true, use the job workflow:

`analyze_ticker` returns a `job_id` immediately. Poll `get_job_status` with
`wait_seconds` up to 300 until the status is `succeeded` or `failed`, then call
`get_job_result`. Use `get_analysis_report` for one report section.
`run_backtest` uses the same polling pattern.
