from __future__ import annotations

import pandas as pd
import pytest


@pytest.mark.unit
def test_fetch_returns_normalizes_symbol(monkeypatch):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    seen = []

    class FakeTicker:
        def __init__(self, symbol):
            seen.append(symbol)

        def history(self, **kwargs):
            return pd.DataFrame({"Close": [100, 101, 102, 103, 104, 105, 106]})

    monkeypatch.setattr("tradingagents.graph.trading_graph.yf.Ticker", FakeTicker)
    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)

    raw, alpha, days = TradingAgentsGraph._fetch_returns(
        graph,
        "XAUUSD",
        "2024-01-02",
        benchmark="SPY",
    )

    assert seen[0] == "GC=F"
    assert seen[1] == "SPY"
    assert raw is not None
    assert alpha == pytest.approx(0.0)
    assert days == 5
