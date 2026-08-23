"""Test checkpoint resume: crash mid-analysis, re-run resumes from last node."""

import tempfile
import unittest
from typing import TypedDict
from unittest import mock

from langgraph.graph import END, StateGraph

import cli.main as cli_main
from cli.models import AnalystType
from tradingagents.graph.checkpointer import (
    checkpoint_step,
    clear_checkpoint,
    get_checkpointer,
    has_checkpoint,
    thread_id,
)
from tradingagents.graph.propagation import Propagator

# Mutable flag to simulate crash on first run
_should_crash = False
_analyst_calls = 0


class _SimpleState(TypedDict):
    count: int


def _node_a(state: _SimpleState) -> dict:
    global _analyst_calls
    _analyst_calls += 1
    return {"count": state.get("count", 0) + 1}


def _node_b(state: _SimpleState) -> dict:
    if _should_crash:
        raise RuntimeError("simulated mid-analysis crash")
    return {"count": state.get("count", 0) + 10}


def _build_graph() -> StateGraph:
    builder = StateGraph(_SimpleState)
    builder.add_node("analyst", _node_a)
    builder.add_node("trader", _node_b)
    builder.set_entry_point("analyst")
    builder.add_edge("analyst", "trader")
    builder.add_edge("trader", END)
    return builder


class TestCheckpointResume(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "TEST"
        self.date = "2026-04-20"

    def test_crash_and_resume(self):
        """Crash at 'trader' node, then resume from checkpoint."""
        global _should_crash
        builder = _build_graph()
        tid = thread_id(self.ticker, self.date)
        cfg = {"configurable": {"thread_id": tid}}

        # Run 1: crash at trader node
        _should_crash = True
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config=cfg)

        # Checkpoint should exist at step 1 (analyst completed)
        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date))
        step = checkpoint_step(self.tmpdir, self.ticker, self.date)
        self.assertEqual(step, 1)

        # Run 2: resume — trader succeeds this time
        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke(None, config=cfg)

        # analyst added 1, trader added 10 → 11
        self.assertEqual(result["count"], 11)

    def test_clear_checkpoint_allows_fresh_start(self):
        """After clearing, the graph starts from scratch."""
        global _should_crash
        builder = _build_graph()
        tid = thread_id(self.ticker, self.date)
        cfg = {"configurable": {"thread_id": tid}}

        # Create a checkpoint by crashing
        _should_crash = True
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config=cfg)

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date))

        # Clear it
        clear_checkpoint(self.tmpdir, self.ticker, self.date)
        self.assertFalse(has_checkpoint(self.tmpdir, self.ticker, self.date))

        # Fresh run succeeds from scratch
        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke({"count": 0}, config=cfg)

        self.assertEqual(result["count"], 11)


    def test_different_date_starts_fresh(self):
        """A different date must NOT resume from an existing checkpoint."""
        global _should_crash
        builder = _build_graph()
        date2 = "2026-04-21"

        # Run with date1 — crash to leave a checkpoint
        _should_crash = True
        tid1 = thread_id(self.ticker, self.date)
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config={"configurable": {"thread_id": tid1}})

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date))

        # date2 should have no checkpoint
        self.assertFalse(has_checkpoint(self.tmpdir, self.ticker, date2))

        # Run with date2 — should start fresh and succeed
        _should_crash = False
        tid2 = thread_id(self.ticker, date2)
        self.assertNotEqual(tid1, tid2)

        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke({"count": 0}, config={"configurable": {"thread_id": tid2}})

        # Fresh run: analyst +1, trader +10 = 11
        self.assertEqual(result["count"], 11)

        # Original date checkpoint still exists (untouched)
        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date))


