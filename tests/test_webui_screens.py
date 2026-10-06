"""The Screens page's API, over real HTTP: metrics, validate, run, saved screens,
custom ratios and the analysis queue. The India database is the hand-written one
in ``tests/screener_db.py``; the agents are the fake graph of the server tests."""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest

import tradingagents.dataflows.config as config_module
from cli import main as cli_main
from cli.webui import server
from cli.webui.jobs import JobRegistry
from tests import screener_db as fx
from tests.test_webui_server import SETTINGS, FakeGraph
from tradingagents.dataflows.vendors.india import store
from tradingagents.graph import trading_graph
from tradingagents.screener import snapshot

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
    httpd = server.make_server("127.0.0.1", 0, JobRegistry())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    fx.build(path)
    config_module._config["india_db_path"] = str(path)
    return path


@pytest.fixture
def built(india):
    conn = store.connect(india)
    snapshot.build_snapshot(conn)
    snapshot.build_snapshot(conn, as_of="2025-10-06")
    conn.close()
    return india


def call(base, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_the_screens_page_is_served(base):
    status, _ = call_raw(base, "/screens")
    assert status == 200


def call_raw(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as res:
        return res.status, res.read()


# --- Metrics, validate, run ---------------------------------------------------------------------

def test_metrics_list_the_catalog_ratios_and_snapshots(base, built):
    status, meta = call(base, "/api/screen/metrics")
    assert status == 200
    assert len(meta["metrics"]) >= 70 and meta["categories"][0] == "Company"
    roce = next(m for m in meta["metrics"] if m["key"] == "roce")
    assert "ROCE" in roce["aliases"] and roce["unit"] == "%" and roce["applies"] == "non_financial"
    assert [s["as_of"] for s in meta["snapshots"]] == ["live", "2025-10-06"]
    assert meta["ratios"] == []


def test_metrics_work_without_a_database(base):
    status, meta = call(base, "/api/screen/metrics")
    assert status == 200 and meta["snapshots"] == [] and meta["metrics"]


def test_validate_returns_ok_or_spans(base):
    status, ok = call(base, "/api/screen/validate", {"query": "ROCE > 20\nMarket cap > 500"})
    assert status == 200 and ok["ok"] and ok["columns"] == ["roce", "market_cap"]
    assert "banks" in ok["warnings"][0]
    status, bad = call(base, "/api/screen/validate", {"query": "Retrun on equity > 15"})
    assert status == 200 and not bad["ok"]
    assert bad["errors"] == [{"message": "Unknown metric 'Retrun on equity' at col 1 — did you mean "
                                         "'Return on equity'?", "start": 0, "end": 16, "line": 1, "col": 1}]


def test_a_run_returns_rows_counts_median_and_its_snapshot(base, built):
    status, r = call(base, "/api/screen/run", {"query": "Current price > 0 AND ROCE > 1", "columns": ["pe"],
                                               "sort": {"key": "roce", "dir": "desc"}})
    assert status == 200, r
    assert (r["total"], r["excluded"], r["excludedFinancial"], r["universe"]) == (1, 2, 1, 3)
    assert [c["id"] for c in r["columns"]] == ["name", "current_price", "roce", "pe"]
    [row] = r["rows"]
    assert row["symbol"] == "GROWCO.NS" and row["values"]["name"] == "Grow Co Limited"
    assert r["median"]["roce"] == row["values"]["roce"]
    assert r["snapshot"]["as_of"] == "live" and r["snapshot"]["data_date"] == "2026-10-02"
    assert r["elapsedMs"] >= 0 and r["page"] == 1


def test_a_run_as_of_a_past_snapshot(base, built):
    status, r = call(base, "/api/screen/run", {"query": "Sales last year > 0", "as_of": "2025-10-06"})
    assert status == 200 and r["snapshot"]["as_of"] == "2025-10-06"


@pytest.mark.parametrize("body, status, message", [
    ({"query": "Retrun on equity > 1"}, 400, "did you mean 'Return on equity'"),
    ({"query": "ROCE > 1", "as_of": "2024-01-01"}, 503, "india build-snapshot --as-of 2024-01-01"),
    ({"query": "ROCE > 1", "as_of": "yesterday"}, 503, "as_of must be a date"),
    ({"query": "ROCE > 1", "columns": ["nope"]}, 400, "Unknown column"),
    ({"query": "ROCE > 1", "sort": {"key": "roce", "dir": "sideways"}}, 400, "sort is"),
    ({"query": 5}, 400, "as text"),
    ({"query": "ROCE > 1", "page": "two"}, 400, "numbers"),
])
def test_bad_runs_say_what_is_wrong(base, built, body, status, message):
    code, reply = call(base, "/api/screen/run", body)
    assert code == status and message in reply["error"], reply


def test_a_query_error_carries_its_span(base, built):
    code, reply = call(base, "/api/screen/run", {"query": "ROCE > 1 AND Retrun on equity > 1"})
    assert code == 400 and reply["errors"][0]["start"] == 13


def test_without_a_database_or_snapshot_the_run_says_which_command_to_run(base, tmp_path):
    code, reply = call(base, "/api/screen/run", {"query": "ROCE > 1"})
    assert code == 503 and reply["setup"] is True and "india sync-all" in reply["error"]
    path = tmp_path / "empty.db"
    store.connect(path).close()
    config_module._config["india_db_path"] = str(path)
    code, reply = call(base, "/api/screen/run", {"query": "ROCE > 1"})
    assert code == 503 and reply["setup"] is True and "india build-snapshot" in reply["error"]


# --- Saved screens ------------------------------------------------------------------------------

def test_screens_are_created_updated_listed_and_deleted(base):
    status, lists = call(base, "/api/screens")
    assert status == 200 and lists["saved"] == [] and len(lists["presets"]) >= 8
    status, s = call(base, "/api/screens", {"name": "Mine", "query": "ROCE > 20", "columns": ["pe"]})
    assert status == 200 and s["name"] == "Mine" and s["columns"] == ["pe"]
    status, s2 = call(base, "/api/screens", {"id": s["id"], "name": "Renamed", "query": "ROCE > 25"})
    assert status == 200 and (s2["id"], s2["name"], s2["query"]) == (s["id"], "Renamed", "ROCE > 25")
    preset = lists["presets"][0]
    status, dup = call(base, "/api/screens", {**preset, "id": None, "name": preset["name"] + " (copy)"})
    assert status == 200 and dup["id"] != s["id"] and not dup["preset"]
    assert [x["name"] for x in call(base, "/api/screens")[1]["saved"]] == [dup["name"], "Renamed"]
    assert call(base, f"/api/screens/{s['id']}/delete", {}) == (200, {"ok": True})
    assert [x["id"] for x in call(base, "/api/screens")[1]["saved"]] == [dup["id"]]


@pytest.mark.parametrize("path, body, status, message", [
    ("/api/screens", {"name": "x", "query": "Retrun on equity > 1"}, 400, "did you mean"),
    ("/api/screens", {"name": "", "query": "ROCE > 1"}, 400, "name"),
    ("/api/screens", {"id": "preset:piotroski-strong", "name": "x", "query": "ROCE > 1"}, 400, "read-only"),
    ("/api/screens/preset:piotroski-strong/delete", {}, 400, "read-only"),
    ("/api/screens/12345/delete", {}, 400, "No such screen"),
    ("/api/screens/abc/delete", {}, 404, "No such screen"),
])
def test_bad_screen_requests(base, path, body, status, message):
    code, reply = call(base, path, body)
    assert code == status and message in reply["error"], reply


# --- Custom ratios ------------------------------------------------------------------------------

def test_ratios_are_created_listed_used_and_deleted(base, built):
    status, r = call(base, "/api/ratios", {"definition": "Earnings to price = Net profit / Market Capitalization"})
    assert status == 200 and r["name"] == "Earnings to price" and r["column"] == "ratio:earnings to price"
    assert [x["name"] for x in call(base, "/api/ratios")[1]] == ["Earnings to price"]
    assert call(base, "/api/screen/metrics")[1]["ratios"][0]["id"] == r["id"]
    status, run = call(base, "/api/screen/run", {"query": "Earnings to price > 0"})
    assert status == 200 and run["total"] == 2 and run["columns"][-1]["id"] == "ratio:earnings to price"
    status, clash = call(base, "/api/ratios", {"definition": "ROE = Sales"})
    assert status == 400 and "already a catalog metric" in clash["error"]
    status, cycle = call(base, "/api/ratios", {"id": r["id"], "definition": "Earnings to price = Earnings to price"})
    assert status == 400 and "circle" in cycle["error"]
    assert call(base, f"/api/ratios/{r['id']}/delete", {}) == (200, {"ok": True})
    assert call(base, "/api/ratios") == (200, [])
    assert call(base, "/api/ratios/x/delete", {})[0] == 404
    assert call(base, "/api/ratios/999/delete", {})[0] == 400


def test_mutations_from_another_origin_are_refused(base):
    for path in ("/api/screens", "/api/ratios", "/api/screen/analyze", "/api/screens/1/delete"):
        code, reply = call(base, path, {"name": "x", "query": "ROCE > 1"}, headers={"Origin": "https://evil.example"})
        assert code == 403, path


# --- Analyze with agents ------------------------------------------------------------------------

def test_picked_stocks_are_queued_and_run_one_after_another(base):
    status, res = call(base, "/api/screen/analyze", {"tickers": ["GROWCO.NS", "LENDERBANK.NS"], "date": "2026-09-01",
                                                     "analysts": ["market"], "settings": SETTINGS})
    assert status == 201, res
    assert len(res["ids"]) == 2 and res["queue"]["runs"][0]["ticker"] == "GROWCO.NS"
    for _ in range(200):
        q = call(base, "/api/queue")[1]
        if all(r["status"] == "done" for r in q["runs"]):
            break
        assert sum(r["status"] == "running" for r in q["runs"]) <= 1
        time.sleep(0.02)
    else:
        raise AssertionError(f"the runs did not finish: {q}")
    analyses = call(base, "/api/analyses")[1]
    assert sorted(a["ticker"] for a in analyses) == ["GROWCO.NS", "LENDERBANK.NS"]
    detail = call(base, f"/api/analyses/{res['ids'][1]}")[1]
    assert detail["status"] == "done" and detail["rating"] == "Overweight"


@pytest.mark.parametrize("body, message", [
    ({"tickers": []}, "Pick at least one"),
    ({"tickers": [f"S{i}.NS" for i in range(11)]}, "at most 10"),
    ({"tickers": ["BAD/ONE"]}, "Tickers use"),
    ({"tickers": ["A.NS"], "date": "2999-01-01"}, "future"),
])
def test_bad_queue_requests(base, body, message):
    code, reply = call(base, "/api/screen/analyze", {"date": "2026-09-01", "analysts": ["market"],
                                                     "settings": SETTINGS, **body})
    assert code == 400 and message in reply["error"], reply


def test_queued_runs_can_be_cancelled(base, monkeypatch):
    gate = threading.Event()

    class Slow(FakeGraph):
        def stream(self, state, **args):
            gate.wait(5)
            yield from super().stream(state, **args)

    monkeypatch.setattr(trading_graph, "TradingAgentsGraph", Slow)
    status, res = call(base, "/api/screen/analyze", {"tickers": ["AAA.NS", "BBB.NS"], "date": "2026-09-01",
                                                     "analysts": ["market"], "settings": SETTINGS})
    assert status == 201
    first, second = res["ids"]
    status, reply = call(base, f"/api/queue/{second}/cancel", {})
    assert status == 200 and reply["ok"]
    assert call(base, f"/api/analyses/{second}")[1]["status"] == "cancelled"
    assert call(base, "/api/queue/nope/cancel", {})[0] == 404
    status, reply = call(base, "/api/queue/cancel", {})
    assert status == 200 and reply["cancelled"] == 1
    gate.set()
    for _ in range(200):
        if call(base, f"/api/analyses/{first}")[1]["status"] not in ("pending", "running"):
            break
        time.sleep(0.02)
    assert call(base, f"/api/analyses/{first}")[1]["status"] == "cancelled"
