"""Sentiment analyst for a target ticker.

The node pre-fetches configured ticker news before the LLM is invoked and
injects it into the prompt as a structured block. For the China A-share
configuration this intentionally avoids StockTwits/Reddit, whose coverage is
mostly US-centric and low signal for A-share tickers.
"""

from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.schemas import SentimentReport, render_sentiment_report
from tradingagents.agents.utils.agent_utils import (
    get_instrument_context_from_state,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.structured import (
    bind_structured,
    invoke_structured_or_freetext,
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph."""
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        news_block = get_news.func(ticker, start_date, end_date)

        system_message = _build_system_message(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
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
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text = invoke_structured_or_freetext(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        return {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data."""
    return f"""You are a China A-share market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on the China-focused news data that has already been collected for you.

## Data sources (pre-fetched, in this prompt)

### China A-share company news, past 7 days
Fact-driven signal from the configured A-share news vendor. Treat it as the primary sentiment input.

<start_of_news>
{news_block}
<end_of_news>

## How to analyze this data (best practices)

1. **Separate event from interpretation.** Identify concrete corporate events, policy items, earnings clues, industry changes, regulatory developments, and risk disclosures before judging tone.

2. **Track source density and recency.** More recent company-specific items should matter more than older generic market stories. If the source returns only sparse data, lower confidence.

3. **Identify recurring narrative themes.** What topic keeps appearing across headlines or article summaries? That is the dominant narrative driving current sentiment.

4. **Be honest about data limits.** If the news block is unavailable, stale, or very small, flag this explicitly in the `confidence` field and the narrative.

5. **Identify catalysts and risks** that emerge from the news: earnings, orders, financing, M&A, regulation, shareholder changes, sector policy, macro liquidity, or litigation.

6. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when the source is genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full breakdown of dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

{get_language_instruction()}"""


def create_social_media_analyst(llm):
    """Deprecated alias for :func:`create_sentiment_analyst`."""
    import warnings

    warnings.warn(
        "create_social_media_analyst is deprecated and will be removed in a "
        "future version. Use create_sentiment_analyst instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return create_sentiment_analyst(llm)
