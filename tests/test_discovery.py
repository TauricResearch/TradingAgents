"""Koral Equities anytime discovery: testable without internet, models or orders."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradingagents.paper import discovery
from tradingagents.paper.discovery_web import DiscoveryRuntime, latest, safe_report
from tradingagents.paper.cli import write_book
from tradingagents.paper.engine import Book


def test_nasdaq_listing_parser_excludes_nonstocks():
    raw = ("Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
           "ABCD|Example Common Stock|G|N|N|100|N|N\n"
           "TEST|Example ETF|G|N|N|100|Y|N\n"
           "WXYZ|Example Warrant|G|N|N|100|N|N\n"
           "FAKE|Example Common Stock|G|Y|N|100|N|N\n"
           "File Creation Time: 2026102208\n")
    assert discovery.parse_directory(raw, "nasdaq") == ["ABCD"]


def test_other_listed_parser_is_supported():
    raw = ("ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n"
           "XYZA|Example Common Stock|N|XYZA|N|100|N|XYZA\n"
           "XYZB|Example Preferred Shares|N|XYZB|N|100|N|XYZB\n")
    assert discovery.parse_directory(raw, "other") == ["XYZA"]


def test_listing_feed_errors_never_fabricate_symbols(monkeypatch):
    monkeypatch.setattr(discovery, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(RuntimeError, match="No universe fabricated"):
        discovery.source_universe()


def test_sample_seed_is_deterministic_and_disclosed():
    names = [f"S{i:04}" for i in range(100)]
    a,sampled = discovery.select_sample(names, 17, 22)
    b,_ = discovery.select_sample(list(reversed(names)),17,22)
    assert sampled and a == b and len(a) == 17
    assert discovery.select_sample(names, 0, 22)[1] is False


@pytest.mark.parametrize("utc_date,expected",[
    (datetime(2026,10,22,14,0,tzinfo=timezone.utc),("2026-10-22","2026-10-21")),
    (datetime(2026,10,22,22,0,tzinfo=timezone.utc),("2026-10-23","2026-10-22")),
])
def test_completed_price_cutoff(utc_date,expected):
    assert discovery.price_cutoff(utc_date) == expected


def test_price_screen_only_complete_momentum_and_liquidity():
    start=datetime(2025,12,1,tzinfo=timezone.utc)
    days=[(start+timedelta(days=x)).date().isoformat() for x in range(250)]
    close=[10+x*.09 for x in range(250)]
    volumes=[1500000]*250
    row=discovery.screen_prices(close,volumes,days)
    assert row and row["return_6m"] > 0 and row["avg_dollar_volume"] > 2e6
    assert discovery.screen_prices(close[:-1],volumes,days) is None
    broken=list(close);broken[-3]=-1
    assert discovery.screen_prices(broken,volumes,days) is None


def test_profile_eligibility_is_strict_and_source_limitation_visible():
    price={"return_3m":.18}
    profile={"quoteType":"EQUITY","marketCap":900000000,"totalRevenue":200000000,
             "revenueGrowth":.22,"operatingMargins":.12,"grossMargins":.51,
             "freeCashflow":15000000,"totalCash":100000000,"totalDebt":15000000,
             "longName":"Test Compounder","sector":"Software","industry":"Applications"}
    qualified,status=discovery.qualify_profile(profile,price,discovery.ScreeningRules())
    assert status=="accepted" and qualified["research_score"]>0
    assert qualified["revenue_growth_vendor"]==.22
    assert discovery.qualify_profile({**profile,"quoteType":"ETF"},price,discovery.ScreeningRules())[0] is None
    assert discovery.qualify_profile({**profile,"revenueGrowth":None},price,discovery.ScreeningRules())[0] is None
    assert discovery.qualify_profile({**profile,"marketCap":70e9},price,discovery.ScreeningRules())[0] is None


def test_bull_case_is_assumption_not_probability():
    company={"market_cap_usd":1e9,"revenue_ttm_usd":300e6}
    outcomes=discovery.scenario_multiples(company)
    assert set(outcomes)=={"bear","base","bull"}
    assert outcomes["bull"]["illustrative_equity_multiple"] > outcomes["base"]["illustrative_equity_multiple"]
    assert outcomes["bull"]["revenue_cagr_assumed"]==.40


def test_safe_report_cannot_traverse_directories(tmp_path):
    home=tmp_path/"discovery"
    root=home/"runs"/"20261022T141500Z"/"reports"/"META"
    root.mkdir(parents=True)
    (root/"complete_report.html").write_text("research",encoding="utf-8")
    assert safe_report(home,"20261022T141500Z","META")==root/"complete_report.html"
    assert safe_report(home,"../", "META") is None
    assert safe_report(home,"20261022T141500Z","../META") is None
    assert safe_report(home,"20261022T141500Z","NOPE") is None


def test_saved_json_sanitises_local_report_paths(tmp_path):
    home=tmp_path/"discovery"
    run_id="20261022T141500Z"
    root=home/"runs"/run_id/"reports"/"META"
    root.mkdir(parents=True)
    (root/"complete_report.html").write_text("research")
    discovery.atomic_json(home/"latest.json",{
        "schema":"koral_equities_discovery_v1","run_id":run_id,"candidates":[],
        "ai_reports":[{"ticker":"META","status":"completed",
                       "report_path":"C:\\private\\research\\META.html"}],
    })
    shown=latest(home)
    assert "report_path" not in str(shown)
    assert shown["ai_reports"][0]["report_url"].startswith("/discovery/reports/")


def test_invalid_background_scan_request_does_not_spawn(tmp_path):
    d=DiscoveryRuntime(tmp_path/"disc")
    for n,ai in [(1,2),(2000,5),(True,0),("350",2)]:
        with pytest.raises(ValueError):
            d.start(n,ai)
    assert d.process is None


def test_research_snapshot_cannot_mutate_paper_book(tmp_path,monkeypatch):
    state=tmp_path/"paper"/"portfolio.json"
    write_book(state,Book.new("2026-10-21"))
    before=state.read_bytes()
    universe=["ABCD","EFGH"]
    monkeypatch.setattr(discovery,"source_universe",lambda:(universe,["offline mock"]))
    monkeypatch.setattr(discovery,"batch_prices",lambda symbols,end:[
        ("ABCD",[
            ((datetime(2025,12,1,tzinfo=timezone.utc)+timedelta(days=i)).date().isoformat(),
              10+i*.12,2_000_000) for i in range(250)
        ]),
    ])
    info={"quoteType":"EQUITY","marketCap":900e6,"totalRevenue":300e6,
          "revenueGrowth":.34,"longName":"Example Public Co","sector":"Software"}
    import sys
    monkeypatch.setitem(sys.modules,"yfinance",SimpleNamespace(Ticker=lambda name:
        SimpleNamespace(info=info)))
    result=discovery.scan_market(home=tmp_path/"discovery",max_symbols=0,top=2,
                profile_limit=2,ai=0,now=datetime(2026,10,22,14,tzinfo=timezone.utc))
    assert result["ai_reports"]==[] and result["notice"].endswith("ZERO ORDERS.")
    assert state.read_bytes()==before
    assert len(result["candidates"])==1


def test_dashboard_declares_discovery_independent():
    from tradingagents.paper.dashboard import STATIC
    html=(STATIC/"index.html").read_text(encoding="utf-8")
    app=(STATIC/"app.js").read_text(encoding="utf-8")
    for token in ('id="discover-btn"','id="discovery-progress"','id="discovery-results"'):
        assert token in html
    assert "beginDiscovery" in app
    assert "/api/discovery/start" in app
    assert "setInterval(updateDiscoveryStatus,3000)" in app


def test_scan_default_has_no_automatic_paper_orders(monkeypatch,tmp_path):
    from tradingagents.paper import cli
    from tradingagents.paper.engine import Bar
    book=Book.new("2026-10-21")
    book=book.step("2026-10-21",{},.75,.75,600)
    class Agent:
        def propagate(self,*args,**kwargs):
            return {"final_trade_decision":"RESEARCH"}, "Overweight"
        def save_reports(self,*args,**kwargs):
            pass
    import sys
    from tradingagents.graph import trading_graph
    monkeypatch.setattr(trading_graph,"TradingAgentsGraph",lambda **kw:Agent())
    quotes={"ABCD":{"2026-10-21":Bar(100,105,99,102)}}
    nextbook,n=cli.run_agents(book,quotes,["ABCD"],tmp_path/"portfolio.json",8.0)
    assert n==1 and nextbook.orders==[] and not nextbook.positions
    assert any(e["type"]=="AGENT_RATING" for e in nextbook.events)
