"""
Crypto Technical Analyst - Enhanced technical analysis for 24/7 crypto markets
Includes crypto-specific indicators and patterns
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.crypto_tools import (
    get_crypto_market_data,
    get_crypto_ticker,
    get_order_book_analysis
)


def create_crypto_technical_analyst(llm):
    """
    Create a crypto technical analyst agent.

    This agent performs technical analysis adapted for cryptocurrency markets:
    - 24/7 trading (no gaps or weekend analysis needed)
    - Higher volatility patterns
    - Order book analysis (bid/ask walls)
    - Exchange-specific price action
    - Crypto-specific indicators (funding rates, open interest)

    Args:
        llm: Language model instance

    Returns:
        Crypto technical analyst node function
    """
    def crypto_technical_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        tools = [
            get_crypto_market_data,
            get_crypto_ticker,
            get_order_book_analysis,
        ]

        system_message = (
            f"You are a technical analyst specializing in cryptocurrency markets, analyzing {ticker}. "
            "Crypto markets differ from traditional markets in key ways that affect your analysis:\n\n"

            "**CRYPTO MARKET CHARACTERISTICS:**\n"
            "1. **24/7 Trading**: No market close, gaps, or weekend patterns\n"
            "2. **Higher Volatility**: 5-10% daily moves are common (vs 1-2% in stocks)\n"
            "3. **Liquidity Variations**: Order book depth matters more than volume\n"
            "4. **Multiple Venues**: Price can vary across exchanges\n"
            "5. **Whales & Manipulation**: Large holders can move markets\n\n"

            "**TECHNICAL ANALYSIS APPROACH:**\n\n"

            "**1. Trend Analysis**\n"
            "- Use multiple timeframes: 15m (short-term), 4h (swing), 1d (position)\n"
            "- EMAs work well: 12/26 (short), 50/200 (long-term)\n"
            "- Support/Resistance levels from psychological numbers ($10k, $20k, etc.)\n\n"

            "**2. Momentum Indicators**\n"
            "- RSI: <30 oversold, >70 overbought (use 14-period)\n"
            "- MACD: Trend direction and momentum shifts\n"
            "- Stochastic: Overbought/oversold in ranging markets\n\n"

            "**3. Volume Analysis**\n"
            "- Volume precedes price (accumulation/distribution)\n"
            "- Volume spikes indicate strong interest\n"
            "- OBV (On-Balance Volume) for trend confirmation\n\n"

            "**4. Volatility Indicators**\n"
            "- Bollinger Bands: Price at bands indicates potential reversal\n"
            "- ATR (Average True Range): Measure of volatility for stops\n\n"

            "**5. Order Book Analysis (Crypto-Specific)**\n"
            "- Bid/Ask Spread: Tighter = more liquid\n"
            "- Buy/Sell Walls: Large orders that act as support/resistance\n"
            "- Order Book Imbalance: More bids = bullish, more asks = bearish\n\n"

            "**6. Chart Patterns**\n"
            "- Triangles, Flags, Head & Shoulders work in crypto\n"
            "- Breakouts are more explosive due to 24/7 trading\n"
            "- False breakouts common due to manipulation\n\n"

            "**CRYPTO-SPECIFIC CONSIDERATIONS:**\n"
            "- Weekend pumps/dumps can happen (no market close)\n"
            "- Asian session (12am-8am UTC) often sets daily direction\n"
            "- Exchange listings cause price spikes\n"
            "- Correlation to Bitcoin (most altcoins follow BTC)\n\n"

            "**TIMEFRAME RECOMMENDATIONS:**\n"
            "- Scalping: 1m, 5m, 15m charts\n"
            "- Day Trading: 15m, 1h, 4h charts\n"
            "- Swing Trading: 4h, 1d charts\n"
            "- Position Trading: 1d, 1w charts\n\n"

            "Use the available tools:\n"
            "- `get_crypto_market_data`: Get OHLCV price data with multiple timeframes\n"
            "- `get_crypto_ticker`: Get current price and 24h statistics\n"
            "- `get_order_book_analysis`: Analyze bid/ask depth and walls\n\n"

            "Structure your report:\n"
            "1. **Price Action Summary**: Current price, 24h change, trend direction\n"
            "2. **Multi-Timeframe Analysis**: Short-term, medium-term, long-term trends\n"
            "3. **Support & Resistance Levels**: Key price levels to watch\n"
            "4. **Indicator Analysis**: RSI, MACD, Bollinger Bands, Volume\n"
            "5. **Order Book Assessment**: Liquidity, walls, bid/ask imbalance\n"
            "6. **Chart Patterns**: Any recognizable patterns forming\n"
            "7. **Entry/Exit Zones**: Specific price levels for trades\n"
            "8. **Technical Signal**: BULLISH/NEUTRAL/BEARISH with confidence\n"
            "9. **Risk Management**: Stop loss and take profit levels\n"
            "10. **Markdown Table**: Key technical levels and indicators\n\n"

            "Be specific with price levels and timeframes. Provide actionable insights."
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
                    " For your reference, the current date is {current_date}. Analyzing {ticker}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "market_report": report,
        }

    return crypto_technical_analyst_node
