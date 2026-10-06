"""The API for peers, industries, watchlists, alerts and exports, over real HTTP.
The India database is ``tests/phase4_db.py``; the agents are the server tests'
fake graph; delivery channels are mocked."""

from __future__ import annotations

import io
import json
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

import pytest

import tradingagents.dataflows.config as config_module
from cli import main as cli_main
from cli.webui import server
from cli.webui.jobs import JobRegistry
from tests import phase4_db as p4
from tests.test_webui_server import SETTINGS, FakeGraph
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.india import profile as india_profile, store
from tradingagents.graph import trading_graph
from tradingagents.screener import delivery, snapshot

pytestmark = pytest.mark.unit

_CONNECT = socket.socket.connect


@pytest.fixture
def base(tmp_path, monkeypatch):
    blocked = socket.socket.connect

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return _CONNECT(sock, address)
        return blocked(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", FakeGraph)
    for config in {id(c): c for c in (server.DEFAULT_CONFIG, cli_main.DEFAULT_CONFIG)}.values():
        monkeypatch.setitem(config, "results_dir", str(tmp_path / "results"))
        monkeypatch.setitem(config, "memory_log_path", str(tmp_path / "memory" / "log.md"))
    monkeypatch.setattr(server, "load_last_run", lambda: {})
    monkeypatch.setattr(server, "save_last_run", lambda selections: None)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for name in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID", "WEBHOOK_URL", "SMTP_HOST", "SMTP_TO", "SMTP_USER",
                 "SMTP_PASSWORD"):
        monkeypatch.delenv(delivery.PREFIX + name, raising=False)
    httpd = server.make_server("127.0.0.1", 0, JobRegistry())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def india(tmp_path, monkeypatch):
    path = tmp_path / "india.db"
    p4.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn)
    conn.close()
    config_module._config["india_db_path"] = str(path)

    def no_yahoo(symbol):
        raise NoMarketDataError(symbol)
    monkeypatch.setattr(india_profile.yahoo, "fetch_company_data", no_yahoo)
    monkeypatch.setattr(india_profile, "_CACHE", {})
    return path


