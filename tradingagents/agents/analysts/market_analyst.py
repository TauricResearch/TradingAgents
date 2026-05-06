"""Market Analyst — BTC technical analysis on Coinbase candles.

Coinbase BTC-USD is the settlement reference for Kalshi BTC daily
contracts, so the price feed here aligns with how the contract resolves.
The analyst picks 5–8 complementary indicators across moving averages,
MACD, RSI, Bollinger, ATR, and VWMA to characterize the daily-horizon
setup heading into the contract close.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_indicators,
    get_language_instruction,
    get_stock_data,
)


def create_market_analyst(llm):
    def market_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_stock_data, get_indicators]

        system_message = (
            """You are the Market Analyst on a Kalshi prediction-market research desk. The contract under analysis settles against the underlying asset (BTC for v1) on the Coinbase BTC-USD index. Your job is to characterize the **daily-horizon technical setup** so the bull/bear researchers can debate whether YES or NO is mispriced.

Select up to **8 complementary indicators** from the following list — avoid redundancy (e.g. don't pick both rsi and stochrsi). Use `get_stock_data` first to load Coinbase OHLCV, then call `get_indicators` once per indicator name.

Moving Averages:
- close_50_sma — medium-term trend; dynamic support/resistance.
- close_200_sma — long-term benchmark; golden/death-cross signals.
- close_10_ema — responsive short-term momentum.

MACD family:
- macd — momentum from EMA differences; crossovers + divergence.
- macds — signal line; trade triggers vs the macd line.
- macdh — histogram; visualize momentum strength.

Momentum:
- rsi — overbought (>70) / oversold (<30) and divergence.

Volatility:
- boll — Bollinger middle (20 SMA).
- boll_ub — upper band (overbought / breakout zones).
- boll_lb — lower band (oversold / capitulation zones).
- atr — Average True Range for stop placement and stake risk math.

Volume:
- vwma — volume-weighted moving average; trend-confirmation with flow.

Use the exact indicator names above when calling `get_indicators`. Write a detailed, nuanced report tying each indicator's reading to a directional implication for the contract under analysis. Highlight conflicting signals where they exist — institutional-grade analysis is honest about ambiguity."""
            + " Append a Markdown table at the end summarizing the indicators, their latest values, and the implied directional bias."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant collaborating with other analysts on a Kalshi "
                    "prediction-market research desk. Use the provided tools to progress towards "
                    "answering the question. If you or any other assistant has the FINAL TRANSACTION "
                    "PROPOSAL: **YES/NO/PASS** or deliverable, prefix your response with FINAL "
                    "TRANSACTION PROPOSAL: **YES/NO/PASS** so the team knows to stop. "
                    "You have access to the following tools: {tool_names}.\n{system_message}"
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

    return market_analyst_node
