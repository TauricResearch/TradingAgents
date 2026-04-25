# Flow: Binance Kline API → Indicators → Claude Prompt

This document traces the end-to-end path taken when the market analyst asks Claude
to reason about a symbol. It walks from the HTTP call against Binance, through the
pandas / stockstats pipeline that derives technical indicators, and finally into
the system prompt that Claude receives.

The relevant files are:

- `tradingagents/dataflows/binance.py` — REST client, pagination, indicator calc.
- `tradingagents/dataflows/binance_models.py` — Pydantic/dataclass DTOs.
- `tradingagents/dataflows/stockstats_utils.py` — dataframe normalisation.
- `tradingagents/dataflows/interface.py` — vendor routing.
- `tradingagents/agents/utils/technical_indicators_tools.py` — LangChain tool wrapper.
- `tradingagents/agents/analysts/market_analyst.py` — Claude prompt assembly.

## High-level flow

```mermaid
flowchart TD
    A[Market Analyst Node<br/>market_analyst_node] -->|bind_tools| B[Claude LLM]
    B -->|tool_call: get_indicators| C[LangChain @tool<br/>technical_indicators_tools.get_indicators]
    C -->|route_to_vendor| D[interface.route_to_vendor]
    D -->|vendor = binance| E[binance.get_binance_indicators_window]
    E -->|KlineParams| F[_fetch_klines_range]
    F -->|GET /fapi/v1/klines| G[Binance REST API]
    G -->|raw array rows| F
    F -->|list of Kline| E
    E -->|_klines_to_dataframe| H[pandas DataFrame]
    H -->|_clean_dataframe + wrap| I[stockstats wrapper]
    I -->|df[indicator]| J[indicator series]
    J -->|format per-day lines| K[Markdown string]
    K -->|tool result| B
    B -->|final content| L[state.market_report]
```

## Step 1 — The agent decides to call a tool

`create_market_analyst(llm)` builds a LangGraph node that exposes three tools to
Claude: `get_stock_data`, `get_indicators`, and `get_fibonacci_retracement`. The
node composes a `ChatPromptTemplate` whose system message instructs Claude to
pick up to eight complementary indicators from a fixed menu (SMA family, MACD
family, RSI, Bollinger Bands, ATR, VWMA, MFI, plus Fibonacci retracement) and to
call `get_stock_data` first, then `get_fibonacci_retracement`, then invoke
`get_indicators` once per chosen indicator. The prompt is partially filled with
the run's `current_date`, the instrument context, and the tool names before
being piped into `llm.bind_tools(tools)`. When Claude responds with
`tool_calls`, LangChain dispatches to the matching `@tool` function.

## Step 2 — Tool wrapper normalises the request

`technical_indicators_tools.get_indicators` is a thin shim. It accepts a
`symbol`, an `indicator`, `curr_date`, and `look_back_days`. Because LLMs
occasionally emit several indicator names in one call (comma-separated), the
wrapper splits the string and invokes `route_to_vendor` once per indicator,
joining the results with a blank line. Every call ends up in
`dataflows.interface.route_to_vendor("get_indicators", …)`.

## Step 3 — Vendor routing

`route_to_vendor` in `interface.py` first maps the method name to a
`TOOLS_CATEGORIES` bucket (here `technical_indicators`). It then reads
`config["tool_vendors"]` / `config["data_vendors"]` to find the configured
primary vendor, falling back to `binance`. A fallback chain is built so that if
the primary raises `AlphaVantageRateLimitError` the next vendor is tried.
`VENDOR_METHODS["get_indicators"]["binance"]` resolves to
`get_binance_indicators_window`.

## Step 4 — Binance kline request

`get_binance_indicators_window(symbol, indicator, curr_date, look_back_days,
interval=None)` does four things:

It validates the indicator against `INDICATOR_DESCRIPTIONS` and raises a
`ValueError` on unknown names, so Claude gets fast feedback instead of silent
garbage. It honours user-configured date overrides from `config.kline_start_date`
and `config.kline_end_date`, otherwise it computes a one-year warm-up window so
indicators like the 89 SMA have enough history to stabilise. It resolves the
kline interval via `_resolve_kline_interval`, preferring the explicit argument,
then `config.kline_interval`, then defaulting to `KlineInterval.ONE_DAY`. It
builds a `KlineParams` dataclass containing `symbol`, `interval`, `start_time`,
`end_time`, and `limit` (defaulting to `BINANCE_KLINE_LIMIT`, 200).

