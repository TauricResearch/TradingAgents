"""Peers and industry tables on the live snapshot (``tests/phase4_db.py``)."""

from __future__ import annotations

import math
import statistics

import pytest

from tests import phase4_db as p4, screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import catalog, peers, screens, snapshot, userdb
from tradingagents.screener.query import parse

pytestmark = pytest.mark.unit
NEAR = set(p4.NEAR)


@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    p4.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn)
    yield conn
    conn.close()


@pytest.fixture
def user(tmp_path):
    conn = userdb.connect(tmp_path / "user.db")
    yield conn
    conn.close()


def symbols(result) -> list[str]:
    return [r["nseSymbol"] for r in result["rows"]]


def test_peers_are_the_industrys_nearest_in_market_cap(india, user):
    r = peers.peers("GROWCO.NS", user_conn=user, india_conn=india)
    assert r["available"] and r["industry"] == "Capital Goods" and r["industryCount"] == 13
    assert set(symbols(r)) == NEAR | {"GROWCO"}  # not TINY20, HUGE300K or HUGE500K
    caps = [row["values"]["market_cap"] for row in r["rows"]]
    assert caps == sorted(caps, reverse=True)  # by market cap, largest first
    assert r["query"] == "Industry = 'Capital Goods'"
    assert r["isin"] == fx.GROWCO and not r["lender"]


def test_nearest_is_by_ratio_and_keeps_the_company():
    members = [("A", 1000.0), ("B", 500.0), ("C", 2000.0), ("D", 4000.0), ("E", None), ("F", -5.0)]
    assert peers.nearest(members, "A", 1000.0, 3) == ["A", "C", "B"]  # 500 and 2000 are equally near: larger first
    assert peers.nearest(members, "Z", None, 3) == ["Z", "D", "C"]  # unknown cap: the largest
    assert "E" not in peers.nearest(members, "A", 1000.0, 10) and "F" not in peers.nearest(members, "A", 1000.0, 10)
    assert math.isclose(abs(math.log(500 / 1000)), abs(math.log(2000 / 1000)))


def test_the_median_row_is_over_the_peers_shown(india, user):
    r = peers.peers("GROWCO.NS", user_conn=user, india_conn=india)
    caps = [row["values"]["market_cap"] for row in r["rows"]]
    assert r["median"]["market_cap"] == pytest.approx(statistics.median(caps))
    assert r["median"]["market_cap"] == pytest.approx((p4.NEAR["NEAR4000"] + caps[5]) / 2)  # GROWCO is 6th of 10


def test_default_columns_are_screener_ins_peer_columns(india, user):
    r = peers.peers("GROWCO.NS", user_conn=user, india_conn=india)
    assert [c["id"] for c in r["columns"]] == list(peers.DEFAULT_COLUMNS)


def test_lenders_get_lender_columns_from_the_applicability_flag(india, user):
    r = peers.peers("LENDERBANK.NS", user_conn=user, india_conn=india)
    ids = [c["id"] for c in r["columns"]]
    assert r["lender"] and "roce" not in ids and {"roe", "pb", "roa"} <= set(ids)
    assert not [k for k in ids if catalog.METRICS[k].applies == catalog.NON_FINANCIAL]
    assert set(symbols(r)) == {"LENDERBANK", "OTHERBANK"}


def test_financial_services_without_filings_counts_as_a_lender(india, user):
    r = peers.peers("OTHERBANK.NS", user_conn=user, india_conn=india)  # no filings: financial flag 0
    assert r["lender"] and "roe" in [c["id"] for c in r["columns"]]


def test_columns_and_sort_follow_the_picker(india, user):
    r = peers.peers("GROWCO.NS", columns=["roce", "return_1y"], sort={"key": "current_price", "dir": "asc"},
                    user_conn=user, india_conn=india)
    assert [c["id"] for c in r["columns"]] == ["name", "current_price", "roce", "return_1y"]
    prices = [row["values"]["current_price"] for row in r["rows"]]
    assert prices == sorted(prices)