def call(base, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            raw = res.read()
            if res.headers.get("Content-Type", "").startswith("application/json"):
                return res.status, json.loads(raw)
            return res.status, (raw, dict(res.headers))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# --- Peers and industries ----------------------------------------------------------------------

def test_peers(base, india):
    status, data = call(base, "/api/peers?symbol=GROWCO.NS")
    assert status == 200 and data["available"] and len(data["rows"]) == 10 and data["industry"] == "Capital Goods"
    assert {"columns", "rows", "median", "sort", "snapshot", "defaultColumns"} <= set(data)
    status, data = call(base, "/api/peers?symbol=GROWCO.NS&columns=roce,pe&sort=pe:asc")
    assert [c["id"] for c in data["columns"]][:4] == ["name", "current_price", "roce", "pe"]
    status, data = call(base, "/api/peers?symbol=UNCLASSED.NS")
    assert status == 200 and not data["available"] and "india sync-securities" in data["note"]
    assert call(base, "/api/peers")[0] == 400
    assert call(base, "/api/peers?symbol=a%20b")[0] == 400


def test_peers_without_a_database_say_what_to_run(base):
    status, data = call(base, "/api/peers?symbol=GROWCO.NS")
    assert status == 200 and not data["available"] and "india sync-all" in data["note"]


def test_industries(base, india):
    status, data = call(base, "/api/industries")
    assert status == 200 and data[0] == {"name": "Capital Goods", "count": 13, "marketCap": data[0]["marketCap"]}
    status, data = call(base, "/api/industry?name=" + urllib.parse.quote("capital goods") + "&sort=market_cap:asc")
    assert status == 200 and data["industry"] == "Capital Goods" and data["total"] == 13
    assert data["rows"][0]["nseSymbol"] == "TINY20" and data["query"] == "Industry = 'Capital Goods'"
    status, data = call(base, "/api/industry?name=Nope")
    assert status == 404 and "No industry" in data["error"]
    assert call(base, "/api/industry")[0] == 400


def test_industry_without_a_snapshot_is_a_setup_error(base, tmp_path):
    path = tmp_path / "bare.db"
    p4.build(path)
    config_module._config["india_db_path"] = str(path)
    status, data = call(base, "/api/industry?name=Capital%20Goods")
    assert status == 503 and data["setup"] and "build-snapshot" in data["error"]


# --- Watchlists --------------------------------------------------------------------------------

def make_watchlist(base, **extra):
    status, w = call(base, "/api/watchlists", {"name": "Core", **extra})
    assert status == 200
    return w["id"]


def test_watchlist_crud_over_http(base, india):
    wid = make_watchlist(base)
    status, out = call(base, f"/api/watchlists/{wid}/items", {"symbols": ["GROWCO", "LENDERBANK.NS", "NOPE!"]})
    assert status == 200 and out["added"] == ["GROWCO.NS", "LENDERBANK.NS"] and out["rejected"][0]["symbol"] == "NOPE!"
    status, table = call(base, f"/api/watchlists/{wid}")
    assert status == 200 and [r["nseSymbol"] for r in table["rows"]] == ["LENDERBANK", "GROWCO"]
    assert table["snapshot"]["data_date"] and table["watchlist"]["name"] == "Core"
    status, item = call(base, f"/api/watchlists/{wid}/items/update", {"symbol": "GROWCO.NS", "note": "core holding"})
    assert status == 200 and item["note"] == "core holding"
    assert call(base, f"/api/watchlists/{wid}/items/update", {"symbol": "GROWCO.NS", "quantity": -1})[0] == 400
    status, out = call(base, f"/api/watchlists/{wid}/items/remove", {"symbols": ["LENDERBANK.NS"]})
    assert status == 200 and out["removed"] == 1
    status, w = call(base, "/api/watchlists", {"id": wid, "name": "Renamed", "columns": ["roce"],
                                               "sort": {"key": "roce", "dir": "asc"}})
    assert status == 200 and w["name"] == "Renamed" and w["columns"] == ["roce"]
    other = make_watchlist(base)
    status, listing = call(base, "/api/watchlists/order", {"ids": [other, wid]})
    assert status == 200 and [w["id"] for w in listing] == [other, wid]
    status, listing = call(base, "/api/watchlists")
    assert status == 200 and [w["count"] for w in listing] == [0, 1]
    assert call(base, f"/api/watchlists/{wid}/delete", {})[0] == 200
    assert call(base, f"/api/watchlists/{wid}")[0] == 404
    assert call(base, "/api/watchlists/999/items", {"symbols": ["GROWCO"]})[0] == 404
    assert call(base, "/api/watchlists", {"name": ""})[0] == 400


def test_watchlist_csv_import_and_symbols_export(base, india):
    wid = make_watchlist(base)
    status, out = call(base, f"/api/watchlists/{wid}/import",
                       {"csv": "symbol,note\nGROWCO,=1+1\nBAD SYMBOL,\nLENDERBANK,\n"})
    assert status == 200 and out["added"] == ["GROWCO.NS", "LENDERBANK.NS"] and out["rejected"][0]["line"] == 3
    status, (raw, headers) = call(base, f"/api/watchlists/{wid}/symbols.csv")
    assert status == 200 and raw.startswith(b"\xef\xbb\xbf") and "text/csv" in headers["Content-Type"]
    assert 'filename="watchlist_Core_symbols_' in headers["Content-Disposition"]
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0] == "symbol,name,note" and "'=1+1" in text
    assert call(base, f"/api/watchlists/{wid}/import", {"csv": ""})[0] == 400


def test_watchlists_need_the_india_database_to_add(base):
    wid = make_watchlist(base)
    status, data = call(base, f"/api/watchlists/{wid}/items", {"symbols": ["GROWCO"]})
    assert status == 503 and data["setup"] and "sync-all" in data["error"]


def test_holdings_become_the_runs_portfolio(base, india):
    wid = make_watchlist(base, holdings=True, cash=50000)
    call(base, f"/api/watchlists/{wid}/items", {"symbols": ["GROWCO"]})
    status, data = call(base, f"/api/watchlists/{wid}/portfolio")
    assert status == 400 and "quantity" in data["error"]
    call(base, f"/api/watchlists/{wid}/items/update", {"symbol": "GROWCO", "quantity": 100, "avgPrice": 150})
    status, portfolio = call(base, f"/api/watchlists/{wid}/portfolio")
    assert status == 200 and portfolio == {"cash": 50000.0, "currency": "INR", "positions": [
        {"ticker": "GROWCO.NS", "quantity": 100.0, "average_price": 150.0}]}
    status, table = call(base, f"/api/watchlists/{wid}")
    assert table["holdings"]["invested"] == 15000 and table["rows"][0]["position"]["pnl"] is not None
    # The Analyze page sends it as it sends a portfolio file's JSON; the run's log shows the block.
    status, run = call(base, "/api/analyses", {"ticker": "GROWCO.NS", "date": "2026-10-02", "analysts": ["market"],
                                               "settings": SETTINGS, "portfolio": portfolio})
    assert status == 201
    for _ in range(100):
        status, detail = call(base, f"/api/analyses/{run['id']}")
        if detail["status"] not in ("running", "pending"):
            break
        time.sleep(0.05)
    log = "\n".join(a["detail"] for a in detail["activity"])
    assert "Portfolio at the analysis date" in log and "Current position in GROWCO.NS: 100 units" in log
    assert "Cash available: 50,000.00 INR" in log
    # Queued from the watchlist page through the screens' queue, with the same portfolio.
    status, queued = call(base, "/api/screen/analyze", {"tickers": ["GROWCO.NS"], "date": "2026-10-02",
                                                        "analysts": ["market"], "settings": SETTINGS,
                                                        "portfolio": portfolio})
    assert status == 201 and len(queued["ids"]) == 1