class TestCheckpointSignature(unittest.TestCase):
    """A different graph shape (analyst selection / depth / asset mode) must not
    resume the previous run's checkpoint (#1089)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "TEST"
        self.date = "2026-04-20"

    def test_empty_signature_is_legacy_id(self):
        self.assertEqual(
            thread_id(self.ticker, self.date),
            thread_id(self.ticker, self.date, ""),
        )

    def test_signature_changes_thread_id(self):
        legacy = thread_id(self.ticker, self.date)
        sig_a = thread_id(self.ticker, self.date, "analysts=market,news|asset=stock")
        sig_b = thread_id(self.ticker, self.date, "analysts=market|asset=stock")
        self.assertNotEqual(sig_a, sig_b)          # different graph shapes differ
        self.assertNotEqual(legacy, sig_a)         # signature-keyed differs from legacy
        self.assertEqual(                          # same inputs are stable
            sig_a, thread_id(self.ticker, self.date, "analysts=market,news|asset=stock")
        )

    def test_different_signature_starts_fresh(self):
        global _should_crash
        builder = _build_graph()
        sig1 = "analysts=market,news,fundamentals|asset=stock"
        sig2 = "analysts=market|asset=stock"       # dropped analysts -> different graph

        _should_crash = True
        tid1 = thread_id(self.ticker, self.date, sig1)
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            with self.assertRaises(RuntimeError):
                graph.invoke({"count": 0}, config={"configurable": {"thread_id": tid1}})

        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date, sig1))
        # A different graph shape has no checkpoint to resume from.
        self.assertFalse(has_checkpoint(self.tmpdir, self.ticker, self.date, sig2))

        _should_crash = False
        tid2 = thread_id(self.ticker, self.date, sig2)
        self.assertNotEqual(tid1, tid2)
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            result = graph.invoke({"count": 0}, config={"configurable": {"thread_id": tid2}})
        self.assertEqual(result["count"], 11)
        # sig1's checkpoint remains untouched.
        self.assertTrue(has_checkpoint(self.tmpdir, self.ticker, self.date, sig1))

    def test_run_signature_captures_graph_shape(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        # Build a bare instance to exercise the pure helper without heavy __init__.
        g = object.__new__(TradingAgentsGraph)
        g.selected_analysts = ("market", "news")
        g.config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        base = g._run_signature("stock")

        self.assertNotEqual(base, g._run_signature("crypto"))     # asset mode
        g.selected_analysts = ("market",)
        self.assertNotEqual(base, g._run_signature("stock"))      # analyst selection
        g.selected_analysts = ("market", "news")
        g.config = {"max_debate_rounds": 3, "max_risk_discuss_rounds": 1}
        self.assertNotEqual(base, g._run_signature("stock"))      # debate depth
        g.config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 5}
        self.assertNotEqual(base, g._run_signature("stock"))      # risk depth
        # Stable for identical inputs.
        g.config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
        self.assertEqual(base, g._run_signature("stock"))


class TestCLICheckpointResume(unittest.TestCase):
    def setUp(self):
        global _should_crash, _analyst_calls
        _should_crash = False
        _analyst_calls = 0
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "TEST"
        self.date = "2026-08-23"

    def test_cli_checkpoint_crash_and_resume(self):
        """When checkpoint=True, CLI must compile checkpointer, save state on crash,
        resume on re-run, and clear checkpoint on success."""
        global _should_crash

        selections = {
            "ticker": self.ticker,
            "analysis_date": self.date,
            "asset_type": "stock",
            "analysts": [AnalystType.MARKET],
            "research_depth": 1,
            "shallow_thinker": "gpt-5.4-mini",
            "deep_thinker": "gpt-5.5",
            "backend_url": None,
            "llm_provider": "openai",
            "google_thinking_level": None,
            "openai_reasoning_effort": None,
            "anthropic_effort": None,
            "output_language": "English",
        }

        test_workflow = _build_graph()

        def _mock_graph_init(graph_self, selected_analysts, *args, **kwargs):
            graph_self.selected_analysts = tuple(selected_analysts)
            graph_self.config = kwargs.get("config", {})
            graph_self.debug = True
            graph_self._checkpointer_ctx = None
            graph_self.workflow = test_workflow
            graph_self.graph = test_workflow.compile()
            graph_self.propagator = Propagator(max_recur_limit=100)

        patched_config = dict(cli_main.DEFAULT_CONFIG, data_cache_dir=self.tmpdir, results_dir=self.tmpdir)

        with mock.patch("cli.main.get_user_selections", return_value=selections), \
            mock.patch.object(cli_main, "DEFAULT_CONFIG", patched_config), \
            mock.patch("cli.main.TradingAgentsGraph.__init__", _mock_graph_init), \
            mock.patch("cli.main.Live"), \
            mock.patch("cli.main.typer.prompt", return_value="N"):

            # Run 1: crash in trader node
            _should_crash = True
            with self.assertRaises(RuntimeError):
                cli_main.run_analysis(checkpoint=True)
            self.assertEqual(
                _analyst_calls, 1, "Initial analyst node should run exactly once"
            )

            # Checkpoint MUST exist after crash
            sig = f"analysts=market|debate={patched_config['max_debate_rounds']}|risk={patched_config['max_risk_discuss_rounds']}|asset=stock"
            self.assertTrue(
                has_checkpoint(self.tmpdir, self.ticker, self.date, sig),
                "Checkpoint DB should have saved state for crashed run"
            )

            # Run 2: resume
            _should_crash = False
            cli_main.run_analysis(checkpoint=True)
            self.assertEqual(
                _analyst_calls, 1, "Resume should not rerun the completed analyst node"
            )

            # Checkpoint should be cleared after successful completion
            self.assertFalse(
                has_checkpoint(self.tmpdir, self.ticker, self.date, sig),
                "Checkpoint should be cleared after successful completion"
            )


if __name__ == "__main__":
    unittest.main()
