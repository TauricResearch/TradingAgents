"""The Company page for Indian stocks: the India database over Yahoo Finance.

Yahoo is the fake ticker of the Phase 1 tests (ACME.NS, four fiscal years);
the database holds the XBRL fixtures (ACME's consolidated Q4 FY2026 and
standalone Q3 FY2025 results, two shareholding patterns, SAMPLE BANK's Q1).
"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import tradingagents.dataflows.config as config_module
from tests.test_company_profile import ACME, FakeTicker
from tradingagents.dataflows.vendors.india import profile, store
from tradingagents.dataflows.vendors.india.sync import Syncer
from tradingagents.dataflows.vendors.yahoo import company_profile as yahoo

pytestmark = pytest.mark.unit
FIXTURES = Path(__file__).parent / "fixtures" / "india"
CR = 1e7


@pytest.fixture(autouse=True)
def fake_yahoo(monkeypatch):
    FakeTicker.calls = []
    FakeTicker.tickers = {"ACME.NS": ACME}
    monkeypatch.setattr(yahoo, "yf", SimpleNamespace(Ticker=FakeTicker))
    monkeypatch.setattr(yahoo, "_CACHE", {})
    monkeypatch.setattr(profile, "_CACHE", {})


class _Raw:
    def __init__(self, raw):
        self.raw = Path(raw)

    def store(self, relative, data):
        path = self.raw / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "india.db"
    conn = store.connect(path)
    Syncer(conn, client=_Raw(tmp_path / "raw"), today=date(2026, 10, 5)).import_files([FIXTURES])
    conn.commit()
    conn.close()
    config_module._config["india_db_path"] = str(path)
    return path


def test_without_a_database_the_page_is_phase_1s():
    assert profile.build_company_profile("ACME.NS") == yahoo.build_company_profile("ACME.NS")


def test_an_empty_database_or_an_unknown_company_changes_nothing(tmp_path):
    store.connect(tmp_path / "empty.db").close()
    config_module._config["india_db_path"] = str(tmp_path / "empty.db")
    assert profile.build_company_profile("ACME.NS") == yahoo.build_company_profile("ACME.NS")


def test_non_indian_symbols_never_touch_the_database(db, monkeypatch):
    monkeypatch.setattr(store, "open_existing", lambda *a: pytest.fail("opened the India database"))
    FakeTicker.tickers["ACME"] = ACME
    assert profile.build_company_profile("ACME")["symbol"] == "ACME"


def test_filed_sections_replace_yahoos_and_say_so(db):
    p = profile.build_company_profile("ACME.NS")
    assert p["basis"] == {"current": "consolidated", "available": ["consolidated", "standalone"]}
    assert p["quarters"]["source"].startswith("NSE filings (consolidated) · Mar 2026")
    assert [x["label"] for x in p["quarters"]["periods"]] == ["Mar 2026"]
    sales = next(r for r in p["quarters"]["rows"] if r["key"] == "sales")
    assert sales["values"] == [12500.0]  # crores on the page, rupees in the database
    assert p["profitLoss"]["source"].startswith("NSE filings (consolidated) · FY2026")
    assert p["balanceSheet"]["source"].startswith("NSE filings") and "lease" in p["balanceSheet"]["note"]
    borrowings = next(r for r in p["balanceSheet"]["rows"] if r["key"] == "borrowings")
    assert borrowings["values"] == [10000.0]
    assert p["cashFlows"]["source"].startswith("NSE filings")
    fcf = next(r for r in p["cashFlows"]["rows"] if r["key"] == "free_cash_flow")
    assert fcf["values"] == [2000.0]
    assert p["source"]["name"] == "NSE filings and Yahoo Finance"
    assert {s["section"] for s in p["sources"]} >= {"Quarterly results", "Profit & loss", "Shareholding"}


def test_phase_1_formulas_run_on_the_filed_figures(db):
    p = profile.build_company_profile("ACME.NS")
    rows = {r["key"]: r["values"][-1] for r in p["profitLoss"]["rows"]}
    # Operating profit = sales - (expenses - finance costs) + depreciation, as Phase 1 defines it.
    assert rows["operating_profit"] == 47000 - (39900 - 800) + 1900
    assert rows["other_income"] == 1100.0  # pbt - operating income + interest
    ratios = {r["key"]: r["values"][-1] for r in p["ratios"]["rows"]}
    assert ratios["roe"] == pytest.approx(5900 / 40100 * 100, abs=0.01)
    face = next(k for k in p["keyRatios"] if k["key"] == "face_value")
    assert face["value"] == 10.0


def test_the_standalone_view_uses_standalone_filings_and_never_yahoos(db):
    p = profile.build_company_profile("ACME.NS", "standalone")
    assert p["basis"]["current"] == "standalone"
    assert [x["label"] for x in p["quarters"]["periods"]] == ["Dec 2024"]
    sales = next(r for r in p["quarters"]["rows"] if r["key"] == "sales")
    assert sales["values"] == [11000.0]
    assert p["profitLoss"]["periods"] == [] and "consolidated figures only" in p["profitLoss"]["note"]
    assert p["balanceSheet"]["periods"] == [] and p["cashFlows"]["periods"] == []


def test_an_unavailable_basis_falls_back_to_what_is_filed(db):
    p = profile.build_company_profile("SAMPLEBANK.NS", "consolidated")
    assert p["basis"] == {"current": "standalone", "available": ["standalone"]}


def test_shareholding_and_documents_sections(db):
    p = profile.build_company_profile("ACME.NS")
    sh = p["shareholding"]
    assert [x["end"] for x in sh["periods"]] == ["2021-09-30", "2026-06-30"]
    rows = {r["key"]: r["values"] for r in sh["rows"]}
    assert rows["promoter_pct"] == [56.0, 55.0] and rows["dii_pct"] == [11.0, 15.0]
    assert rows["pledged"] == [5.0, 10.0] and "reported together" in sh["note"]
    assert sh["trend"]["fii_pct"] == [19.0, 18.0]
    groups = {g["kind"]: g["items"] for g in p["documents"]["groups"]}
    assert set(groups) == {"results", "shareholding"}
    assert all(i["url"].startswith("https://nsearchives.nseindia.com/corporate/xbrl/") for i in groups["results"])


def test_the_chart_uses_adjusted_bhavcopy_prices_when_the_database_has_them(db):
    conn = store.connect(db)
    store.upsert_prices(conn, [("INE999Z01019", "2026-09-29", 1, 1, 1, 2000.0, 100, "EQ", "NSE bhavcopy"),
                               ("INE999Z01019", "2026-09-30", 1, 1, 1, 1000.0, 200, "EQ", "NSE bhavcopy")])
    store.upsert_action(conn, isin="INE999Z01019", ex_date="2026-09-30", type="bonus", details="BONUS 1:1",
                        ratio_num=1, ratio_den=1, factor=2.0, seen="2026-09-20")
    conn.commit()
    conn.close()
    p = profile.build_company_profile("ACME.NS")
    assert p["chart"]["close"] == [1000.0, 1000.0] and p["chart"]["volume"] == [200, 200]
    assert p["chart"]["source"].startswith("NSE bhavcopy") and "bonus" in p["chart"]["note"]


def test_a_bank_gets_the_lenders_layout_from_its_filing_format(db):
    p = profile.build_company_profile("SAMPLEBANK.NS")
    assert p["financial"] is True
    assert [r["key"] for r in p["quarters"]["rows"]][:3] == ["interest_income", "interest", "net_interest_income"]
    nii = next(r for r in p["quarters"]["rows"] if r["key"] == "net_interest_income")
    assert nii["values"] == [13000.0]


def test_when_yahoo_has_nothing_the_page_stands_on_the_filings(db, monkeypatch):
    p = profile.build_company_profile("SAMPLEBANK.NS")  # unknown to the fake Yahoo
    assert p["name"] == "SAMPLE BANK LIMITED" and "notice" in p
    assert p["quarters"]["periods"]


def test_an_unknown_symbol_with_no_filings_still_raises(db, monkeypatch):
    from tradingagents.dataflows.errors import NoMarketDataError
    from tradingagents.dataflows.vendors.yahoo import ohlcv

    monkeypatch.setattr(ohlcv, "vendor_reachable", lambda url: True)
    FakeTicker.tickers = {}
    with pytest.raises(NoMarketDataError):
        profile.build_company_profile("NOSUCH.NS")


def test_eps_before_a_later_bonus_is_restated_to_todays_shares(db):
    conn = store.connect(db)
    store.upsert_action(conn, isin="INE999Z01019", ex_date="2026-05-15", type="bonus", details="BONUS 1:1",
                        ratio_num=1, ratio_den=1, factor=2.0, seen="2026-05-01")
    conn.commit()
    conn.close()
    p = profile.build_company_profile("ACME.NS")
    eps = next(r for r in p["quarters"]["rows"] if r["key"] == "eps")
    assert eps["values"] == [82.25]  # 164.50 as filed on 24 Apr 2026, before the 2026-05-15 bonus


def test_fiscal_labels():
    assert profile.fiscal_label("2026-03-31") == "FY2026"
    assert profile.fiscal_label("2025-12-31") == "Dec 2025"


def test_server_passes_the_basis_through(db, monkeypatch):
    from cli.webui import server

    seen = []
    monkeypatch.setattr(profile, "build_company_profile", lambda s, b=None: seen.append((s, b)) or {"ok": 1})
    assert server.company("ACME.NS", "standalone") == {"ok": 1}
    assert seen == [("ACME.NS", "standalone")]
    with pytest.raises(server.ApiError):
        server.company("ACME.NS", "sideways")

