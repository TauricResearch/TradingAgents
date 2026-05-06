"""Sentiment Analyst — Reddit + CoinMarketCap snapshot for the underlying crypto asset.

The "social" slot, repurposed from the equity-era social-media analyst.
Uses ``get_reddit_sentiment`` (cred-gated, falls back to a clear message)
and ``get_cmc_sentiment`` (free-tier price/volume snapshot as a momentum
proxy). The analyst reads these to assess whether crowd sentiment is
extreme in either direction — a useful signal at the daily horizon
where a Kalshi contract resolves on a 24-hour window.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_cmc_sentiment,
    get_language_instruction,
    get_reddit_sentiment,
)


def create_social_media_analyst(llm):
    def sentiment_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_reddit_sentiment, get_cmc_sentiment]

        system_message = (
            "You are the Sentiment Analyst on a Kalshi prediction-market research desk. "
            "Your job is to gauge **crypto crowd sentiment** for the underlying asset of "
            "the contract under analysis (BTC for v1). Combine Reddit signal with the "
            "CoinMarketCap price/volume snapshot to assess: is sentiment extreme bullish, "
            "extreme bearish, or balanced? Where is the crowd most one-sided? "
            "When sentiment hits an extreme, the contrarian read often pays off at the "
            "daily-horizon settlement. "
            "Use `get_reddit_sentiment` for Reddit r/Bitcoin / r/CryptoCurrency / r/CryptoMarkets coverage; "
            "use `get_cmc_sentiment` for the CoinMarketCap snapshot. "
            "Provide specific, actionable insights with citations to the most-upvoted posts and the price/volume figures."
            " Append a Markdown table at the end summarizing key sentiment readings."
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
            "sentiment_report": report,
        }

    return sentiment_analyst_node
