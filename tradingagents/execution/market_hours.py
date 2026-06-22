"""Regular-session guard via the Toss market calendar.

The Toss account is for short-term trading and the user only wants to trade
during regular market hours (tighter spreads, no after-hours penalty). This
checks whether a market's regular session is currently open so the order flow
can refuse out-of-hours submissions before hitting the API's
``order-hours-closed`` rejection.
"""

from datetime import datetime, timezone

from tradingagents.dataflows.toss_client import TossClient


def _regular_node(market: str) -> dict:
    market = market.upper()
    result = TossClient.instance().request(
        "GET", f"/api/v1/market-calendar/{market}"
    )["result"]
    today = result["today"]
    # KR nests sessions under "integrated"; US exposes them at top level.
    if market == "KR":
        return today["integrated"]["regularMarket"]
    return today["regularMarket"]


def regular_session_open(market: str):
    """Return (is_open, start_iso, end_iso) for the market's regular session today."""
    node = _regular_node(market)
    start = datetime.fromisoformat(node["startTime"])
    end = datetime.fromisoformat(node["endTime"])
    now = datetime.now(timezone.utc)
    return start <= now <= end, node["startTime"], node["endTime"]
