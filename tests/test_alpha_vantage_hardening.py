"""Alpha Vantage request hardening.

Regressions for #990 (no request timeout -> can hang), #991 (invalid-key
responses mislabeled as rate limits and silently treated as transient), and
#1115 (fundamentals look-ahead filter never ran because the payload is a JSON
string, not a dict), and the date trim that keeps post-end_date bars out of a
historical run.
"""
import json

import pytest

import tradingagents.dataflows.alpha_vantage_common as av
import tradingagents.dataflows.alpha_vantage_fundamentals as avf
import tradingagents.dataflows.alpha_vantage_news as avn
import tradingagents.dataflows.alpha_vantage_stock as avs


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
    body = '{"Information": "Our standard API rate limit is 25 requests per day. ... your API key ..."}'
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageRateLimitError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


@pytest.mark.unit
def test_invalid_key_not_mislabeled_as_rate_limit(monkeypatch):
    # AV's invalid-key notice mentions "API key"; it must NOT be treated as a
    # (transient) rate limit, but surface as a real configuration error (#991).
    body = ('{"Information": "the parameter apikey is invalid or missing. '
            'Please claim your free API key on (https://www.alphavantage.co/support/#api-key)."}')
    monkeypatch.setattr(av.requests, "get", _patched_get(body))
    with pytest.raises(av.AlphaVantageNotConfiguredError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    with pytest.raises(av.AlphaVantageRateLimitError):  # sanity: rate-limit path still distinct
        monkeypatch.setattr(av.requests, "get", _patched_get('{"Note": "API call frequency is 5 calls per minute."}'))
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


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


# ---------------------------------------------------------------------------
# Date trim (see the rationale on the unguarded trim in alpha_vantage_common)
# ---------------------------------------------------------------------------

_DAILY_CSV = (
    "timestamp,open,high,low,close,volume\n"
    "2024-05-13,1,1,1,1,10\n"   # after end_date -> must never be served
    "2024-05-10,1,1,1,1,10\n"
    "2024-05-09,1,1,1,1,10\n"
)


@pytest.mark.unit
def test_stock_data_is_trimmed_to_the_requested_window(monkeypatch):
    monkeypatch.setattr(avs, "_make_api_request", lambda *a, **k: _DAILY_CSV)
    out = avs.get_stock("IBM", "2024-05-09", "2024-05-10")
    assert "2024-05-10" in out and "2024-05-09" in out
    assert "2024-05-13" not in out, "bar after end_date leaked into the window"


@pytest.mark.unit
def test_unparseable_body_is_never_served_untrimmed(monkeypatch):
    """The trim used to swallow the failure and return the whole body, putting
    bars after end_date into a backtest. It must raise instead."""
    monkeypatch.setattr(avs, "_make_api_request",
                        lambda *a, **k: "timestamp,close\nnot-a-date,1\n")

    with pytest.raises(ValueError):
        avs.get_stock("IBM", "2024-05-09", "2024-05-10")


@pytest.mark.unit
def test_empty_body_still_passes_through(monkeypatch):
    monkeypatch.setattr(avs, "_make_api_request", lambda *a, **k: "")
    assert avs.get_stock("IBM", "2024-05-09", "2024-05-10") == ""


def _capture_global_news_params(monkeypatch, config):
    captured = {}
    monkeypatch.setattr(avn, "_make_api_request", lambda fn, params: captured.update(params) or "{}")
    monkeypatch.setattr(avn, "get_config", lambda: config)
    return captured


@pytest.mark.unit
def test_global_news_omitted_optionals_resolve_from_config(monkeypatch):
    # The get_global_news tool marks look_back_days/limit optional and forwards
    # None; Alpha Vantage must resolve them from config like the yfinance path
    # does, instead of crashing on timedelta(days=None).
    captured = _capture_global_news_params(
        monkeypatch, {"global_news_lookback_days": 7, "global_news_article_limit": 10}
    )
    avn.get_global_news("2026-01-10", None, None)
    assert captured["limit"] == "10"
    assert captured["time_from"] == "20260103T0000"  # 2026-01-10 minus 7 days


@pytest.mark.unit
def test_global_news_explicit_optionals_win_over_config(monkeypatch):
    captured = _capture_global_news_params(
        monkeypatch, {"global_news_lookback_days": 7, "global_news_article_limit": 10}
    )
    avn.get_global_news("2026-01-10", 3, 5)
    assert captured["limit"] == "5"
    assert captured["time_from"] == "20260107T0000"  # 2026-01-10 minus 3 days
