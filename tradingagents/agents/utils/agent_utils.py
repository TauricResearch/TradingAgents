"""Shared helper utilities and analyst-facing tool functions.

The crypto/Kalshi data implementations live in ``tradingagents/dataflows/``
(Phase 1). This module exposes them as ``@tool``-decorated functions so the
existing analyst factories can keep importing them by name. Phase 2 will
likely rename and rewire these to live closer to the dataflows package,
but the names below are kept stable while data layer work lands.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.tools import tool

from tradingagents.dataflows import coinbase, indicators
from tradingagents.dataflows.crypto_news import (
    fetch_headlines,
    render_headlines_markdown,
)
from tradingagents.dataflows.kalshi_market import render_market_markdown
from tradingagents.dataflows.onchain import render_onchain_markdown
from tradingagents.dataflows.sentiment_sources import (
    fetch_cmc_sentiment,
    fetch_reddit_posts,
    render_cmc_markdown,
    render_reddit_markdown,
)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def build_instrument_context(contract_id: str) -> str:
    """Describe the exact Kalshi contract under analysis so agents preserve the identifier.

    The framework analyzes Kalshi binary prediction-market contracts (not
    equities); ``contract_id`` is the Kalshi-issued ticker such as
    ``KXBTCD-26MAY05-T100000`` for a daily BTC contract. Phase 2 enriches
    this context with the underlying asset and resolution rules.
    """
    return (
        f"The Kalshi contract under analysis is `{contract_id}`. "
        "Use this exact contract identifier in every tool call, report, "
        "and recommendation."
    )


def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility."""
        messages = state["messages"]

        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


# ---------------------------------------------------------------------------
# Market data tools — Coinbase OHLCV + indicators
# ---------------------------------------------------------------------------