# --- Alerts --------------------------------------------------------------------------------------

def test_alert_crud_and_the_inbox(base, india):
    status, alert = call(base, "/api/alerts", {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 100})
    assert status == 200 and alert["name"] == "GROWCO.NS above ₹100.00"
    status, bad = call(base, "/api/alerts", {"kind": "metric", "symbol": "GROWCO", "query": "Price to earnings <"})
    assert status == 400 and bad["errors"] and {"start", "end", "line", "col"} <= set(bad["errors"][0])
    status, overview = call(base, "/api/alerts")
    assert status == 200 and [a["id"] for a in overview["alerts"]] == [alert["id"]]
    assert overview["poller"]["enabled"] is False and not any(c["configured"] for c in overview["channels"].values())
    status, result = call(base, "/api/alerts/evaluate", {})
    assert status == 200 and result["evaluated"] == 1 and result["fired"] == 0  # a baseline
    status, off = call(base, "/api/alerts", {"id": alert["id"], "enabled": False})
    assert status == 200 and off["enabled"] is False
    assert call(base, "/api/alerts/evaluate", {"ids": "x"})[0] == 400
    status, inbox = call(base, "/api/alerts/inbox?unread=1")
    assert status == 200 and inbox == {"items": [], "unread": 0, "total": 0}
    assert call(base, "/api/alerts/unread") == (200, {"unread": 0})
    assert call(base, f"/api/alerts/{alert['id']}/delete", {})[0] == 200
    assert call(base, f"/api/alerts/{alert['id']}/delete", {})[0] == 404


def test_a_fired_alert_reaches_the_inbox_and_is_marked_read(base, india):
    conn = store.connect(india)
    call(base, "/api/alerts", {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200})
    call(base, "/api/alerts/evaluate", {})
    store.upsert_prices(conn, [(p4.fx.GROWCO, "2026-10-05", 205, 205, 205, 205, 1000, "EQ", "t")])
    conn.commit()
    conn.close()
    status, result = call(base, "/api/alerts/evaluate", {})
    assert result["fired"] == 1 and result["unread"] == 1
    assert call(base, "/api/alerts/evaluate", {})[1]["fired"] == 0
    status, inbox = call(base, "/api/alerts/inbox")
    [item] = inbox["items"]
    assert item["title"] == "GROWCO.NS closed at ₹205.00, above ₹200.00" and item["data_date"] == "2026-10-05"
    status, out = call(base, "/api/alerts/inbox/read", {"ids": [item["id"]]})
    assert status == 200 and out["unread"] == 0
    assert call(base, "/api/alerts/inbox/read", {"ids": "some"})[0] == 400
    status, out = call(base, "/api/alerts/inbox/delete", {"ids": "all"})
    assert status == 200 and out["deleted"] == 1


def test_channel_tests_and_secrets(base, india, monkeypatch):
    secrets = {"WEBHOOK_URL": "https://hooks.example.com/SECRET-PATH-123", "TELEGRAM_TOKEN": "42:SECRET-TOKEN-xyz",
               "TELEGRAM_CHAT_ID": "SECRET-CHAT", "SMTP_PASSWORD": "SECRET-PASSWORD"}
    for name, value in secrets.items():
        monkeypatch.setenv(delivery.PREFIX + name, value)
    assert call(base, "/api/alerts/channels/pigeon/test", {})[0] == 404
    status, data = call(base, "/api/alerts/channels/email/test", {})
    assert status == 400 and "not configured" in data["error"]

    def fail(url, data, content_type):
        raise urllib.error.URLError(f"no route to {url}")
    monkeypatch.setattr(delivery, "_post", fail)
    status, result = call(base, "/api/alerts/channels/webhook/test", {})
    assert status == 200 and result["ok"] is False and "no route to ***" in result["error"]
    status, telegram = call(base, "/api/alerts/channels/telegram/test", {})
    status, overview = call(base, "/api/alerts")
    seen = json.dumps([result, telegram, overview])
    assert overview["channels"]["webhook"]["configured"] and overview["channels"]["telegram"]["configured"]
    assert not any(v in seen for v in secrets.values()) and "SECRET" not in seen
    monkeypatch.setattr(delivery, "_post", lambda url, data, content_type: None)
    assert call(base, "/api/alerts/channels/webhook/test", {})[1]["ok"] is True


