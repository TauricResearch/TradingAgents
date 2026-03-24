from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    format_prefetched_context,
    prefetch_tools_parallel,
)
from tradingagents.agents.utils.core_stock_tools import get_stock_data
from tradingagents.agents.utils.fundamental_data_tools import get_macro_regime
from tradingagents.agents.utils.technical_indicators_tools import get_indicators
from tradingagents.agents.utils.tool_runner import run_tool_loop
from tradingagents.dataflows.config import get_config


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        instrument_context = build_instrument_context(ticker)

        # ── Pre-fetch macro regime and stock price data in parallel ──────────
        # Both are always required; fetching them upfront removes 2 LLM round-
        # trips and lets the LLM focus its single tool-call budget on choosing
        # the right indicators based on the macro regime it sees.
        trade_date = datetime.strptime(current_date, "%Y-%m-%d")
        stock_start = (trade_date - timedelta(days=365)).strftime("%Y-%m-%d")

        prefetched = prefetch_tools_parallel(
            [
                {
                    "tool": get_macro_regime,
                    "args": {"curr_date": current_date},
                    "label": "Macro Regime Classification",
                },
                {
                    "tool": get_stock_data,
                    "args": {
                        "symbol": ticker,
                        "start_date": stock_start,
                        "end_date": current_date,
                    },
                    "label": "Stock Price Data",
                },
            ]
        )
        prefetched_context = format_prefetched_context(prefetched)

        # ── Only get_indicators remains iterative ─────────────────────────────
        # The LLM reads the macro regime from the pre-loaded context and decides
        # which indicators are most relevant before calling get_indicators.
        tools = [get_indicators]

        system_message = (
            "You are a trading assistant tasked with analyzing financial markets.\n\n"
            "## Pre-loaded Data\n\n"
            "The macro regime classification and recent stock price data for the company under "
            "analysis have already been fetched and are provided in the **Pre-loaded Context** "
            "section below. "
            "Do NOT call `get_macro_regime` or `get_stock_data` — the data is already available.\n\n"
            "## Your Task\n\n"
            "1. Read the macro regime classification from the pre-loaded context. "
            "The macro regime has been classified above — use it to weight your indicator "
            "choices before calling `get_indicators`. For example, in risk-off environments "
            "favour ATR, Bollinger Bands, and long-term SMAs; in risk-on environments favour "
            "momentum indicators like MACD and short EMAs.\n\n"
            "2. Select the **most relevant indicators** for the given market condition from "
            "the list below. Choose up to **8 indicators** that provide complementary insights "
            "without redundancy.\n\n"
            "Moving Averages:\n"
            "- close_50_sma: 50 SMA: A medium-term trend indicator. Usage: Identify trend "
            "direction and serve as dynamic support/resistance. Tips: It lags price; combine "
            "with faster indicators for timely signals.\n"
            "- close_200_sma: 200 SMA: A long-term trend benchmark. Usage: Confirm overall "
            "market trend and identify golden/death cross setups. Tips: It reacts slowly; best "
            "for strategic trend confirmation rather than frequent trading entries.\n"
            "- close_10_ema: 10 EMA: A responsive short-term average. Usage: Capture quick "
            "shifts in momentum and potential entry points. Tips: Prone to noise in choppy "
            "markets; use alongside longer averages for filtering false signals.\n\n"
            "MACD Related:\n"
            "- macd: MACD: Computes momentum via differences of EMAs. Usage: Look for "
            "crossovers and divergence as signals of trend changes. Tips: Confirm with other "
            "indicators in low-volatility or sideways markets.\n"
            "- macds: MACD Signal: An EMA smoothing of the MACD line. Usage: Use crossovers "
            "with the MACD line to trigger trades. Tips: Should be part of a broader strategy "
            "to avoid false positives.\n"
            "- macdh: MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. Tips: Can be "
            "volatile; complement with additional filters in fast-moving markets.\n\n"
            "Momentum Indicators:\n"
            "- rsi: RSI: Measures momentum to flag overbought/oversold conditions. Usage: "
            "Apply 70/30 thresholds and watch for divergence to signal reversals. Tips: In "
            "strong trends, RSI may remain extreme; always cross-check with trend analysis.\n\n"
            "Volatility Indicators:\n"
            "- boll: Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. Tips: Combine with the "
            "upper and lower bands to effectively spot breakouts or reversals.\n"
            "- boll_ub: Bollinger Upper Band: Typically 2 standard deviations above the middle "
            "line. Usage: Signals potential overbought conditions and breakout zones. Tips: "
            "Confirm signals with other tools; prices may ride the band in strong trends.\n"
            "- boll_lb: Bollinger Lower Band: Typically 2 standard deviations below the middle "
            "line. Usage: Indicates potential oversold conditions. Tips: Use additional "
            "analysis to avoid false reversal signals.\n"
            "- atr: ATR: Averages true range to measure volatility. Usage: Set stop-loss "
            "levels and adjust position sizes based on current market volatility. Tips: It's "
            "a reactive measure, so use it as part of a broader risk management strategy.\n\n"
            "Volume-Based Indicators:\n"
            "- vwma: VWMA: A moving average weighted by volume. Usage: Confirm trends by "
            "integrating price action with volume data. Tips: Watch for skewed results from "
            "volume spikes; use in combination with other volume analyses.\n\n"
            "3. Select indicators that provide diverse and complementary information. Avoid "
            "redundancy (e.g., do not select both rsi and stochrsi). Briefly explain why each "
            "chosen indicator is suitable for the current macro context. When calling "
            "`get_indicators`, use the exact indicator names listed above — they are defined "
            "parameters and any deviation will cause the call to fail.\n\n"
            "4. Write a very detailed and nuanced report of the trends you observe. Provide "
            "specific, actionable insights with supporting evidence to help traders make "
            "informed decisions. Make sure to append a Markdown table at the end of the report "
            "to organise key points, making it easy to read."
        )

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
                    "For your reference, the current date is {current_date}. {instrument_context}\n\n"
                    "## Pre-loaded Context\n\n{prefetched_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)
        prompt = prompt.partial(prefetched_context=prefetched_context)

        chain = prompt | llm.bind_tools(tools)

        result = run_tool_loop(chain, state["messages"], tools)

        report = result.content or ""
        macro_regime_report = ""

        # Extract macro regime section if present (from pre-loaded context or report)
        regime_data = prefetched.get("Macro Regime Classification", "")
        if regime_data and not regime_data.startswith("[Error"):
            macro_regime_report = regime_data
        elif report and (
            "Macro Regime Classification" in report
            or "RISK-ON" in report.upper()
            or "RISK-OFF" in report.upper()
            or "TRANSITION" in report.upper()
        ):
            macro_regime_report = report

        return {
            "messages": [result],
            "market_report": report,
            "macro_regime_report": macro_regime_report,
        }

    return market_analyst_node
