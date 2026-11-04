"""ASX (.AX) support: ticker spellings, the announcements feed, regional news,
Australian macro aliases and Australian subreddits."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from tradingagents.agents import tools
from tradingagents.agents.analysts.sentiment_analyst import _build_system_message
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.symbols import asx_code, is_asx, normalize_symbol
from tradingagents.dataflows.vendors import asx, fred, reddit
from tradingagents.dataflows.vendors.yahoo import news as ynews

# --- ticker spellings ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("raw, expected", [
    ("ASX:BHP", "BHP.AX"),
    ("asx:cba", "CBA.AX"),
    ("BHP.ASX", "BHP.AX"),
    ("BHP.AX", "BHP.AX"),
    ("bhp.ax", "BHP.AX"),
    ("ASX:A2M", "A2M.AX"),
    # Not ASX spellings: left as they were.
    ("BHP", "BHP"),
    ("ASX:TOOLONGX", "ASX:TOOLONGX"),
    ("NYSE:BHP", "NYSE:BHP"),
])
def test_asx_spellings_resolve_to_yahoo(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.unit
def test_is_asx_and_asx_code():
    assert is_asx("BHP.AX") and is_asx("ASX:BHP") and is_asx("bhp.asx")
    assert not is_asx("BHP") and not is_asx("0700.HK") and not is_asx("BTC-USD")
    assert asx_code("ASX:WES") == "WES"
    assert asx_code("NVDA") is None


# --- ASX announcements --------------------------------------------------------

def _items():
    # Newest first, as the feed returns them.
    return [
        # 22 Oct 09:45 in Sydney (AEDT, UTC+11), though 21 Oct in UTC.
        {"date": "2026-10-21T22:45:40.000Z", "headline": "AGM Addresses",
         "announcementType": "CHAIRMAN'S ADDRESS", "isPriceSensitive": False},
        {"date": "2026-10-20T21:30:00.000Z", "headline": "Quarterly Activities Report",
         "announcementType": "QUARTERLY ACTIVITIES REPORT", "isPriceSensitive": True},
        {"date": "2026-10-15T05:00:00.000Z", "headline": "Change of Director's Interest",
         "announcementType": "DIRECTOR'S INTEREST", "isPriceSensitive": False},
    ]


def _response(status=200, items=None):
    resp = MagicMock(status_code=status)
    resp.json.return_value = {"data": {"items": _items() if items is None else items}}
    return resp


@pytest.mark.unit
def test_announcements_are_windowed_by_sydney_date():
    with patch.object(asx.requests, "get", return_value=_response()) as get:
        out = asx.get_announcements("BHP.AX", "2026-10-15", "2026-10-21")
    assert get.call_args.args[0].endswith("/companies/bhp/announcements")
    assert "Quarterly Activities Report" in out
    assert "**[PRICE SENSITIVE]**" in out
    assert "2026-10-21 08:30 Sydney" in out
    assert "Change of Director's Interest" in out
    # Dated 21 Oct in UTC but made on 22 Oct in Sydney: after a 21 Oct run.
    assert "AGM Addresses" not in out


@pytest.mark.unit
def test_a_window_older_than_the_feed_is_unavailable_not_empty():
    with patch.object(asx.requests, "get", return_value=_response()):
        out = asx.get_announcements("BHP.AX", "2026-09-01", "2026-09-07")
    assert "unavailable" in out and "not an absence" in out


@pytest.mark.unit
def test_a_window_partly_older_than_the_feed_says_what_is_missing():
    with patch.object(asx.requests, "get", return_value=_response()):
        out = asx.get_announcements("BHP.AX", "2026-10-01", "2026-10-21")
    assert "Quarterly Activities Report" in out
    assert "before 2026-10-15" in out


@pytest.mark.unit
def test_a_code_unknown_to_the_feed_reads_as_no_announcements():
    with patch.object(asx.requests, "get", return_value=_response(status=404)):
        out = asx.get_announcements("ZZZ.AX", "2026-10-15", "2026-10-21")
    assert "unavailable" in out or "no ASX announcements" in out


@pytest.mark.unit
@pytest.mark.parametrize("failure", [
    {"return_value": _response(status=503)},
    {"side_effect": requests.ConnectionError("down")},
])
def test_a_feed_failure_is_a_vendor_outage(failure):
    with patch.object(asx.requests, "get", **failure), pytest.raises(VendorUnavailableError):
        asx.get_announcements("BHP.AX", "2026-10-15", "2026-10-21")


@pytest.mark.unit
def test_a_non_asx_ticker_has_no_announcements():
    with pytest.raises(NoMarketDataError):
        asx.get_announcements("NVDA", "2026-10-15", "2026-10-21")


@pytest.mark.unit
def test_get_news_appends_announcements_for_asx_tickers_only():
    def fake_route(method, *args, **kwargs):
        return {"get_news": "NEWS", "get_company_announcements": "ANNOUNCEMENTS"}[method]

    with patch.object(tools, "route_to_vendor", side_effect=fake_route) as route:
        asx_out = tools.get_news.func("BHP.AX", "2026-10-15", "2026-10-21", "2026-10-21")
        us_out = tools.get_news.func("NVDA", "2026-10-15", "2026-10-21", "2026-10-21")
    assert asx_out == "NEWS\n\nANNOUNCEMENTS"
    assert us_out == "NEWS"
    assert [c.args[0] for c in route.call_args_list] == [
        "get_news", "get_company_announcements", "get_news"]


@pytest.mark.unit
def test_an_announcements_outage_does_not_end_the_run():
    from tradingagents.dataflows.router import route_to_vendor

    with patch.object(asx.requests, "get", side_effect=requests.ConnectionError("down")):
        out = route_to_vendor("get_company_announcements", "BHP.AX", "2026-10-15", "2026-10-21")
    assert out.startswith("DATA_UNAVAILABLE")


# --- regional news --------------------------------------------------------------

@pytest.mark.unit
def test_asx_global_news_runs_the_australian_searches_first(monkeypatch):
    searched = []

    class FakeSearch:
        def __init__(self, query, **_):
            searched.append(query)
            self.news = []

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    monkeypatch.setattr(ynews, "get_config", lambda: {
        "global_news_lookback_days": 7, "global_news_article_limit": 5,
        "global_news_queries": ["fed", "oil"],
        "regional_news_queries": {".AX": ["rba", "iron ore"]},
    })
    ynews.get_global_news_yfinance("2026-10-21", ticker="ASX:BHP")
    assert searched == ["rba", "iron ore", "fed", "oil"]

    searched.clear()
    ynews.get_global_news_yfinance("2026-10-21", ticker="NVDA")
    assert searched == ["fed", "oil"]


@pytest.mark.unit
def test_default_config_has_australian_news_searches():
    from tradingagents.default_config import build_default_config

    config = build_default_config()
    assert any("RBA" in q for q in config["regional_news_queries"][".AX"])
    assert config["data_vendors"]["exchange_announcements"] == "asx"


# --- macro ----------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("alias, series_id", [
    ("rba_cash_rate", "IRSTCI01AUM156N"),
    ("australia_10y", "IRLTLT01AUM156N"),
    ("australia_cpi", "AUSCPIALLQINMEI"),
    ("australia_unemployment", "LRUNTTTTAUM156S"),
    ("australia_real_gdp", "NGDPRSAXDCAUQ"),
    ("aud_usd", "DEXUSAL"),
    ("iron_ore", "PIORECRUSDM"),
    ("RBA Cash Rate", "IRSTCI01AUM156N"),
])
def test_australian_macro_aliases(alias, series_id):
    assert fred._resolve_series_id(alias) == series_id


# --- Reddit ---------------------------------------------------------------------

@pytest.mark.unit
def test_an_asx_ticker_is_searched_by_code_in_australian_communities():
    assert reddit.subreddits_for("BHP.AX") == reddit.ASX_SUBREDDITS
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=[]) as fetch:
        out = reddit.fetch_reddit_posts("BHP.AX")
    query, subs = fetch.call_args.args[:2]
    assert (query, subs) == ("BHP", "ASX_Bets+ausstocks+AusFinance")
    assert "r/wallstreetbets" not in out


@pytest.mark.unit
def test_sentiment_prompt_describes_the_australian_subreddits():
    msg = _build_system_message(
        ticker="BHP.AX", start_date="2026-10-14", end_date="2026-10-21",
        news_block="", stocktwits_block="", reddit_block="",
        subreddits=reddit.ASX_SUBREDDITS,
    )
    assert "r/ASX_Bets is speculative" in msg


@pytest.mark.unit
def test_announcement_types_read_naturally():
    items = [
        {"date": "2026-10-20T21:30:00.000Z", "headline": "Quarterly Activities Report",
         "announcementType": "QUARTERLY ACTIVITIES REPORT", "isPriceSensitive": True},
        {"date": "2026-10-19T21:30:00.000Z", "headline": "AGM Addresses",
         "announcementType": "CHAIRMAN'S ADDRESS", "isPriceSensitive": False},
    ]
    with patch.object(asx.requests, "get", return_value=_response(items=items)):
        out = asx.get_announcements("BHP.AX", "2026-10-15", "2026-10-21")
    assert "(Chairman's Address)" in out
    assert "Quarterly Activities Report (Quarterly" not in out
