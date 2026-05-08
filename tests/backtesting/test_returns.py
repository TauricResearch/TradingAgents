# tests/backtesting/test_returns.py
import pandas as pd
import pytest
from unittest.mock import MagicMock, patch


def _make_prices(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range(start="2024-01-15", periods=len(prices), freq="B")
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.mark.unit
class TestFetchReturns:
    def test_basic_long_gain(self):
        from tradingagents.backtesting.returns import fetch_returns

        stock = _make_prices([100.0, 110.0, 108.0])
        spy = _make_prices([400.0, 404.0, 402.0])

        def side_effect(sym):
            m = MagicMock()
            m.history.return_value = stock if sym == "NVDA" else spy
            return m

        with patch("tradingagents.backtesting.returns.yf.Ticker", side_effect=side_effect):
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=1)

        assert raw == pytest.approx(0.10)          # (110-100)/100
        assert alpha == pytest.approx(0.10 - 0.01) # stock 10% - SPY 1%
        assert days == 1

    def test_insufficient_stock_data_returns_none(self):
        from tradingagents.backtesting.returns import fetch_returns

        with patch("tradingagents.backtesting.returns.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame()
            raw, alpha, days = fetch_returns("DELISTED", "2024-01-15", holding_days=5)

        assert (raw, alpha, days) == (None, None, None)

    def test_network_exception_returns_none(self):
        from tradingagents.backtesting.returns import fetch_returns

        with patch("tradingagents.backtesting.returns.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = Exception("connection refused")
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=5)

        assert (raw, alpha, days) == (None, None, None)

    def test_actual_days_clamped_to_available_data(self):
        from tradingagents.backtesting.returns import fetch_returns

        # Only 2 rows available — actual_days must be min(holding_days, len-1)
        stock = _make_prices([100.0, 105.0])
        spy = _make_prices([400.0, 402.0])

        def side_effect(sym):
            m = MagicMock()
            m.history.return_value = stock if sym == "NVDA" else spy
            return m

        with patch("tradingagents.backtesting.returns.yf.Ticker", side_effect=side_effect):
            raw, alpha, days = fetch_returns("NVDA", "2024-01-15", holding_days=10)

        assert days == 1   # only 1 usable interval in 2-row series
