from sqlmodel import select

from web.server import db
from web.server.db import Watchlist, Run, Event


def test_init_db_creates_tables(temp_db):
    # init_db already called by fixture
    with db.get_session() as s:
        assert s.exec(select(Watchlist)).first() is None
        assert s.exec(select(Run)).first() is None
        assert s.exec(select(Event)).first() is None


from datetime import datetime, timezone
from web.server import db
from web.server.db import Watchlist, Run, Event


def test_watchlist_add_list_remove(temp_db):
    db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))
    db.add_watchlist(Watchlist(ticker="AAPL", company_name="Apple", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))

    rows = db.list_watchlist()
    tickers = {r.ticker for r in rows}
    assert tickers == {"NVDA", "AAPL"}

    db.remove_watchlist("NVDA")
    rows = db.list_watchlist()
    assert {r.ticker for r in rows} == {"AAPL"}


def test_watchlist_duplicate_raises(temp_db):
    db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))
    import pytest
    with pytest.raises(db.DuplicateTicker):
        db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))


def test_run_crud_and_events(temp_db):
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    assert rid > 0

    db.append_event(rid, "run_started", {})
    db.append_event(rid, "analyst_thinking", {"stage": "market", "message": "hi"})
    db.append_event(rid, "decision", {"action": "BUY", "target": 260.0})

    run = db.get_run(rid)
    assert run.ticker == "NVDA"
    assert run.status == "running"

    events = db.events_for_run(rid)
    assert [e.type for e in events] == ["run_started", "analyst_thinking", "decision"]

    db.mark_run_done(rid, decision_action="BUY", decision_target=260.0, decision_rationale="r", decision_confidence=0.8)
    run = db.get_run(rid)
    assert run.status == "done"
    assert run.decision_action == "BUY"
    assert run.finished_at is not None


def test_run_idempotency(temp_db):
    rid1 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    db.mark_run_done(rid1, decision_action="HOLD", decision_target=None, decision_rationale="", decision_confidence=0.5)
    rid2 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    assert rid1 == rid2
