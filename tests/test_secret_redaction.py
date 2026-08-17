"""API keys must never reach an error message.

FRED and Alpha Vantage authenticate with a query parameter, so any ``requests``
exception stringifies to include the full URL — key and all. Those strings are
logged, returned to the model as the ``DATA_UNAVAILABLE:`` sentinel for optional
categories, and handed to the LLM verbatim by the indicators tool, from where
they land in ``message_tool.log`` and the saved markdown report.
"""
import logging

import pytest
import requests

import tradingagents.dataflows.alpha_vantage_common as av
import tradingagents.dataflows.fred as fred
from tradingagents.dataflows import http_utils
from tradingagents.dataflows.http_utils import raise_for_status, redact_secrets

SECRET = "abcdef0123456789abcdef0123456789"


def _response(status_code, url, body=b"boom"):
    response = requests.Response()
    response.status_code = status_code
    response.reason = "Internal Server Error"
    response.url = url
    response._content = body
    return response


@pytest.mark.unit
def test_redact_secrets_masks_key_and_keeps_other_params():
    url = f"https://api.stlouisfed.org/fred/series?series_id=CPIAUCSL&api_key={SECRET}&file_type=json"
    redacted = redact_secrets(f"500 Server Error: for url: {url}")
    assert SECRET not in redacted
    assert "series_id=CPIAUCSL" in redacted
    assert "file_type=json" in redacted


@pytest.mark.unit
@pytest.mark.parametrize("param", ["api_key", "apikey", "token", "access_token"])
def test_redact_secrets_covers_common_key_param_names(param):
    assert SECRET not in redact_secrets(f"https://x.test/q?{param}={SECRET}&a=1")


@pytest.mark.unit
def test_raise_for_status_redacts_the_url():
    response = _response(500, f"https://x.test/q?apikey={SECRET}")
    with pytest.raises(requests.HTTPError) as excinfo:
        raise_for_status(response)
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_raise_for_status_does_not_chain_the_unredacted_original():
    # A chained __cause__/__context__ would print the raw URL in any traceback.
    response = _response(500, f"https://x.test/q?apikey={SECRET}")
    with pytest.raises(requests.HTTPError) as excinfo:
        raise_for_status(response)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__ is True


@pytest.mark.unit
def test_fred_http_error_does_not_leak_the_key(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", SECRET)
    url = f"{fred.FRED_API_BASE}/series?series_id=CPIAUCSL&api_key={SECRET}&file_type=json"
    monkeypatch.setattr(http_utils.requests, "get", lambda *a, **kw: _response(500, url))
    with pytest.raises(requests.RequestException) as excinfo:
        fred._request("series", {"series_id": "CPIAUCSL"})
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_fred_connection_error_does_not_leak_the_key(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", SECRET)

    def boom(*a, **kw):
        raise requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.stlouisfed.org', port=443): Max retries "
            f"exceeded with url: /fred/series?series_id=CPIAUCSL&api_key={SECRET}"
        )

    monkeypatch.setattr(http_utils.requests, "get", boom)
    with pytest.raises(requests.RequestException) as excinfo:
        fred._request("series", {"series_id": "CPIAUCSL"})
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_fred_400_body_path_still_reports_fred_message(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", SECRET)
    url = f"{fred.FRED_API_BASE}/series?series_id=NOPE&api_key={SECRET}&file_type=json"
    body = b'{"error_message": "Bad Request. The series does not exist."}'
    monkeypatch.setattr(http_utils.requests, "get", lambda *a, **kw: _response(400, url, body))
    with pytest.raises(ValueError) as excinfo:
        fred._request("series", {"series_id": "NOPE"})
    assert "does not exist" in str(excinfo.value)
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_alpha_vantage_http_error_does_not_leak_the_key(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", SECRET)
    url = f"{av.API_BASE_URL}?function=TIME_SERIES_DAILY&symbol=AAPL&apikey={SECRET}"
    monkeypatch.setattr(http_utils.requests, "get", lambda *a, **kw: _response(500, url))
    with pytest.raises(requests.RequestException) as excinfo:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_alpha_vantage_connection_error_does_not_leak_the_key(monkeypatch):
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", SECRET)

    def boom(*a, **kw):
        raise requests.Timeout(
            f"HTTPSConnectionPool(host='www.alphavantage.co', port=443): Read timed "
            f"out. url: /query?function=TIME_SERIES_DAILY&apikey={SECRET}"
        )

    monkeypatch.setattr(http_utils.requests, "get", boom)
    with pytest.raises(requests.RequestException) as excinfo:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert SECRET not in str(excinfo.value)


@pytest.mark.unit
def test_indicators_tool_redacts_a_vendor_error(monkeypatch):
    """Backstop: the tool hands this string to the LLM verbatim."""
    from tradingagents.agents.utils import technical_indicators_tools as tools

    def boom(*a, **kw):
        raise ValueError(f"boom for url: https://x.test/query?function=RSI&apikey={SECRET}")

    monkeypatch.setattr(tools, "route_to_vendor", boom)
    result = tools.get_indicators.invoke(
        {"symbol": "AAPL", "indicator": "rsi", "curr_date": "2025-01-02"}
    )
    assert SECRET not in result


@pytest.mark.unit
def test_optional_category_sentinel_redacts_a_raw_vendor_error(monkeypatch, caplog):
    """Backstop for a vendor that raises without going through http_utils."""
    from tradingagents.dataflows import interface
    from tradingagents.dataflows.config import set_config

    def boom(*a, **kw):
        raise RuntimeError(f"boom for url: https://x.test/fred?api_key={SECRET}")

    monkeypatch.setitem(interface.VENDOR_METHODS["get_macro_indicators"], "fred", boom)
    set_config({"data_vendors": {"macro_data": "fred"}})

    with caplog.at_level(logging.WARNING):
        result = interface.route_to_vendor("get_macro_indicators", "cpi", "2025-01-02")

    assert result.startswith("DATA_UNAVAILABLE:")
    assert SECRET not in result
    assert SECRET not in caplog.text


@pytest.mark.unit
def test_optional_category_sentinel_carries_no_key(monkeypatch, caplog):
    """The macro_data degradation path returns the error text to the model."""
    from tradingagents.dataflows import interface
    from tradingagents.dataflows.config import set_config

    monkeypatch.setenv("FRED_API_KEY", SECRET)
    url = f"{fred.FRED_API_BASE}/series?series_id=CPIAUCSL&api_key={SECRET}&file_type=json"
    monkeypatch.setattr(http_utils.requests, "get", lambda *a, **kw: _response(500, url))
    set_config({"data_vendors": {"macro_data": "fred"}})

    with caplog.at_level(logging.WARNING):
        result = interface.route_to_vendor("get_macro_indicators", "cpi", "2025-01-02")

    assert result.startswith("DATA_UNAVAILABLE:")
    assert SECRET not in result
    assert SECRET not in caplog.text
