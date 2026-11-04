"""Recorded DEBYKO /v2 responses, replayed offline; no keys or external calls.

snapshots.json was captured via DEBYKO's snapshots MCP projection on
2026-11-02 11:21:49.957 UTC: instrument = BTC-PERP, published/string,
layers ticker/mark/funding/oi/stats. settlements.json is the funding_settlements
projection with the same selection, (2026-11-01T11:21:49.957Z,
2026-11-02T11:21:49.957Z], desc, limit=100, string. These tools forward
the /v2 response envelopes unchanged. Edge cases mutate fresh copies only.
"""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from tradingagents.agents import tools
from tradingagents.agents.analysts import fundamentals_analyst, market_analyst
from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import debyko

FIXTURES = Path(__file__).parent / "fixtures" / "debyko"
NOW = datetime(2026, 11, 2, 11, 21, 49, 957000, tzinfo=UTC)
KEY = "fake-debyko-key-never-real"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("DEBYKO_API_KEY", KEY)
    monkeypatch.setattr(debyko, "_now", lambda: NOW)


@pytest.fixture
def responses(monkeypatch):
    snapshot = json.loads((FIXTURES / "snapshots.json").read_text())
    settlements = json.loads((FIXTURES / "settlements.json").read_text())

    def request(method, url, **kwargs):
        assert url.startswith("https://api.debyko.com/v2/")
        payload = snapshot if method == "POST" else settlements
        return SimpleNamespace(status_code=200, json=lambda: copy.deepcopy(payload))

    mocked = Mock(side_effect=request)
    monkeypatch.setattr(debyko.requests, "request", mocked)
    return snapshot, settlements, mocked


def report(ticker="BTC-PERP", day="2026-11-02"):
    return json.loads(debyko.get_perpetual_context(ticker, day).split("\n\n", 1)[1])


def test_recorded_snapshot_is_per_listing_and_preserves_values_and_provenance(responses):
    snapshot, _, request = responses
    data = report()
    assert data["instrument"] == "BTC-PERP"
    assert len(data["current"]["venues"]) == len(snapshot["items"])
    for received, original in zip(data["current"]["venues"], snapshot["items"], strict=True):
        assert received["venue"] == original["venue"]
        assert received["venue_symbol"] == original["venue_symbol"]
        for name in debyko.LAYERS:
            old, new = original["layers"][name], received["layers"][name]
            for key in ("status", "reason", "venue_ts", "received_at", "age_ms", "valid_until"):
                if key in old:
                    assert new[key] == old[key]
            if old["status"] == "present":
                assert new["values"] == old["values"]
                assert new["units"] == old["units"]
            else:
                assert "values" not in new
    first = request.call_args_list[0]
    assert first.args == ("POST", "https://api.debyko.com/v2/snapshots")
    assert first.kwargs["json"] == {
        "where": "instrument = BTC-PERP", "layers": list(debyko.LAYERS),
        "kind": "perpetual", "number_format": "string", "units": "published",
    }
    assert all("candles" not in call.args[1] for call in request.call_args_list)


def test_auth_is_only_in_header_and_requests_are_bounded(responses):
    _, _, request = responses
    report()
    for call in request.call_args_list:
        assert call.kwargs["headers"]["Authorization"] == f"Bearer {KEY}"
        assert call.kwargs["timeout"] == (5, 20)
        assert call.kwargs["allow_redirects"] is False
        assert KEY not in call.args[1]
        assert KEY not in json.dumps(call.kwargs.get("params", {}))
        assert KEY not in json.dumps(call.kwargs.get("json", {}))


def test_settlements_are_recorded_prints_not_current_predictions(responses):
    _, settlements, request = responses
    data = report()["settlements"]
    assert len(data["items"]) == 65
    assert data["not_recorded"] == settlements["not_recorded"]
    assert data["truncated"] is False
    for row, old in zip(data["items"], settlements["items"], strict=True):
        for key in ("time", "venue", "origin", "status", "interval", "interval_check", "rate_source"):
            assert row[key] == old[key]
        if row["status"] == "present":
            assert row["rate"] == old["rate"]
            assert row["rate_8h"] == old["rate_8h"]
        else:
            assert "rate" not in row
    query = request.call_args_list[1].kwargs["params"]
    assert debyko._instant(query["to"]) == NOW
    assert debyko._instant(query["from"]) == NOW - timedelta(days=1)


@pytest.mark.parametrize("ticker", ["btc-perp", " BTC-PERP ", "ZEC-PERP", "1INCH-PERP"])
def test_perpetual_symbols_are_normalized_without_a_network_call(ticker):
    assert debyko._instrument(ticker) == ticker.strip().upper()


