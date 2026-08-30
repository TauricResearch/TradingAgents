"""The checkpoint lifecycle is reusable so --checkpoint works on the CLI path (#1249).

Checkpoint setup previously lived only inside ``propagate``; the CLI streamed the
checkpointer-less graph, so ``--checkpoint`` neither saved nor resumed. The
lifecycle is now ``begin_checkpoint`` / ``end_checkpoint`` /
``clear_checkpoint_on_success`` on TradingAgentsGraph, used by both paths. These
tests drive that lifecycle exactly as the CLI does (begin -> stream self.graph ->
clear/end) and prove state is saved and resumed.
"""
from __future__ import annotations

import tempfile
from typing import TypedDict

import pytest
from langgraph.graph import END, StateGraph

from tradingagents.graph.checkpointer import checkpoint_step
from tradingagents.graph.trading_graph import TradingAgentsGraph

_should_crash = False


class _State(TypedDict):
    count: int


def _node_a(state: _State) -> dict:
    return {"count": state["count"] + 1}


def _node_b(state: _State) -> dict:
    if _should_crash:
        raise RuntimeError("simulated mid-stream crash")
    return {"count": state["count"] + 10}


def _workflow() -> StateGraph:
    b = StateGraph(_State)
    b.add_node("analyst", _node_a)
    b.add_node("trader", _node_b)
    b.set_entry_point("analyst")
    b.add_edge("analyst", "trader")
    b.add_edge("trader", END)
    return b


def _bare_graph(tmpdir, *, enabled=True):
    g = object.__new__(TradingAgentsGraph)
    g.config = {
        "checkpoint_enabled": enabled, "data_cache_dir": tmpdir,
        "max_debate_rounds": 1, "max_risk_discuss_rounds": 1,
    }
    g.selected_analysts = ("market",)
    g.workflow = _workflow()
    g.graph = g.workflow.compile()
    g._checkpointer_ctx = None
    return g




@pytest.mark.unit
def test_disabled_is_a_noop():
    with tempfile.TemporaryDirectory() as tmp:
        g = _bare_graph(tmp, enabled=False)
        plain = g.graph
        assert g.begin_checkpoint("AAPL", "2026-05-08", "stock") is None
        assert g.graph is plain  # graph not recompiled
        g.end_checkpoint()  # safe no-op


@pytest.mark.unit
def test_begin_returns_thread_id_and_recompiles():
    with tempfile.TemporaryDirectory() as tmp:
        g = _bare_graph(tmp)
        plain = g.graph
        tid = g.begin_checkpoint("AAPL", "2026-05-08", "stock")
        try:
            assert tid  # a real thread_id
            assert g.graph is not plain  # recompiled with a checkpointer
        finally:
            g.end_checkpoint()
        assert g._checkpointer_ctx is None  # restored


@pytest.mark.unit
def test_cli_style_usage_saves_then_resumes():
    global _should_crash
    with tempfile.TemporaryDirectory() as tmp:
        cfg_args = ("AAPL", "2026-05-08", "stock")

        # Run 1 (the CLI path): begin -> stream self.graph -> crash at 'trader'.
        _should_crash = True
        g1 = _bare_graph(tmp)
        tid = g1.begin_checkpoint(*cfg_args)
        args = {"config": {"configurable": {"thread_id": tid}}}
        try:
            with pytest.raises(RuntimeError):
                for _ in g1.graph.stream({"count": 0}, **args):
                    pass
        finally:
            g1.end_checkpoint()

        # A checkpoint was saved for this run signature (so --checkpoint works).

        sig = g1._run_signature("stock")
        assert checkpoint_step(tmp, "AAPL", "2026-05-08", sig) is not None

        # Run 2 (fresh graph, as a new CLI invocation): resume and finish.
        _should_crash = False
        g2 = _bare_graph(tmp)
        tid2 = g2.begin_checkpoint(*cfg_args)
        assert tid2 == tid  # stable id -> same thread resumes
        try:
            result = g2.graph.invoke(None, config={"configurable": {"thread_id": tid2}})
            assert result["count"] == 11  # analyst(+1) resumed into trader(+10)
            g2.clear_checkpoint_on_success(*cfg_args)
        finally:
            g2.end_checkpoint()

        # Cleared on success -> a later run starts fresh.
        assert checkpoint_step(tmp, "AAPL", "2026-05-08", sig) is None
