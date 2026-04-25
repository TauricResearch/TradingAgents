import json

from .alpha_vantage_common import _make_api_request, format_datetime_for_api

_DEFAULT_COMPANY_NEWS_LIMIT = 12


def _coerce_json_payload(
    response: dict[str, str] | str,
) -> tuple[dict | None, dict[str, str] | str]:
    if isinstance(response, dict):
        return response, response
    try:
        return json.loads(response), response
    except (TypeError, json.JSONDecodeError):
        return None, response


def _dedupe_feed(feed: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[str] = set()
    for article in feed:
        key = str(article.get("url") or article.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(article)
    return deduped


def _ticker_relevance(article: dict, ticker: str) -> float:
    ticker_upper = ticker.upper()
    for item in article.get("ticker_sentiment", []) or []:
        if str(item.get("ticker", "")).upper() != ticker_upper:
            continue
        try:
            return float(item.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _trim_company_news_payload(
    response: dict[str, str] | str,
    *,
    ticker: str,
    limit: int = _DEFAULT_COMPANY_NEWS_LIMIT,
) -> dict[str, str] | str:
    payload, original = _coerce_json_payload(response)
    if not isinstance(payload, dict):
        return response

    feed = payload.get("feed")
    if not isinstance(feed, list):
        return response

    deduped = _dedupe_feed(feed)
    matching = [article for article in deduped if _ticker_relevance(article, ticker) > 0.0]
    ranked = sorted(
        matching or deduped,
        key=lambda article: (
            _ticker_relevance(article, ticker),
            str(article.get("time_published", "")),
        ),
        reverse=True,
    )

    trimmed = dict(payload)
    trimmed["feed"] = ranked[:limit]
    trimmed["items"] = str(len(trimmed["feed"]))
    if isinstance(original, str):
        return json.dumps(trimmed, indent=4)
    return trimmed


def _trim_global_news_payload(
    response: dict[str, str] | str,
    *,
    limit: int,
) -> dict[str, str] | str:
    payload, original = _coerce_json_payload(response)
    if not isinstance(payload, dict):
        return response

    feed = payload.get("feed")
    if not isinstance(feed, list):
        return response

    trimmed = dict(payload)
    trimmed["feed"] = _dedupe_feed(feed)[: max(limit, 0)]
    trimmed["items"] = str(len(trimmed["feed"]))
    if isinstance(original, str):
        return json.dumps(trimmed, indent=4)
    return trimmed


def get_news(ticker: str, start_date: str, end_date: str) -> dict[str, str] | str:
    """Returns live and historical market news & sentiment data from premier news outlets worldwide.

    Covers stocks, cryptocurrencies, forex, and topics like fiscal policy, mergers & acquisitions, IPOs.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date for news search.
        end_date: End date for news search.

    Returns:
        Dictionary containing news sentiment data or JSON string.
    """

    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
    }

    response = _make_api_request("NEWS_SENTIMENT", params)
    return _trim_company_news_payload(response, ticker=ticker)


def get_global_news(
    curr_date: str, look_back_days: int = 7, limit: int = 50
) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    from datetime import datetime, timedelta

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

    response = _make_api_request("NEWS_SENTIMENT", params)
    return _trim_global_news_payload(response, limit=limit)


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
