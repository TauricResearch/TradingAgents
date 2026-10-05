"""SiftingIO stock history contract and router tests. All HTTP calls are mocked."""

import copy
import csv
import io
from datetime import UTC, datetime
from unittest import mock

import pytest
import requests

from tradingagents.dataflows import router
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.vendors import siftingio
from tradingagents.default_config import DEFAULT_CONFIG

pytestmark = pytest.mark.unit


def bar(day="2026-09-11", **changes):
    return {
        "t": int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp() * 1000),
        "o": 100.1234, "h": 102.5678, "l": 99.1234, "c": 101.4567, "v": 123456,
        **changes,
    }


def response(rows=None, cursor="", status=200, **meta):
    result = mock.Mock(status_code=status)
    result.json.return_value = {
        "data": [bar()] if rows is None else rows,
        "meta": {"symbol": "AAPL", "interval": "1d", "next_cursor": cursor, **meta},
    }
    return result


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv("SIFTINGIO_API_KEY", "test-key-not-a-real-secret")
    with mock.patch.object(siftingio.requests, "get", return_value=response()) as get:
        yield get


def fetch():
    return siftingio.get_stock_data(" aapl ", "2026-09-01", "2026-09-11")


def test_csv_and_wire_contract(http):
    output = fetch()
    rows = list(csv.DictReader(io.StringIO("\n".join(
        line for line in output.splitlines() if not line.startswith("#")
    ))))
    assert rows == [{"Date": "2026-09-11", "Open": "100.1234", "High": "102.5678",
                     "Low": "99.1234", "Close": "101.4567", "Volume": "123456"}]
    assert "NOT adjusted" in output
    http.assert_called_once_with(
        "https://api.sifting.io/v1/hist/stocks/AAPL/bars",
        params={"start": "2026-09-01", "end": "2026-09-11", "interval": "1d", "limit": 1000},
        headers={"X-API-Key": "test-key-not-a-real-secret", "Accept-Encoding": "gzip"},
        timeout=30, allow_redirects=False,
    )
    http.return_value.close.assert_called_once()


def test_missing_key_never_sends_request(http, monkeypatch):
    monkeypatch.setenv("SIFTINGIO_API_KEY", "  ")
    with pytest.raises(VendorNotConfiguredError):
        fetch()
    http.assert_not_called()


@pytest.mark.parametrize("symbol,start,end", [
    ("../AAPL", "2026-09-01", "2026-09-11"),
    ("AAPL?api_key=x", "2026-09-01", "2026-09-11"),
    ("0123", "2026-09-01", "2026-09-11"),
    ("ABCDEFGHIJK", "2026-09-01", "2026-09-11"),
    ("AAPL", "2026-9-1", "2026-09-11"),
    ("AAPL", "2026-02-30", "2026-09-11"),
    ("AAPL", "2026-09-12", "2026-09-11"),
])
def test_invalid_inputs(http, symbol, start, end):
    with pytest.raises(ValueError):
        siftingio.get_stock_data(symbol, start, end)
    http.assert_not_called()


@pytest.mark.parametrize("status,error", [
    (401, VendorNotConfiguredError), (403, VendorNotConfiguredError),
    (404, NoMarketDataError), (429, VendorUnavailableError),
    (500, VendorUnavailableError), (302, VendorUnavailableError),
    (406, VendorUnavailableError),
])
def test_status_mapping_and_no_response_body_leak(http, status, error):
    http.return_value = response(status=status)
    http.return_value.text = "test-key-not-a-real-secret"
    with pytest.raises(error) as exc:
        fetch()
    assert "test-key-not-a-real-secret" not in str(exc.value)
    http.return_value.close.assert_called_once()


def test_network_failure_is_safe(http):
    http.side_effect = requests.Timeout("test-key-not-a-real-secret")
    with pytest.raises(VendorUnavailableError) as exc:
        fetch()
    assert "test-key-not-a-real-secret" not in str(exc.value)
    assert exc.value.__suppress_context__


def test_pagination_dedupe_sort_and_inclusive_filter(http):
    http.side_effect = [
        response([bar("2026-09-11"), bar("2026-09-01")], cursor="opaque-cursor"),
        response([bar("2026-09-01"), bar("2026-08-31"), bar("2026-09-12")]),
    ]
    data = [line for line in fetch().splitlines() if line.startswith("2026-")]
    assert [line.split(",")[0] for line in data] == ["2026-09-01", "2026-09-11"]
    assert http.call_args_list[1].kwargs["params"]["cursor"] == "opaque-cursor"


@pytest.mark.parametrize("payload", [None, [], {"data": {}}, {"data": []}, {"data": [], "meta": []}])
def test_invalid_envelope(http, payload):
    http.return_value.json.return_value = payload
    with pytest.raises(VendorUnavailableError):
        fetch()


def test_invalid_json(http):
    http.return_value.json.side_effect = ValueError("test-key-not-a-real-secret")
    with pytest.raises(VendorUnavailableError, match="invalid JSON"):
        fetch()


@pytest.mark.parametrize("row", [
    {}, None, bar(c="101.4567"), bar(v=None), bar(v=-1),
    bar(c=float("nan")), bar(v=True), bar(h=90), bar(t=1), bar(o=0),
])
def test_invalid_bars_not_fabricated(http, row):
    http.return_value = response([row])
    with pytest.raises(VendorUnavailableError):
        fetch()


@pytest.mark.parametrize("meta", [{"symbol": "MSFT"}, {"interval": "1m"}])
def test_wrong_series(http, meta):
    http.return_value = response(**meta)
    with pytest.raises(VendorUnavailableError):
        fetch()


def test_conflicting_duplicate(http):
    http.return_value = response([bar(), bar(c=101)])
    with pytest.raises(VendorUnavailableError, match="conflicting"):
        fetch()


def test_repeated_cursor(http):
    http.return_value = response(cursor="same")
    with pytest.raises(VendorUnavailableError, match="repeated cursor"):
        fetch()
    assert http.call_count == 2


def test_page_limit_never_returns_partial_history(http, monkeypatch):
    monkeypatch.setattr(siftingio, "MAX_PAGES", 1)
    http.return_value = response(cursor="more")
    with pytest.raises(VendorUnavailableError, match="pagination limit"):
        fetch()


@pytest.mark.parametrize("rows", [[], [bar("2026-08-31")], [bar("2026-09-01")]])
def test_empty_or_stale(http, rows):
    http.return_value = response(rows)
    with pytest.raises(NoMarketDataError):
        siftingio.get_stock_data("AAPL", "2026-09-01", "2026-09-14")


def test_opt_in_router_and_defaults(http):
    before = copy.deepcopy(DEFAULT_CONFIG)
    assert DEFAULT_CONFIG["data_vendors"]["core_stock_apis"] == "yfinance"
    set_config({"data_vendors": {"core_stock_apis": "siftingio"}})
    result = router.route_to_vendor("get_stock_data", "AAPL", "2026-09-01", "2026-09-11")
    assert "100.1234" in result
    assert before == DEFAULT_CONFIG
    assert "siftingio" not in router.VENDOR_METHODS["get_indicators"]


def test_router_returns_unavailable_for_throttle(http):
    set_config({"data_vendors": {"core_stock_apis": "siftingio"}})
    http.return_value = response(status=429)
    assert router.route_to_vendor(
        "get_stock_data", "AAPL", "2026-09-01", "2026-09-11"
    ).startswith("DATA_UNAVAILABLE")
