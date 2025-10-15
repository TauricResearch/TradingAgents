"""
On-Chain Analyst - Crypto-specific agent for blockchain data analysis
Analyzes network health, whale activity, and exchange flows
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.crypto_tools import (
    get_onchain_metrics,
    get_exchange_flows,
    get_whale_activity
)


def create_onchain_analyst(llm):
    """
    Create an on-chain analyst agent for cryptocurrency analysis.

    This agent specializes in blockchain-level data analysis:
    - Network health metrics (active addresses, transactions)
    - Exchange flow analysis (inflows/outflows)
    - Whale wallet tracking (large holder movements)
    - On-chain valuation metrics (NVT, MVRV ratios)

    Args:
        llm: Language model instance

    Returns:
        On-chain analyst node function
    """
    def onchain_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]  # For crypto, this will be the asset symbol

        # Determine if this is a crypto asset
        crypto_symbols = ['BTC', 'ETH', 'SOL', 'ADA', 'AVAX', 'DOT', 'MATIC', 'ARB', 'OP']
        is_crypto = any(symbol in ticker.upper() for symbol in crypto_symbols)

        if not is_crypto:
            # If not crypto, return empty report
            return {
                "messages": [],
                "onchain_report": "On-chain analysis not applicable for non-crypto assets.",
            }

        # Extract crypto symbol (e.g., BTC from BTC/USDT)
        crypto_symbol = ticker.split('/')[0] if '/' in ticker else ticker.upper()

        tools = [
            get_onchain_metrics,
            get_exchange_flows,
            get_whale_activity,
        ]

        system_message = (
            f"You are an on-chain analyst specializing in blockchain data analysis for cryptocurrency {crypto_symbol}. "
            "Your role is to analyze on-chain metrics to identify accumulation/distribution patterns, "
            "network health trends, and whale activity that may indicate future price movements.\n\n"

            "Focus on these key areas:\n"
            "1. **Network Health**: Active addresses, transaction volume, network growth\n"
            "2. **Exchange Flows**: Net inflows (bearish) vs outflows (bullish)\n"
            "3. **Whale Activity**: Large holder accumulation or distribution patterns\n"
            "4. **Valuation Metrics**: NVT ratio, MVRV ratio, realized price comparisons\n"
            "5. **Supply Profitability**: Percentage of supply in profit/loss\n\n"

            "Interpretation Guidelines:\n"
            "- **Bullish Signals**: Net exchange outflows, whale accumulation, rising active addresses, MVRV < 1.5\n"
            "- **Bearish Signals**: Net exchange inflows, whale distribution, declining network activity, MVRV > 3.0\n"
            "- **Neutral**: Mixed signals, low volatility in on-chain metrics\n\n"

            "Use the available tools:\n"
            "- `get_onchain_metrics`: Get comprehensive network health and valuation data\n"
            "- `get_exchange_flows`: Analyze exchange inflows/outflows (key sentiment indicator)\n"
            "- `get_whale_activity`: Track large holder movements\n\n"

            "Structure your report with:\n"
            "1. Executive Summary (2-3 sentences on overall on-chain sentiment)\n"
            "2. Network Health Analysis\n"
            "3. Exchange Flow Analysis\n"
            "4. Whale Activity Assessment\n"
            "5. On-Chain Trading Signal (BULLISH/NEUTRAL/BEARISH with confidence level)\n"
            "6. Markdown table summarizing key on-chain metrics\n\n"

            "Be specific with numbers and trends. Avoid generic statements like 'metrics are mixed.'"
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
                    " For your reference, the current date is {current_date}. The crypto asset we are analyzing is {ticker}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=crypto_symbol)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "onchain_report": report,
        }

    return onchain_analyst_node
