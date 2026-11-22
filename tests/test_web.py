import base64
import time
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

import cli.web
from cli.models import AnalystType, AssetType
from cli.web import (
    _is_loopback_host,
    _web_credentials,
    parse_run_request,
)


@pytest.mark.unit
def test_web_run_request_parses_ticker_date_and_analysts():
    request = parse_run_request(
        {
            "ticker": "btc-usd",
            "date": date.today().isoformat(),
            "analysts": ["market", "news"],
        }
    )

    assert request == {
        "ticker": "BTC-USD",
        "date": date.today().isoformat(),
        "asset_type": AssetType.CRYPTO,
        "analysts": [AnalystType.MARKET, AnalystType.NEWS],
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"ticker": "../NVDA", "date": "2026-01-01", "analysts": ["market"]},
        {
            "ticker": "NVDA",
            "date": (date.today() + timedelta(days=1)).isoformat(),
            "analysts": ["market"],
        },
        {"ticker": "NVDA", "date": date.today().isoformat(), "analysts": []},
        {"ticker": "NVDA", "date": date.today().isoformat(), "analysts": ["unknown"]},
        {"ticker": "NVDA", "date": date.today().isoformat(), "analysts": ["market", "market"]},
        {"ticker": "BTC-USD", "date": date.today().isoformat(), "analysts": ["fundamentals"]},
    ],
)
def test_web_run_request_rejects_invalid_input(payload):
    with pytest.raises(ValueError):
        parse_run_request(payload)


@pytest.mark.unit
def test_web_service_runs_analysis_and_records_html_report(tmp_path, monkeypatch):
    class FakeGraph:
        def __init__(self, **kwargs):
            assert kwargs["debug"] is False

        def propagate(self, ticker, trade_date, asset_type):
            assert (ticker, trade_date, asset_type) == ("NVDA", date.today().isoformat(), "stock")
            return {"final_trade_decision": "Hold"}, "Hold"

        def default_report_path(self, ticker):
            assert ticker == "NVDA"
            return tmp_path

        def save_reports(self, state, ticker, save_path, html):
            assert html is True
            report = save_path / "complete_report.html"
            report.write_text("<h1>NVDA</h1>", encoding="utf-8")
            return report

    monkeypatch.setattr(cli.web, "TradingAgentsGraph", FakeGraph)
    service = cli.web.AnalysisService()
    request = parse_run_request(
        {
            "ticker": "NVDA",
            "date": date.today().isoformat(),
            "analysts": ["market"],
        }
    )
    try:
        job = service.start(request)
        for _ in range(100):
            status = service.get(job["id"])
            if status["status"] in ("complete", "failed"):
                break
            time.sleep(0.01)
        assert status["status"] == "complete"
        assert status["report_url"] == f"/api/runs/{job['id']}/report"
        assert service.report(job["id"]).read_text(encoding="utf-8") == "<h1>NVDA</h1>"
    finally:
        service._executor.shutdown(wait=True)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("username", "password", "valid"),
    [
        ("", "", True),
        ("trader", "a" * 20, True),
        ("trader", "short", False),
        ("", "a" * 20, False),
        ("name:with-colon", "a" * 20, False),
    ],
)
def test_web_credentials_require_a_complete_strong_pair(monkeypatch, username, password, valid):
    monkeypatch.setenv("TRADINGAGENTS_WEB_USERNAME", username)
    monkeypatch.setenv("TRADINGAGENTS_WEB_PASSWORD", password)
    if valid:
        credentials = _web_credentials()
        if username:
            assert (credentials.username, credentials.password) == (username, password)
        else:
            assert credentials is None
    else:
        with pytest.raises(ValueError):
            _web_credentials()


@pytest.mark.unit
def test_web_requires_credentials_for_non_loopback_bind(monkeypatch):
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert _is_loopback_host("localhost")
    assert not _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("example.com")


@pytest.mark.unit
def test_web_auth_protects_ui_and_api():
    credentials = cli.web.WebCredentials("trader", "a" * 20)
    sent = []

    class RequestHandler:
        server = SimpleNamespace(credentials=credentials)
        headers = {}

        def _send(self, *args, **kwargs):
            sent.append((args, kwargs))

    handler = RequestHandler()
    assert not cli.web.TradingAgentsRequestHandler._authorized(handler)
    assert sent[-1][1]["status"] == 401
    assert sent[-1][1]["headers"]["WWW-Authenticate"].startswith("Basic ")

    token = base64.b64encode(b"trader:" + b"a" * 20).decode()
    handler.headers = {"Authorization": f"Basic {token}"}
    assert cli.web.TradingAgentsRequestHandler._authorized(handler)

    handler.headers = {"Authorization": "Basic not-base64"}
    assert not cli.web.TradingAgentsRequestHandler._authorized(handler)
