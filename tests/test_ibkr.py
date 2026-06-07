"""Offline tests for the IBKR adapter helpers (no TWS connection needed)."""

from __future__ import annotations

import pytest

from tradingagents.broker.base import OrderRequest, OrderStatus
from tradingagents.broker.ibkr import IBKRBroker, default_port, map_status, order_action

pytestmark = pytest.mark.unit


def test_status_mapping():
    assert map_status("Filled") is OrderStatus.FILLED
    assert map_status("Submitted") is OrderStatus.ACCEPTED
    assert map_status("PreSubmitted") is OrderStatus.ACCEPTED
    assert map_status("Cancelled") is OrderStatus.CANCELLED
    assert map_status("Inactive") is OrderStatus.REJECTED
    assert map_status("Whatever") is OrderStatus.PENDING


def test_order_action_and_default_port():
    assert order_action(OrderRequest("AAPL", "buy", 1)) == "BUY"
    assert order_action(OrderRequest("AAPL", "sell", 1)) == "SELL"
    assert default_port("paper") == 7497
    assert default_port("live") == 7496


def test_build_limit_and_market_orders():
    broker = IBKRBroker()
    limit = broker._order(OrderRequest("AAPL", "buy", 10, order_type="limit",
                                       limit_price=180.0, client_order_id="coid-1"))
    assert limit.action == "BUY"
    assert limit.orderType == "LMT"
    assert limit.lmtPrice == 180.0
    assert limit.orderRef == "coid-1"

    market = broker._order(OrderRequest("AAPL", "sell", 5, order_type="market"))
    assert market.action == "SELL"
    assert market.orderType == "MKT"


@pytest.mark.integration
def test_ibkr_connect_real():
    """Needs a running TWS/IB Gateway; skipped otherwise."""
    broker = IBKRBroker()
    try:
        acct = broker.get_account()
    except Exception as exc:  # pragma: no cover - needs the gateway
        pytest.skip(f"IBKR gateway unavailable: {exc}")
    finally:
        broker.disconnect()
    assert "cash" in acct