def test_custom_ratios_work_as_peer_columns(india, user):
    ratio = screens.save_ratio(user, {"definition": "Cap per price = Market Capitalization / Current price"})
    r = peers.peers("GROWCO.NS", columns=[ratio.describe()["column"]], user_conn=user, india_conn=india)
    ids = [c["id"] for c in r["columns"]]
    assert ids == ["name", "current_price", "ratio:cap per price", "market_cap"]  # the sort's column joins
    assert r["columns"][2]["custom"] and r["rows"][0]["values"]["ratio:cap per price"] == pytest.approx(150.0)


def test_no_snapshot_explains_what_to_run(tmp_path, user):
    path = tmp_path / "bare.db"
    p4.build(path)
    conn = store.connect(path)
    with pytest.raises(peers.PeersUnavailable, match="build-snapshot"):
        peers.peers("GROWCO.NS", user_conn=user, india_conn=conn)


def test_no_india_database_explains_what_to_run(user):
    with pytest.raises(peers.PeersUnavailable, match="sync-all"):
        peers.peers("GROWCO.NS", user_conn=user)


def test_a_company_without_an_industry_has_no_peers(india, user):
    with pytest.raises(peers.PeersUnavailable, match="sync-securities"):
        peers.peers("UNCLASSED.NS", user_conn=user, india_conn=india)
    with pytest.raises(peers.PeersUnavailable, match="not in the India database"):
        peers.peers("NOSUCH.NS", user_conn=user, india_conn=india)


def test_a_company_outside_the_snapshot_says_so(tmp_path, user):
    path = tmp_path / "one.db"
    p4.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn, universe="GROWCO")
    with pytest.raises(peers.PeersUnavailable, match="not in the live snapshot"):
        peers.peers("LENDERBANK.NS", user_conn=user, india_conn=conn)


def test_the_industry_page_lists_every_stock_with_its_medians(india, user):
    r = peers.industry("capital goods", user_conn=user, india_conn=india)
    assert r["industry"] == "Capital Goods" and r["total"] == 13
    assert "industry" not in [c["id"] for c in r["columns"]]
    caps = [v for (v,) in india.execute("SELECT market_cap FROM metrics_snapshot WHERE industry='Capital Goods'")]
    assert r["median"]["market_cap"] == pytest.approx(statistics.median(caps))
    paged = peers.industry("Capital Goods", page_size=5, page=3, user_conn=user, india_conn=india)
    assert paged["pages"] == 3 and len(paged["rows"]) == 3


def test_an_unknown_industry_suggests_the_nearest(india, user):
    with pytest.raises(peers.IndustryNotFound, match="Capital Goods"):
        peers.industry("Capital Good", user_conn=user, india_conn=india)


def test_industries_are_counted(india):
    found = {i["name"]: i["count"] for i in peers.industries(india)}
    assert found == {"Capital Goods": 13, "Financial Services": 2}


def test_the_industry_query_escapes_quotes_and_parses():
    query = peers.industry_query("O'Brien & Sons")
    assert query == "Industry = 'O''Brien & Sons'"
    assert parse(query, screens.name_table([])).right.value == "O'Brien & Sons"


def test_lender_defaults_hold_no_non_financial_metric():
    assert not [k for k in peers.default_columns(True) if catalog.METRICS[k].applies == catalog.NON_FINANCIAL]
    assert "roce" in peers.default_columns(False)


def test_peer_selection_reads_the_snapshot_through_the_engine(india, user, monkeypatch):
    from tradingagents.screener import engine

    calls = []
    real = engine.run
    monkeypatch.setattr(engine, "run", lambda *a, **k: calls.append((a, k)) or real(*a, **k))
    peers.peers("GROWCO.NS", user_conn=user, india_conn=india)
    assert calls[0][0][0] == "Industry = 'Capital Goods'" and calls[1][1]["isins"]
