"""
Crypto News Analyst - Analyzes crypto-specific news and regulatory developments
Focus on protocol upgrades, partnerships, regulations, and ecosystem news
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.crypto_tools import get_crypto_news


def create_crypto_news_analyst(llm):
    """
    Create a crypto news analyst agent.

    This agent analyzes cryptocurrency-specific news including:
    - Regulatory announcements (SEC, global regulators)
    - Protocol upgrades and hard forks
    - Partnership announcements
    - Exchange listings
    - Ecosystem developments
    - Macro crypto trends

    Args:
        llm: Language model instance

    Returns:
        Crypto news analyst node function
    """
    def crypto_news_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        # Extract crypto asset key
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
        }

        crypto_symbol = ticker.split('/')[0] if '/' in ticker else ticker.upper()
        asset_key = crypto_map.get(crypto_symbol, crypto_symbol.lower())

        tools = [get_crypto_news]

        system_message = (
            f"You are a crypto news analyst specializing in market-moving news for {asset_key.upper()}. "
            "Your role is to analyze recent news and assess its impact on market sentiment and price.\n\n"

            "**TYPES OF MARKET-MOVING CRYPTO NEWS:**\n\n"

            "**1. REGULATORY NEWS (High Impact)**\n"
            "- SEC announcements (lawsuits, approvals, ETFs)\n"
            "- Country-level bans or adoption (China ban, El Salvador adoption)\n"
            "- Regulatory clarity or uncertainty\n"
            "- Compliance requirements for exchanges\n"
            "**Impact**: Immediate and significant (often 10-30% moves)\n\n"

            "**2. PROTOCOL/TECHNICAL NEWS (Medium-High Impact)**\n"
            "- Network upgrades (Ethereum Merge, Bitcoin Taproot)\n"
            "- Hard forks or chain splits\n"
            "- Security vulnerabilities or exploits\n"
            "- Scalability improvements (Layer-2 launches)\n"
            "**Impact**: Varies (upgrades bullish, exploits very bearish)\n\n"

            "**3. ADOPTION & PARTNERSHIPS (Medium Impact)**\n"
            "- Institutional adoption (Tesla, MicroStrategy)\n"
            "- Payment integrations (PayPal, Visa)\n"
            "- Corporate partnerships or investments\n"
            "- DeFi protocol integrations\n"
            "**Impact**: Gradual accumulation of positive sentiment\n\n"

            "**4. EXCHANGE LISTINGS (Medium Impact)**\n"
            "- Major exchange listings (Binance, Coinbase)\n"
            "- Delistings (very bearish)\n"
            "- Trading pair additions\n"
            "**Impact**: Immediate (often 20-50% pump on listing)\n\n"

            "**5. ECOSYSTEM DEVELOPMENTS (Low-Medium Impact)**\n"
            "- DApp launches on platform\n"
            "- Developer activity metrics\n"
            "- Community growth\n"
            "- Governance proposals\n"
            "**Impact**: Cumulative over time\n\n"

            "**6. MACRO CRYPTO TRENDS (Variable Impact)**\n"
            "- Bitcoin halving cycles\n"
            "- Federal Reserve policy (rate changes affect crypto)\n"
            "- Inflation data (crypto as inflation hedge)\n"
            "- Stock market correlation shifts\n"
            "**Impact**: Sets overall market direction\n\n"

            "**7. SECURITY EVENTS (High Impact, Negative)**\n"
            "- Exchange hacks (Mt. Gox, FTX)\n"
            "- Smart contract exploits\n"
            "- Rug pulls and scams\n"
            "**Impact**: Very bearish, immediate\n\n"

            "**NEWS SENTIMENT ANALYSIS:**\n"
            "For each news item, assess:\n"
            "- **Sentiment**: Bullish, Neutral, or Bearish\n"
            "- **Impact Level**: High, Medium, Low\n"
            "- **Time Horizon**: Immediate, Short-term, Long-term\n"
            "- **Credibility**: Official source vs rumor\n\n"

            "**CRYPTO NEWS RED FLAGS:**\n"
            "- Unverified sources (crypto Twitter rumors)\n"
            "- Pump & dump schemes\n"
            "- Fake partnerships\n"
            "- Misleading headlines\n\n"

            "**TRUSTED SOURCES:**\n"
            "- Official project announcements\n"
            "- CoinDesk, The Block, Decrypt\n"
            "- SEC filings and official government sites\n"
            "- Exchange official channels\n\n"

            "Use the available tool:\n"
            "- `get_crypto_news`: Fetch recent news for the asset\n\n"

            "Structure your report:\n"
            "1. **News Summary**: 2-3 sentence overview of major news\n"
            "2. **Key News Items**: Top 5-10 most impactful news pieces\n"
            "   - For each: Headline, Date, Sentiment, Impact Level, Analysis\n"
            "3. **Regulatory Update**: Any regulatory developments\n"
            "4. **Technical/Protocol News**: Upgrades, partnerships, listings\n"
            "5. **Overall News Sentiment**: Bullish/Neutral/Bearish\n"
            "6. **Market Implications**: How news likely affects price\n"
            "7. **Risk Factors**: Negative news to watch\n"
            "8. **Markdown Table**: News items with sentiment and impact\n\n"

            "Prioritize recent news and focus on market-moving events. Be critical of sources."
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
                    " For your reference, the current date is {current_date}. Analyzing news for {ticker}.",
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
            "news_report": report,
        }

    return crypto_news_analyst_node
