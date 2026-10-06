"""The screener's metrics: the catalog, the snapshot, point-in-time builds, and
agreement with the Company page. No network: the India database is the
hand-written one in ``tests/screener_db.py`` and Yahoo Finance is a fake that
knows no stock, so the Company page stands on the database alone."""

from __future__ import annotations

import math
import random
import sqlite3
import time
from types import SimpleNamespace

import pytest

import tradingagents.dataflows.config as config_module
from tests import screener_db as fx
from tests.test_company_profile import FakeTicker
from tradingagents.dataflows import formulas as f
from tradingagents.dataflows.vendors.india import profile, store
from tradingagents.dataflows.vendors.yahoo import company_profile as yahoo, ohlcv
from tradingagents.screener import catalog, engine, snapshot

pytestmark = pytest.mark.unit
CR = fx.CR


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "india.db"
    fx.build(path)
    config_module._config["india_db_path"] = str(path)
    FakeTicker.calls, FakeTicker.tickers = [], {}
    monkeypatch.setattr(yahoo, "yf", SimpleNamespace(Ticker=FakeTicker))
    monkeypatch.setattr(yahoo, "_CACHE", {})
    monkeypatch.setattr(profile, "_CACHE", {})
    monkeypatch.setattr(ohlcv, "vendor_reachable", lambda url: True)
    return path


def build(path, as_of=None, universe="eq"):
    conn = store.connect(path)
    try:
        return snapshot.build_snapshot(conn, as_of=as_of, universe=universe)
    finally:
        conn.close()


