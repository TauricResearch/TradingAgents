---
description: Run the full TradingAgents multi-agent analysis for a ticker and produce a Buy/Overweight/Hold/Underweight/Sell decision (powered by your Claude subscription, no API-key spend).
argument-hint: <TICKER> [YYYY-MM-DD] [analysts: market,social,news,fundamentals] [debate_rounds] [risk_rounds]
---

You are orchestrating the **TradingAgents** multi-agent pipeline. Data comes from the local `tradingagents-data` MCP server; all agent reasoning is done by you (Claude), so this run costs **no LLM API spend**.

Arguments provided: `$ARGUMENTS`

## Step 0 — Parse arguments and preconditions

1. Parse `$ARGUMENTS`:
   - **ticker** (required, 1st token): e.g. `NVDA`, `0700.HK`, `BTC-USD`. If missing, ask the user for it and stop.
   - **trade_date** (optional, 2nd token, `YYYY-MM-DD`): if omitted, run `date +%F` (Bash) to get today.
   - **analysts** (optional): a comma-separated subset of `market,social,news,fundamentals`. Default: all four.
   - **debate_rounds** (optional int, default `1`) and **risk_rounds** (optional int, default `1`).
   - **asset_type**: infer `crypto` when the ticker looks like a crypto pair (e.g. ends in `-USD` such as `BTC-USD`, `ETH-USD`); otherwise `stock`.
2. Confirm the `tradingagents-data` MCP server is connected (its tools appear as `resolve_instrument`, `get_stock_price_data`, … ). If not, tell the user to run:
   `claude mcp add --transport stdio tradingagents-data --scope project -- tradingagents-data-mcp`
   and stop.

## Step 1 — Reflect on prior decisions (best-effort, skip on any error)

1. Run: `python -m tradingagents.mcp.memory_cli pending <TICKER>` → a JSON list of prior unresolved decisions for this ticker.
2. For each pending `{date}`: call the MCP tool `get_realized_return(ticker=<TICKER>, trade_date=<date>)`.
   - If `available` is `false`, skip it (prices aren't out yet).
   - If `available` is `true`, write a concise one-paragraph **reflection**: did the prior call look right given the realized `raw_return` and `alpha_return` vs the benchmark? What would you adjust? Save it to a temp file and run:
     `python -m tradingagents.mcp.memory_cli resolve <TICKER> <date> --raw <raw_return> --alpha <alpha_return> --holding <holding_days> --reflection-file <tmpfile>`
3. This step is optional — if anything fails, note it briefly and continue.

## Step 2 — Load past context

Run: `python -m tradingagents.mcp.memory_cli get-context <TICKER>` and keep the output as `past_context` (may be empty).

## Step 3 — Run the workflow

Call the **Workflow** tool with the saved `trade-decision` workflow:

```
Workflow({
  name: "trade-decision",
  args: {
    ticker: "<TICKER>",
    trade_date: "<YYYY-MM-DD>",
    analysts: [<selected analysts>],
    debate_rounds: <int>,
    risk_rounds: <int>,
    asset_type: "<stock|crypto>",
    past_context: "<past_context from Step 2>"
  }
})
```

Wait for it to finish. The result is an object with `decision`, `final_trade_decision`, `reports`, `investment_plan`, `trader_investment_plan`, `investment_debate`, `risk_debate`.

## Step 4 — Persist the result

1. **Full-state log** — write a JSON file to `~/.tradingagents/logs/<TICKER>/TradingAgentsStrategy_logs/full_states_log_<DATE>.json` (create dirs as needed) with these keys, taken from the workflow result:
   `company_of_interest`, `trade_date`, `market_report`, `sentiment_report`, `news_report`, `fundamentals_report`, `investment_plan`, `trader_investment_decision`, `investment_debate_state` (the bull/bear debate text), `risk_debate_state` (the risk debate text), `final_trade_decision`.
2. **Decision log** — write the workflow's `final_trade_decision` to a temp file, then run:
   `python -m tradingagents.mcp.memory_cli store <TICKER> <DATE> --decision-file <tmpfile>`
   (this appends a pending entry that the next run for this ticker will reflect on).

## Step 5 — Report to the user

Present, concisely:
- The headline **decision** (the 5-tier rating) for `<TICKER>` on `<DATE>`.
- The Portfolio Manager's `final_trade_decision` (executive summary + thesis).
- A one-line pointer to the saved full-state log path.
- A reminder that this is research output, **not** financial advice.
