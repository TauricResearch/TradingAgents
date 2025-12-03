import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .alpha_vantage_common import _make_api_request, format_datetime_for_api

def get_news(ticker, start_date, end_date) -> dict[str, str] | str:
    params = {
        "tickers": ticker,
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "sort": "LATEST",
        "limit": "50",
    }

    return _make_api_request("NEWS_SENTIMENT", params)

def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    params = {
        "symbol": symbol,
    }

    return _make_api_request("INSIDER_TRANSACTIONS", params)


def get_bulk_news_alpha_vantage(lookback_hours: int) -> List[Dict[str, Any]]:
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=lookback_hours)

    params = {
        "time_from": format_datetime_for_api(start_date),
        "time_to": format_datetime_for_api(end_date),
        "sort": "LATEST",
        "limit": "200",
        "topics": "financial_markets,earnings,economy_fiscal,economy_monetary,mergers_and_acquisitions",
    }

    response = _make_api_request("NEWS_SENTIMENT", params)

    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return []

    if not isinstance(response, dict):
        return []

    feed = response.get("feed", [])

    articles = []
    for item in feed:
        try:
            time_published = item.get("time_published", "")
            if time_published:
                try:
                    published_at = datetime.strptime(time_published, "%Y%m%dT%H%M%S")
                except ValueError:
                    published_at = datetime.now()
            else:
                published_at = datetime.now()

            article = {
                "title": item.get("title", ""),
                "source": item.get("source", ""),
                "url": item.get("url", ""),
                "published_at": published_at.isoformat(),
                "content_snippet": item.get("summary", "")[:500],
            }
            articles.append(article)
        except Exception:
            continue

    return articles
