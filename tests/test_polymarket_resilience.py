"""Prediction-market data resilience:

Part A — Polymarket trips a per-session circuit breaker on a *hard* network
failure (DNS/connection) so it stops re-hitting an unreachable host once per
topic, but keeps retrying *transient* failures (timeout / HTTP error).

Part B — A category configured "off" routes to a graceful disabled sentinel
instead of raising or fabricating data.
"""

from __future__ import annotations

import copy
from unittest.mock import patch

import pytest
import requests

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import interface, polymarket


@pytest.fixture(autouse=True)
def _reset_breaker():
    """The breaker is process-global; reset it around every test."""
    polymarket._HOST_UNREACHABLE = False
    yield
    polymarket._HOST_UNREACHABLE = False


# --------------------------------------------------------------------------- #
# Part A — circuit breaker
# --------------------------------------------------------------------------- #
@pytest.mark.unit
def test_hard_failure_trips_breaker_and_skips_repeat_calls():
    """A ConnectionError trips the breaker; later topics skip the network call."""
    with patch.object(
        polymarket, "_request", side_effect=requests.ConnectionError("dns fail")
    ) as mock_req:
        first = polymarket.get_prediction_markets("Fed rate cut")
        second = polymarket.get_prediction_markets("recession 2026")
        third = polymarket.get_prediction_markets("semiconductor")

    # The host is only actually contacted once — the breaker short-circuits the rest.
    assert mock_req.call_count == 1
    assert polymarket._HOST_UNREACHABLE is True
    assert "unavailable" in first.lower()
    assert "earlier this session" in second.lower()
    assert "earlier this session" in third.lower()


@pytest.mark.unit
def test_transient_failure_does_not_trip_breaker():
    """A timeout is transient — keep trying subsequent topics, breaker stays open."""
    with patch.object(
        polymarket, "_request", side_effect=requests.Timeout("slow")
    ) as mock_req:
        polymarket.get_prediction_markets("Fed rate cut")
        polymarket.get_prediction_markets("recession 2026")

    # Both topics were attempted; the breaker did NOT trip.
    assert mock_req.call_count == 2
    assert polymarket._HOST_UNREACHABLE is False


@pytest.mark.unit
def test_success_path_unaffected():
    """A normal response still parses (breaker logic doesn't intercept success)."""
    payload = {
        "events": [
            {
                "markets": [
                    {
                        "question": "Fed cuts in July?",
                        "closed": False,
                        "endDate": "2030-07-31T00:00:00Z",
                        "outcomes": '["Yes", "No"]',
                        "outcomePrices": '["0.76", "0.24"]',
                        "volumeNum": 1_000_000,
                    }
                ]
            }
        ]
    }
    with patch.object(polymarket, "_request", return_value=payload):
        out = polymarket.get_prediction_markets("Fed rate cut")
    assert "Fed cuts in July?" in out
    assert "76%" in out
    assert polymarket._HOST_UNREACHABLE is False


# --------------------------------------------------------------------------- #
# Part B — "off" switch in route_to_vendor
# --------------------------------------------------------------------------- #
@pytest.mark.unit
@pytest.mark.parametrize("off_value", ["off", "none", "disabled", "", "OFF"])
def test_disabled_category_returns_sentinel_without_calling_vendor(off_value):
    """Setting a category to an off-sentinel skips the source gracefully.

    The disabled check returns before the routing table is consulted, so we
    additionally swap the impl for one that fails loudly if ever invoked.
    """
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config_module._config["data_vendors"]["prediction_markets"] = off_value

    def _boom(*_a, **_k):
        raise AssertionError("vendor impl should not be called when disabled")

    with patch.dict(
        interface.VENDOR_METHODS["get_prediction_markets"], {"polymarket": _boom}
    ):
        out = interface.route_to_vendor("get_prediction_markets", "Fed rate cut")

    assert "disabled in configuration" in out.lower()
    assert "prediction_markets" in out


@pytest.mark.unit
def test_enabled_category_still_routes_normally():
    """A normally-configured category is unaffected by the disable check.

    Patch the routing-table entry itself — ``interface`` binds the vendor
    function into ``VENDOR_METHODS`` at import time, so patching the source
    module's attribute would not be seen by the router.
    """
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    config_module._config["data_vendors"]["prediction_markets"] = "polymarket"

    with patch.dict(
        interface.VENDOR_METHODS["get_prediction_markets"],
        {"polymarket": lambda *a, **k: "ROUTED OK"},
    ):
        out = interface.route_to_vendor("get_prediction_markets", "Fed rate cut")

    assert out == "ROUTED OK"
