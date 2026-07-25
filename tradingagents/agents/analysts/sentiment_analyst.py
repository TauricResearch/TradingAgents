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
turn 0. Output uses the structured-output pattern (json_schema for
OpenAI/xAI, response_schema for Gemini, tool-use for Anthropic), falling
back to free-text generation for providers that lack native support, so
the sentiment header (band + score + confidence) is deterministic across
runs and providers instead of free-form per-model prose.

See: https://github.com/TauricResearch/TradingAgents/issues/557
See: https://github.com/TauricResearch/TradingAgents/issues/796
"""

from datetime import datetime, timedelta
from typing import Any

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
    invoke_structured_or_freetext_with_artifact,
)
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.reddit import fetch_reddit_posts
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from tradingagents.dataflows.ticker_utils import is_a_share_ticker
from tradingagents.observability.provenance import capture_direct_call, direct_data_scope
from tradingagents.skills import (
    build_role_skill_prompt,
    build_skill_trigger_context,
    emit_methodology_artifact,
    persist_role_report,
)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def _safe_a_share_fetch(label: str, fetcher) -> str:
    """Run one A-share sentiment-data fetch with fail-open degradation.

    A-share capital-flow sources can be unavailable (anti-crawler, holiday,
    vendor outage). Each fetch is isolated so one failing source never breaks
    the whole sentiment report: the LLM always sees either real data or a
    clearly labelled placeholder for every block.
    """
    try:
        result = fetcher()
    except Exception as exc:  # fail-open: sentiment must not halt on one source
        return f"<{label} unavailable: {type(exc).__name__}>"
    text = str(result)
    if not text or text.startswith("NO_DATA_AVAILABLE"):
        return f"<{label} unavailable>"
    return text


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data, injects them into the
    prompt as structured blocks, and produces a deterministic sentiment
    report via structured output (with a free-text fallback for providers
    that do not support it).
    """
    structured_llm = bind_structured(llm, SentimentReport, "Sentiment Analyst")

    def sentiment_analyst_node(state):
        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)

        # Pre-fetch all three sources. Each fetcher degrades gracefully and
        # returns a string (no exceptions surface from here), so the LLM
        # always sees something — either real data or a clear placeholder.
        is_a_share = is_a_share_ticker(ticker)

        if is_a_share:
            # A-share: use capital-flow / insider / dragon-tiger signals instead
            # of Reddit/StockTwits, which have near-zero A-share coverage. Each
            # source degrades gracefully so one outage never blocks the report.
            with direct_data_scope("sentiment.prefetch.news"):
                news_block = get_news.func(ticker, start_date, end_date)
            northbound_flow_block = _safe_a_share_fetch(
                "northbound_flow",
                lambda: route_to_vendor(
                    "get_a_share_northbound_flow", start_date, end_date
                ),
            )
            northbound_holdings_block = _safe_a_share_fetch(
                "northbound_holdings",
                lambda: route_to_vendor(
                    "get_a_share_northbound_holdings", ticker
                ),
            )
            margin_block = _safe_a_share_fetch(
                "margin_financing",
                lambda: route_to_vendor(
                    "get_a_share_margin_financing", ticker, end_date
                ),
            )
            insider_block = _safe_a_share_fetch(
                "insider_trades",
                lambda: route_to_vendor(
                    "get_a_share_insider_trades", ticker, start_date, end_date
                ),
            )
            dragon_tiger_block = ""
            if get_config().get("sentiment_a_share_dragon_tiger_enabled", True):
                dragon_tiger_block = _safe_a_share_fetch(
                    "dragon_tiger",
                    lambda: route_to_vendor(
                        "get_a_share_dragon_tiger", ticker, end_date
                    ),
                )
            skill_trigger_text = build_skill_trigger_context(
                state.get("messages", ()),
                news_block,
                northbound_flow_block,
                northbound_holdings_block,
                margin_block,
                insider_block,
                dragon_tiger_block,
            )
            emit_methodology_artifact("sentiment_analyst", trigger_text=skill_trigger_text)
            system_message = _build_a_share_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                northbound_flow_block=northbound_flow_block,
                northbound_holdings_block=northbound_holdings_block,
                margin_block=margin_block,
                insider_block=insider_block,
                dragon_tiger_block=dragon_tiger_block,
            )
        else:
            # Non-A-share: keep Reddit/StockTwits retail-sentiment sources.
            with direct_data_scope("sentiment.prefetch.news"):
                news_block = get_news.func(ticker, start_date, end_date)
            stocktwits_block = capture_direct_call(
                invocation_path="sentiment.prefetch.stocktwits",
                method="fetch_stocktwits_messages",
                vendor="stocktwits",
                function=fetch_stocktwits_messages,
                args=(ticker,),
                kwargs={"limit": 30},
            )
            reddit_block = capture_direct_call(
                invocation_path="sentiment.prefetch.reddit",
                method="fetch_reddit_posts",
                vendor="reddit",
                function=fetch_reddit_posts,
                args=(ticker,),
            )
            skill_trigger_text = build_skill_trigger_context(
                state.get("messages", ()), news_block, stocktwits_block, reddit_block
            )
            emit_methodology_artifact("sentiment_analyst", trigger_text=skill_trigger_text)
            system_message = _build_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=news_block,
                stocktwits_block=stocktwits_block,
                reddit_block=reddit_block,
            )
        system_message += build_role_skill_prompt(
            "sentiment_analyst", trigger_text=skill_trigger_text
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}"
                    "\n{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(current_date=end_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        # Format the template into a concrete message list so the structured
        # and free-text paths receive the same input. No bind_tools — the
        # data is already in the prompt.
        formatted_messages = prompt.format_messages(messages=state["messages"])

        report_text, structured_report = invoke_structured_or_freetext_with_artifact(
            structured_llm,
            llm,
            formatted_messages,
            render_sentiment_report,
            "Sentiment Analyst",
        )

        output: dict[str, Any] = {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
        }
        # The structured report carries the optional SentimentRealityGap
        # scorecard. Persist it through the same public channel the other
        # analysts use via their fenced methodology-artifact contract, so the
        # sentiment role is no longer the only analyst without a durable
        # methodology scorecard. The free-text fallback leaves it absent
        # rather than fabricating one.
        reality_gap = getattr(structured_report, "reality_gap", None)
        if reality_gap is not None:
            payload = reality_gap.model_dump(mode="json")
            persist_role_report("sentiment_analyst", payload)
            output["methodology_reports"] = {
                **state.get("methodology_reports", {}),
                "sentiment_analyst": payload,
            }
        return output

    return sentiment_analyst_node


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

