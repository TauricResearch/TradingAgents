"""Alpha Vantage request hardening.

Regressions for #990 (no request timeout -> can hang), #991 (invalid-key
responses mislabeled as rate limits and silently treated as transient), and
#1115 (fundamentals look-ahead filter never ran because the payload is a JSON
string, not a dict).
"""
import json

import pytest
import requests

import tradingagents.dataflows.alpha_vantage_common as av
import tradingagents.dataflows.alpha_vantage_fundamentals as avf
import tradingagents.dataflows.alpha_vantage_indicator as avi


class _FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _patched_get(body, capture=None):
    def fake_get(url, params=None, **kwargs):
        if capture is not None:
            capture.update(kwargs)
        return _FakeResponse(body)
    return fake_get


@pytest.mark.unit
def test_request_passes_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(av.requests, "get", _patched_get("Date,Close\n2025-01-02,1.0", captured))
    av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert captured.get("timeout") == av.REQUEST_TIMEOUT  # #990


@pytest.mark.unit
def test_rate_limit_detected(monkeypatch):
    secret = "must-not-escape"
    body = (
        '{"Information": "Our standard API rate limit is 25 requests per day. '
        f'API key {secret}"}}'
    )
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageRateLimitError) as captured:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert secret not in str(captured.value)


@pytest.mark.unit
def test_invalid_key_not_mislabeled_as_rate_limit(monkeypatch):
    # AV's invalid-key notice mentions "API key"; it must NOT be treated as a
    # (transient) rate limit, but surface as a real configuration error (#991).
    body = ('{"Information": "the parameter apikey is invalid or missing. '
            'Please claim your free API key on (https://www.alphavantage.co/support/#api-key)."}')
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageNotConfiguredError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


@pytest.mark.unit
def test_http_error_does_not_expose_request_url(monkeypatch):
    secret = "https://provider.invalid/?apikey=must-not-escape"

    class FailedResponse:
        text = ""

        def raise_for_status(self):
            raise requests.HTTPError(secret)

    monkeypatch.setattr(av.requests, "get", lambda *args, **kwargs: FailedResponse())
    with pytest.raises(av.AlphaVantageDataError) as captured:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert secret not in str(captured.value)
    assert "HTTPError" in str(captured.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        [],
        "unexpected",
        None,
        {"Information": None},
        {"Note": ["unexpected"]},
        {"Information": "https://provider.invalid/?token=must-not-escape"},
    ],
)
def test_unusable_json_shapes_fail_closed(monkeypatch, payload):
    secret = "must-not-escape"
    body = json.dumps(payload)
    monkeypatch.setattr(av.requests, "get", _patched_get(body))

    with pytest.raises(av.AlphaVantageDataError) as captured:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert secret not in str(captured.value)


@pytest.mark.unit
def test_response_read_failure_is_sanitized(monkeypatch):
    secret = "https://provider.invalid/?token=must-not-escape"

    class UnreadableResponse:
        def raise_for_status(self):
            pass

        @property
        def text(self):
            raise UnicodeError(secret)

    monkeypatch.setattr(av.requests, "get", lambda *args, **kwargs: UnreadableResponse())
    with pytest.raises(av.AlphaVantageDataError) as captured:
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert secret not in str(captured.value)
    assert "UnicodeError" in str(captured.value)


@pytest.mark.unit
def test_indicator_failure_raises_sanitized_vendor_error(monkeypatch):
    secret = "https://provider.invalid/?apikey=must-not-escape"

    def fail(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(avi, "_make_api_request", fail)

    with pytest.raises(av.AlphaVantageDataError) as captured:
        avi.get_indicator("AAPL", "rsi", "2026-01-01", 30)

    assert secret not in str(captured.value)
    assert "RuntimeError" in str(captured.value)
    with pytest.raises(av.AlphaVantageRateLimitError):  # sanity: distinct path
        monkeypatch.setattr(
            av.requests,
            "get",
            _patched_get('{"Note": "API call frequency is 5 calls per minute."}'),
        )
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


@pytest.mark.unit
def test_csv_date_filter_excludes_future_rows():
    csv_data = (
        "timestamp,open,close\n"
        "2026-01-03,3,4\n"
        "2026-01-02,2,3\n"
        "2026-01-01,1,2\n"
    )

    filtered = av._filter_csv_by_date_range(
        csv_data, "2026-01-01", "2026-01-02"
    )

    assert filtered == (
        "timestamp,open,close\n"
        "2026-01-02,2,3\n"
        "2026-01-01,1,2\n"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "csv_data,start_date,end_date",
    [
        (None, "2026-01-01", "2026-01-02"),
        ("date,close\n2026-01-01,2\n", "2026-01-01", "2026-01-02"),
        ("timestamp,close\nnot-a-date,2\n", "2026-01-01", "2026-01-02"),
        ("timestamp,close\n2026-01-01,2\n", "2026-01-03", "2026-01-02"),
    ],
)
def test_csv_date_filter_fails_closed(csv_data, start_date, end_date, capsys):
    with pytest.raises(
        av.AlphaVantageDataError,
        match="^Alpha Vantage CSV response could not be safely filtered$",
    ):
        av._filter_csv_by_date_range(csv_data, start_date, end_date)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.unit
def test_csv_date_filter_does_not_expose_parser_error(monkeypatch):
    secret = "https://example.invalid/?apikey=must-not-escape"

    def fail_sensitively(*_args, **_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr(av.pd, "read_csv", fail_sensitively)
    with pytest.raises(av.AlphaVantageDataError) as error:
        av._filter_csv_by_date_range(
            "timestamp,close\n2026-01-01,2\n", "2026-01-01", "2026-01-02"
        )

    assert secret not in str(error.value)


_FUNDAMENTALS_JSON = json.dumps({
    "symbol": "AAPL",
    "annualReports": [
        {"fiscalDateEnding": "2025-12-31", "totalAssets": "1"},   # future -> must drop
        {"fiscalDateEnding": "2023-12-31", "totalAssets": "2"},   # past   -> must keep
    ],
    "quarterlyReports": [
        {"fiscalDateEnding": "2024-06-30", "totalAssets": "3"},   # future -> must drop
        {"fiscalDateEnding": "2023-09-30", "totalAssets": "4"},   # past   -> must keep
    ],
})


@pytest.mark.unit
def test_fundamentals_look_ahead_filter_runs_on_json_string(monkeypatch):
    # #1115: the payload arrives as a JSON *string*; the old dict-only guard let
    # future-dated fiscal periods leak into historical runs.
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: _FUNDAMENTALS_JSON)
    out = avf.get_balance_sheet("AAPL", curr_date="2024-01-01")
    assert isinstance(out, str)  # callers still receive a str
    parsed = json.loads(out)
    assert [r["fiscalDateEnding"] for r in parsed["annualReports"]] == ["2023-12-31"]
    assert [r["fiscalDateEnding"] for r in parsed["quarterlyReports"]] == ["2023-09-30"]


@pytest.mark.unit
def test_fundamentals_no_curr_date_passes_through(monkeypatch):
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: _FUNDAMENTALS_JSON)
    assert avf.get_income_statement("AAPL") == _FUNDAMENTALS_JSON


@pytest.mark.unit
def test_fundamentals_non_json_body_unchanged(monkeypatch):
    monkeypatch.setattr(avf, "_make_api_request", lambda fn, params: "not-json")
    assert avf.get_cashflow("AAPL", curr_date="2024-01-01") == "not-json"
