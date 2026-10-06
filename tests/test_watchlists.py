"""Watchlists: lists, stocks, notes, order, CSV, holdings and the portfolio they make."""

from __future__ import annotations

import json

import pytest

from tests import phase4_db as p4, screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.portfolio import load_portfolio
from tradingagents.screener import export, snapshot, userdb, watchlists
from tradingagents.screener.watchlists import WatchlistError

pytestmark = pytest.mark.unit


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


def make(user, india, symbols=("GROWCO", "LENDERBANK"), **body):
    w = watchlists.save(user, {"name": "Core", **body})
    watchlists.add(user, w["id"], list(symbols), india)
    return w["id"]


def test_create_rename_reorder_and_delete(user):
    a = watchlists.save(user, {"name": "  Long   term "})
    b = watchlists.save(user, {"name": "Trading"})
    c = watchlists.save(user, {"name": "Ideas", "holdings": True})
    assert a["name"] == "Long term" and c["holdings"]
    assert [w["name"] for w in watchlists.list_watchlists(user)] == ["Long term", "Trading", "Ideas"]
    watchlists.save(user, {"id": b["id"], "name": "Swing"})
    assert [w["name"] for w in watchlists.reorder(user, [c["id"], a["id"]])] == ["Ideas", "Long term", "Swing"]
    watchlists.delete(user, a["id"])
    assert [w["name"] for w in watchlists.list_watchlists(user)] == ["Ideas", "Swing"]
    with pytest.raises(WatchlistError, match="No such watchlist"):
        watchlists.get(user, a["id"])
    with pytest.raises(WatchlistError, match="No such watchlist"):
        watchlists.reorder(user, [999])
    with pytest.raises(WatchlistError, match="name"):
        watchlists.save(user, {"name": "  "})


def test_add_resolves_symbols_and_reports_the_rest(user, india):
    w = watchlists.save(user, {"name": "Core"})
    out = watchlists.add(user, w["id"], ["growco", "LENDERBANK.NS", fx.NODATA, "BAD SYMBOL!", "NOSUCH", ""], india)
    assert out["added"] == ["GROWCO.NS", "LENDERBANK.NS", "NODATA.NS"]
    assert [(r["symbol"], r["reason"]) for r in out["rejected"]] == [
        ("BAD SYMBOL!", "not a symbol (letters, digits and . & _ - only)"), ("NOSUCH", "not in the India database")]
    again = watchlists.add(user, w["id"], ["GROWCO.NS"], india)
    assert again["added"] == [] and again["already"] == ["GROWCO.NS"]
    items = watchlists.get(user, w["id"])["items"]
    assert [(i["isin"], i["symbol"], i["name"]) for i in items][0] == (fx.GROWCO, "GROWCO.NS", "Grow Co Limited")


def test_remove_by_symbol_or_isin(user, india):
    wid = make(user, india, ("GROWCO", "LENDERBANK", "NODATA"))
    assert watchlists.remove(user, wid, ["growco", fx.BANK, "NOT-THERE"]) == 2
    assert [i["symbol"] for i in watchlists.get(user, wid)["items"]] == ["NODATA.NS"]


def test_notes_and_holdings_fields(user, india):
    wid = make(user, india)
    item = watchlists.update_item(user, wid, "GROWCO.NS", {"note": "  Watch the margins  "})
    assert item["note"] == "Watch the margins"
    item = watchlists.update_item(user, wid, "GROWCO", {"quantity": "1,000", "avgPrice": 150.5})
    assert (item["quantity"], item["avgPrice"], item["note"]) == (1000.0, 150.5, "Watch the margins")
    for bad in ({"quantity": 0}, {"quantity": -5}, {"quantity": "lots"}, {"avgPrice": -1}, {"note": "x" * 501}):
        with pytest.raises(WatchlistError):
            watchlists.update_item(user, wid, "GROWCO", bad)
    with pytest.raises(WatchlistError, match="not on this watchlist"):
        watchlists.update_item(user, wid, "NODATA", {"note": "x"})


def test_columns_and_sort_are_saved_per_watchlist(user, india):
    wid = make(user, india)
    watchlists.save(user, {"id": wid, "columns": ["roce", "pe"], "sort": {"key": "pe", "dir": "asc"}})
    w = watchlists.get(user, wid)
    assert (w["columns"], w["sort"]) == (["roce", "pe"], {"key": "pe", "dir": "asc"})
    t = watchlists.table(user, wid, india)
    assert [c["id"] for c in t["columns"]] == ["name", "current_price", "roce", "pe"] and t["sort"]["key"] == "pe"
    with pytest.raises(Exception, match="Unknown column"):
        watchlists.save(user, {"id": wid, "columns": ["no_such_metric"]})


def test_csv_round_trip(user, india):
    wid = make(user, india, holdings=True)
    watchlists.update_item(user, wid, "GROWCO", {"note": "=HYPERLINK(\"x\")", "quantity": 10, "avgPrice": 150})
    header, rows = watchlists.csv_rows(user, wid)
    data = export.csv_bytes(header, rows)
    assert data.startswith("﻿".encode())
    text = data.decode("utf-8")
    assert "'=HYPERLINK" in text  # guarded on the way out
    other = watchlists.save(user, {"name": "Copy", "holdings": True})
    out = watchlists.import_csv(user, other["id"], text, india)
    assert out["added"] == ["GROWCO.NS", "LENDERBANK.NS"] and out["rejected"] == []
    growco = next(i for i in watchlists.get(user, other["id"])["items"] if i["symbol"] == "GROWCO.NS")
    assert (growco["note"], growco["quantity"], growco["avgPrice"]) == ("=HYPERLINK(\"x\")", 10.0, 150.0)


