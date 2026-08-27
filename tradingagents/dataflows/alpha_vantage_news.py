import json
from datetime import date, datetime, timedelta

from .alpha_vantage_common import _make_api_request, format_datetime_for_api


def _filter_news_by_date(result, start_date: str, end_date: str):
    """Defensively filter Alpha Vantage news payloads to the requested dates.

    Server-side ``time_from``/``time_to`` remains useful for bandwidth, but the
    local filter is the point-in-time safety boundary. Undated items are excluded
    for historical analysis because their availability cannot be established.
    """
    was_string = isinstance(result, str)
    try:
        payload = json.loads(result) if was_string else result
    except (json.JSONDecodeError, TypeError):
        return (
            "DATA_UNAVAILABLE: Alpha Vantage news payload could not be parsed, so its "
            "publication times could not be verified against the analysis cutoff."
        )
    if not isinstance(payload, dict) or not isinstance(payload.get("feed"), list):
        return (
            "DATA_UNAVAILABLE: Alpha Vantage news payload did not contain a verifiable "
            "article feed. Do not infer news facts from this response."
        )

    historical = datetime.strptime(end_date, "%Y-%m-%d").date() < date.today()
    filtered = []
    for article in payload["feed"]:
        published = str(article.get("time_published") or "")[:8]
        if not published:
            if not historical:
                filtered.append(article)
            continue
        try:
            published_date = datetime.strptime(published, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            if not historical:
                filtered.append(article)
            continue
        if start_date <= published_date <= end_date:
            filtered.append(article)
    payload["feed"] = filtered
    return json.dumps(payload) if was_string else payload


def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
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
        "time_to": format_datetime_for_api(
            (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
        ),
    }

    result = _make_api_request("NEWS_SENTIMENT", params)
    return _filter_news_by_date(result, start_date, end_date)

def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> dict[str, str] | str:
    """Returns global market news & sentiment data without ticker-specific filtering.

    Covers broad market topics like financial markets, economy, and more.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Dictionary containing global news sentiment data or JSON string.
    """
    # Calculate start date
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    params = {
        "topics": "financial_markets,economy_macro,economy_monetary",
        "time_from": format_datetime_for_api(start_date),
        # Ask through midnight after curr_date so the requested date is
        # complete, then enforce an inclusive local cutoff below.
        "time_to": format_datetime_for_api(
            (curr_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        ),
        "limit": str(limit),
    }

    result = _make_api_request("NEWS_SENTIMENT", params)
    return _filter_news_by_date(result, start_date, curr_date)


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
