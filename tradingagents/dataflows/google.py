import logging
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List

import requests
from dateutil import parser as dateutil_parser
from dateutil.relativedelta import relativedelta

from .googlenews_utils import getNewsData

logger = logging.getLogger(__name__)


def _parse_google_news_date(date_str: str) -> datetime:
    if not date_str:
        return datetime.now()

    date_str = date_str.strip().lower()

    relative_patterns = [
        (r"(\d+)\s*(?:hour|hr)s?\s*ago", "hours"),
        (r"(\d+)\s*(?:minute|min)s?\s*ago", "minutes"),
        (r"(\d+)\s*(?:day)s?\s*ago", "days"),
        (r"(\d+)\s*(?:week)s?\s*ago", "weeks"),
        (r"(\d+)\s*(?:month)s?\s*ago", "months"),
    ]

    for pattern, unit in relative_patterns:
        match = re.search(pattern, date_str)
        if match:
            value = int(match.group(1))
            now = datetime.now()
            if unit == "hours":
                return now - timedelta(hours=value)
            elif unit == "minutes":
                return now - timedelta(minutes=value)
            elif unit == "days":
                return now - timedelta(days=value)
            elif unit == "weeks":
                return now - timedelta(weeks=value)
            elif unit == "months":
                return now - relativedelta(months=value)

    if "yesterday" in date_str:
        return datetime.now() - timedelta(days=1)

    try:
        return dateutil_parser.parse(date_str, fuzzy=True)
    except (ValueError, TypeError):
        return datetime.now()


def get_google_news(
    query: Annotated[str, "Query to search with"],
    curr_date: Annotated[str, "Curr date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    query = query.replace(" ", "+")

    start_date = datetime.strptime(curr_date, "%Y-%m-%d")
    before = start_date - relativedelta(days=look_back_days)
    before = before.strftime("%Y-%m-%d")

    news_results = getNewsData(query, before, curr_date)

    news_str = ""

    for news in news_results:
        news_str += (
            f"### {news['title']} (source: {news['source']}) \n\n{news['snippet']}\n\n"
        )

    if len(news_results) == 0:
        return ""

    return f"## {query} Google News, from {before} to {curr_date}:\n\n{news_str}"


def get_bulk_news_google(lookback_hours: int) -> list[dict[str, Any]]:
    end_date = datetime.now()
    start_date = end_date - timedelta(hours=lookback_hours)

    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    queries = [
        "stock market",
        "trading news",
        "earnings report",
    ]

    all_articles = []
    seen_titles = set()

    for query in queries:
        try:
            news_results = getNewsData(query.replace(" ", "+"), start_str, end_str)

            for news in news_results:
                title = news.get("title", "")
                if title and title not in seen_titles:
                    seen_titles.add(title)

                    date_str = news.get("date", "")
                    published_at = _parse_google_news_date(date_str)

                    article = {
                        "title": title,
                        "source": news.get("source", "Google News"),
                        "url": news.get("link", ""),
                        "published_at": published_at.isoformat(),
                        "content_snippet": news.get("snippet", "")[:500],
                    }
                    all_articles.append(article)

        except (TypeError, KeyError, AttributeError, requests.RequestException) as e:
            logger.debug("Google News search failed for query '%s': %s", query, e)
            continue

    return all_articles
