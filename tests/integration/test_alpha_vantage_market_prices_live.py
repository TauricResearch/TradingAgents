"""Live integration tests for Alpha Vantage market-price endpoints using demo.

These tests intentionally exercise the production Alpha Vantage request helper.
The ``demo`` key currently exposes monthly oil series for ``WTI`` and ``BRENT``
but not the bitcoin or gold endpoints used by the scanner.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from tradingagents.dataflows.alpha_vantage_common import _make_api_request

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket()]


def _parse_json_response(raw: str, context: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"{context} returned non-JSON payload: {raw[:200]!r}") from exc


@pytest.mark.integration
def test_alpha_vantage_demo_monthly_oil_endpoints_live():
    with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
        for function_name in ("WTI", "BRENT"):
            raw = _make_api_request(function_name, {"interval": "monthly"})
            payload = _parse_json_response(raw, function_name)
            if payload.get("data"):
                assert payload.get("name")
                assert payload.get("interval") == "monthly"
                data = payload.get("data")
                assert isinstance(data, list)
                latest = data[0]
                assert latest.get("date")
                assert float(latest["value"]) > 0
            else:
                info = payload.get("Information", "")
                assert "demo" in info.lower()


@pytest.mark.integration
def test_alpha_vantage_demo_gold_and_bitcoin_endpoints_are_not_exposed():
    with patch.dict("os.environ", {"ALPHA_VANTAGE_API_KEY": "demo"}):
        responses = {
            "CURRENCY_EXCHANGE_RATE/BTCUSD": _make_api_request(
                "CURRENCY_EXCHANGE_RATE",
                {"from_currency": "BTC", "to_currency": "USD"},
            ),
            "GOLD_SILVER_SPOT/GOLD": _make_api_request(
                "GOLD_SILVER_SPOT",
                {"symbol": "GOLD"},
            ),
        }

    for context, raw in responses.items():
        payload = _parse_json_response(raw, context)
        info = payload.get("Information", "")
        assert "demo" in info.lower()
