"""Regression test: a graph node that produces a BaseMessage must round-trip
through our SqliteSaver wrapper without raising
``TypeError: Object of type AIMessage is not JSON serializable``.

The upstream ``langgraph_checkpoint_sqlite 3.1.0`` (bundled with
``langgraph 0.4.8``) builds checkpoint metadata by calling
``get_checkpoint_metadata``, which includes the per-tick ``writes`` dict.
When a node writes to a ``messages`` channel, ``writes[node][messages]``
holds a list of ``AIMessage`` instances — which ``json.dumps`` cannot
serialise. Our wrapper strips ``writes`` from the metadata before
serialising.

This test pins the contract so the next ``pip install`` that bumps either
package back to a working version still passes — we want to know if the
fix becomes unnecessary, not silently regress.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from typing import TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, StateGraph

from tradingagents.graph.checkpointer import get_checkpointer


class _State(TypedDict):
    messages: list


def _emit_ai(state: _State) -> dict:
    return {"messages": [AIMessage(content="hello world")]}  # pragma: no cover - executed via graph


def _emit_ai_with_tool_call(state: _State) -> dict:
    msg = AIMessage(
        content="calling tool",
        tool_calls=[{"name": "search", "args": {"q": "x"}, "id": "call_1"}],
    )
    return {"messages": [msg]}  # pragma: no cover - executed via graph


class TestCheckpointWithAIMessage(unittest.TestCase):
    """LangGraph SqliteSaver must not crash when nodes write BaseMessages."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.ticker = "MSG"

    def _build_graph(self) -> StateGraph:
        builder = StateGraph(_State)
        builder.add_node("analyst", _emit_ai)
        builder.set_entry_point("analyst")
        builder.add_edge("analyst", END)
        return builder

    def test_put_does_not_raise_on_aimessage_writes(self) -> None:
        cfg = {"configurable": {"thread_id": "msg-1"}}
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = self._build_graph().compile(checkpointer=saver)
            # This is the exact failure mode the user reported.
            # Without the fix: TypeError raised out of SqliteSaver.put.
            graph.invoke({"messages": [HumanMessage(content="hi")]}, config=cfg)

    def test_put_survives_aimessage_with_tool_calls(self) -> None:
        """Tool-call messages also contain non-JSON-serialisable bits."""
        builder = StateGraph(_State)
        builder.add_node("analyst", _emit_ai_with_tool_call)
        builder.set_entry_point("analyst")
        builder.add_edge("analyst", END)

        cfg = {"configurable": {"thread_id": "msg-tool"}}
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = builder.compile(checkpointer=saver)
            graph.invoke({"messages": [HumanMessage(content="go")]}, config=cfg)

    def test_checkpoint_is_persisted_for_resume(self) -> None:
        """After a successful run, the checkpoint row should exist on disk."""
        cfg = {"configurable": {"thread_id": "msg-resume"}}
        with get_checkpointer(self.tmpdir, self.ticker) as saver:
            graph = self._build_graph().compile(checkpointer=saver)
            graph.invoke({"messages": [HumanMessage(content="hi")]}, config=cfg)

        # Direct DB inspection — the metadata blob must be valid JSON
        # (proving we didn't accidentally break the contract).
        db = Path(self.tmpdir) / "checkpoints" / f"{self.ticker}.db"
        self.assertTrue(db.exists(), f"expected checkpoint db at {db}")
        with sqlite3.connect(str(db)) as conn:
            row = conn.execute(
                "SELECT metadata FROM checkpoints WHERE thread_id = ?",
                ("msg-resume",),
            ).fetchone()
        self.assertIsNotNone(row, "expected a checkpoint row to be persisted")
        # Round-tripping the metadata JSON must succeed.
        import json as _json
        _json.loads(row[0])  # raises if corrupted


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
