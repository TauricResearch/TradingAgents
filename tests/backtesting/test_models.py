# tests/backtesting/test_models.py
from datetime import datetime
import pytest

from tradingagents.backtesting.models import (
    DIRECTION_MAP, BacktestResult, derive_direction,
)


@pytest.mark.unit
class TestDeriveDirection:
    def test_buy(self):
        assert derive_direction("Buy") == +1

    def test_overweight(self):
        assert derive_direction("Overweight") == +1

    def test_hold(self):
        assert derive_direction("Hold") == 0

    def test_underweight(self):
        assert derive_direction("Underweight") == -1

    def test_sell(self):
        assert derive_direction("Sell") == -1

    def test_none_rating_returns_none(self):
        assert derive_direction(None) is None

    def test_unknown_rating_returns_none_not_zero(self):
        # Unknown string must return None — not 0 (which means Hold)
        assert derive_direction("StrongBuy") is None


@pytest.mark.unit
class TestBacktestResult:
    def test_defaults(self):
        r = BacktestResult(ticker="NVDA", trade_date="2024-01-15")
        assert r.rating is None
        assert r.direction is None
        assert r.error is None
        assert r.raw_output == ""
        assert r.run_duration_seconds == 0.0

    def test_trade_date_iso_parseable(self):
        r = BacktestResult(ticker="AAPL", trade_date="2024-06-01")
        # Must not raise — enforces ISO-8601 format contract
        datetime.strptime(r.trade_date, "%Y-%m-%d")

    def test_error_result_has_no_rating(self):
        r = BacktestResult(ticker="TSLA", trade_date="2024-03-01", error="timeout")
        assert r.rating is None
        assert r.direction is None


def test_public_exports():
    from tradingagents import backtesting
    assert hasattr(backtesting, "BacktestEngine")
    assert hasattr(backtesting, "BacktestReport")
    assert hasattr(backtesting, "BacktestResult")
    assert hasattr(backtesting, "BacktestSummary")
    assert hasattr(backtesting, "DIRECTION_MAP")
    assert hasattr(backtesting, "derive_direction")
