"""Incremental polling window: only items posted after the last poll are stored."""
import pytest

from tradingagents import poller
from tradingagents.dataflows.media_sources import _row
from tradingagents.dataflows.media_store import SqliteMediaStore


@pytest.mark.unit
def test_within_filters_by_since_and_keeps_undated():
    rows = [
        _row("x", "fresh", "NVDA", 0.0, created_utc=100.0),
        _row("x", "stale", "NVDA", 0.0, created_utc=10.0),
        _row("x", "undated", "NVDA", 0.0, created_utc=None),
    ]
    kept = {r["external_id"] for r in poller._within(rows, since=50.0)}
    assert kept == {"fresh", "undated"}            # > since, plus undated backstop
    # No prior poll → no lower bound (one-time backfill).
    assert len(poller._within(rows, since=None)) == 3


@pytest.mark.unit
def test_poll_once_only_stores_items_in_window(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")

    def fake_source(ticker, now):
        return [_row("x", "a", ticker, now, created_utc=9995.0),   # in window
                _row("x", "b", ticker, now, created_utc=9000.0)]   # too old

    monkeypatch.setattr(poller, "FETCHERS", {"x": fake_source})
    poller.poll_once(store, ["NVDA"], ["x"], now=10000.0, since=9990.0)

    stored = store.window("NVDA", "2100-01-01", days=400000)
    assert {r["external_id"] for r in stored} == {"a"}
    store.close()


@pytest.mark.unit
def test_meta_roundtrip_persists_last_poll(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    assert store.get_meta("last_poll_utc") is None
    store.set_meta("last_poll_utc", 12345.0)
    assert store.get_meta("last_poll_utc") == 12345.0
    store.set_meta("last_poll_utc", 67890.0)       # upsert
    assert store.get_meta("last_poll_utc") == 67890.0
    store.close()


@pytest.mark.unit
def test_x_only_cycle_does_not_advance_shared_poll_cursor(tmp_path, monkeypatch):
    store = SqliteMediaStore(tmp_path / "m.db")
    store.set_meta("last_poll_utc", 100.0)
    monkeypatch.setattr(poller, "poll_x_topics_once", lambda *args, **kwargs: None)

    poller.run_cycle(
        store,
        tickers=["IGNORED"],
        sources=[],
        macro_themes={},
        x_enabled=True,
        force_x=True,
    )

    assert store.get_meta("last_poll_utc") == 100.0
    store.close()


@pytest.mark.unit
def test_paper_watchdog_rejects_stale_or_newer_failure_heartbeat(tmp_path):
    store = SqliteMediaStore(tmp_path / "m.db")
    store.set_meta("paper:last_success_utc", 100.0)
    assert poller.check_paper_heartbeat(store, now=150.0, max_age=100.0)

    store.set_meta("paper:last_failure_utc", 160.0)
    assert not poller.check_paper_heartbeat(store, now=170.0, max_age=100.0)
    assert not poller.check_paper_heartbeat(store, now=250.0, max_age=100.0)
    store.close()
