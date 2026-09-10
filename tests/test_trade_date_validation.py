import pytest

import tradingagents.graph.trading_graph as trading_graph


def test_propagate_rejects_future_trade_date_before_running(monkeypatch):
    monkeypatch.setattr(trading_graph, "get_current_date", lambda: "2026-09-10")
    graph = object.__new__(trading_graph.TradingAgentsGraph)

    with pytest.raises(ValueError, match="cannot be in the future"):
        graph.propagate("AAPL", "2026-09-11")


def test_trade_date_validation_rejects_non_canonical_values():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        trading_graph._validate_trade_date("2026-9-10")


def test_trade_date_validation_accepts_today(monkeypatch):
    monkeypatch.setattr(trading_graph, "get_current_date", lambda: "2026-09-10")

    assert trading_graph._validate_trade_date("2026-09-10") == "2026-09-10"
