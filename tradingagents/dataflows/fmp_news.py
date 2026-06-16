from datetime import datetime, timedelta

from .config import get_config
from .fmp_common import make_request
from .vendor_utils import format_json_section


def get_news(ticker, start_date, end_date) -> str:
    config = get_config()
    limit = config["news_article_limit"]
    payload = make_request(
        "news/stock",
        {"symbols": ticker, "from": start_date, "to": end_date, "limit": limit},
    )
    return format_json_section(f"FMP Stock News for {ticker}", payload)


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> str:
    start_date = (
        datetime.strptime(curr_date, "%Y-%m-%d") - timedelta(days=look_back_days)
    ).strftime("%Y-%m-%d")
    payload = make_request(
        "news/general",
        {"from": start_date, "to": curr_date, "limit": limit},
    )
    return format_json_section("FMP Global Market News", payload)