@pytest.mark.parametrize("ticker", ["BTC-USD", "BTCUSDT", "BTC-USDC"])
def test_crypto_pair_mapping_requires_explicit_opt_in(ticker, responses):
    request = responses[2]
    with pytest.raises(NoMarketDataError):
        debyko.get_perpetual_context(ticker)
    request.assert_not_called()
    with run_config({"debyko_allow_crypto_pairs": True}):
        assert report(ticker)["instrument"] == "BTC-PERP"


@pytest.mark.parametrize("ticker", ["AAPL", "EURUSD", "BTC-PERP or true", "BTC/PERP", "BTC-PERP\nINJECT"])
def test_non_perpetuals_and_selection_injection_do_not_reach_api(ticker, responses):
    with run_config({"debyko_allow_crypto_pairs": True}), pytest.raises(NoMarketDataError):
        debyko.get_perpetual_context(ticker)
    responses[2].assert_not_called()


@pytest.mark.parametrize("status", ["stale", "missing", "off", "not_published"])
def test_non_present_values_and_withheld_are_never_exposed(status, responses):
    snapshot = responses[0]
    layer = snapshot["items"][0]["layers"]["funding"]
    layer.update(status=status, reason="source_error",
                 values={"funding_8h": "-99999"}, withheld={"funding": "123456"})
    text = debyko.get_perpetual_context("BTC-PERP")
    assert "-99999" not in text and "123456" not in text
    cleaned = json.loads(text.split("\n\n", 1)[1])["current"]["venues"][0]["layers"]["funding"]
    assert cleaned["status"] == status and cleaned["reason"] == "source_error"


def test_comparison_uses_present_8h_rates_only_without_summing_oi(responses):
    snapshot = responses[0]
    snapshot["items"] = [copy.deepcopy(snapshot["items"][0]) for _ in range(5)]
    for row, rate, status, unit in zip(snapshot["items"],
            ["-100", "0.00002", "0.000010000000000000001", "100", "NaN"],
            ["stale", "present", "present", "present", "present"],
            ["fraction", "fraction", "fraction", "percent", "fraction"], strict=True):
        row["layers"]["funding"].update(status=status,
            values={"funding_8h": rate}, units={"funding_8h": unit})
    comparison = report()["current"]["cross_venue"]
    assert comparison["lowest_rate"]["funding_8h"] == "0.000010000000000000001"
    assert comparison["highest_rate"]["funding_8h"] == "0.00002"
    assert "OI is not summed" in comparison["basis"]


def test_historical_run_withholds_live_snapshot_and_pins_settlements(responses):
    _, _, request = responses
    data = report(day="2026-11-01")
    assert isinstance(data["current"], str) and "withheld" in data["current"]
    assert all(call.args[0] == "GET" for call in request.call_args_list)
    query = request.call_args.kwargs["params"]
    assert query["from"] == "2026-11-01T00:00:00+00:00"
    assert query["to"] == "2026-11-02T00:00:00+00:00"
    assert all(debyko._instant(row["time"]) <= datetime(2026, 11, 2, tzinfo=UTC)
               for row in data["settlements"]["items"])


def test_future_date_does_not_read_live_data(responses):
    with pytest.raises(NoMarketDataError):
        report(day="2026-11-03")
    responses[2].assert_not_called()


def test_paging_is_pinned_and_bounded_and_partial_coverage_is_labelled(responses):
    _, settlements, request = responses
    settlements["items"] = []
    settlements["next_cursor"] = "opaque-recording-cursor"
    data = report()
    queries = [c.kwargs["params"] for c in request.call_args_list[1:]]
    assert len(queries) == debyko.MAX_SETTLEMENT_PAGES
    assert "cursor" not in queries[0]
    assert queries[1]["cursor"] == "opaque-recording-cursor"
    assert all(q["from"] == queries[0]["from"] and q["to"] == queries[0]["to"]
               for q in queries)
    assert data["settlements"]["truncated"] is True


def test_missing_key_falls_through_only_selected_chain(monkeypatch, responses):
    monkeypatch.delenv("DEBYKO_API_KEY")
    fallback, unselected = Mock(return_value="selected fallback"), Mock()
    monkeypatch.setitem(router.VENDOR_METHODS["get_fundamentals"], "yfinance", fallback)
    monkeypatch.setitem(router.VENDOR_METHODS["get_fundamentals"], "alpha_vantage", unselected)
    with run_config({"tool_vendors": {"get_fundamentals": "debyko,yfinance"}}):
        assert router.route_to_vendor("get_fundamentals", "BTC-PERP", "2026-11-02") == "selected fallback"
    fallback.assert_called_once()
    unselected.assert_not_called()
    responses[2].assert_not_called()
    with pytest.raises(VendorNotConfiguredError):
        debyko.get_perpetual_context("BTC-PERP")