def row(path, isin, as_of="live") -> dict:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        r = conn.execute("SELECT * FROM metrics_snapshot WHERE as_of_date=? AND isin=?", (as_of, isin)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


# --- The catalog ---------------------------------------------------------------------------

def test_every_metric_is_fully_described():
    assert len(catalog.METRICS) >= 70
    for m in catalog.METRICS.values():
        assert m.key == m.key.lower() and " " not in m.key
        assert m.name and m.description and m.category in catalog.CATEGORIES, m.key
        assert m.unit in {"", catalog.RS_CR, catalog.RS, catalog.PCT, catalog.PTS, catalog.TIMES, catalog.DAYS,
                          catalog.SCORE, catalog.SHARES, catalog.CR_SHARES, catalog.COUNT}, m.key
        assert m.applies in (catalog.ALL, catalog.NON_FINANCIAL) and callable(m.compute)
    names = [catalog.normalize(n) for m in catalog.METRICS.values() for n in (m.name, *m.aliases)]
    assert len(names) == len(set(names)), "a name or alias that two metrics share"
    assert catalog.lookup("roce").key == "roce" and catalog.lookup("Market  capitalization").key == "market_cap"
    assert catalog.lookup("Sector").key == "industry"


def test_the_catalog_covers_each_requested_group():
    keys = set(catalog.METRICS)
    assert {"market_cap", "current_price", "pe", "pb", "ev", "ev_ebitda", "peg", "dividend_yield",
            "earnings_yield", "graham_number", "price_to_sales"} <= keys
    assert {"roce", "roe", "roa", "opm", "npm", "roce_3y", "roce_5y", "roe_3y", "roe_5y"} <= keys
    assert {f"{w}_growth_{n}y" for w in ("sales", "profit", "eps") for n in (1, 3, 5, 10)} <= keys
    assert {"promoter_holding", "promoter_change_1q", "promoter_change_1y", "pledged", "fii_holding",
            "dii_holding", "fii_change_1q", "dii_change_1q", "num_shareholders", "shareholders_change_1q"} <= keys
    assert {"return_1m", "return_3m", "return_6m", "return_1y", "return_3y", "return_5y", "high_52w", "low_52w",
            "from_52w_high", "dma_50", "dma_200", "price_vs_dma50", "rsi", "volume_1m", "piotroski"} <= keys
    assert {"name", "nse_symbol", "industry"} <= {k for k, m in catalog.METRICS.items() if m.kind == "text"}


def test_shared_formulas_are_the_company_pages():
    from tradingagents.dataflows import company_profile as cp

    for name in ("roce", "roe", "opm", "ttm", "cagr", "leverage", "working_capital_days", "annual_growth",
                 "operating_profit", "price_growth", "roe_averages"):
        assert getattr(cp, name) is getattr(f, name), name


def test_rsi_and_moving_averages():
    assert f.sma([1, 2, 3, 4], 2) == 3.5 and f.sma([1], 2) is None
    assert f.rsi([float(i) for i in range(30)]) == 100.0
    assert f.rsi([5.0] * 30) is None
    up_down = [10.0, 11.0] * 20
    assert f.rsi(up_down) == pytest.approx(50.0, abs=3)


# --- The live snapshot ----------------------------------------------------------------------

def test_a_snapshot_has_a_row_per_stock_and_null_for_what_is_missing(db):
    result = build(db)
    assert (result.as_of_date, result.rows, result.data_date) == ("live", 3, "2026-10-02")
    empty = row(db, fx.NODATA)
    numeric = [k for k, m in catalog.METRICS.items() if m.kind == "number"]
    assert all(empty[k] is None for k in numeric), [k for k in numeric if empty[k] is not None]
    assert empty["name"] == "No Data Limited"
    bank = row(db, fx.BANK)
    assert bank["financial"] == 1 and bank["roce"] is None and bank["opm"] is None and bank["roe"] is not None


def test_growco_metrics_follow_the_formulas(db):
    build(db)
    g = row(db, fx.GROWCO)
    ttm_sales = sum(list(fx.QUARTER_SALES.values())[1:])
    assert g["sales"] == pytest.approx(ttm_sales)
    assert g["sales_ly"] == pytest.approx(fx.FY_SALES[2026])
    assert g["opm"] == pytest.approx(23.0)  # (0.20 + 0.03) of sales
    assert g["npm"] == pytest.approx(15.75)
    assert g["sales_growth_5y"] == pytest.approx(10.0) and g["sales_growth_3y"] == pytest.approx(10.0)
    assert g["sales_growth_10y"] is None  # six years of filings
    assert g["eps_growth_3y"] == pytest.approx(10.0)  # EPS restated for the split on both ends
    # ROCE: EBIT (pbt + interest = 0.22 s) over total assets - current liabilities (0.95 s).
    assert g["roce"] == pytest.approx(0.22 / 0.95 * 100)
    assert g["roe"] == pytest.approx(0.1575 / 0.6 * 100)
    assert g["debt_to_equity"] == pytest.approx(50 / (0.6 * fx.FY_SALES[2026]))
    assert g["current_ratio"] == pytest.approx(2.0)
    # 200 million shares after the 2:1 split, from NSE's PR file.
    assert g["shares_outstanding"] == pytest.approx(20.0)
    assert g["market_cap"] == pytest.approx(g["current_price"] * 2e8 / CR)
    # Dividends in the year to 2 Oct 2026: Rs 3.00 (Nov 2025) and Rs 2.50 (Aug 2026).
    assert g["dividend_yield"] == pytest.approx(5.5 / g["current_price"] * 100)
    eps_ttm = 0.1575 * ttm_sales * CR / 2e8
    assert g["eps"] == pytest.approx(eps_ttm) and g["pe"] == pytest.approx(g["current_price"] / eps_ttm)
    assert g["return_1y"] == pytest.approx((1.0004 ** 261 - 1) * 100, abs=1.0)
    assert g["promoter_holding"] == 52.0 and g["promoter_change_1q"] == pytest.approx(0.5)
    assert g["promoter_change_1y"] == pytest.approx(2.0) and g["pledged"] == 0.5
    assert g["shareholders_change_1q"] == pytest.approx((120 / 115 - 1) * 100)
    assert g["fcf_3y"] == pytest.approx(0.12 * (fx.FY_SALES[2024] + fx.FY_SALES[2025] + fx.FY_SALES[2026]))
    assert g["sales_growth_yoy_q"] == pytest.approx((440 / 380 - 1) * 100)
    assert g["sales_growth_qoq"] == pytest.approx((440 / 425.51 - 1) * 100)
    assert 0 <= g["piotroski"] <= 9 and g["rsi"] == 100.0  # a price that only rises


def test_the_company_page_shows_the_snapshots_figures(db):
    """The consistency rule: every figure a screen filters on reads the same on the
    Company page, for a manufacturer and for a bank."""
    build(db)
    for symbol, isin in (("GROWCO.NS", fx.GROWCO), ("LENDERBANK.NS", fx.BANK)):
        snap = row(db, isin)
        page = profile.build_company_profile(symbol)
        shown = page["metrics"]["values"]
        assert set(shown) == set(catalog.METRICS)
        for key, value in shown.items():
            assert value == snap[key], (symbol, key, value, snap[key])
        ratios = {r["key"]: r["value"] for r in page["keyRatios"]}
        for key in ("market_cap", "pe", "book_value", "dividend_yield", "roe", "face_value"):
            assert ratios[key] == snap[{"market_cap": "market_cap"}.get(key, key)], (symbol, key)
        assert ("roce" in ratios) is (snap["financial"] == 0)

    # The page's own tables, built by Phase 1's row formulas, agree with the screener to the cent.
    g = row(db, fx.GROWCO)
    page = profile.build_company_profile("GROWCO.NS")
    last = {r["key"]: r["values"][-1] for r in page["ratios"]["rows"]}
    assert last["roce"] == round(g["roce"], 2) and last["roe"] == round(g["roe"], 2)
    assert last["working_capital_days"] == round(g["working_capital_days"], 2)
    assert last["cash_conversion_cycle"] == round(g["cash_conversion_cycle"], 2)
    pl = page["profitLoss"]
    assert pl["periods"][-1]["ttm"] is True
    ttm = {r["key"]: r["values"][-1] for r in pl["rows"]}
    year = {r["key"]: r["values"][-2] for r in pl["rows"]}
    assert ttm["sales"] == round(g["sales"], 2) and ttm["net_profit"] == round(g["net_profit"], 2)
    assert ttm["operating_profit"] == round(g["operating_profit"], 2) and ttm["opm"] == round(g["opm"], 2)
    assert ttm["eps"] == round(g["eps"], 2) and year["sales"] == round(g["sales_ly"], 2)
    growth = {box["key"]: {i["label"]: i["value"] for i in box["items"]} for box in page["growth"]}
    assert growth["sales"]["3 Years"] == round(g["sales_growth_3y"], 2)
    assert growth["sales"]["5 Years"] == round(g["sales_growth_5y"], 2)
    assert growth["profit"]["3 Years"] == round(g["profit_growth_3y"], 2)
    assert growth["roe"]["3 Years"] == round(g["roe_3y"], 2) and growth["roe"]["5 Years"] == round(g["roe_5y"], 2)
    assert growth["price"]["1 Year"] == round(g["return_1y"], 2)
    assert growth["price"]["3 Years"] == round(g["return_3y"], 2)
    bs = {r["key"]: r["values"][-1] for r in page["balanceSheet"]["rows"]}
    assert bs["borrowings"] == round(g["debt"], 2) and bs["reserves"] == round(g["reserves"], 2)
    cf = {r["key"]: r["values"][-1] for r in page["cashFlows"]["rows"]}
    assert cf["free_cash_flow"] == round(g["fcf"], 2) and cf["operating"] == round(g["cfo"], 2)
    quarter = {r["key"]: r["values"][-1] for r in page["quarters"]["rows"]}
    assert quarter["sales"] == round(g["sales_q"], 2)
    assert page["shareholding"]["trend"]["promoter_pct"][-1] == g["promoter_holding"]
    hi_lo = next(r for r in page["keyRatios"] if r["key"] == "high_low")["value"]
    assert hi_lo == [g["high_52w"], g["low_52w"]]


def test_the_standalone_view_keeps_its_own_key_ratios(db):
    conn = store.connect(db)
    end = "2026-03-31"
    rows = [(end, "A", "2025-04-01", k, v, "INR") for k, v in fx.income(900.0, 2e8, 5.0).items()]
    rows += [(end, "I", None, k, v, "INR") for k, v in fx.balance(900.0).items()]
    store.upsert_financials(conn, isin=fx.GROWCO, basis="standalone", filing_id="GROWCO-S", filed_at="2026-05-20T16:00:00",
                            source="test", rows=rows)
    conn.commit()
    conn.close()
    build(db)
    consolidated = profile.build_company_profile("GROWCO.NS")
    standalone = profile.build_company_profile("GROWCO.NS", "standalone")
    roe = {p["basis"]["current"]: next(r for r in p["keyRatios"] if r["key"] == "roe") for p in (consolidated, standalone)}
    assert roe["consolidated"]["screener"] == "roe" and roe["consolidated"]["value"] == row(db, fx.GROWCO)["roe"]
    assert "screener" not in roe["standalone"]  # its own basis, not the screener's consolidated figure
    assert standalone["metrics"]["basis"] == "consolidated"


# --- Point in time --------------------------------------------------------------------------

def test_a_snapshot_before_a_filing_does_not_see_it(db):
    build(db, "2026-05-19")
    before = row(db, fx.GROWCO, "2026-05-19")
    build(db, "2026-05-20")  # FY2026 was filed at 16:00 that day; a date covers the whole day
    after = row(db, fx.GROWCO, "2026-05-20")
    assert before["sales_ly"] == pytest.approx(fx.RESTATED_FY2025_SALES)
    assert after["sales_ly"] == pytest.approx(fx.FY_SALES[2026])
    assert before["sales_growth_5y"] is None  # FY2020 is not in the database
    assert after["sales_growth_5y"] == pytest.approx(10.0)


def test_a_restatement_counts_only_from_its_own_filing(db):
    build(db, "2025-10-06")
    build(db, "2026-04-01")
    original = row(db, fx.GROWCO, "2025-10-06")
    restated = row(db, fx.GROWCO, "2026-04-01")
    assert original["sales_ly"] == pytest.approx(fx.FY_SALES[2025])
    assert restated["sales_ly"] == pytest.approx(fx.RESTATED_FY2025_SALES)


def test_a_historical_snapshot_reads_prices_and_shares_as_they_were(db):
    build(db, "2025-05-02")  # a month before the 2:1 split
    g = row(db, fx.GROWCO, "2025-05-02")
    conn = store.open_existing(db)
    raw = conn.execute("SELECT close FROM prices_daily WHERE isin=? AND date='2025-05-02'", (fx.GROWCO,)).fetchone()[0]
    conn.close()
    assert g["current_price"] == pytest.approx(raw)  # not yet halved for a split nobody knew of
    assert g["shares_outstanding"] == pytest.approx(10.0)
    assert g["market_cap"] == pytest.approx(raw * 1e8 / CR)
    # The year to 2 May 2025 holds only the Rs 4 dividend of February, before any restatement.
    assert g["dividend_yield"] == pytest.approx(4.0 / raw * 100)
    assert g["price_date"] == "2025-05-02" and g["sales_q"] is None  # no quarter filed by then


def test_historical_snapshots_are_kept_side_by_side(db):
    build(db)
    build(db, "2025-10-06")
    conn = store.open_existing(db)
    built = [s["as_of"] for s in snapshot.list_snapshots(conn)]
    conn.close()
    assert built == ["live", "2025-10-06"]
    result = engine.run("Sales last year < 2000", as_of="2025-10-06")  # GROWCO, not the bank
    assert result["snapshot"]["as_of"] == "2025-10-06" and result["total"] == 1
    with pytest.raises(snapshot.SnapshotError, match="build-snapshot --as-of 2024-01-01"):
        engine.run("Sales > 0", as_of="2024-01-01")


def test_a_future_or_unpriced_date_is_refused(db):
    with pytest.raises(snapshot.SnapshotError, match="future"):
        build(db, "2999-01-01")
    with pytest.raises(snapshot.SnapshotError, match="sync-prices"):
        build(db, "2019-01-01")


def test_the_universe_can_be_chosen(db):
    assert build(db, universe="GROWCO,LENDERBANK").rows == 2
    assert build(db, universe="all").rows == 3
    with pytest.raises(snapshot.SnapshotError, match="unknown universe"):
        build(db, universe="NOSUCH")


# --- NULLs and counts -------------------------------------------------------------------------

def test_missing_data_is_excluded_and_counted(db):
    build(db)
    r = engine.run("Return on capital employed > 0")
    assert (r["total"], r["excluded"], r["excludedFinancial"], r["universe"]) == (1, 2, 1, 3)
    r = engine.run("NOT Return on capital employed > 1000")
    assert (r["total"], r["excluded"]) == (1, 2)  # NOT of unknown is still unknown
    r = engine.run("ROCE > 0 OR ROE > 0")
    assert (r["total"], r["excluded"]) == (2, 1)  # the bank passes on its ROE
    r = engine.run("ROCE > 1000 AND Current price > 0")
    assert (r["total"], r["excluded"]) == (0, 2)  # false for GROWCO, unknown for the other two
    r = engine.run("Industry IN ('capital goods', 'Power')")
    assert [x["nseSymbol"] for x in r["rows"]] == ["GROWCO"] and r["excluded"] == 1


def test_a_run_reports_rows_columns_median_and_pages(db):
    build(db)
    r = engine.run("Current price > 0", columns=["roe", "market_cap"], sort={"key": "current_price", "dir": "asc"},
                   page_size=1)
    assert [c["id"] for c in r["columns"]] == ["name", "current_price", "roe", "market_cap"]
    assert (r["total"], r["pages"], r["page"]) == (2, 2, 1)
    assert r["rows"][0]["nseSymbol"] == "GROWCO" and r["rows"][0]["symbol"] == "GROWCO.NS"
    prices = sorted(row(db, i)["current_price"] for i in (fx.GROWCO, fx.BANK))
    assert r["median"]["current_price"] == pytest.approx(sum(prices) / 2)
    second = engine.run("Current price > 0", sort={"key": "current_price", "dir": "asc"}, page=2, page_size=1)
    assert second["rows"][0]["nseSymbol"] == "LENDERBANK"


# --- Performance --------------------------------------------------------------------------------

def test_a_typical_screen_over_5000_stocks_runs_well_under_300_ms(tmp_path):
    path = tmp_path / "big.db"
    conn = store.connect(path)
    snapshot.ensure_schema(conn)
    rnd = random.Random(7)
    numeric = [k for k, m in catalog.METRICS.items() if m.kind == "number"]
    names = ["as_of_date", "isin", "built_at", "name", "nse_symbol", "industry", "financial", *numeric]
    rows = []
    for i in range(5000):
        values = [None if rnd.random() < 0.15 else rnd.uniform(-50, 5000) for _ in numeric]
        rows.append(["live", f"IN{i:010d}", "now", f"Company {i}", f"SYM{i}", rnd.choice(["Power", "Realty", None]),
                     0, *values])
    conn.executemany(f"INSERT INTO metrics_snapshot ({', '.join(chr(34) + n + chr(34) for n in names)}) "
                     f"VALUES ({', '.join('?' * len(names))})", rows)
    conn.execute("INSERT INTO snapshot_builds VALUES ('live', '2026-10-02', 'now', 5000, 'eq', 0, 1)")
    conn.commit()
    query = ("Market Capitalization > 500 AND Return on capital employed > 20\nDebt to equity < 0.5\n"
             "Sales growth 3 years > 10 OR Price to earnings < 15\nPromoter holding > 40")
    engine.run(query, india_conn=conn)  # warm the page cache
    began = time.perf_counter()
    result = engine.run(query, india_conn=conn)
    elapsed = (time.perf_counter() - began) * 1000
    conn.close()
    assert result["universe"] == 5000 and result["total"] > 0
    assert elapsed < 300, f"{elapsed:.0f} ms"


def test_a_screen_that_runs_too_long_is_stopped(tmp_path):
    path = tmp_path / "slow.db"
    conn = store.connect(path)
    snapshot.ensure_schema(conn)
    conn.executemany('INSERT INTO metrics_snapshot (as_of_date, isin, built_at, "roce") VALUES (?,?,?,?)',
                     [("live", f"IN{i:010d}", "now", float(i)) for i in range(3000)])
    conn.execute("INSERT INTO snapshot_builds VALUES ('live', '2026-10-02', 'now', 3000, 'eq', 0, 1)")
    conn.commit()
    with pytest.raises(engine.ScreenTimeout, match="longer than"):
        engine.run("ROCE * ROCE / (ROCE + 1) > 5", india_conn=conn, time_limit=0)
    assert engine.run("ROCE > 5", india_conn=conn)["total"] == 2994  # the limit is reset afterwards
    conn.close()


def test_no_india_database_says_what_to_run():
    with pytest.raises(engine.ScreenerUnavailable, match="india sync-all"):
        engine.run("ROCE > 20")


def test_a_database_without_a_snapshot_says_what_to_run(db):
    with pytest.raises(snapshot.SnapshotError, match="india build-snapshot"):
        engine.run("ROCE > 20")
    assert math.isfinite(build(db).elapsed)
