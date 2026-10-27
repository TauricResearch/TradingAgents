"""Unit tests for the agentRobin brokerage adapter (mocked subprocess)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tradingagents.brokerages.agentrobin import (
    AgentRobinBridgeError,
    fetch_portfolio,
    list_accounts,
)
from tradingagents.portfolio import PortfolioContext


@pytest.mark.unit
def test_list_accounts_via_cli(tmp_path):
    root = tmp_path / "agentRobin"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "tradingagents_bridge.rb").write_text("# stub\n")
    payload = [
        {
            "account": "FakeAcct.01",
            "label": "paper",
            "paper": True,
            "live": False,
            "backend": "fake_broker",
            "broker": "FakeBroker",
        }
    ]

    with (
        patch.dict("os.environ", {"AGENTROBIN_ROOT": str(root)}, clear=False),
        patch("tradingagents.brokerages.agentrobin._bridge_url", return_value=None),
        patch(
            "tradingagents.brokerages.agentrobin.subprocess.run",
            return_value=type(
                "P",
                (),
                {"returncode": 0, "stdout": json.dumps(payload), "stderr": ""},
            )(),
        ),
    ):
        rows = list_accounts(sandbox_only=True)
    assert rows[0]["account"] == "FakeAcct.01"
    assert rows[0]["paper"] is True


@pytest.mark.unit
def test_fetch_portfolio_validates_context(tmp_path):
    root = tmp_path / "agentRobin"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "tradingagents_bridge.rb").write_text("# stub\n")
    book = {
        "cash": 1000.0,
        "currency": "USD",
        "positions": [{"ticker": "AAPL", "quantity": 5, "average_price": 10.0}],
    }

    with (
        patch.dict("os.environ", {"AGENTROBIN_ROOT": str(root)}, clear=False),
        patch("tradingagents.brokerages.agentrobin._bridge_url", return_value=None),
        patch(
            "tradingagents.brokerages.agentrobin.subprocess.run",
            return_value=type(
                "P",
                (),
                {"returncode": 0, "stdout": json.dumps(book), "stderr": ""},
            )(),
        ),
    ):
        ctx = fetch_portfolio("FakeAcct.01")
    assert isinstance(ctx, PortfolioContext)
    assert ctx.cash == 1000.0
    assert ctx.position_in("AAPL").quantity == 5


@pytest.mark.unit
def test_fetch_portfolio_raises_on_cli_error(tmp_path):
    root = tmp_path / "agentRobin"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "tradingagents_bridge.rb").write_text("# stub\n")

    with (
        patch.dict("os.environ", {"AGENTROBIN_ROOT": str(root)}, clear=False),
        patch("tradingagents.brokerages.agentrobin._bridge_url", return_value=None),
        patch(
            "tradingagents.brokerages.agentrobin.subprocess.run",
            return_value=type(
                "P",
                (),
                {"returncode": 2, "stdout": "", "stderr": "boom"},
            )(),
        ),
        pytest.raises(AgentRobinBridgeError, match="exit 2"),
    ):
        fetch_portfolio("FakeAcct.01")