## Data sources (pre-fetched, in this prompt)

### News headlines — Yahoo Finance, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — r/wallstreetbets, r/stocks, r/investing (past 7 days)
Community discussion. Engagement signal via upvote score and comment count. Subreddit character matters (r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Weight Reddit posts by engagement.** A 400-upvote / 200-comment thread reflects community attention; a 3-upvote post is noise. Read the body excerpts for context — the title alone often misleads.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this explicitly in the `confidence` field and the narrative. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).
- **reality_gap**: Optional public scorecard that compares the observed narrative with supplied operating facts only. Include ``narrative``, ``reality_check``, ``divergence`` (temporary / structural / indeterminate / unavailable), an optional -100 to +100 ``reality_gap_score``, an optional ``resolution_trigger``, and explicit data limitations. Leave null when operating facts are unavailable. Never include private reasoning, prompts, or tool traces.

{get_language_instruction()}"""


def _build_a_share_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    northbound_flow_block: str,
    northbound_holdings_block: str,
    margin_block: str,
    insider_block: str,
    dragon_tiger_block: str,
) -> str:
    """Assemble the A-share sentiment system message with capital-flow blocks.

    A-share tickers have near-zero coverage on Reddit/StockTwits, so this
    variant substitutes China-specific sentiment signals: northbound
    (foreign-investor) flow, margin financing, insider trades, and the
    dragon-tiger list. ``reality_gap`` is left null because operating facts
    are not supplied in this branch.
    """
    dragon_tiger_section = (
        f"### Dragon-Tiger List (短线资金活跃度)\n{dragon_tiger_block}"
        if dragon_tiger_block
        else ""
    )
    return f"""You are a financial market sentiment analyst covering the China A-share {ticker} for the period {start_date} to {end_date}. A-share retail sentiment is not available on Reddit/StockTwits; instead, analyze the following China-specific sentiment signals that have been pre-fetched for you.

