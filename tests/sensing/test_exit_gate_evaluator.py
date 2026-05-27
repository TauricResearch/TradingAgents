import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from tradingagents.persistence.db import connect
from tradingagents.persistence.store import (
    insert_event, insert_event_ticker, upsert_watchlist,
)


def _seed_events(conn, n_active: int, n_dup: int, base_ts):
    for i in range(n_active):
        insert_event(conn, event_id=f"a-{i}", source="polygon_news",
                     ingested_ts=(base_ts + timedelta(minutes=i)).isoformat(),
                     salience=0.7, raw_path=f"p/{i}",
                     status="triaged", deduped_of=None)
    for j in range(n_dup):
        insert_event(conn, event_id=f"d-{j}", source="rss",
                     ingested_ts=(base_ts + timedelta(minutes=j)).isoformat(),
                     salience=None, raw_path=f"p/d-{j}",
                     status="duplicate", deduped_of=f"a-{j % max(n_active, 1)}")


@pytest.mark.unit
def test_evaluator_counts_events_and_dups(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=120, n_dup=80, base_ts=since)
    upsert_watchlist(conn, ticker="AAPL",
                     ttl_until=(datetime.now(timezone.utc)
                                + timedelta(days=7)).isoformat(),
                     tags=["auto", "event:a-0"])
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since,
        services=[], check_systemd=False,
    )
    assert res.events_total == 200
    assert res.duplicates == 80
    assert res.autos >= 1
    assert res.crit_events is True
    assert res.crit_autos is True


@pytest.mark.unit
def test_evaluator_fails_when_no_autos(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=120, n_dup=0, base_ts=since)
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since, services=[], check_systemd=False,
    )
    assert res.crit_autos is False
    assert res.passed_auto is False


@pytest.mark.unit
def test_evaluator_renders_artifact(tmp_path):
    from scripts import f3_exit_gate
    db = tmp_path / "iic.db"
    conn = connect(str(db))
    since = datetime.now(timezone.utc) - timedelta(hours=12)
    _seed_events(conn, n_active=2, n_dup=2, base_ts=since)
    res = f3_exit_gate.evaluate(
        db_path=str(db), since=since, services=[], check_systemd=False,
    )
    md = f3_exit_gate.render_report(res)
    assert "Spot-check" in md
    assert "events" in md.lower()
    assert "duplicates" in md.lower()
