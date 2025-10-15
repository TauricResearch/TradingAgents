"""
Crypto Fundamentals Analyst - Analyzes tokenomics, project fundamentals, and crypto-specific metrics
Replaces traditional financial statement analysis with crypto fundamentals
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.crypto_tools import (
    get_crypto_fundamentals,
    get_tokenomics,
    get_market_overview
)


def create_crypto_fundamentals_analyst(llm):
    """
    Create a crypto fundamentals analyst agent.

    This agent analyzes cryptocurrency-specific fundamentals:
    - Tokenomics (supply, inflation, distribution)
    - Project information (technology, consensus mechanism)
    - Market metrics (market cap, volume, circulation)
    - Competitive positioning

    Args:
        llm: Language model instance

    Returns:
        Crypto fundamentals analyst node function
    """
    def crypto_fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # Extract crypto asset key (e.g., 'bitcoin' from 'BTC/USDT')
        crypto_map = {
            'BTC': 'bitcoin',
            'ETH': 'ethereum',
            'SOL': 'solana',
            'ADA': 'cardano',
            'AVAX': 'avalanche',
            'DOT': 'polkadot',
            'MATIC': 'polygon',
            'ARB': 'arbitrum',
            'OP': 'optimism',
            'LINK': 'chainlink',
            'UNI': 'uniswap',
            'AAVE': 'aave',
        }

        # Determine crypto symbol
        crypto_symbol = ticker.split('/')[0] if '/' in ticker else ticker.upper()
        asset_key = crypto_map.get(crypto_symbol, crypto_symbol.lower())

        tools = [
            get_crypto_fundamentals,
            get_tokenomics,
            get_market_overview,
        ]

        system_message = (
            f"You are a crypto fundamentals analyst specializing in tokenomics and project analysis for {asset_key.upper()}. "
            "Unlike traditional equity analysis, crypto fundamentals focus on:\n\n"

            "**1. TOKENOMICS (Critical)**\n"
            "- Supply Dynamics: Circulating vs Total vs Max supply\n"
            "- Inflation Rate: Annual emission schedule and dilution\n"
            "- Distribution: How tokens are allocated (team, public, treasury)\n"
            "- Utility: What the token is used for (gas, governance, staking, collateral)\n\n"

            "**2. PROJECT FUNDAMENTALS**\n"
            "- Technology: Consensus mechanism, hashing algorithm, Layer-1/Layer-2\n"
            "- Category: DeFi, Layer-1, Infrastructure, Gaming, etc.\n"
            "- Development Activity: GitHub commits, developer community\n"
            "- Partnerships and Ecosystem: DApps built on platform, integrations\n\n"

            "**3. MARKET METRICS**\n"
            "- Market Cap Ranking: Position among all cryptocurrencies\n"
            "- Fully Diluted Valuation: If all tokens were unlocked\n"
            "- Trading Volume: Liquidity and market interest\n"
            "- Price Performance: % down from ATH, historical ROI\n\n"

            "**4. COMPETITIVE ANALYSIS**\n"
            "- Compare to competitors in same category\n"
            "- Market share and dominance trends\n"
            "- Technical advantages/disadvantages\n\n"

            "**Key Questions to Answer:**\n"
            "- Is the token inflationary or deflationary?\n"
            "- What % of max supply is already circulating? (scarcity)\n"
            "- Is there significant dilution risk from token unlocks?\n"
            "- Does the token have real utility or is it speculative?\n"
            "- How does market cap compare to competitors?\n"
            "- Is the project technically sound and actively developed?\n\n"

            "Use the available tools:\n"
            "- `get_crypto_fundamentals`: Comprehensive project profile and metrics\n"
            "- `get_tokenomics`: Detailed supply and inflation analysis\n"
            "- `get_market_overview`: Competitive positioning context\n\n"

            "Structure your report:\n"
            "1. **Executive Summary**: 2-3 sentence fundamental assessment\n"
            "2. **Tokenomics Analysis**: Supply, inflation, utility, dilution risk\n"
            "3. **Project Fundamentals**: Technology, category, development\n"
            "4. **Market Position**: Ranking, market cap, competitive landscape\n"
            "5. **Valuation Assessment**: Overvalued/Fairly Valued/Undervalued\n"
            "6. **Risk Factors**: Key risks to consider\n"
            "7. **Fundamental Rating**: STRONG BUY/BUY/HOLD/SELL with reasoning\n"
            "8. **Markdown Table**: Key metrics organized clearly\n\n"

            "Be specific and analytical. Provide actual numbers and comparisons, not generic statements."
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
                    " For your reference, the current date is {current_date}. The cryptocurrency we are analyzing is {ticker}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=asset_key)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return crypto_fundamentals_analyst_node
