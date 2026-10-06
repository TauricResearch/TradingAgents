"""`tradingagents india evaluate-alerts`, and alerts at the end of `india sync-all`."""

from __future__ import annotations

import io

import pytest
from rich.console import Console
from typer.testing import CliRunner

import cli.main as m
import tradingagents.dataflows.config as config_module
from cli import india as india_cli
from tests import screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import alerts, snapshot, userdb

pytestmark = pytest.mark.unit


@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    fx.build(path)
    conn = store.connect(path)
    snapshot.build_snapshot(conn)
    conn.close()
    config_module._config["india_db_path"] = str(path)
    return path


def run(*args):
    return CliRunner().invoke(m.app, list(args), terminal_width=200)


def test_no_alerts_says_so(india):
    out = run("india", "evaluate-alerts")
    assert out.exit_code == 0 and "none set up yet" in out.output


def test_evaluating_twice_fires_once(india):
    user = userdb.connect()
    conn = store.connect(india)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 200}, conn)
    first = run("india", "evaluate-alerts")
    assert first.exit_code == 0 and "1 evaluated, 0 fired" in first.output
    store.upsert_prices(conn, [(fx.GROWCO, "2026-10-05", 205, 205, 205, 205, 1000, "EQ", "t")])
    conn.commit()
    fired = run("india", "evaluate-alerts")
    assert "1 fired" in fired.output and "GROWCO.NS closed at" in fired.output and "(data 2026-10-05)" in fired.output
    again = run("india", "evaluate-alerts", "--kinds", "price")
    assert "0 fired" in again.output and "Unread in the inbox: 1" in again.output
    assert run("india", "evaluate-alerts", "--kinds", "gossip").exit_code != 0


def test_sync_all_evaluates_alerts_after_the_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(india_cli, "_run", lambda work, force=False: calls.append("sync"))
    monkeypatch.setattr(india_cli, "_build_snapshot", lambda as_of, universe: calls.append("snapshot"))
    monkeypatch.setattr(india_cli, "_evaluate_alerts", lambda kinds: calls.append("alerts"))
    assert run("india", "sync-all").exit_code == 0
    assert calls == ["sync", "snapshot", "alerts"]
    calls.clear()
    assert run("india", "sync-all", "--no-alerts").exit_code == 0
    assert calls == ["sync", "snapshot"]


def test_a_terminal_without_the_rupee_sign_gets_rs(monkeypatch):
    legacy = Console(file=io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    monkeypatch.setattr(india_cli, "console", legacy)
    assert india_cli._printable("GROWCO.NS closed at ₹205.00") == "GROWCO.NS closed at Rs 205.00"
    assert india_cli._printable("“Pricey”: 1 entered") == "“Pricey”: 1 entered"  # cp1252 has curly quotes
    utf8 = Console(file=io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    monkeypatch.setattr(india_cli, "console", utf8)
    assert india_cli._printable("₹205.00") == "₹205.00"
