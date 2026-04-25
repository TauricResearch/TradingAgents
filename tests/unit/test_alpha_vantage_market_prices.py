from unittest.mock import MagicMock, patch

from tradingagents.dataflows.alpha_vantage_common import _make_api_request
from tradingagents.dataflows.alpha_vantage_market_prices import (
    get_bitcoin_price_alpha_vantage,
    get_gold_price_alpha_vantage,
    get_oil_prices_alpha_vantage,
)


def test_get_gold_price_alpha_vantage_formats_gold_spot():
    payload = '{"nominal":"XAUUSD","timestamp":"2026-03-30 18:55:18","price":"4509.767931852"}'

    with patch(
        "tradingagents.dataflows.alpha_vantage_market_prices._make_api_request",
        return_value=payload,
    ):
        result = get_gold_price_alpha_vantage()

    assert result.startswith("# Gold Price Snapshot")
    assert "XAUUSD" in result
    assert "Gold" in result


def test_get_oil_prices_alpha_vantage_formats_wti_and_brent():
    def fake_request(function_name: str, params: dict) -> str:
        if function_name == "WTI":
            return '{"name":"Crude Oil Prices WTI","interval":"daily","data":[{"date":"2026-03-30","value":"89.33"},{"date":"2026-03-29","value":"88.11"}]}'
        if function_name == "BRENT":
            return '{"name":"Crude Oil Prices Brent","interval":"daily","data":[{"date":"2026-03-30","value":"103.79"},{"date":"2026-03-29","value":"101.79"}]}'
        raise AssertionError(function_name)

    with patch(
        "tradingagents.dataflows.alpha_vantage_market_prices._make_api_request",
        side_effect=fake_request,
    ):
        result = get_oil_prices_alpha_vantage()

    assert result.startswith("# Oil Price Snapshot")
    assert "WTI Crude" in result
    assert "Brent Crude" in result
    assert "+2.00" in result


def test_get_bitcoin_price_alpha_vantage_formats_rate():
    payload = (
        '{"Realtime Currency Exchange Rate":{"1. From_Currency Code":"BTC",'
        '"3. To_Currency Code":"USD","5. Exchange Rate":"66526.32000000"}}'
    )

    with patch(
        "tradingagents.dataflows.alpha_vantage_market_prices._make_api_request",
        return_value=payload,
    ):
        result = get_bitcoin_price_alpha_vantage()

    assert result.startswith("# Bitcoin Price Snapshot")
    assert "BTC/USD" in result
    assert "Bitcoin" in result


def test_make_api_request_omits_source_for_demo_key():
    response = MagicMock()
    response.status_code = 200
    response.text = '{"name":"Crude Oil Prices WTI","interval":"monthly","data":[{"date":"2026-02-01","value":"64.51"}]}'
    response.raise_for_status = MagicMock()

    with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
        with patch(
            "tradingagents.dataflows.alpha_vantage_common.requests.get", return_value=response
        ) as mock_get:
            _make_api_request("WTI", {"interval": "monthly"})

    params = mock_get.call_args.kwargs["params"]
    assert params["function"] == "WTI"
    assert params["apikey"] == "demo"
    assert "source" not in params
