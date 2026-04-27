"""Sentiment analyst — qualitative tone and sentiment analysis of recent news.

Previously named ``social_media_analyst``. Renamed because the only available
data tool is ``get_news`` (Yahoo Finance headlines), not a social media feed.
The prompt has been updated to reflect what the agent actually does: it
analyses the *tone* and *sentiment* of recent news articles rather than
claiming to process Reddit, X/Twitter, or StockTwits data that it does not
have access to.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    This analyst reads recent news headlines and articles for the target
    company and assesses the overall qualitative sentiment and tone — bullish,
    bearish, or neutral — along with any notable narrative shifts.  It does
    *not* process live social media data; that capability would require
    additional data tools (e.g. Reddit via PRAW, StockTwits public API).
    """

    def sentiment_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [get_news]

        system_message = (
            "You are a financial news sentiment analyst. "
            "Your task is to analyse recent news articles and headlines for a specific company "
            "and produce a comprehensive sentiment report covering: "
            "(1) the overall tone of coverage — bullish, bearish, or neutral — and how it has "
            "shifted over the past week; "
            "(2) the key themes and narratives appearing repeatedly across sources; "
            "(3) any notable risks or catalysts surfaced by the news; "
            "(4) a qualitative summary of public and analyst perception based on the articles. "
            "Use the get_news(query, start_date, end_date) tool to retrieve recent company-specific "
            "news articles. Focus on tone, framing, and recurring signals rather than raw facts "
            "(the News Analyst covers factual content separately). "
            "Note: this analysis is based on news headlines and article summaries only — "
            "live social media feeds (Reddit, X/Twitter, StockTwits) are not currently available. "
            "Be transparent about this scope limitation in your report."
            + " Make sure to append a Markdown table at the end of the report to organise key "
            "sentiment signals, their direction, and supporting evidence."
            + get_language_instruction()
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


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    The agent was renamed from ``social_media_analyst`` to ``sentiment_analyst``
    because it does not actually consume social media data — it analyses the
    tone of Yahoo Finance news headlines.  This alias is kept so that existing
    code that imports ``create_social_media_analyst`` continues to work without
    modification.

    .. deprecated::
        Import :func:`create_sentiment_analyst` directly instead.
    """
    import warnings
    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
