import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_BACKOFF = 1.0


def get_api_key() -> str:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise ValueError("TAVILY_API_KEY environment variable is not set.")
    return api_key


def _search_with_retry(client, query: str, search_depth: str, topic: str, time_range: str, max_results: int, max_retries: int = MAX_RETRIES) -> Dict[str, Any]:
    last_exception = None
    for attempt in range(max_retries):
        try:
            response = client.search(
                query=query,
                search_depth=search_depth,
                topic=topic,
                time_range=time_range,
                max_results=max_results,
            )
            return response
        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "limit" in error_str or "429" in error_str:
                wait_time = RETRY_BACKOFF * (attempt + 1) * 2
                print(f"DEBUG: Tavily rate limited, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                last_exception = e
            elif "timeout" in error_str or "timed out" in error_str:
                wait_time = RETRY_BACKOFF * (attempt + 1)
                print(f"DEBUG: Tavily timeout, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                last_exception = e
            elif "connection" in error_str or "network" in error_str:
                wait_time = RETRY_BACKOFF * (attempt + 1)
                print(f"DEBUG: Tavily connection error, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                time.sleep(wait_time)
                last_exception = e
            else:
                raise
    raise last_exception if last_exception else Exception("Max retries exceeded")


def get_bulk_news_tavily(lookback_hours: int) -> List[Dict[str, Any]]:
    if not TAVILY_AVAILABLE:
        print("DEBUG: Tavily library not installed")
        return []

    try:
        client = TavilyClient(api_key=get_api_key())
    except ValueError as e:
        print(f"DEBUG: Tavily API key not configured: {e}")
        return []

    queries = [
        "stock market news today",
        "earnings report announcement",
        "merger acquisition deal",
        "IPO stock market",
        "company financial results",
    ]

    days = max(1, lookback_hours // 24)
    if lookback_hours <= 24:
        time_range = "day"
    elif lookback_hours <= 168:
        time_range = "week"
    else:
        time_range = "month"

    all_articles = []
    seen_urls = set()

    for query in queries:
        try:
            response = _search_with_retry(
                client=client,
                query=query,
                search_depth="advanced",
                topic="news",
                time_range=time_range,
                max_results=10,
            )

            results = response.get("results", [])
            for item in results:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)

                    published_date = item.get("published_date")
                    if published_date:
                        try:
                            published_at = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            published_at = datetime.now()
                    else:
                        published_at = datetime.now()

                    article = {
                        "title": item.get("title", ""),
                        "source": "Tavily",
                        "url": url,
                        "published_at": published_at.isoformat(),
                        "content_snippet": item.get("content", "")[:500],
                    }
                    all_articles.append(article)

        except Exception as e:
            print(f"DEBUG: Tavily search failed for query '{query}': {e}")
            continue

    print(f"DEBUG: Tavily returned {len(all_articles)} articles")
    return all_articles