@tool
def get_stock_data(
    symbol: Annotated[str, "Crypto asset symbol (e.g. BTC, ETH)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch daily OHLCV candles for a crypto asset from Coinbase.

    Coinbase BTC-USD is the settlement reference for Kalshi BTC daily
    contracts, so price data here aligns with how contracts resolve.
    """
    try:
        candles = coinbase.get_candles(
            symbol=symbol, granularity="1d", start=start_date, end=end_date
        )
        return coinbase.render_candles_markdown(candles)
    except Exception as e:  # noqa: BLE001
        return f"Coinbase candle fetch failed for {symbol}: {e}"


@tool
def get_indicators(
    symbol: Annotated[str, "Crypto asset symbol (e.g. BTC)"],
    indicator: Annotated[str, "Technical indicator name (e.g. rsi, macd, close_50_sma)"],
    curr_date: Annotated[str, "Current date you are trading at, yyyy-mm-dd"],
    look_back_days: Annotated[int, "How many days of history to load before computing"] = 60,
) -> str:
    """Compute a technical indicator on Coinbase daily candles.

    Supported names mirror the Market Analyst prompt: ``close_50_sma``,
    ``close_200_sma``, ``close_10_ema``, ``macd``, ``macds``, ``macdh``,
    ``rsi``, ``boll``, ``boll_ub``, ``boll_lb``, ``atr``, ``vwma``.
    """
    try:
        names = [n.strip().lower() for n in indicator.split(",") if n.strip()]
        # Pull a wider window than ``look_back_days`` so long-MA indicators
        # have enough warm-up to produce non-NaN values at the tail.
        warmup_days = max(look_back_days + 200, 240)
        import datetime as _dt
        end = _dt.datetime.fromisoformat(curr_date).replace(tzinfo=_dt.timezone.utc)
        start = end - _dt.timedelta(days=warmup_days)
        candles = coinbase.get_candles(
            symbol=symbol,
            granularity="1d",
            start=start.date().isoformat(),
            end=end.date().isoformat(),
        )
        df = indicators.candles_to_df(candles)
        if df.empty:
            return f"No candles available for {symbol} ending {curr_date}."

        sections = []
        for name in names:
            try:
                sections.append(f"#### {name}")
                sections.append(indicators.render_indicator_markdown(df, name, look_back=look_back_days))
            except ValueError as e:
                sections.append(f"#### {name}\n{e}")
        return "\n\n".join(sections)
    except Exception as e:  # noqa: BLE001
        return f"Indicator computation failed for {symbol}/{indicator}: {e}"


# ---------------------------------------------------------------------------
# News tools — RSS aggregation
# ---------------------------------------------------------------------------


@tool
def get_news(
    query: Annotated[str, "Asset/keyword to filter on (e.g. bitcoin, ETF, regulation)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch recent crypto headlines matching ``query`` from reputable RSS feeds.

    Aggregates CoinDesk, CoinTelegraph, The Block, Decrypt, Bitcoin Magazine.
    Only the ``end_date`` is used to derive the look-back window; entries
    older than ``end_date - start_date`` are dropped.
    """
    try:
        import datetime as _dt
        s = _dt.datetime.fromisoformat(start_date)
        e = _dt.datetime.fromisoformat(end_date)
        look_back = max((e - s).days, 1)
        items = fetch_headlines(query=query, look_back_days=look_back, limit=20)
        return render_headlines_markdown(items)
    except Exception as e:  # noqa: BLE001
        return f"Crypto news fetch failed: {e}"


@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 3,
    limit: Annotated[int, "Maximum number of articles to return"] = 15,
) -> str:
    """Fetch broad crypto + macro headlines (no query filter)."""
    try:
        items = fetch_headlines(query=None, look_back_days=look_back_days, limit=limit)
        return render_headlines_markdown(items)
    except Exception as e:  # noqa: BLE001
        return f"Global crypto news fetch failed: {e}"


# ---------------------------------------------------------------------------
# Kalshi market data — read-only (Phase 1)
# ---------------------------------------------------------------------------


@tool
def get_kalshi_market(
    contract_id: Annotated[str, "Kalshi contract identifier (e.g. KXBTCD-26MAY05-T100000)"],
) -> str:
    """Fetch current Kalshi market state for the contract under analysis.

    Returns YES/NO bid/ask, last trade, status, open/close times. Used by
    the Portfolio Manager (Phase 2) to compute ``edge_bps`` between the
    agent's ``p_yes`` estimate and the market's implied probability.
    """
    try:
        return render_market_markdown(contract_id)
    except Exception as e:  # noqa: BLE001
        return f"Kalshi market fetch failed for {contract_id}: {e}"


# ---------------------------------------------------------------------------
# Sentiment tools — Reddit + CMC
# ---------------------------------------------------------------------------


@tool
def get_reddit_sentiment(
    asset: Annotated[str, "Asset name to filter posts (e.g. bitcoin)"] = "bitcoin",
) -> str:
    """Aggregate top recent Reddit posts referencing ``asset`` across crypto subreddits.

    Surveys r/Bitcoin, r/CryptoCurrency, r/CryptoMarkets, r/btc. Requires
    REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET env vars; returns a clear
    "missing-creds" message otherwise.
    """
    try:
        posts = fetch_reddit_posts(asset=asset)
        return render_reddit_markdown(posts, asset=asset)
    except Exception as e:  # noqa: BLE001
        return f"Reddit sentiment fetch failed: {e}"


@tool
def get_cmc_sentiment(
    asset: Annotated[str, "Asset symbol (e.g. BTC)"] = "BTC",
) -> str:
    """CoinMarketCap snapshot: price, 1h/24h/7d change, volume, rank.

    The first-party "Crypto Community Sentiment" dashboard endpoint is on
    CMC's paid tier; the free tier surfaces price + volume metrics which
    serve as a momentum proxy. Requires CMC_API_KEY env var; returns a
    "missing-creds" message otherwise.
    """
    try:
        data = fetch_cmc_sentiment(asset=asset)
        return render_cmc_markdown(data, asset=asset)
    except Exception as e:  # noqa: BLE001
        return f"CMC fetch failed: {e}"


# ---------------------------------------------------------------------------
# On-chain tool — free sources only
# ---------------------------------------------------------------------------


@tool
def get_onchain_metrics(
    asset: Annotated[str, "Asset symbol (e.g. BTC)"] = "BTC",
    look_back_days: Annotated[int, "Days of on-chain history to summarize"] = 7,
) -> str:
    """Fetch on-chain activity summary for an asset.

    BTC-only in v1. Pulls hash rate, transaction count, fee revenue,
    miner revenue, mempool depth from blockchain.com + mempool.space.
    Both endpoints are free and key-less. ETF custody flows are deferred
    to v1.1 (paid sources).
    """
    try:
        return render_onchain_markdown(asset=asset, look_back_days=look_back_days)
    except Exception as e:  # noqa: BLE001
        return f"On-chain metrics fetch failed: {e}"
