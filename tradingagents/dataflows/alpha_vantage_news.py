"""Alpha Vantage news vendor.

``NEWS_SENTIMENT`` answers with a large JSON document: every article carries a
banner image, an author list, a topic array with relevance scores, and one
sentiment entry per ticker it mentions. Returned verbatim — which is what
``_make_api_request`` hands back — a single call filled 6-7k tokens of an
analyst's context with fields no agent reads (#291).

The feed is rendered here into the same compact markdown the yfinance vendor
emits, keeping what an analyst actually uses: headline, source, date,
sentiment, a length-bounded summary, and the link.
"""

import json

from .alpha_vantage_common import _make_api_request, format_datetime_for_api
from .config import get_config
from .news_format import trim_summary


def _format_time_published(raw: str) -> str:
    """Alpha Vantage stamps articles as ``20250115T093000``; keep the date."""
    if len(raw) >= 8 and raw[:8].isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _sentiment_line(article: dict, ticker: str | None) -> str:
    """One line of sentiment, dropping the per-ticker array around it.

    The feed scores every ticker an article mentions, so a piece on the S&P
    can arrive with twenty entries. Only the requested ticker's score tells the
    analyst anything, and the overall label covers the rest.
    """
    parts = []
    overall = article.get("overall_sentiment_label")
    if overall:
        parts.append(f"overall {overall}")

    if ticker:
        wanted = ticker.upper()
        for entry in article.get("ticker_sentiment") or []:
            if not isinstance(entry, dict) or entry.get("ticker", "").upper() != wanted:
                continue
            label = entry.get("ticker_sentiment_label")
            relevance = entry.get("relevance_score")
            if label:
                detail = f"{wanted} {label}"
                if relevance:
                    detail += f" (relevance {relevance})"
                parts.append(detail)
            break

    return f"Sentiment: {', '.join(parts)}\n" if parts else ""


def _render_feed(
    result,
    *,
    header: str,
    empty: str,
    limit: int,
    ticker: str | None = None,
) -> str:
    """Render a ``NEWS_SENTIMENT`` payload as compact markdown.

    A body that is not a JSON object carrying a ``feed`` list is returned
    unchanged, so Alpha Vantage notices and any payload shape this function
    does not recognise still reach the caller verbatim instead of being
    flattened into an empty report.
    """
    if not isinstance(result, str):
        return result
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return result
    if not isinstance(payload, dict) or not isinstance(payload.get("feed"), list):
        return result

    articles = [a for a in payload["feed"] if isinstance(a, dict)]
    if limit and limit > 0:
        articles = articles[:limit]
    if not articles:
        return empty

    blocks = []
    for article in articles:
        title = article.get("title") or "No title"
        source = article.get("source") or "Unknown"
        published = _format_time_published(article.get("time_published") or "")
        attribution = f"source: {source}, {published}" if published else f"source: {source}"

        block = f"### {title} ({attribution})\n"
        block += _sentiment_line(article, ticker)
        summary = trim_summary(article.get("summary") or "")
        if summary:
            block += f"{summary}\n"
        if article.get("url"):
            block += f"Link: {article['url']}\n"
        blocks.append(block)

    return f"{header}\n\n" + "\n".join(blocks)


def get_news(ticker, start_date, end_date) -> str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Compact markdown of the matching articles.
    """
    limit = get_config()["news_article_limit"]

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        # Ask for what we will keep: the endpoint otherwise serves its own
        # default of 50 articles that we would only discard after paying for
        # the transfer.
        "limit": str(limit),
    }

    return _render_feed(
        _make_api_request("NEWS_SENTIMENT", params),
        header=f"## {ticker} News, from {start_date} to {end_date}:",
        empty=f"No news found for {ticker} between {start_date} and {end_date}",
        limit=limit,
        ticker=ticker,
    )


def get_global_news(curr_date, look_back_days: int | None = None, limit: int | None = None) -> str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Compact markdown of the matching articles.
    """
    from datetime import datetime, timedelta

    # The tool wrapper advertises both arguments as omittable and forwards the
    # omission as an explicit ``None``, which overrode the literal defaults that
    # used to sit in this signature and crashed the call in ``timedelta``. Read
    # them from config the way the yfinance vendor does.
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    # Calculate start date
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(curr_date),
        "limit": str(limit),
    }

    return _render_feed(
        _make_api_request("NEWS_SENTIMENT", params),
        header=f"## Global Market News, from {start_date} to {curr_date}:",
        empty=f"No global news found between {start_date} and {curr_date}",
        limit=limit,
    )


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders.

    Covers transactions by founders, executives, board members, etc.

    Args:
        symbol: Ticker symbol. Example: "IBM".

    Returns:
        Dictionary containing insider transaction data or JSON string.
    """

    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)
