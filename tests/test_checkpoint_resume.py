"""Test checkpoint resume: crash mid-analysis, re-run resumes from last node."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.base import CheckpointTuple
from langgraph.graph import END, StateGraph

from tradingagents.graph.checkpointer import (
    checkpoint_access,
    checkpoint_step,
    clear_checkpoint,
    get_checkpointer,
    has_checkpoint,
    thread_id,
)

# Mutable flag to simulate crash on first run
_should_crash = False


class _SimpleState(TypedDict):
    count: int


def _node_a(state: _SimpleState) -> dict:
    return {"count": state["count"] + 1}


def _node_b(state: _SimpleState) -> dict:
    if _should_crash:
        raise RuntimeError("simulated mid-analysis crash")
    return {"count": state["count"] + 10}


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

    def test_legacy_thread_id_golden_is_unchanged(self):
        self.assertEqual(thread_id(self.ticker, self.date), "9a59da14cb713f5e")
        self.assertEqual(
            thread_id(
                self.ticker,
                self.date,
                "analysts=market,news|asset=stock",
            ),
            "ba0c97ad8f3a7d50",
        )

    def test_run_id_namespaces_web_threads_without_changing_legacy(self):
        legacy = thread_id(self.ticker, self.date, "shape")
        run_a = thread_id(self.ticker, self.date, "shape", run_id="run_a")
        run_b = thread_id(self.ticker, self.date, "shape", run_id="run_b")

        self.assertEqual(run_a, thread_id(self.ticker, self.date, "shape", run_id="run_a"))
        self.assertNotEqual(run_a, run_b)
        self.assertNotEqual(run_a, legacy)

    def test_explicit_empty_run_id_is_rejected(self):
        with self.assertRaises(ValueError):
            thread_id(self.ticker, self.date, run_id="")

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


class TestCheckpointAccess(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "TEST"
        self.date = "2026-04-20"
        self.signature = "shape-v1"

    def _create_completed_checkpoint(self, run_id: str | None) -> dict:
        builder = _build_graph()
        tid = thread_id(
            self.ticker,
            self.date,
            self.signature,
            run_id=run_id,
        )
        config = {"configurable": {"thread_id": tid}}
        global _should_crash
        _should_crash = False
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            graph.invoke({"count": 0}, config=config)
        return config

    def test_access_returns_raw_latest_parent_and_pending_writes(self):
        config = self._create_completed_checkpoint("run_access")
        expected_write = ("task_pending", "count", 42)
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            latest = saver.get_tuple(config)
            self.assertIsNotNone(latest)
            saver.put_writes(
                latest.config,
                [(expected_write[1], expected_write[2])],
                expected_write[0],
            )

        access = checkpoint_access(
            self.tmpdir,
            self.ticker,
            self.date,
            self.signature,
            run_id="run_access",
        )

        self.assertIsInstance(access.latest, CheckpointTuple)
        self.assertIsInstance(access.parent, CheckpointTuple)
        self.assertEqual(access.parent.config, access.latest.parent_config)
        self.assertIn(expected_write, access.latest.pending_writes)
        self.assertIs(access.pending_writes, access.latest.pending_writes)

    def test_access_for_missing_checkpoint_is_empty(self):
        access = checkpoint_access(
            self.tmpdir,
            self.ticker,
            self.date,
            self.signature,
            run_id="run_missing",
        )
        self.assertIsNone(access.latest)
        self.assertIsNone(access.parent)
        self.assertIsNone(access.pending_writes)

    def test_run_scoped_helpers_and_clear_do_not_touch_siblings_or_legacy(self):
        self._create_completed_checkpoint("run_a")
        self._create_completed_checkpoint("run_b")
        self._create_completed_checkpoint(None)

        self.assertTrue(
            has_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_a",
            )
        )
        self.assertTrue(
            has_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_b",
            )
        )
        self.assertTrue(
            has_checkpoint(self.tmpdir, self.ticker, self.date, self.signature)
        )
        self.assertIsNotNone(
            checkpoint_step(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_a",
            )
        )

        clear_checkpoint(
            self.tmpdir,
            self.ticker,
            self.date,
            self.signature,
            run_id="run_a",
        )

        self.assertFalse(
            has_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_a",
            )
        )
        self.assertTrue(
            has_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_b",
            )
        )
        self.assertTrue(
            has_checkpoint(self.tmpdir, self.ticker, self.date, self.signature)
        )

    def test_web_clear_fails_closed_but_legacy_keeps_compatibility(self):
        database = Path(self.tmpdir) / "checkpoints" / f"{self.ticker}.db"
        database.parent.mkdir(parents=True)
        database.touch()
        connection = MagicMock()
        connection.execute.side_effect = sqlite3.OperationalError("broken schema")

        with patch(
            "tradingagents.graph.checkpointer.sqlite3.connect",
            return_value=connection,
        ):
            clear_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
            )

        with (
            patch(
                "tradingagents.graph.checkpointer.sqlite3.connect",
                return_value=connection,
            ),
            self.assertRaises(sqlite3.OperationalError),
        ):
            clear_checkpoint(
                self.tmpdir,
                self.ticker,
                self.date,
                self.signature,
                run_id="run_strict",
            )


if __name__ == "__main__":
    unittest.main()
