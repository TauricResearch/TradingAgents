# tests/test_trade_endpoint.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_portfolio():
    """Give each test a clean in-memory portfolio."""
    import backend
    from portfolio import Portfolio
    backend.portfolio = Portfolio()
    backend.portfolio.cash = 100_000.0
    yield


@pytest.fixture
def client():
    from backend import app
    return TestClient(app)


def _mock_price(price: float):
    m = MagicMock()
    m.fast_info = {"last_price": price}
    return m


class TestGetPortfolio:
    def test_empty_portfolio(self, client):
        r = client.get("/api/portfolio")
        assert r.status_code == 200
        data = r.json()
        assert data["cash"] == pytest.approx(100_000.0)
        assert data["positions"] == {}
        assert data["total_value"] == pytest.approx(100_000.0)

    def test_with_position(self, client):
        import backend
        backend.portfolio.positions = {"NVDA": {"shares": 10.0, "avg_cost": 100.0}}
        with patch("backend.yf.Ticker", return_value=_mock_price(120.0)):
            r = client.get("/api/portfolio")
        data = r.json()
        assert "NVDA" in data["positions"]
        assert data["positions"]["NVDA"]["current_price"] == pytest.approx(120.0)
        assert data["total_value"] == pytest.approx(100_000.0 + 1_200.0)


class TestGetPrice:
    def test_returns_price(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(134.52)):
            r = client.get("/api/price/NVDA")
        assert r.status_code == 200
        assert r.json()["price"] == pytest.approx(134.52)
        assert r.json()["ticker"] == "NVDA"

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.return_value = _mock_price(100.0)
            client.get("/api/price/nvda")
        mock_t.assert_called_once_with("NVDA")

    def test_price_unavailable_returns_404(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.side_effect = Exception("network error")
            r = client.get("/api/price/BADINPUT")
        assert r.status_code == 404
        assert r.json()["error"] == "Price unavailable"


class TestPostTrade:
    def test_buy_happy_path(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 1000.0})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "portfolio_update"
        assert "NVDA" in data["positions"]
        assert data["cash"] == pytest.approx(99_000.0)
        assert data["last_trade"]["side"] == "BUY"

    def test_sell_happy_path(self, client):
        import backend
        backend.portfolio.positions = {"NVDA": {"shares": 10.0, "avg_cost": 100.0}}
        backend.portfolio.cash = 99_000.0
        with patch("backend.yf.Ticker", return_value=_mock_price(110.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "SELL", "amount_usd": 500.0})
        assert r.status_code == 200
        data = r.json()
        assert data["last_trade"]["side"] == "SELL"

    def test_buy_insufficient_cash(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 200_000.0})
        assert r.status_code == 400
        assert r.json()["error"] == "Insufficient cash"

    def test_sell_no_position(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "SELL", "amount_usd": 500.0})
        assert r.status_code == 400
        assert r.json()["error"] == "No position"

    def test_price_unavailable_returns_503(self, client):
        with patch("backend.yf.Ticker") as mock_t:
            mock_t.side_effect = Exception("network error")
            r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 1000.0})
        assert r.status_code == 503

    def test_invalid_side_returns_400(self, client):
        r = client.post("/api/trade", json={"ticker": "NVDA", "side": "HOLD", "amount_usd": 1000.0})
        assert r.status_code == 400

    def test_zero_amount_returns_400(self, client):
        r = client.post("/api/trade", json={"ticker": "NVDA", "side": "BUY", "amount_usd": 0.0})
        assert r.status_code == 400

    def test_ticker_uppercased(self, client):
        with patch("backend.yf.Ticker", return_value=_mock_price(100.0)):
            r = client.post("/api/trade", json={"ticker": "nvda", "side": "BUY", "amount_usd": 500.0})
        assert r.status_code == 200
        assert "NVDA" in r.json()["positions"]