`_fetch_klines_range(params)` issues `GET https://fapi.binance.com/fapi/v1/klines`
with the query `{symbol, interval, limit}` plus optional `startTime`. Each call
goes through `_get`, which wraps `requests.get` with an exponential back-off
retry loop for HTTP 429. The raw response is a list of lists; each row is
converted into a `Kline` dataclass via `Kline.from_raw`, which parses the
positional array (open_time, O, H, L, C, volume, close_time, quote_asset_volume,
number_of_trades, taker_buy_base_volume, taker_buy_quote_volume). When the
returned batch is shorter than `limit` or the last `close_time` exceeds
`end_time`, pagination stops; otherwise the loop advances
`startTime = last_close_time + 1` and requests the next page.

## Step 5 — DataFrame assembly

`_klines_to_dataframe` projects the `Kline` list into a pandas DataFrame with
the canonical columns `Date`, `Open`, `High`, `Low`, `Close`, `Volume`. `Date`
is derived from `open_time / 1000` in UTC and formatted to `YYYY-MM-DD` before
being re-parsed with `pd.to_datetime`, which guarantees consistent dtype for
downstream joins. Empty responses yield an empty DataFrame rather than raising,
so the caller can surface a friendly "No data available" message.

## Step 6 — Indicator calculation with stockstats

The DataFrame is passed through `_clean_dataframe` (lower-cases columns, sorts
by date, drops duplicates) and then wrapped by `stockstats.wrap(df)`. Stockstats
exposes indicators as virtual columns that are computed lazily the first time
they are accessed, so `df[indicator]` is the line that actually runs the math
(SMA/EMA folds, MACD subtraction, RSI gain/loss averaging, Bollinger variance,
ATR true-range, VWMA, MFI typical-price flows, etc.). Because the fetch window
spans one year by default, the indicator has plenty of warm-up before the
reporting window begins, which avoids the "NaN until period-n" artifact that
otherwise trips up short look-backs.

## Step 7 — Windowed, human-readable serialisation

The function then builds a `date → value` dictionary from the DataFrame and
walks day-by-day from `curr_date` backwards `look_back_days` calendar days.
Non-trading days (weekends, holidays, venue downtime) are labelled
`N/A: Not a trading day`, while NaN values are labelled `N/A`. The final return
string starts with a Markdown header listing the indicator and window, followed
by one `YYYY-MM-DD: value` line per day, and ends with the indicator's short
description from `INDICATOR_DESCRIPTIONS` so Claude has in-context guidance on
what the number means. This is the payload that flows back through LangChain
as the tool's result.

## Step 8 — The result lands back in the prompt

LangGraph appends the tool result to `state["messages"]` as a `ToolMessage` and
re-invokes the market analyst chain. On the next iteration Claude sees all
prior tool outputs — the kline CSV from `get_stock_data`, the Fibonacci levels
from `get_fibonacci_retracement`, and every `get_indicators` window — and is
instructed by the system message to synthesise them into a detailed Markdown
report that ends with a summary table. Because the system message forbids
redundant picks (for example RSI plus StochRSI) and enumerates each indicator's
"Usage / Tips" rubric, the final report is grounded in the precise numbers that
the pipeline just computed rather than in Claude's priors about the symbol.

## Sequence summary

1. `market_analyst_node` binds tools and sends the system prompt to Claude.
2. Claude emits a `tool_call` for `get_indicators` (plus siblings).
3. `technical_indicators_tools.get_indicators` splits multi-indicator strings
   and calls `route_to_vendor`.
4. `interface.route_to_vendor` selects the vendor (`binance` by default) and
   invokes `get_binance_indicators_window`.
5. `get_binance_indicators_window` resolves interval + dates and calls
   `_fetch_klines_range`.
6. `_fetch_klines_range` paginates `GET /fapi/v1/klines` with 429 back-off and
   returns `list[Kline]`.
7. `_klines_to_dataframe` produces an OHLCV DataFrame.
8. `_clean_dataframe` + `stockstats.wrap` compute the indicator column.
9. The function emits a Markdown window of values plus an indicator
   description.
10. LangGraph feeds the string back to Claude, which writes the final
    market-analysis report into `state["market_report"]`.

## Failure modes worth knowing

Binance rate-limits are retried with exponential back-off up to
`_MAX_RETRIES = 3`; after that the exception propagates and `route_to_vendor`
falls through to `alpha_vantage`. Unknown indicator names raise a `ValueError`
before any HTTP is issued — this is deliberate, because wasted tool calls are
expensive and Claude gets a clear error message to recover from. Empty kline
ranges short-circuit to a friendly "No data available" string so the LLM can
decide whether to retry with different dates rather than hallucinating numbers.
Finally, user-configured `kline_start_date` / `kline_end_date` override the
agent's inferred dates, which is critical for deterministic back-tests.
