import pytest


pytestmark = pytest.mark.smoke


def test_persona_memory_store_has_no_api_to_read_other_personas(tmp_path):
    """The PersonaMemoryStore must not expose any method that returns rows
    not matching its (persona_id, component) key. This is the R6
    boundary contract."""
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.memory import PersonaMemoryStore

    conn = connect(str(tmp_path / "iic.db"))
    macro = PersonaMemoryStore(conn, persona_id="macro", component="decision_log")
    momentum = PersonaMemoryStore(conn, persona_id="momentum", component="decision_log")

    macro.add_memory(situation_md="MACRO_PRIVATE_THOUGHT", outcome=None)
    momentum.add_memory(situation_md="MOMENTUM_PRIVATE_THOUGHT", outcome=None)

    # Every public method's return value, when called from a persona, must
    # only reference that persona's rows.
    public_methods = [name for name in dir(macro)
                      if not name.startswith("_") and callable(getattr(macro, name))]
    # Currently: ["add_memory", "recent"]. If the future adds more, this
    # test will catch any that leak.
    for name in public_methods:
        if name == "add_memory":
            continue   # writer, not a reader
        result = getattr(macro, name)()
        for row in result:
            assert "MOMENTUM" not in row["situation_md"], \
                f"PersonaMemoryStore.{name} leaked momentum row to macro"


def test_outcome_log_is_intentionally_shared(tmp_path):
    """Contrast test: the OutcomeLog *is* shared across personas. This
    documents the design and guards against an accidental future scoping."""
    from tradingagents.persistence.db import connect
    from tradingagents.persistence.memory import OutcomeLog
    from tradingagents.persistence import store
    from datetime import datetime, timezone
    import uuid

    conn = connect(str(tmp_path / "iic.db"))
    macro_run = uuid.uuid4().hex
    momentum_run = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    store.insert_run(conn, run_id=macro_run, ticker="AAPL", persona_id="macro",
                     started_ts=now, artifact_dir="x")
    store.insert_run(conn, run_id=momentum_run, ticker="AAPL", persona_id="momentum",
                     started_ts=now, artifact_dir="y")

    log = OutcomeLog(conn)
    log.append(run_id=macro_run, ticker="AAPL", decision="SELL",
               outcome_md="macro outcome")
    log.append(run_id=momentum_run, ticker="AAPL", decision="BUY",
               outcome_md="momentum outcome")

    rows = log.recent_for_ticker("AAPL", limit=10)
    decisions = {r["decision"] for r in rows}
    assert decisions == {"SELL", "BUY"}, \
        "OutcomeLog must surface rows from all personas — it is the cross-pollination channel"
