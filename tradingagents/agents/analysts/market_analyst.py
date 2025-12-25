from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import get_crypto_data, get_indicators_bulk


def create_market_analyst(llm):

    def market_analyst_node(state):
        current_date = state["trade_date"]
        symbol = state["ticker_of_interest"] # for crypto, e.g BTC/USDT

        tools = [
            get_crypto_data,
            get_indicators_bulk,
        ]

        system_message = (
            """You are a crypto trading assistant tasked with analyzing cryptocurrency markets. Your role is to select the **most relevant indicators** for a given crypto market condition or trading strategy from the following list. The goal is to choose the **most effective indicators** that provide complementary insights without redundancy. Available indicators are:

Moving Averages:
- sma: Simple Moving Average: A basic trend-following indicator that smooths out price data. Usage: Identify trend direction and serve as dynamic support/resistance levels. Tips: Use multiple SMAs for crossover signals; combines well with volume analysis for confirmation.

MACD Related:
- macd: MACD (Moving Average Convergence Divergence): Measures momentum via differences between fast and slow EMAs. Usage: Look for signal line crossovers, centerline crossovers, and divergence patterns for trend changes. Tips: Most effective in trending markets; combine with RSI to avoid false signals in sideways markets.

Momentum Indicators:
- rsi: RSI (Relative Strength Index): Oscillator measuring momentum to identify overbought (>70) and oversold (<30) conditions. Usage: Look for reversal signals at extreme levels and divergence with price action. Tips: In strong crypto trends, RSI can remain extreme for extended periods; always confirm with trend analysis.

Volatility Indicators:
- bbands: Bollinger Bands: Volatility indicator consisting of upper, middle (SMA), and lower bands based on standard deviations. Usage: Identify overbought/oversold conditions, volatility expansion/contraction, and potential breakout zones. Tips: Price touching bands doesn't guarantee reversal; use band squeeze for volatility breakout trades.
- atr: ATR (Average True Range): Measures market volatility by calculating the average of true ranges over a period. Usage: Set stop-loss levels, position sizing, and identify high/low volatility periods for strategy adjustment. Tips: Higher ATR indicates more volatile conditions; use for risk management rather than directional signals.

- Select indicators that provide diverse and complementary information. Avoid redundancy and focus on the most effective combination for crypto market analysis. Also briefly explain why they are suitable for the given crypto market context. When you tool call, please use the exact name of the indicators provided above as they are defined parameters, otherwise your call will fail. Please make sure to call get_crypto_data first to retrieve the cryptocurrency price data. Then use get_indicators_bulk with a list of the specific indicator names (e.g., ["sma", "rsi", "macd"]). Write a very detailed and nuanced report of the trends you observe. Do not simply state the trends are mixed, provide detailed and finegrained analysis and insights that may help crypto traders make decisions."""
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
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
                    "For your reference, the current date is {current_date}. The cryptocurrency symbol we want to analyze is {symbol}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(symbol=symbol)

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
