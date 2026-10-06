"""The user database: Phase 3's file brought up to date in place, once, with no
screen or ratio lost; and user data that outlives a rebuilt India database."""

from __future__ import annotations

import sqlite3

import pytest

from tests import screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import alerts, screens, snapshot, userdb, watchlists

pytestmark = pytest.mark.unit

# The file Phase 3 wrote: its schema as it shipped, no user_version.
PHASE3_SCHEMA = """
CREATE TABLE IF NOT EXISTS screens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', query TEXT NOT NULL,
    columns TEXT NOT NULL DEFAULT '[]',
    sort TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS custom_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, key TEXT NOT NULL UNIQUE,
    expression TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
"""


def phase3_file(path):
    conn = sqlite3.connect(path)
    conn.executescript(PHASE3_SCHEMA)
    conn.execute("INSERT INTO screens (name, query, columns, sort, created_at, updated_at) VALUES "
                 "('Quality', 'Return on capital employed > 20', '[\"pe\"]', '{\"key\": \"roce\", \"dir\": \"desc\"}', "
                 "'2026-10-06T10:00:00', '2026-10-06T10:00:00')")
    conn.execute("INSERT INTO custom_ratios (name, key, expression, created_at, updated_at) VALUES "
                 "('Earnings to price', 'earnings to price', 'Net profit / Market Capitalization', "
                 "'2026-10-06T10:00:00', '2026-10-06T10:00:00')")
    conn.commit()
    conn.close()


def tables(conn) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_phase_3_file_is_upgraded_in_place_without_losing_screens_or_ratios(tmp_path):
    path = tmp_path / "screens.db"
    phase3_file(path)
    conn = userdb.connect(path)
    assert userdb.version(conn) == userdb.VERSION == 1
    assert {"screens", "custom_ratios", "watchlists", "watchlist_items", "alerts", "alert_events"} <= tables(conn)
    [screen] = screens.list_screens(conn)
    assert (screen["name"], screen["query"], screen["columns"], screen["sort"]) == (
        "Quality", "Return on capital employed > 20", ["pe"], {"key": "roce", "dir": "desc"})
    [ratio] = screens.list_ratios(conn)
    assert (ratio.name, ratio.expression) == ("Earnings to price", "Net profit / Market Capitalization")
    # The new tables work beside the old rows.
    w = watchlists.save(conn, {"name": "Core"})
    assert watchlists.get(conn, w["id"])["name"] == "Core"
    conn.close()


def test_the_upgrade_runs_once_and_again_changes_nothing(tmp_path):
    path = tmp_path / "screens.db"
    phase3_file(path)
    first = userdb.connect(path)
    before = first.execute("SELECT * FROM screens").fetchall(), first.execute("SELECT * FROM custom_ratios").fetchall()
    first.close()
    again = userdb.connect(path)
    assert userdb.upgrade(again) == []  # nothing left to do
    after = again.execute("SELECT * FROM screens").fetchall(), again.execute("SELECT * FROM custom_ratios").fetchall()
    assert [list(map(tuple, t)) for t in before] == [list(map(tuple, t)) for t in after]
    assert userdb.version(again) == 1


def test_a_new_file_gets_every_table(tmp_path):
    conn = userdb.connect(tmp_path / "new" / "user.db")
    assert userdb.version(conn) == 1
    assert {"screens", "custom_ratios", "watchlists", "watchlist_items", "alerts", "alert_events"} <= tables(conn)


def test_a_failed_step_leaves_the_file_as_it_was(tmp_path, monkeypatch):
    path = tmp_path / "screens.db"
    phase3_file(path)
    broken = ((1, (*userdb.WATCHLISTS_AND_ALERTS[:1], "CREATE TABLE oops (")),)
    monkeypatch.setattr(userdb, "MIGRATIONS", broken)
    with pytest.raises(sqlite3.OperationalError):
        userdb.connect(path)
    conn = sqlite3.connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert "watchlists" not in tables(conn)  # the step's first table went back out with it
    assert conn.execute("SELECT COUNT(*) FROM screens").fetchone()[0] == 1


def test_screens_connect_is_the_user_database(tmp_path):
    conn = screens.connect(tmp_path / "s.db")
    assert userdb.version(conn) == 1 and "alerts" in tables(conn)


def test_user_data_outlives_a_rebuilt_india_database(tmp_path):
    india = tmp_path / "india.db"
    fx.build(india)
    conn = store.connect(india)
    snapshot.build_snapshot(conn)
    user = userdb.connect(tmp_path / "screens.db")
    screens.save_screen(user, {"name": "Big", "query": "Market Capitalization > 1000"}, [])
    w = watchlists.save(user, {"name": "Core"})
    watchlists.add(user, w["id"], ["GROWCO"], conn)
    alerts.save(user, {"kind": "price", "symbol": "GROWCO", "op": "above", "level": 500}, conn)
    assert not {"screens", "watchlists", "alerts", "alert_events"} & tables(conn)  # nothing of the user's there
    conn.close()

    for suffix in ("", "-wal", "-shm"):  # a full rebuild: the market database deleted and synced again
        (tmp_path / f"india.db{suffix}").unlink(missing_ok=True)
    fx.build(india)
    conn = store.connect(india)
    snapshot.build_snapshot(conn)
    assert [s["name"] for s in screens.list_screens(user)] == ["Big"]
    assert [i["symbol"] for i in watchlists.get(user, w["id"])["items"]] == ["GROWCO.NS"]
    assert [a["name"] for a in alerts.list_alerts(user)] == ["GROWCO.NS above ₹500.00"]
    assert alerts.evaluate(user, conn).errors == []
