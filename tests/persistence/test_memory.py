import pytest
from datetime import datetime, timezone


@pytest.fixture
def conn(tmp_path):
    from tradingagents.persistence.db import connect
    return connect(str(tmp_path / "test.db"))


@pytest.mark.unit
def test_memory_store_writes_partitioned_row(conn):
    from tradingagents.persistence.memory import PersonaMemoryStore
    store = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    store.add_memory(situation_md="AAPL: rates rising", outcome="SELL was correct")
    rows = list(conn.execute(
        "SELECT * FROM memories WHERE persona_id=? AND component=?",
        ("macro", "decision_log"),
    ))
    assert len(rows) == 1
    assert rows[0]["situation_md"].startswith("AAPL")


@pytest.mark.unit
def test_memory_get_cannot_read_other_personas(conn):
    """The wrapper is the only way to read; it MUST NOT cross persona boundaries."""
    from tradingagents.persistence.memory import PersonaMemoryStore
    macro = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    momentum = PersonaMemoryStore(conn, persona_id="momentum", component="decision_log")
    macro.add_memory(situation_md="macro-only-thought", outcome=None)
    momentum.add_memory(situation_md="momentum-only-thought", outcome=None)

    macro_results = macro.recent(limit=10)
    momentum_results = momentum.recent(limit=10)

    assert len(macro_results) == 1
    assert "macro-only-thought" in macro_results[0]["situation_md"]
    assert all("momentum" not in m["situation_md"] for m in macro_results)

    assert len(momentum_results) == 1
    assert all("macro" not in m["situation_md"] for m in momentum_results)


@pytest.mark.unit
def test_memory_rejects_empty_persona_id(conn):
    from tradingagents.persistence.memory import PersonaMemoryStore
    with pytest.raises(ValueError, match="persona_id"):
        PersonaMemoryStore(conn, persona_id="", component="decision_log")
    with pytest.raises(ValueError, match="persona_id"):
        PersonaMemoryStore(conn, persona_id="*", component="decision_log")


@pytest.mark.unit
def test_outcome_log_is_shared_across_personas(conn):
    """Outcome_log is the cross-pollination channel — readable by any persona."""
    from tradingagents.persistence.memory import OutcomeLog
    from tradingagents.persistence import store
    import uuid
    log = OutcomeLog(conn)
    # Need real run_ids that satisfy the FK.
    macro_run = uuid.uuid4().hex
    momentum_run = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=macro_run, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir="x")
    store.insert_run(conn, run_id=momentum_run, ticker="AAPL", persona_id="momentum",
                     started_ts=now, artifact_dir="y")

    log.append(run_id=macro_run, ticker="AAPL", decision="BUY",
               outcome_md="macro-call worked")
    log.append(run_id=momentum_run, ticker="AAPL", decision="SELL",
               outcome_md="momentum-call worked")

    all_for_aapl = log.recent_for_ticker("AAPL", limit=10)
    assert len(all_for_aapl) == 2
    decisions = {r["decision"] for r in all_for_aapl}
    assert decisions == {"BUY", "SELL"}
