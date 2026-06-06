"""Sentiment analyst — multi-source sentiment analysis for a target ticker.

Previously named ``social_media_analyst``. Renamed and redesigned because
the old version had a prompt that demanded social-media analysis but the
only tool available was Yahoo Finance news — which led LLMs to fabricate
Reddit/X/StockTwits content under prompt pressure (verified live).

The redesigned agent pre-fetches three complementary data sources before
the LLM is invoked and injects them into the prompt as structured blocks:

  1. News headlines     — Yahoo Finance (institutional framing)
  2. StockTwits messages — retail-trader posts indexed by cashtag, with
                           user-labeled Bullish/Bearish sentiment tags
  3. Reddit posts        — r/wallstreetbets, r/stocks, r/investing

The agent does not use tool-calling; the data is in the prompt from
turn 0. The LLM produces the sentiment report in a single invocation.

See: https://github.com/TauricResearch/TradingAgents/issues/557
"""

from datetime import datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_language_instruction,
    get_news,
)
from tradingagents.agents.utils.prompt_cache import (
    budgeted_dynamic_text,
    stable_join_sections,
)
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.personas.prompt_overlay import apply_fragment


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


SENTIMENT_SYSTEM_MESSAGE = """You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for the instrument using three complementary data sources that have already been collected for you.

## Data sources

### News headlines - Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

### StockTwits messages - retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

### Reddit posts - r/wallstreetbets, r/stocks, r/investing
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters: r/wallstreetbets is often contrarian or exuberant; r/stocks is more measured; r/investing is longer-term.

## How to analyze this data

1. Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal. A 70/30 bullish/bearish split is moderately bullish; 90/10 or higher may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters.
2. Look for cross-source divergences. If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal.
3. Weight Reddit posts by engagement. A highly engaged thread reflects community attention; a low-engagement post is noise.
4. Distinguish opinion from event. News headlines are events; social posts are opinions.
5. Identify recurring narrative themes across sources.
6. Be honest about data limits. If a source is unavailable or thin, say so explicitly.
7. Identify catalysts and risks surfaced by the data.
8. Past sentiment is not predictive. Frame conclusions as a signal for the trader to weigh alongside fundamentals and technicals.

## Output

Produce a sentiment report covering, in order:

1. Overall sentiment direction: Bullish, Bearish, Neutral, or Mixed, with a confidence note based on data quality and sample size.
2. Source-by-source breakdown with specific evidence.
3. Divergences, alignments, and key narratives across sources.
4. Catalysts and risks surfaced by the data.
5. A Markdown table summarizing key sentiment signals, direction, source, and supporting evidence."""


def build_sentiment_user_prompt(
    *,
    ticker: str,
    instrument_context: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    return stable_join_sections(
        [
            ("Ticker", ticker),
            ("Instrument Context", instrument_context),
            ("Sentiment Window", f"{start_date} to {end_date}"),
            (
                "News Headlines - Yahoo Finance",
                budgeted_dynamic_text(
                    news_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "sentiment news",
                ),
            ),
            (
                "StockTwits Messages",
                budgeted_dynamic_text(
                    stocktwits_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "stocktwits messages",
                ),
            ),
            (
                "Reddit Posts",
                budgeted_dynamic_text(
                    reddit_block,
                    "prompt_cache_report_budget_chars",
                    5000,
                    "reddit posts",
                ),
            ),
            (
                "Current Task",
                "Produce the sentiment report using the static methodology and the dynamic source blocks above.",
            ),
        ]
    )


def create_sentiment_analyst(llm, persona=None):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data, injects them into the
    prompt as structured blocks, and produces a sentiment report in a
    single LLM call.
    """

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = build_instrument_context(ticker)

        # Pre-fetch all three sources. Each fetcher degrades gracefully and
        # returns a string (no exceptions surface from here), so the LLM
        # always sees something — either real data or a clear placeholder.
        news_block = get_news.func(ticker, start_date, end_date)
        stocktwits_block = fetch_stocktwits_messages(ticker, limit=30)
        reddit_block = fetch_reddit_posts(ticker)

        system_message = apply_fragment(
            SENTIMENT_SYSTEM_MESSAGE + get_language_instruction(),
            persona,
        )
        user_prompt = build_sentiment_user_prompt(
            ticker=ticker,
            instrument_context=instrument_context,
            start_date=start_date,
            end_date=end_date,
            news_block=news_block,
            stocktwits_block=stocktwits_block,
            reddit_block=reddit_block,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    "\n{system_message}",
                ),
                ("human", "{user_prompt}"),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(user_prompt=user_prompt)

        # No bind_tools — the data is already in the prompt; a single LLM
        # call produces the report directly.
        chain = prompt | llm
        result = chain.invoke(state["messages"])

        return {
            "messages": [result],
            "sentiment_report": result.content,
        }

    return sentiment_analyst_node


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm, persona=None):
    """Deprecated alias for :func:`create_sentiment_analyst`.

    Kept so existing code that imports ``create_social_media_analyst``
    continues to work.

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
    return create_sentiment_analyst(llm, persona=persona)