def test_csv_import_reports_bad_lines_with_their_numbers(user, india):
    wid = watchlists.save(user, {"name": "Import"})["id"]
    text = "symbol,note,quantity\nGROWCO,core,10\nNOSUCH,,\nBAD SYM,,\nLENDERBANK,,many\n,,\nNODATA,,\n"
    out = watchlists.import_csv(user, wid, text, india)
    assert out["added"] == ["GROWCO.NS", "NODATA.NS"]
    assert [(r["line"], r["symbol"]) for r in out["rejected"]] == [(3, "NOSUCH"), (4, "BAD SYM"), (5, "LENDERBANK")]
    assert "Quantity must be a number" in out["rejected"][2]["reason"]


def test_csv_import_without_a_header_reads_the_first_column(user, india):
    wid = watchlists.save(user, {"name": "Plain"})["id"]
    out = watchlists.import_csv(user, wid, "GROWCO\nLENDERBANK.NS\n", india)
    assert out["added"] == ["GROWCO.NS", "LENDERBANK.NS"]
    with pytest.raises(WatchlistError, match="empty"):
        watchlists.import_csv(user, wid, "  \n", india)


def test_holdings_math():
    p = watchlists.position_values(10, 150.0, 180.0)
    assert p == {"invested": 1500.0, "current": 1800.0, "pnl": 300.0, "pnlPct": 20.0}
    loss = watchlists.position_values(4, 250.0, 200.0)
    assert (loss["pnl"], loss["pnlPct"]) == (-200.0, -20.0)
    no_price = watchlists.position_values(5, 100.0, None)
    assert no_price["current"] is None and no_price["pnl"] is None and no_price["invested"] == 500.0
    total = watchlists.totals([p, loss, no_price])
    assert total == {"invested": 2500.0, "current": 2600.0, "pnl": 100.0, "pnlPct": 4.0, "counted": 2,
                     "positions": 3}


def test_the_table_values_holdings_at_the_snapshot_close(user, india):
    wid = make(user, india, holdings=True)
    watchlists.update_item(user, wid, "GROWCO", {"quantity": 100, "avgPrice": 150})
    t = watchlists.table(user, wid, india)
    row = next(r for r in t["rows"] if r["nseSymbol"] == "GROWCO")
    price = row["values"]["current_price"]
    assert row["position"]["current"] == pytest.approx(100 * price)
    assert row["position"]["pnl"] == pytest.approx(100 * (price - 150))
    assert t["holdings"]["invested"] == 15000 and t["holdings"]["positions"] == 1
    assert t["snapshot"]["data_date"] == fx.LAST_PRICE_DAY.isoformat()
    assert "position" not in next(r for r in t["rows"] if r["nseSymbol"] == "LENDERBANK")


def test_stocks_outside_the_snapshot_still_show(user, tmp_path):
    path = tmp_path / "narrow.db"
    p4.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn, universe="GROWCO")
    wid = make(user, conn)
    t = watchlists.table(user, wid, conn)
    assert [r["nseSymbol"] for r in t["rows"]] == ["GROWCO", "LENDERBANK"]
    assert t["rows"][1]["missing"] and t["rows"][1]["values"]["name"] == "Lender Bank Limited"


def test_without_a_snapshot_the_list_still_shows(user, tmp_path):
    path = tmp_path / "nosnap.db"
    p4.build(path)
    conn = store.connect(path)
    wid = make(user, conn)
    t = watchlists.table(user, wid, conn)
    assert len(t["rows"]) == 2 and "build-snapshot" in t["note"]


def test_holdings_make_the_portfolio_load_portfolio_reads(user, india, tmp_path):
    wid = make(user, india, holdings=True, cash=25000)
    watchlists.update_item(user, wid, "GROWCO", {"quantity": 100, "avgPrice": 150})
    watchlists.update_item(user, wid, "LENDERBANK", {"quantity": 20})
    built = watchlists.portfolio(user, wid)
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps({"cash": 25000, "currency": "INR", "positions": [
        {"ticker": "GROWCO.NS", "quantity": 100, "average_price": 150},
        {"ticker": "LENDERBANK.NS", "quantity": 20}]}), encoding="utf-8")
    assert built == load_portfolio(path)
    assert built.fingerprint() == load_portfolio(path).fingerprint()
    assert "Current position in GROWCO.NS: 100 units, average price 150.00" in built.render("GROWCO.NS")


def test_a_portfolio_needs_holdings(user, india):
    wid = make(user, india)
    with pytest.raises(WatchlistError, match="holdings mode"):
        watchlists.portfolio(user, wid)
    watchlists.save(user, {"id": wid, "holdings": True})
    with pytest.raises(WatchlistError, match="quantity"):
        watchlists.portfolio(user, wid)
