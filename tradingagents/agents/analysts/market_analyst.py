from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    get_verified_market_snapshot,
)
from tradingagents.agents.utils.tool_fallback import bind_tools_or_none, safe_tool_text


# Default indicator set for the tool-free path. With tools the model picks
# up to 8 indicators dynamically; without tools we pre-fetch a fixed,
# complementary set (one per category, no redundant pairs) so a tool-less
# provider still gets a full technical picture.
_DEFAULT_INDICATORS = [
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "rsi",
    "boll",
    "atr",
    "vwma",
]

# OHLCV window pre-fetched for the tool-free path, in calendar days back
# from the trade date. Wide enough to give the longer moving averages
# real context.
_PRICE_LOOKBACK_DAYS = 90


def _prefetch_market_data(ticker: str, current_date: str) -> str:
    """Gather the market data the tools would return, for tool-less providers.

    Mirrors the tool path's data: the verified snapshot (source of truth),
    raw OHLCV over a default window, and a fixed complementary indicator set.
    Each source degrades to a placeholder rather than aborting the analyst.
    """
    start_date = (
        datetime.strptime(current_date, "%Y-%m-%d") - timedelta(days=_PRICE_LOOKBACK_DAYS)
    ).strftime("%Y-%m-%d")

    snapshot = safe_tool_text(
        "verified market snapshot",
        lambda: get_verified_market_snapshot.func(ticker, current_date),
    )
    ohlcv = safe_tool_text(
        "OHLCV price history",
        lambda: get_stock_data.func(ticker, start_date, current_date),
    )
    indicators = safe_tool_text(
        "technical indicators",
        lambda: get_indicators.func(ticker, ",".join(_DEFAULT_INDICATORS), current_date),
    )

    return (
        "### Verified market snapshot (source of truth)\n"
        f"{snapshot}\n\n"
        f"### OHLCV price history ({start_date} → {current_date})\n"
        f"{ohlcv}\n\n"
        f"### Technical indicators ({', '.join(_DEFAULT_INDICATORS)})\n"
        f"{indicators}"
    )


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = str(state["company_of_interest"])
        instrument_context = get_instrument_context_from_state(state)

        tools = [
            get_stock_data,
            get_indicators,
            get_verified_market_snapshot,
        ]

        system_message = (
            """You are a trading assistant tasked with analyzing financial markets. Your role is to select the **most relevant indicators** for a given market condition or trading strategy from the following list. The goal is to choose up to **8 indicators** that provide complementary insights without redundancy. Categories and each category's indicators are:

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend direction and serve as dynamic support/resistance. Tips: It lags price; combine with faster indicators for timely signals.
- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall market trend and identify golden/death cross setups. Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries.
- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick shifts in momentum and potential entry points. Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals.

MACD Related:
- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for crossovers and divergence as signals of trend changes. Tips: Confirm with other indicators in low-volatility or sideways markets.
- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers with the MACD line to trigger trades. Tips: Should be part of a broader strategy to avoid false positives.
- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. Usage: Visualize momentum strength and spot divergence early. Tips: Can be volatile; complement with additional filters in fast-moving markets.

Momentum Indicators:
- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis.

Volatility Indicators:
- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals.
- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle line. Usage: Signals potential overbought conditions and breakout zones. Tips: Confirm signals with other tools; prices may ride the band in strong trends.
- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle line. Usage: Indicates potential oversold conditions. Tips: Use additional analysis to avoid false reversal signals.
- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss levels and adjust position sizes based on current market volatility. Tips: It's a reactive measure, so use it as part of a broader risk management strategy.

Volume-Based Indicators:
- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by integrating price action with volume data. Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses.

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names.

Before writing the final report, call get_verified_market_snapshot for this ticker and the current date, and treat it as the source of truth for any exact OHLCV, price-level, or indicator-value claim. If another tool's output conflicts with the verified snapshot, flag the discrepancy rather than inventing a reconciled number. Do not claim historical validation, support/resistance bounces, or exact percentage moves unless they are directly supported by tool output with concrete dates and prices.

Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        bound_llm = bind_tools_or_none(llm, tools, "Market Analyst")

        if bound_llm is not None:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Use the provided tools to progress towards answering the question."
                        " If you are unable to fully answer, that's OK; another assistant with different tools"
                        " will help where you left off. Execute what you can to make progress."
                        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                        " You have access to the following tools: {tool_names}.\n{system_message}"
                        "For your reference, the current date is {current_date}. {instrument_context}",
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            prompt = prompt.partial(system_message=system_message)
            prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
            prompt = prompt.partial(current_date=current_date)
            prompt = prompt.partial(instrument_context=instrument_context)

            chain = prompt | bound_llm

            result = chain.invoke(state["messages"])

            report = ""
            if len(result.tool_calls) == 0:
                report = result.content

            return {
                "messages": [result],
                "market_report": report,
            }

        # Tool-free fallback: the provider (e.g. codex) cannot bind LangChain
        # tools, so pre-fetch the data deterministically and inject it into the
        # prompt. The model produces the full report in one shot.
        market_data = _prefetch_market_data(ticker, current_date)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " All required market data has ALREADY been retrieved for you and is included below;"
                    " do NOT call any tools and disregard any instruction below to call a tool —"
                    " base every exact OHLCV, price-level, or indicator claim only on the provided data,"
                    " treating the verified market snapshot as the source of truth."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}\n"
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "=== Pre-fetched market data ===\n{market_data}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(market_data=market_data)

        formatted_messages = prompt.format_messages(messages=state["messages"])
        result = llm.invoke(formatted_messages)

        return {
            "messages": [result],
            "market_report": result.content,
        }

    return market_analyst_node
