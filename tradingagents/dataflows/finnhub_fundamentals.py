from datetime import datetime, timedelta

from .finnhub_common import make_request
from .vendor_utils import format_json_section


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    profile = make_request("stock/profile2", {"symbol": ticker})
    metrics = make_request("stock/metric", {"symbol": ticker, "metric": "all"})

    if curr_date:
        current = datetime.strptime(curr_date, "%Y-%m-%d")
    else:
        current = datetime.utcnow()
    start = (current - timedelta(days=31)).strftime("%Y-%m-%d")
    end = (current + timedelta(days=31)).strftime("%Y-%m-%d")

    earnings = make_request("calendar/earnings", {"symbol": ticker, "from": start, "to": end})
    insider = make_request("stock/insider-transactions", {"symbol": ticker, "from": start, "to": end})

    return "\n\n".join(
        [
            format_json_section("Finnhub Company Profile", profile),
            format_json_section("Finnhub Basic Financial Metrics", metrics),
            format_json_section("Finnhub Upcoming / Recent Earnings", earnings),
            format_json_section("Finnhub Recent Insider Transactions", insider),
        ]
    )


def get_insider_transactions(symbol: str):
    return make_request("stock/insider-transactions", {"symbol": symbol})