## Data sources (pre-fetched, in this prompt)

### News headlines (past 7 days)
Institutional and media framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### Northbound capital flow (aggregate market-wide)
Foreign-investor (Stock Connect) net inflow/outflow. Sustained net inflow into the market = foreign-investor optimism; net outflow = caution. Read the aggregate as a market-wide risk-appetite backdrop for {ticker}.

<start_of_northbound_flow>
{northbound_flow_block}
<end_of_northbound_flow>

### Northbound holdings for {ticker}
Provider-reported northbound holding/ranking for this ticker. Rising northbound holdings = foreign-investor accumulation; falling = distribution.

<start_of_northbound_holdings>
{northbound_holdings_block}
<end_of_northbound_holdings>

### Margin financing (融资融券) for {ticker}
Margin buy balance reflects leveraged bullish positioning; short-selling balance reflects bearish positioning. Rising margin balance = leveraged long buildup (bullish but fragile); rapid deleveraging = forced-selling risk.

<start_of_margin>
{margin_block}
<end_of_margin>

### Insider trades (董监高增减持) for {ticker}
Disclosed share changes by directors, supervisors, and managers. Net insider buying = internal confidence; net selling = caution signal.

<start_of_insider>
{insider_block}
<end_of_insider>

{dragon_tiger_section}

## How to analyze this data (best practices)

1. **Read northbound flow directionally.** Sustained net inflow is a bullish backdrop; pair the market-wide flow with this ticker's northbound holdings to see if foreign investors are specifically accumulating {ticker}.

2. **Margin financing is a double-edged signal.** Rising margin balance is bullish for momentum but raises forced-deleveraging risk on a drawdown. Flag the fragility.

3. **Insider trades are a slow signal.** A single insider buy is weak evidence; a cluster of insider buys (or a large single buy) is stronger. Insider selling is often routine (liquidity, tax) - flag but do not overweight.

4. **Dragon-Tiger list (when present) shows short-term hot-money activity.** Frequent appearances = speculative attention; absence does not imply bearishness.

5. **Look for cross-source divergences.** If news is bearish but northbound is accumulating and insiders are buying, the divergence itself is a signal. If margin is sharply rising while northbound exits, that is leveraged retail chasing foreign-investor distribution - fragile.

6. **Distinguish event from opinion.** A news headline is an event; northbound flow is an action. Both are inputs but weighted differently.

7. **Be honest about data limits.** If a source returned an "<unavailable>" placeholder, flag lower confidence. Holidays and trading suspensions produce empty blocks - say so rather than inferring.

8. **Past sentiment is not predictive.** Frame conclusions as a signal for the trader to weigh alongside fundamentals and technicals.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions; Neutral only when all sources are genuinely silent.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and how many sources returned real data.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).
- **reality_gap**: Leave null. Operating facts are not supplied in the A-share sentiment branch; do not fabricate a reality-gap scorecard.

{get_language_instruction()}"""


# ---------------------------------------------------------------------------
# Backwards-compatibility shim
# ---------------------------------------------------------------------------
def create_social_media_analyst(llm):
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
    return create_sentiment_analyst(llm)
