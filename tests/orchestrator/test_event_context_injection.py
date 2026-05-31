import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock

from tradingagents.persistence.db import connect


@pytest.mark.unit
def test_run_recorder_writes_event_context_md_when_present(tmp_path):
    """When state.event_context_text is non-empty, RunRecorder.record writes
    it to data/runs/<run_id>/event_context.md."""
    from tradingagents.graph.run_recorder import RunRecorder

    conn = connect(str(tmp_path / "iic.db"))
    cost_cb = MagicMock()
    cost_cb.totals_by_model.return_value = {}

    rec = RunRecorder(
        conn=conn, data_dir=str(tmp_path / "data"),
        run_id="r1", persona_id="macro",
        cost_callback=cost_cb, queue_job_id=None,
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    rec.record({
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-27",
        "final_trade_decision": "BUY",
        "event_context_text": "Apple beats Q3 earnings by 12%.",
    })
    ctx = Path(tmp_path / "data" / "runs" / "r1" / "event_context.md")
    assert ctx.exists()
    assert ctx.read_text() == "Apple beats Q3 earnings by 12%."


@pytest.mark.unit
def test_run_recorder_skips_event_context_md_when_absent(tmp_path):
    from tradingagents.graph.run_recorder import RunRecorder

    conn = connect(str(tmp_path / "iic.db"))
    cost_cb = MagicMock()
    cost_cb.totals_by_model.return_value = {}

    rec = RunRecorder(
        conn=conn, data_dir=str(tmp_path / "data"),
        run_id="r2", persona_id="macro",
        cost_callback=cost_cb, queue_job_id=None,
    )
    rec.start("AAPL", started_ts=datetime.now(timezone.utc).isoformat())
    rec.record({
        "company_of_interest": "AAPL",
        "trade_date": "2026-05-27",
        "final_trade_decision": "BUY",
    })
    assert not (tmp_path / "data" / "runs" / "r2" / "event_context.md").exists()


@pytest.mark.unit
def test_trading_graph_seeds_event_context_into_initial_state(monkeypatch, tmp_path):
    """TradingAgentsGraph._run_graph must enrich propagator.create_initial_state
    with event_context_text from self.config['event_context'] before invoking
    the compiled graph."""
    monkeypatch.setenv("TRADINGAGENTS_IIC_DB_PATH", str(tmp_path / "iic.db"))
    monkeypatch.setenv("TRADINGAGENTS_IIC_DATA_DIR", str(tmp_path / "data"))

    # Reload default_config so the env vars take effect.
    import importlib
    import tradingagents.default_config as m
    importlib.reload(m)

    captured: dict = {}

    # Monkeypatch the compiled graph's stream / invoke to capture initial state
    # without paying for a real run. We patch BEFORE constructing the graph so
    # the post-construction wiring uses our fake.
    from tradingagents.graph import trading_graph as tg_mod

    class FakeCompiled:
        def compile(self, checkpointer=None):
            return self

        def invoke(self, state, *args, **kwargs):
            captured.update(state)
            # Return a minimal final state shape so propagate() can continue.
            state["final_trade_decision"] = "BUY"
            return state

        def stream(self, state, *args, **kwargs):
            self.invoke(state)
            yield {"messages": []}

    # Patch GraphSetup.setup_graph so it returns a FakeCompiled. Use direct
    # class-attribute patching (monkeypatch.setattr with a string path can
    # silently miss when the import binding differs from the attribute path).
    from tradingagents.graph import setup as _setup_mod
    monkeypatch.setattr(
        _setup_mod.GraphSetup, "setup_graph",
        lambda self, selected_analysts, run_recorder_node=None: FakeCompiled(),
    )

    cfg = dict(m.DEFAULT_CONFIG)
    cfg["event_context"] = "Apple beats Q3 earnings by 12%."
    cfg["llm_provider"] = "deepseek"
    cfg["deep_think_llm"] = "deepseek-v4-pro"
    cfg["quick_think_llm"] = "deepseek-v4-flash"

    construction_err = None
    try:
        g = tg_mod.TradingAgentsGraph(config=cfg, selected_analysts=["market"])
    except Exception as exc:
        construction_err = exc

    if construction_err:
        raise AssertionError(f"TradingAgentsGraph construction failed: {construction_err!r}")

    propagate_err = None
    try:
        g.propagate("AAPL", "2026-05-27")
    except Exception as exc:
        propagate_err = exc
    # Print for diagnosis (visible in -s); do not fail on it — downstream
    # wiring may legitimately raise after the state was already passed to invoke.
    if propagate_err is not None:
        print(f"\n[debug] propagate raised: {type(propagate_err).__name__}: {propagate_err}")

    assert captured.get("event_context_text") == "Apple beats Q3 earnings by 12%."
