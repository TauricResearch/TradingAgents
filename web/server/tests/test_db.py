from sqlmodel import select

from web.server import db
from web.server.db import Watchlist, Run, Event, LlmCall
from web.server.llm_calls import save_llm_call, llm_calls_for_run, list_runs_for_ticker


def test_init_db_creates_tables(temp_db):
    # init_db already called by fixture
    with db.get_session() as s:
        assert s.exec(select(Watchlist)).first() is None
        assert s.exec(select(Run)).first() is None
        assert s.exec(select(Event)).first() is None
        assert s.exec(select(LlmCall)).first() is None


from datetime import datetime, timezone
from web.server import db
from web.server.db import Watchlist, Run, Event, LlmCall


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


def test_run_force_flag(temp_db):
    rid1 = db.create_run(ticker="TSLA", idempotency_key="TSLA:2026-06-01")
    db.mark_run_done(rid1, decision_action="BUY", decision_target=300.0, decision_rationale="ok", decision_confidence=0.7)
    rid2 = db.create_run(ticker="TSLA", idempotency_key="TSLA:2026-06-01", force=True)
    assert rid1 != rid2


from datetime import datetime, timezone


def test_llm_call_crud(temp_db):
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")

    save_llm_call(
        run_id=rid,
        ticker="NVDA",
        node_name="Market Analyst",
        started_at=datetime.now(timezone.utc),
        model="gpt-4",
        prompt_text="user: hello",
        response_text="world",
        tool_calls=[{"name": "get_price"}],
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        duration_ms=1234,
    )

    calls = llm_calls_for_run(rid)
    assert len(calls) == 1
    c = calls[0]
    assert c.ticker == "NVDA"
    assert c.node_name == "Market Analyst"
    assert c.model == "gpt-4"
    assert c.prompt_text == "user: hello"
    assert c.response_text == "world"
    assert c.total_tokens == 15

    rows = list_runs_for_ticker("NVDA")
    assert len(rows) >= 1
    assert rows[0]["ticker"] == "NVDA"


def test_llm_calls_empty(temp_db):
    assert llm_calls_for_run(9999) == []


def test_list_runs_empty(temp_db):
    assert list_runs_for_ticker("NONEXISTENT") == []


def test_llm_calls_ordered(temp_db):
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-03")
    from datetime import timedelta
    save_llm_call(
        run_id=rid, ticker="NVDA", node_name="A",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        model="gpt-4", prompt_text="first", response_text="",
    )
    save_llm_call(
        run_id=rid, ticker="NVDA", node_name="B",
        started_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        model="gpt-4", prompt_text="second", response_text="",
    )
    calls = llm_calls_for_run(rid)
    assert [c.node_name for c in calls] == ["A", "B"]