def test_cross_origin_posts_are_refused(base, india):
    for path in ("/api/watchlists", "/api/alerts", "/api/alerts/evaluate", "/api/alerts/inbox/read"):
        status, data = call(base, path, {"name": "x"}, headers={"Origin": "https://evil.example"})
        assert status == 403 and "Cross-origin" in data["error"]


# --- Exports -----------------------------------------------------------------------------------------

def sheets(raw: bytes) -> list[str]:
    import xml.etree.ElementTree as ET

    book = ET.fromstring(zipfile.ZipFile(io.BytesIO(raw)).read("xl/workbook.xml"))
    return [s.get("name") for s in book.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet")]


def test_screen_exports(base, india):
    query = urllib.parse.quote("Market Capitalization > 100")
    status, (raw, headers) = call(base, f"/api/export/screen.csv?query={query}&columns=pe&sort=current_price:asc"
                                        "&name=Big%20ones")
    assert status == 200 and raw.startswith(b"\xef\xbb\xbf")
    assert headers["Content-Disposition"].startswith('attachment; filename="screen_Big_ones_results_')
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == "Symbol,Name,Current price (Rs),Market Capitalization (Rs Cr),Price to earnings (x)"
    assert len(lines) == 15
    status, (raw, headers) = call(base, f"/api/export/screen.xlsx?query={query}")
    assert status == 200 and sheets(raw) == ["Stocks", "Notes"] and "spreadsheetml" in headers["Content-Type"]
    assert call(base, "/api/export/screen.csv")[0] == 400
    assert call(base, "/api/export/screen.pdf?query=x")[0] == 404
    status, data = call(base, "/api/export/screen.csv?query=" + urllib.parse.quote("Nonsense > 1"))
    assert status == 400 and data["errors"]


def test_peers_industry_and_watchlist_exports(base, india):
    status, (raw, headers) = call(base, "/api/export/peers.csv?symbol=GROWCO.NS")
    assert status == 200 and len(raw.decode("utf-8-sig").splitlines()) == 11
    assert 'filename="GROWCO_peers_' in headers["Content-Disposition"]
    assert call(base, "/api/export/peers.csv?symbol=UNCLASSED.NS")[0] == 503
    status, (raw, headers) = call(base, "/api/export/industry.xlsx?name=Capital%20Goods")
    assert status == 200 and sheets(raw) == ["Stocks", "Notes"]
    assert 'filename="industry_Capital_Goods_stocks_' in headers["Content-Disposition"]
    wid = make_watchlist(base, holdings=True)
    call(base, f"/api/watchlists/{wid}/items", {"symbols": ["GROWCO"]})
    call(base, f"/api/watchlists/{wid}/items/update", {"symbol": "GROWCO", "quantity": 10, "avgPrice": 100})
    status, (raw, headers) = call(base, f"/api/export/watchlist/{wid}.csv")
    header = raw.decode("utf-8-sig").splitlines()[0]
    assert status == 200 and header.endswith(",Note,Quantity,Average price (Rs),Invested (Rs),Current value (Rs),"
                                             "P&L (Rs),P&L (%)")
    assert call(base, "/api/export/watchlist/999.csv")[0] == 404


def test_the_company_workbook_downloads(base, india):
    status, (raw, headers) = call(base, "/api/export/company.xlsx?symbol=GROWCO.NS")
    assert status == 200 and sheets(raw) == ["Summary", "Quarters", "Profit & Loss", "Balance Sheet", "Cash Flow",
                                             "Ratios", "Shareholding", "Peers", "Notes"]
    assert headers["Content-Disposition"].startswith('attachment; filename="GROWCO_financials_')
    assert call(base, "/api/export/company.xlsx?symbol=")[0] == 400


def test_new_pages_are_served(base):
    for page in ("/watchlists", "/alerts", "/industry"):
        req = urllib.request.urlopen(base + page, timeout=5)
        assert req.status == 200 and b"app.js" in req.read()
