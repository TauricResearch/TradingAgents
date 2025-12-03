import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from .alpha_vantage_common import _make_api_request, format_datetime_for_api

logger = logging.getLogger(__name__)

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
            logger.debug("Alpha Vantage JSON decode failed")
            return []

    if not isinstance(response, dict):
        logger.debug("Alpha Vantage response not a dict: %s", type(response))
        return []

    if "Information" in response:
        logger.debug("Alpha Vantage info message: %s", response.get("Information"))

    feed = response.get("feed", [])
    if not feed:
        logger.debug("Alpha Vantage feed empty. Keys in response: %s", list(response.keys()))

    articles = []
    for item in feed:
        try:
            time_published = item.get("time_published", "")
            if not time_published:
                continue

            try:
                published_at = datetime.strptime(time_published, "%Y%m%dT%H%M%S")
            except ValueError:
                continue

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
