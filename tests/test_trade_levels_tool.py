import json

import pytest

from tradingagents.agents.utils.trade_levels_tools import suggest_trade_levels


@pytest.mark.unit
def test_suggest_trade_levels_returns_json(monkeypatch):
    csv = "\n".join(
        [
            "# header",
            "Date,Open,High,Low,Close,Volume",
            "2026-01-01,100,105,99,104,1000",
            "2026-01-02,104,106,102,105,1200",
            "2026-01-03,105,108,104,107,1300",
            "2026-01-04,107,110,106,109,1400",
            "2026-01-05,109,111,108,110,1500",
            "2026-01-06,110,112,109,111,1600",
            "2026-01-07,111,113,110,112,1700",
            "2026-01-08,112,114,111,113,1800",
            "2026-01-09,113,115,112,114,1900",
            "2026-01-10,114,116,113,115,2000",
            "2026-01-11,115,117,114,116,2100",
            "2026-01-12,116,118,115,117,2200",
            "2026-01-13,117,119,116,118,2300",
            "2026-01-14,118,120,117,119,2400",
            "2026-01-15,119,121,118,120,2500",
        ]
    )

    def _fake_route(method, *args, **kwargs):
        assert method == "get_stock_data"
        return csv

    monkeypatch.setattr("tradingagents.agents.utils.trade_levels_tools.route_to_vendor", _fake_route)
    out = suggest_trade_levels.invoke(
        {
            "symbol": "AAPL",
            "curr_date": "2026-01-15",
            "look_back_days": 30,
            "swing_window": 5,
            "atr_period": 3,
            "rr": 2.0,
            "direction": "long",
        }
    )
    payload = json.loads(out)
    assert payload["symbol"] == "AAPL"
    assert payload["bias"] == "long"
    assert payload["regime"] in ("trend", "range", "unknown")
    assert "rr_target" in payload
    assert isinstance(payload["entry_price"], float)
    assert isinstance(payload["stop_loss"], float)
    assert isinstance(payload["take_profit"], float)
    assert payload["take_profit_2"] == payload["take_profit"]
