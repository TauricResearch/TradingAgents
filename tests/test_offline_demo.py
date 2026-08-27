import pytest
from examples.offline_demo import run_offline_simulation


def test_offline_simulation_returns_decision():
    res = run_offline_simulation("AAPL", "2024-06-01")
    assert isinstance(res, dict)
    assert res["ticker"] == "AAPL"
    assert res["date"] == "2024-06-01"
    assert res["action"] in ("BUY", "SELL", "HOLD")
    assert 0 <= res["confidence"] <= 1.0
    assert "rationale" in res
