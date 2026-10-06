"""A backtest gets its own checkpoint namespace (F1).

A backtest shares a live run's ticker, date, settings, analysts and portfolio,
and the live run keeps its price caches under the same ``data_cache_dir``. The
checkpoint thread ID must nevertheless differ per run owner: an interrupted live
run's saved context must survive a backtest, distinct backtest run IDs must not
resume or clear each other, and the same backtest run ID must still resume.

These tests drive the real ``run_backtest`` and the real checkpoint signature,
thread ID, saver and clear paths through a minimal LangGraph workflow, so they
fail if a run owner's namespace is dropped from the thread ID.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, StateGraph

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.checkpointer import checkpoint_step, thread_id
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.memory import TradingMemoryLog


class _State(TypedDict):
    context: str


class _CheckpointGraph(TradingAgentsGraph):
    """The real checkpoint machinery over a two-node graph, no LLMs or vendors.

    ``propagate`` mirrors the real graph's checkpoint-relevant parts: enter
    ``checkpoint_scope``, resume with ``None`` or start with fresh state, then
    clear the checkpoint on success. ``crash`` makes the second node raise so an
    interrupted run leaves a checkpoint behind.
    """

    def __init__(self, config, crash=False, observations=None, selected_analysts=("market",)):
        self.config = config
        self.selected_analysts = tuple(selected_analysts)
        self.crash = crash
        self.observations = observations if observations is not None else {}
        workflow = StateGraph(_State)
        workflow.add_node("analyst", lambda state: {})
        workflow.add_node("trader", self._trader)
        workflow.set_entry_point("analyst")
        workflow.add_edge("analyst", "trader")
        workflow.add_edge("trader", END)
        self.workflow = workflow
        self.graph = workflow.compile()
        self._checkpointer_ctx = None
        self._resuming = False
        self.memory_log = TradingMemoryLog(config)

    def _trader(self, state):
        if self.crash:
            raise RuntimeError("simulated crash")
        return {}

    def propagate(self, ticker, date, asset_type="stock", portfolio=None):
        signature = self._run_signature(asset_type, portfolio)
        with self.checkpoint_scope(ticker, date, asset_type, portfolio) as tid:
            self.observations.update(
                thread_id=tid,
                resuming=self._resuming,
                signature=signature,
            )
            args = {}
            if tid is not None:
                args["config"] = {"configurable": {"thread_id": tid}}
            graph_input = None if self._resuming else {"context": "FRESH"}
            self.graph.invoke(graph_input, **args)
        self.clear_checkpoint_on_success(ticker, date, asset_type, portfolio)
        return {"context": "FRESH"}, "Buy"

    def settle_pending(self, ticker):
        return None


def _checkpoint_config(tmp_path):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "live.md"),
        checkpoint_enabled=True,
    )
    return cfg


@pytest.mark.unit
def test_a_backtest_starts_fresh_and_leaves_the_live_checkpoint_untouched(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    cfg = _checkpoint_config(tmp_path)
    live = _CheckpointGraph(cfg, crash=True)
    with pytest.raises(RuntimeError, match="simulated crash"):
        live.propagate("NVDA", "2026-01-05")

    live_signature = live._run_signature("stock")
    live_tid = thread_id("NVDA", "2026-01-05", live_signature)
    assert checkpoint_step(cfg["data_cache_dir"], "NVDA", "2026-01-05", live_signature) is not None

    seen = {}
    monkeypatch.setattr(
        bt,
        "TradingAgentsGraph",
        lambda analysts=None, config=None, **kw: _CheckpointGraph(
            config, observations=seen, selected_analysts=analysts
        ),
    )
    result = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-a", selected_analysts=["market"]
    )

    assert result.cells_run == 1
    assert seen["resuming"] is False  # started fresh, not from the live run
    assert seen["thread_id"] != live_tid  # its own checkpoint namespace
    assert checkpoint_step(cfg["data_cache_dir"], "NVDA", "2026-01-05", live_signature) is not None


@pytest.mark.unit
def test_distinct_backtest_run_ids_do_not_resume_or_clear_each_other(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    cfg = _checkpoint_config(tmp_path)
    crash = {"on": True}

    def make(analysts=None, config=None, observations=None):
        return _CheckpointGraph(
            config, crash=crash["on"], observations=observations, selected_analysts=analysts
        )

    seen_a = {}
    monkeypatch.setattr(
        bt,
        "TradingAgentsGraph",
        lambda analysts=None, config=None, **kw: make(analysts, config, seen_a),
    )
    first = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-a", selected_analysts=["market"]
    )

    assert first.failures == [("NVDA", "2026-01-05", "simulated crash")]
    sig_a = seen_a["signature"]
    assert seen_a["resuming"] is False
    assert checkpoint_step(cfg["data_cache_dir"], "NVDA", "2026-01-05", sig_a) is not None

    crash["on"] = False
    seen_b = {}
    monkeypatch.setattr(
        bt,
        "TradingAgentsGraph",
        lambda analysts=None, config=None, **kw: make(analysts, config, seen_b),
    )
    result = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-b", selected_analysts=["market"]
    )

    assert result.cells_run == 1
    assert seen_b["resuming"] is False  # did not resume bt-a's checkpoint
    assert seen_b["thread_id"] != seen_a["thread_id"]  # distinct run IDs, distinct namespaces
    assert checkpoint_step(cfg["data_cache_dir"], "NVDA", "2026-01-05", sig_a) is not None


@pytest.mark.unit
def test_the_same_backtest_run_id_resumes_its_own_checkpoint(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    cfg = _checkpoint_config(tmp_path)
    crash = {"on": True}
    seen = {}
    monkeypatch.setattr(
        bt,
        "TradingAgentsGraph",
        lambda analysts=None, config=None, **kw: _CheckpointGraph(
            config, crash=crash["on"], observations=seen, selected_analysts=analysts
        ),
    )

    first = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-a", selected_analysts=["market"]
    )

    assert first.failures == [("NVDA", "2026-01-05", "simulated crash")]
    first_tid = seen["thread_id"]
    assert seen["resuming"] is False

    crash["on"] = False
    result = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-a", selected_analysts=["market"]
    )

    assert result.cells_run == 1
    assert seen["resuming"] is True  # same run identity resumes its cell
    assert seen["thread_id"] == first_tid


@pytest.mark.unit
def test_a_backtest_without_checkpoints_still_runs(tmp_path, monkeypatch):
    import tradingagents.backtest as bt

    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg.update(
        results_dir=str(tmp_path / "results"),
        data_cache_dir=str(tmp_path / "cache"),
        memory_log_path=str(tmp_path / "live.md"),
        checkpoint_enabled=False,
    )

    seen = {}
    monkeypatch.setattr(
        bt,
        "TradingAgentsGraph",
        lambda analysts=None, config=None, **kw: _CheckpointGraph(
            config, observations=seen, selected_analysts=analysts
        ),
    )
    result = bt.run_backtest(
        ["NVDA"], ["2026-01-05"], cfg, run_id="bt-off", selected_analysts=["market"]
    )

    assert result.cells_run == 1
    assert seen["thread_id"] is None
    assert seen["resuming"] is False
    assert not (Path(cfg["data_cache_dir"]) / "checkpoints").exists()
