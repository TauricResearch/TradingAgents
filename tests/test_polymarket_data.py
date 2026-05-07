"""Unit tests for polymarket_data Gamma REST client."""

from unittest.mock import patch, MagicMock
import pytest
import httpx

from tradingagents.dataflows.polymarket_data import (
    get_open_markets,
    get_market_by_id,
    GammaAPIError,
)


@pytest.mark.unit
def test_get_open_markets_parses_response():
    """Happy path: Gamma returns a list of markets, function parses cleanly."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {
            "id": "0x123",
            "question": "Will X happen by Y date?",
            "outcomePrices": '["0.65", "0.35"]',
            "volume": "12345.67",
            "endDate": "2026-12-31T00:00:00Z",
            "active": True,
            "closed": False,
        }
    ]
    fake_response.raise_for_status = MagicMock()

    with patch("tradingagents.dataflows.polymarket_data.httpx.get", return_value=fake_response):
        markets = get_open_markets(limit=10)

    assert len(markets) == 1
    assert markets[0]["id"] == "0x123"
    assert markets[0]["question"] == "Will X happen by Y date?"
    assert markets[0]["yes_price"] == 0.65
    assert markets[0]["volume"] == 12345.67


@pytest.mark.unit
def test_empty_markets_returns_empty_list():
    """No active markets returns an empty list, no crash."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = []
    fake_response.raise_for_status = MagicMock()

    with patch("tradingagents.dataflows.polymarket_data.httpx.get", return_value=fake_response):
        markets = get_open_markets(limit=10)

    assert markets == []


@pytest.mark.unit
def test_non_200_raises_clear_error():
    """API returns 500 raises GammaAPIError with status code."""
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error",
        request=MagicMock(),
        response=fake_response,
    )

    with patch("tradingagents.dataflows.polymarket_data.httpx.get", return_value=fake_response):
        with pytest.raises(GammaAPIError) as exc_info:
            get_open_markets(limit=10)

    assert "500" in str(exc_info.value) or "Server Error" in str(exc_info.value)


@pytest.mark.unit
def test_get_market_by_id_returns_normalized_dict():
    """get_market_by_id returns a single market with yes_price extracted."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "id": "0xabc",
        "question": "Single market test",
        "outcomePrices": '["0.42", "0.58"]',
        "volume": "999.00",
        "endDate": "2026-06-01T00:00:00Z",
        "active": True,
        "closed": False,
    }
    fake_response.raise_for_status = MagicMock()

    with patch("tradingagents.dataflows.polymarket_data.httpx.get", return_value=fake_response):
        market = get_market_by_id("0xabc")

    assert market["id"] == "0xabc"
    assert market["yes_price"] == 0.42


@pytest.mark.unit
def test_malformed_outcome_prices_excluded():
    """Markets with malformed outcomePrices are filtered out, not crashed on."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = [
        {
            "id": "0xgood",
            "question": "Good market",
            "outcomePrices": '["0.65", "0.35"]',
            "volume": "1000",
            "endDate": "2026-12-31T00:00:00Z",
            "active": True,
            "closed": False,
        },
        {
            "id": "0xbad",
            "question": "Bad market",
            "outcomePrices": "not-json",
            "volume": "1000",
            "endDate": "2026-12-31T00:00:00Z",
            "active": True,
            "closed": False,
        },
    ]
    fake_response.raise_for_status = MagicMock()

    with patch("tradingagents.dataflows.polymarket_data.httpx.get", return_value=fake_response):
        markets = get_open_markets(limit=10)

    ids = [m["id"] for m in markets]
    assert "0xgood" in ids
    assert "0xbad" not in ids


@pytest.mark.integration
def test_smoke_gamma_returns_active_markets():
    """Real HTTP call to Gamma. Skipped in unit-only runs."""
    markets = get_open_markets(limit=5)
    assert isinstance(markets, list)
    assert len(markets) >= 1
    assert "id" in markets[0]
    assert "question" in markets[0]
    assert "yes_price" in markets[0]
    assert 0.0 <= markets[0]["yes_price"] <= 1.0
