"""Tests for Phase 0 — Checkpoint archival (T0.4).

When a propagate() run completes successfully, the thread's checkpoint
rows must land in a per-(ticker, date) standalone DB under the audit
store before the active DB rows get cleared. This file validates the
``archive_checkpoint`` helper directly and also the integration with
``clear_checkpoint`` (archive happens BEFORE clear).
"""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

from langgraph.graph import END, StateGraph

from tradingagents.graph.checkpointer import (
    archive_checkpoint,
    clear_checkpoint,
    get_checkpointer,
    thread_id,
)


class _SimpleState(TypedDict):
    count: int


def _build_graph() -> StateGraph:
    """Two-node graph; ``_run_until_persisted`` uses this to seed a checkpoint."""
    builder = StateGraph(_SimpleState)
    builder.add_node("analyst", lambda s: {"count": s["count"] + 1})
    builder.add_node("trader", lambda s: {"count": s["count"] + 10})
    builder.set_entry_point("analyst")
    builder.add_edge("analyst", "trader")
    builder.add_edge("trader", END)
    return builder


def _seed_checkpoint(tmpdir: str, ticker: str, date: str) -> None:
    """Run a tiny graph to populate the per-ticker DB with this thread's rows."""
    builder = _build_graph()
    tid = thread_id(ticker, date)
    with get_checkpointer(tmpdir, ticker) as saver:
        graph = builder.compile(checkpointer=saver)
        graph.invoke({"count": 0}, config={"configurable": {"thread_id": tid}})


def _count_thread_rows(db_path: Path, tid: str) -> dict:
    """Return per-table row counts filtered to ``tid``."""
    conn = sqlite3.connect(str(db_path))
    counts = {}
    try:
        for table in ("checkpoints", "writes"):
            try:
                cur = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE thread_id = ?", (tid,)
                )
                counts[table] = cur.fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = None
    finally:
        conn.close()
    return counts


class TestArchiveCheckpoint(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = self._tmp.name
        self.archive_root = Path(self.tmpdir) / "audit"
        self.ticker = "TEST"
        self.date = "2026-04-20"
        self.tid = thread_id(self.ticker, self.date)

    # ------------------------------------------------------------------ #
    # Direct contract
    # ------------------------------------------------------------------ #

    def test_archive_extracts_only_target_thread(self):
        """An AAPL archive must not include MSFT rows even though the
        DBs are per-ticker — same ticker different dates is the realistic
        co-mingling case."""
        # Seed two dates for the same ticker
        _seed_checkpoint(self.tmpdir, self.ticker, "2026-04-20")
        _seed_checkpoint(self.tmpdir, self.ticker, "2026-04-21")

        dest = archive_checkpoint(
            self.tmpdir, self.ticker, "2026-04-20", archive_dir=self.archive_root,
        )

        self.assertIsNotNone(dest)
        self.assertTrue(dest.exists())
        # Archive should contain rows for date1 only
        tid1 = thread_id(self.ticker, "2026-04-20")
        tid2 = thread_id(self.ticker, "2026-04-21")
        c1 = _count_thread_rows(dest, tid1)
        c2 = _count_thread_rows(dest, tid2)
        self.assertGreater(c1["checkpoints"], 0)
        self.assertEqual(c2["checkpoints"], 0)

    def test_archive_path_layout(self):
        """Output lands at audit_dir/checkpoints/{TICKER}/{date}.db."""
        _seed_checkpoint(self.tmpdir, self.ticker, self.date)
        dest = archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )
        self.assertEqual(
            dest,
            self.archive_root / "checkpoints" / "TEST" / f"{self.date}.db",
        )

    def test_archive_returns_none_when_no_source_db(self):
        """If checkpointing was never enabled, no DB exists — archive no-ops."""
        result = archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )
        self.assertIsNone(result)

    def test_archive_returns_none_when_thread_has_no_rows(self):
        """Source DB exists but this thread has no checkpoints — no-op."""
        _seed_checkpoint(self.tmpdir, self.ticker, "2026-04-20")
        # Try to archive a DIFFERENT date; that thread has nothing
        result = archive_checkpoint(
            self.tmpdir, self.ticker, "2099-12-31", archive_dir=self.archive_root,
        )
        self.assertIsNone(result)

    def test_archive_overwrites_existing_destination(self):
        """Re-archiving the same (ticker, date) replaces the file rather
        than stacking. An updated run for the same trade date is more
        useful than a tower of partial archives."""
        _seed_checkpoint(self.tmpdir, self.ticker, self.date)
        dest1 = archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )
        first_mtime = dest1.stat().st_mtime

        # Re-archive (after some change would have happened in real use)
        import time
        time.sleep(0.05)
        dest2 = archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )

        self.assertEqual(dest1, dest2)
        self.assertGreaterEqual(dest2.stat().st_mtime, first_mtime)

    def test_archive_does_not_touch_active_db(self):
        """Archive must be read-only against the source so it can run
        before clear_checkpoint without race risk."""
        _seed_checkpoint(self.tmpdir, self.ticker, self.date)
        active_before = _count_thread_rows(
            Path(self.tmpdir) / "checkpoints" / "TEST.db", self.tid
        )

        archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )

        active_after = _count_thread_rows(
            Path(self.tmpdir) / "checkpoints" / "TEST.db", self.tid
        )
        self.assertEqual(active_before, active_after)

    # ------------------------------------------------------------------ #
    # Integration with clear_checkpoint
    # ------------------------------------------------------------------ #

    def test_archive_then_clear_yields_complete_archive(self):
        """The realistic flow: archive, then clear. After clear, the
        active DB has zero rows for this thread but the archive is
        intact — auditor can still inspect it."""
        _seed_checkpoint(self.tmpdir, self.ticker, self.date)

        dest = archive_checkpoint(
            self.tmpdir, self.ticker, self.date, archive_dir=self.archive_root,
        )
        clear_checkpoint(self.tmpdir, self.ticker, self.date)

        # Active DB no longer has this thread
        active = _count_thread_rows(
            Path(self.tmpdir) / "checkpoints" / "TEST.db", self.tid
        )
        self.assertEqual(active["checkpoints"], 0)
        # But archive does
        archived = _count_thread_rows(dest, self.tid)
        self.assertGreater(archived["checkpoints"], 0)

    def test_default_archive_dir_uses_home(self, *, _real_home=None):
        """When archive_dir=None, archive lands under ~/.tradingagents/audit.

        We monkeypatch Path.home for the duration of the test so we don't
        actually write into the user's real home dir.
        """
        from unittest.mock import patch

        _seed_checkpoint(self.tmpdir, self.ticker, self.date)

        fake_home = Path(self.tmpdir) / "fake_home"
        with patch("pathlib.Path.home", return_value=fake_home):
            dest = archive_checkpoint(
                self.tmpdir, self.ticker, self.date, archive_dir=None,
            )

        self.assertEqual(
            dest,
            fake_home / ".tradingagents" / "audit" / "checkpoints" / "TEST"
            / f"{self.date}.db",
        )
        self.assertTrue(dest.exists())


if __name__ == "__main__":
    unittest.main()
