from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
    supports_tool_calls,
)


# All indicator keys the market analyst may select from.
_ALL_INDICATORS = (
    "close_50_sma", "close_200_sma", "close_10_ema",
    "macd", "macds", "macdh",
    "rsi",
    "boll", "boll_ub", "boll_lb", "atr",
    "vwma",
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        if supports_tool_calls(llm):
            return _tool_call_path(llm, state, current_date, ticker, instrument_context)
        return _prefetch_path(llm, state, current_date, ticker, instrument_context)

    return market_analyst_node


# ── Tool-call path (API providers) ────────────────────────────────────────

def _tool_call_path(llm, state, current_date, ticker, instrument_context):
    """Original flow: bind_tools → LLM selects and calls tools."""
    tools = [get_stock_data, get_indicators]

    system_message = _base_system_message()

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

    chain = prompt | llm.bind_tools(tools)
    result = chain.invoke(state["messages"])

    report = ""
    if len(result.tool_calls) == 0:
        report = result.content

    return {
        "messages": [result],
        "market_report": report,
    }


# ── Pre-fetch path (CLI provider) ────────────────────────────────────────

def _prefetch_path(llm, state, current_date, ticker, instrument_context):
    """Pre-fetch all data and inject into prompt (no tool-calling needed)."""
    start_date = _seven_days_back(current_date)

    # Fetch stock price data
    try:
        stock_data = get_stock_data.func(ticker, start_date, current_date)
    except Exception as e:
        stock_data = f"<unavailable: {e}>"

    # Fetch all indicators — let the LLM pick what's relevant
    indicator_blocks: list[str] = []
    for ind in _ALL_INDICATORS:
        try:
            result = get_indicators.func(ticker, ind, current_date, 30)
            indicator_blocks.append(f"### {ind}\n{result}")
        except Exception as e:
            indicator_blocks.append(f"### {ind}\n<unavailable: {e}>")

    indicators_text = "\n\n".join(indicator_blocks)

    system_message = _build_prefetch_system_message(
        ticker=ticker,
        start_date=start_date,
        end_date=current_date,
        stock_data=stock_data,
        indicators_text=indicators_text,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful AI assistant, collaborating with other assistants."
                " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                "\n{system_message}\n"
                "For your reference, the current date is {current_date}. {instrument_context}",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    prompt = prompt.partial(system_message=system_message)
    prompt = prompt.partial(current_date=current_date)
    prompt = prompt.partial(instrument_context=instrument_context)

    chain = prompt | llm
    result = chain.invoke(state["messages"])

    return {
        "messages": [result],
        "market_report": result.content,
    }


# ── System messages ──────────────────────────────────────────────────────

def _base_system_message() -> str:
    """System message for the tool-calling path (unchanged from original)."""
    return (
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

- Select indicators that provide diverse and complementary information. Avoid redundancy (e.g., do not select both rsi and stochrsi). Also briefly explain why they are suitable for the given market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_stock_data first to retrieve the CSV that is needed to generate indicators. Then use get_indicators with the specific indicator names. Write a very detailed and nuanced report of the trends you observe. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."""
        + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
        + get_language_instruction()
    )


def _build_prefetch_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    stock_data: str,
    indicators_text: str,
) -> str:
    """System message for the pre-fetch path with data already injected."""
    return f"""You are a trading assistant tasked with analyzing financial markets for {ticker} over the period {start_date} to {end_date}.

All market data has been pre-fetched and is included below. Select the **most relevant indicators** (up to 8) from the data for the current market context. Provide diverse and complementary insights without redundancy.

## Stock Price Data (OHLCV)

<start_of_stock_data>
{stock_data}
<end_of_stock_data>

## Technical Indicators

All available indicators are below. Select the most relevant ones for your analysis and explain why they are suitable for the current market conditions.

<start_of_indicators>
{indicators_text}
<end_of_indicators>

## Instructions

1. Analyze the stock price data for trends, support/resistance, and volume patterns.
2. Select up to 8 of the most relevant indicators from the data above.
3. For each selected indicator, explain why it is suitable for the current market context.
4. Write a very detailed and nuanced report of the trends you observe.
5. Provide specific, actionable insights with supporting evidence to help traders make informed decisions.
6. Append a Markdown table at the end summarizing key points.

{get_language_instruction()}"""
