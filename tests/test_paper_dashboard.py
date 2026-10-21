"""The Koral Equities browser serves genuine paper data and never broker orders."""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tradingagents.paper.cli import write_book
from tradingagents.paper.dashboard import ScanRuntime, _csv_bytes, make_handler, snapshot
from tradingagents.paper.engine import Bar, Book


def test_snapshot_untraded_account_has_no_invented_equity_curve(tmp_path):
    view = snapshot(Book.new("2026-10-21"), tmp_path / "portfolio.json")
    assert view["account"]["equity_gbp"] == 10000
    assert view["account"]["return_gbp"] == 0
    assert view["account"]["risk_per_trade_pct"] == 2
    assert view["history"] == view["ratings"] == view["events"] == []
    assert view["account"]["base_currency"] == "GBP"
    assert view["account"]["mode"] == "PAPER ONLY"


def test_snapshot_real_paper_fill_and_decision(tmp_path):
    book = Book.new("2026-10-20")
    book = book.step("2026-10-20", {}, 0.75, 0.75, 600)
    book._event("2026-10-20", "AGENT_RATING", ticker="AAPL", rating="Buy", reference_close_usd=100)
    assert book.submit_signal("AAPL", "Buy", 100, "2026-10-20")
    book = book.step("2026-10-21", {"AAPL": Bar(100, 102, 98, 101)}, .75, .75, 601)
    view = snapshot(book, tmp_path / "portfolio.json")
    assert len(view["positions"]) == 1
    assert view["positions"][0]["ticker"] == "AAPL"
    assert len(view["history"]) == 2
    assert view["ratings"][0]["rating"] == "Buy"
    assert view["account"]["invested_gbp"] > 0
    assert view["account"]["positions_count"] == 1


def test_export_protects_spreadsheet_formula_cells():
    result = _csv_bytes([{"ticker": '=cmd("oops")', "pnl_gbp": 0}], ["ticker", "pnl_gbp"])
    assert b"'=cmd" in result
    assert b"pnl_gbp" in result


def test_scan_rejects_invalid_tickers_without_starting_process(tmp_path):
    state = tmp_path / "portfolio.json"
    write_book(state, Book.new("2026-10-21"))
    runtime = ScanRuntime(state)
    with pytest.raises(ValueError):
        runtime.start(["AAPL;rm", "MSFT"])
    with pytest.raises(ValueError):
        runtime.start(["AAPL", "AAPL"])
    assert runtime.process is None


def test_read_only_http_api_and_scan_origin_guard(tmp_path):
    state = tmp_path / "portfolio.json"
    write_book(state, Book.new("2026-10-21"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(state, ScanRuntime(state)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(base + "/api/state", timeout=3) as response:
            data = json.load(response)
            assert data["account"]["equity_gbp"] == 10000
            assert response.headers["Cache-Control"] == "no-store"
        for name, content_type in [("/styles.css", "text/css"), ("/app.js", "javascript")]:
            with urlopen(base + name, timeout=3) as response:
                assert content_type in response.headers["Content-Type"]
                assert len(response.read()) > 2000
        request = Request(base + "/api/scan", method="POST", data=b'{"tickers":["AAPL"]}',
                          headers={"Content-Type": "application/json", "X-Koral-Action": "scan"})
        with pytest.raises(HTTPError) as exc:
            urlopen(request, timeout=3)
        assert exc.value.code == 403  # no Origin header, so no cross-site launch
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_scan_status_starts_idle(tmp_path):
    runtime = ScanRuntime(tmp_path / "portfolio.json")
    assert runtime.status()["running"] is False
    assert runtime.status()["finished"] is False
