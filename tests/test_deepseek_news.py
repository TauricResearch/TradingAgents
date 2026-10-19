"""DeepSeek Search news must stay inside the run's window.

A search result can carry later information three ways: a date that reads a day early, a rolling
page that keeps its first date while its text changes, and a summary that is today's version of
the page. Each guard is pinned here; no test reaches the network.
"""
import copy
from datetime import date, timedelta

import pytest

import tradingagents.dataflows.config as config_module
import tradingagents.default_config as default_config
from tradingagents.dataflows import router
from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.vendors import deepseek_search as ds


@pytest.fixture(autouse=True)
def _config():
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


def _result(title, day, summary="", url=None):
    return {"title": title, "date": f"{day}T14:00:00Z" if day else None, "summary": summary,
            "url": url or f"https://example.com/{title.replace(' ', '-').lower()}",
            "site_name": "Example"}


@pytest.mark.unit
def test_past_window_ends_the_day_before_the_run():
    assert ds._last_day("2026-10-12") == date(2026, 10, 11)
    today = date.today().isoformat()
    assert ds._last_day(today) == date.today()


@pytest.mark.unit
def test_dates_written_in_text():
    text = "Mad Money 10/12/26, briefing 12 October 2026, Oct. 13 update, filed 2026-10-11, Q3 2026"
    assert sorted(set(ds.mentioned_dates(text, 2026))) == [
        date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13)]


@pytest.mark.unit
def test_each_kind_of_later_information_is_dropped():
    start, last = date(2026, 10, 5), date(2026, 10, 11)
    later = min(last + timedelta(days=2), date.today())
    rows = [
        _result("Inside the window", "2026-10-07", "Shares rose on Oct. 6."),
        _result("Dated after the window", "2026-10-12"),
        _result("Dated before the window", "2026-10-01"),
        _result("Undated", None),
        _result("NVDA News Today live page", "2026-10-06"),
        _result("NVIDIA Stock Forecast & Analyst Predictions", "2026-10-06"),
        _result("Updated story", "2026-10-08", f"Updated {later:%b %d, %Y}: shares fell."),
        _result("Scheduled date ahead", "2026-10-08",
                f"Results due {date.today() + timedelta(days=40):%B %d, %Y}."),
    ]
    kept = ds._in_window(rows, start, last, set())
    assert [r["title"] for r in kept] == ["Inside the window", "Scheduled date ahead"]


@pytest.mark.unit
def test_queries_carry_the_window_and_later_results_never_reach_the_report(monkeypatch):
    sent = []

    def fake_search(query, count):
        sent.append(query)
        return [_result("Old enough", "2026-10-09"), _result("Too new", "2026-10-12")]

    monkeypatch.setattr(ds, "_search", fake_search)
    report = ds.get_news_deepseek("NVDA", "2026-10-05", "2026-10-12")
    assert sent and all("after:2026-10-05 before:2026-10-12" in q for q in sent)
    assert "Old enough" in report and "Too new" not in report
    assert report.startswith("## NVDA News, from 2026-10-05 to 2026-10-11:")


@pytest.mark.unit
def test_page_furniture_stays_out_of_the_report():
    summary = "## Summary:\n### Big news\n237.30 USD  | -0.81%  | +27.12%\n...\nShares rose. " + "x " * 400
    report = ds._format([_result("Story - 273253183a86f0.TSGIBDZq", "2026-10-07", summary,
                                 url="https://example.com/story")])
    assert report.count("###") == 1
    assert "273253183a86f0" not in report and "USD" not in report
    assert "Big news Shares rose." in report
    assert len(report) < 800


@pytest.mark.unit
def test_missing_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        ds._search("NVDA stock news", 5)


@pytest.mark.unit
def test_news_data_chain_keeps_insider_trades_on_yahoo(monkeypatch):
    # news_data also covers get_insider_transactions, which DeepSeek does not serve.
    monkeypatch.setattr(ds, "_search", lambda query, count: [_result("Routed", "2026-10-09")])
    monkeypatch.setitem(router.VENDOR_METHODS["get_insider_transactions"], "yfinance",
                        lambda *a, **k: "insider rows")
    config_module._config["data_vendors"]["news_data"] = "deepseek,yfinance"
    assert "Routed" in router.route_to_vendor("get_news", "NVDA", "2026-10-05", "2026-10-12")
    assert router.route_to_vendor("get_insider_transactions", "NVDA", "2026-10-12") == "insider rows"
