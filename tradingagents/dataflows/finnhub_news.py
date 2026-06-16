from datetime import datetime, timedelta

from .config import get_config
from .finnhub_common import make_request
from .vendor_utils import format_json_section


def get_news(ticker, start_date, end_date) -> str:
    payload = make_request("company-news", {"symbol": ticker, "from": start_date, "to": end_date})
    limit = get_config()["news_article_limit"]
    return format_json_section(f"Finnhub Company News for {ticker}", payload[:limit])


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> str:
    start = datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
    payload = make_request("news", {"category": "general", "minId": 0})
    filtered = []
    for article in payload:
        published = article.get("datetime")
        if not published:
            continue
        if datetime.utcfromtimestamp(published) >= start:
            filtered.append(article)
        if len(filtered) >= limit:
            break
    return format_json_section("Finnhub Global Market News", filtered)
