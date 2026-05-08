# tests/test_chart_endpoint.py
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


def _make_history(n=30):
    dates = pd.date_range("2026-04-01", periods=n, freq="B")
    return pd.DataFrame({
        "Close": [100.0 + i for i in range(n)],
        "Volume": [1_000_000 + i * 10_000 for i in range(n)],
        "Open": [99.0 + i for i in range(n)],
        "High": [101.0 + i for i in range(n)],
        "Low":  [98.0 + i for i in range(n)],
    }, index=dates)


@pytest.fixture
def client():
    from backend import app
    return TestClient(app)


class TestChartEndpoint:
    def test_returns_dates_close_volume(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(30)
            r = client.get("/api/tickers/NVDA/chart")
        assert r.status_code == 200
        data = r.json()
        assert "dates" in data
        assert "close" in data
        assert "volume" in data
        assert len(data["dates"]) == 30
        assert len(data["close"]) == 30
        assert len(data["volume"]) == 30

    def test_dates_are_iso_strings(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(5)
            r = client.get("/api/tickers/AAPL/chart")
        assert r.status_code == 200
        from datetime import datetime
        for d in r.json()["dates"]:
            datetime.strptime(d, "%Y-%m-%d")   # must not raise

    def test_empty_data_returns_404(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = pd.DataFrame()
            r = client.get("/api/tickers/DELISTED/chart")
        assert r.status_code == 404
        assert r.json()["error"] == "No data"

    def test_yfinance_exception_returns_404(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.side_effect = RuntimeError("network error")
            r = client.get("/api/tickers/BADINPUT/chart")
        assert r.status_code == 404
        assert r.json()["error"] == "No data"

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker") as mock_ticker:
            mock_ticker.return_value.history.return_value = _make_history(10)
            r = client.get("/api/tickers/nvda/chart")
        assert r.status_code == 200
        mock_ticker.assert_called_once_with("NVDA")
