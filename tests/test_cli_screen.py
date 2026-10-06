"""`tradingagents screen ...` and `tradingagents india build-snapshot`, plus the
India-layer fixes the screener needed (future ex-dates, preference-share bonuses)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from typer.testing import CliRunner

import cli.main as m
import tradingagents.dataflows.config as config_module
from cli import india as india_cli
from tests import screener_db as fx
from tradingagents.dataflows.vendors.india import store
from tradingagents.dataflows.vendors.india.sync import Syncer

pytestmark = pytest.mark.unit


@pytest.fixture
def india(tmp_path):
    path = tmp_path / "india.db"
    fx.build(path)
    config_module._config["india_db_path"] = str(path)
    return path


def run(*args):
    return CliRunner().invoke(m.app, list(args), terminal_width=200)


def test_build_snapshot_then_run_a_screen(india):
    built = run("india", "build-snapshot")
    assert built.exit_code == 0, built.output
    assert "Snapshot live (data to 2026-10-02): 3 securities (eq)" in built.output
    result = run("screen", "run", "Current price > 0\nROCE > 1", "--columns", "pe")
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())  # the console wraps long lines
    assert "1 of 3 stocks match" in text and "Grow Co Limited" in text and "Price to earnings" in text
    assert "Median" in text and "2 stocks left out for missing data" in text


def test_a_historical_snapshot_from_the_cli(india):
    assert run("india", "build-snapshot", "--as-of", "2025-10-06").exit_code == 0
    result = run("screen", "run", "Sales last year > 0", "--as-of", "2025-10-06", "--sort", "+sales_ly")
    assert result.exit_code == 0, result.output
    assert "snapshot 2025-10-06" in result.output
    assert run("india", "build-snapshot", "--as-of", "soon").exit_code != 0


def test_a_bad_query_points_at_the_problem(india):
    run("india", "build-snapshot")
    result = run("screen", "run", "Retrun on equity > 15")
    assert result.exit_code == 1
    assert "did you mean 'Return on equity'?" in result.output and "^^^^" in result.output


def test_a_missing_snapshot_says_what_to_run(india):
    result = run("screen", "run", "ROCE > 1")
    assert result.exit_code == 1 and "india build-snapshot" in result.output


def test_screen_list_and_metrics():
    listed = run("screen", "list")
    assert listed.exit_code == 0 and "preset:piotroski-strong" in listed.output
    metrics = run("screen", "metrics", "pledge")
    assert metrics.exit_code == 0 and "Pledged percentage" in metrics.output and "ROCE" not in metrics.output


def test_sync_all_rebuilds_the_live_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(india_cli, "_run", lambda work, force=False: calls.append("sync"))
    monkeypatch.setattr(india_cli, "_build_snapshot", lambda as_of, universe: calls.append(("snapshot", as_of)))
    assert run("india", "sync-all").exit_code == 0
    assert calls == ["sync", ("snapshot", None)]
    calls.clear()
    assert run("india", "sync-all", "--no-snapshot").exit_code == 0
    assert calls == ["sync"]


# --- India-layer fixes ---------------------------------------------------------------------

def test_an_action_announced_for_a_future_ex_date_does_not_adjust_todays_prices(tmp_path):
    conn = store.connect(tmp_path / "india.db")
    today = date.today()
    store.upsert_prices(conn, [("INE1", (today - timedelta(days=2)).isoformat(), 1, 1, 1, 100.0, 10, "EQ", "t")])
    store.upsert_action(conn, isin="INE1", ex_date=(today + timedelta(days=7)).isoformat(), type="split",
                        details="FV SPLT FRM RS 10 TO RS 5", ratio_num=10, ratio_den=5, factor=2.0,
                        seen=today.isoformat())
    assert store.adjustment_events("INE1", conn=conn) == []
    assert store.get_prices("INE1", conn=conn)[0]["close"] == 100.0
    conn.close()


def test_reparse_actions_fixes_stored_rows_with_todays_parser(tmp_path):
    conn = store.connect(tmp_path / "india.db")
    store.upsert_action(conn, isin="INE1", ex_date="2026-09-08", type="bonus", details="SCH AGMT-BONUS NCRPS46:1",
                        ratio_num=46, ratio_den=1, factor=47.0, seen="2026-09-03")  # as the old parser stored it
    store.upsert_action(conn, isin="INE1", ex_date="2026-01-05", type="bonus", details="BONUS 1:1",
                        ratio_num=1, ratio_den=1, factor=2.0, seen="2026-01-01")
    conn.commit()
    result = Syncer(conn, client=object(), today=date(2026, 10, 5)).reparse_actions()
    assert (result.done, result.skipped) == (1, 1)
    factors = {r[0]: r[1] for r in conn.execute("SELECT details, factor FROM corporate_actions")}
    assert factors == {"SCH AGMT-BONUS NCRPS46:1": None, "BONUS 1:1": 2.0}
    assert [e["details"] for e in store.adjustment_events("INE1", conn=conn)] == ["BONUS 1:1"]
    conn.close()
