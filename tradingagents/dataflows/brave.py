import logging
import os
import time
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/news/search"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


def get_api_key() -> str:
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        raise ValueError("BRAVE_API_KEY environment variable is not set.")
    return api_key


def _make_request_with_retry(url: str, headers: Dict, params: Dict, max_retries: int = MAX_RETRIES) -> requests.Response:
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", RETRY_BACKOFF * (attempt + 1)))
                logger.debug("Brave rate limited, waiting %ds before retry %d/%d", retry_after, attempt + 1, max_retries)
                time.sleep(retry_after)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout as e:
            last_exception = e
            logger.debug("Brave request timeout, retry %d/%d", attempt + 1, max_retries)
            time.sleep(RETRY_BACKOFF * (attempt + 1))
        except requests.exceptions.ConnectionError as e:
            last_exception = e
            logger.debug("Brave connection error, retry %d/%d", attempt + 1, max_retries)
            time.sleep(RETRY_BACKOFF * (attempt + 1))
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code >= 500:
                last_exception = e
                logger.debug("Brave server error %d, retry %d/%d", e.response.status_code, attempt + 1, max_retries)
                time.sleep(RETRY_BACKOFF * (attempt + 1))
            else:
                raise
    raise last_exception if last_exception else requests.exceptions.RequestException("Max retries exceeded")


def get_bulk_news_brave(lookback_hours: int) -> List[Dict[str, Any]]:
    try:
        api_key = get_api_key()
    except ValueError as e:
        logger.debug("Brave API key not configured: %s", e)
        return []

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }

    queries = [
        "stock market news",
        "earnings report",
        "merger acquisition",
        "company financial news",
        "trading stocks",
    ]

    all_articles = []
    seen_urls = set()

    if lookback_hours <= 24:
        freshness = "pd"
    elif lookback_hours <= 168:
        freshness = "pw"
    else:
        freshness = "pm"

    for query in queries:
        try:
            params = {
                "q": query,
                "count": 20,
                "freshness": freshness,
            }

            response = _make_request_with_retry(BRAVE_SEARCH_URL, headers, params)

            data = response.json()
            results = data.get("results", [])

            for item in results:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)

                    age = item.get("age", "")
                    published_at = _parse_brave_age(age)

                    article = {
                        "title": item.get("title", ""),
                        "source": item.get("meta_url", {}).get("netloc", "Brave News"),
                        "url": url,
                        "published_at": published_at.isoformat(),
                        "content_snippet": item.get("description", "")[:500],
                    }
                    all_articles.append(article)

        except requests.exceptions.HTTPError as e:
            logger.debug("Brave search HTTP error for '%s': %s", query, e)
            continue
        except requests.exceptions.Timeout as e:
            logger.debug("Brave search timeout for '%s': %s", query, e)
            continue
        except requests.exceptions.RequestException as e:
            logger.debug("Brave search request failed for '%s': %s", query, e)
            continue
        except Exception as e:
            logger.debug("Brave search failed for query '%s': %s", query, e)
            continue

    logger.debug("Brave returned %d articles", len(all_articles))
    return all_articles


def _parse_brave_age(age_str: str) -> datetime:
    now = datetime.now()
    if not age_str:
        return now

    age_str = age_str.lower()
    try:
        if "hour" in age_str:
            hours = int("".join(filter(str.isdigit, age_str)) or "1")
            return now - timedelta(hours=hours)
        elif "day" in age_str:
            days = int("".join(filter(str.isdigit, age_str)) or "1")
            return now - timedelta(days=days)
        elif "week" in age_str:
            weeks = int("".join(filter(str.isdigit, age_str)) or "1")
            return now - timedelta(weeks=weeks)
        elif "minute" in age_str:
            minutes = int("".join(filter(str.isdigit, age_str)) or "1")
            return now - timedelta(minutes=minutes)
    except (ValueError, TypeError):
        pass

    return now