@pytest.mark.parametrize("status", [301, 400, 401, 403, 404, 429, 500, 503])
def test_http_failures_are_typed_and_follow_existing_fallback(status, monkeypatch, responses):
    responses[2].side_effect = None
    responses[2].return_value = SimpleNamespace(status_code=status)
    with pytest.raises(VendorUnavailableError, match=f"HTTP {status}"):
        report()
    fallback = Mock(return_value="fallback")
    monkeypatch.setitem(router.VENDOR_METHODS["get_fundamentals"], "yfinance", fallback)
    with run_config({"tool_vendors": {"get_fundamentals": "debyko,yfinance"}}):
        assert router.route_to_vendor("get_fundamentals", "BTC-PERP") == "fallback"


def test_request_errors_do_not_leak_keys_in_exception_chains_or_logs(responses, caplog):
    responses[2].side_effect = requests.Timeout(f"failed with {KEY}")
    with pytest.raises(VendorUnavailableError) as exc:
        report()
    assert KEY not in str(exc.value)
    assert exc.value.__context__ is None and exc.value.__cause__ is None
    with run_config({"tool_vendors": {"get_fundamentals": "debyko"}}):
        answer = router.route_to_vendor("get_fundamentals", "BTC-PERP")
    assert KEY not in answer and KEY not in caplog.text
    assert answer.startswith("DATA_UNAVAILABLE")


@pytest.mark.parametrize("payload", [None, [], {}, {"items": [None]}])
def test_invalid_envelopes_are_typed_unavailability(payload, responses):
    responses[2].side_effect = None
    responses[2].return_value = SimpleNamespace(status_code=200, json=lambda: payload)
    with pytest.raises(VendorUnavailableError, match="invalid data envelope"):
        report()


def test_optional_context_without_key_does_not_abort_run(monkeypatch):
    monkeypatch.delenv("DEBYKO_API_KEY")
    assert router.route_to_vendor("get_crypto_perpetual_context", "BTC-PERP").startswith("DATA_UNAVAILABLE")


def test_settlement_failure_preserves_available_current_context(responses):
    snapshot, _, request = responses
    request.side_effect = [SimpleNamespace(status_code=200, json=lambda: snapshot),
                           SimpleNamespace(status_code=403)]
    data = report()
    assert data["current"]["venues"]
    assert "HTTP 403" in data["settlements"]["unavailable"]


@pytest.mark.parametrize("timestamp", [None, "not-a-date", "2026-11-02T10:00:00", {}])
def test_invalid_settlement_timestamp_is_unavailable_not_a_false_zero(timestamp, responses):
    responses[1]["items"][0]["time"] = timestamp
    data = report()
    assert "invalid settlement timestamp" in data["settlements"]["unavailable"]


@pytest.mark.parametrize("layers", [None, [], {"ticker": None}, {"ticker": {"status": "present", "values": []}}])
def test_invalid_snapshot_layers_follow_typed_error_contract(layers, responses):
    responses[0]["items"][0]["layers"] = layers
    with pytest.raises(VendorUnavailableError, match="invalid snapshot"):
        report()


def test_real_empty_results_are_not_zero(responses):
    responses[0]["items"] = []
    responses[1]["items"] = []
    responses[1]["not_recorded"] = []
    with pytest.raises(NoMarketDataError):
        report()


def test_tool_date_and_instrument_are_injected_and_clamped(monkeypatch):
    routed = Mock(return_value="context")
    monkeypatch.setattr(tools, "route_to_vendor", routed)
    assert tools.get_crypto_perpetual_context.func(
        "BTC-PERP", "2026-11-02", trade_date="2026-10-31") == "context"
    routed.assert_called_once_with("get_crypto_perpetual_context", "BTC-PERP", "2026-10-31")
    schema = tools.get_crypto_perpetual_context.tool_call_schema.model_json_schema()["properties"]
    assert "ticker" not in schema and "trade_date" not in schema


def test_both_analysts_have_context_but_candle_indicator_vendors_are_unchanged():
    for analyst in (fundamentals_analyst, market_analyst):
        assert tools.get_crypto_perpetual_context in analyst.TOOLS
    for method in ("get_stock_data", "get_indicators"):
        assert "debyko" not in router.VENDOR_METHODS[method]


def test_readme_section_has_ten_lines():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    section = readme.split("### DEBYKO crypto perpetual context", 1)[1].split("\n### ", 1)[0]
    assert len(("### DEBYKO crypto perpetual context" + section).rstrip().splitlines()) == 10
