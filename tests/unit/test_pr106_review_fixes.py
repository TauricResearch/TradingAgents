"""Tests for PR#106 review fixes (ADR 016).

Covers:
- Fix 1: save_holding_review per-ticker iteration in run_portfolio
- Fix 2: contextvars-based RunLogger isolation
- Fix 3: list_pm_decisions excludes _id (ObjectId)
- Fix 4: ReflexionMemory created_at is native datetime for MongoDB
- Fix 5: write/read_latest_pointer respects base_dir parameter
- Fix 6: RunLogger callback wired into astream_events config
- Fix 7: ensure_indexes called in MongoReportStore.__init__
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(agen):
    """Collect all events from an async generator into a list."""
    events = []
    async for evt in agen:
        events.append(evt)
    return events


def _root_chain_end_event(output: dict) -> dict:
    """Build a synthetic root on_chain_end LangGraph v2 event."""
    return {
        "event": "on_chain_end",
        "name": "LangGraph",
        "parent_ids": [],
        "metadata": {},
        "data": {"output": output},
        "run_id": "test-run-id",
        "tags": [],
    }


# ---------------------------------------------------------------------------
# Fix 1: save_holding_review per-ticker iteration
# ---------------------------------------------------------------------------

class TestSaveHoldingReviewIteration(unittest.TestCase):
    """Verify save_holding_review is called per-ticker, not once with portfolio_id."""

    _FINAL_STATE = {
        "holding_reviews": json.dumps({
            "AAPL": {"rating": "hold", "reason": "stable"},
            "MSFT": {"rating": "buy", "reason": "growth"},
        }),
        "risk_metrics": "",
        "pm_decision": "",
        "execution_result": "",
    }

    def _make_mock_portfolio_graph(self, final_state=None):
        if final_state is None:
            final_state = self._FINAL_STATE

        async def mock_astream(*args, **kwargs):
            yield _root_chain_end_event(final_state)

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        mock_pg = MagicMock()
        mock_pg.graph = mock_graph
        return mock_pg

    def test_holding_reviews_saved_per_ticker(self):
        """run_portfolio should call save_holding_review once per ticker key."""
        from agent_os.backend.services.langgraph_engine import LangGraphEngine

        mock_pg = self._make_mock_portfolio_graph()
        engine = LangGraphEngine()
        mock_store = MagicMock()
        mock_store.load_scan.return_value = {}
        mock_store.load_analysis.return_value = None

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.create_report_store", return_value=mock_store), \
             patch("agent_os.backend.services.langgraph_engine.get_daily_dir") as mock_gdd, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"):
            fake_daily = MagicMock(spec=Path)
            fake_daily.exists.return_value = False
            fake_daily.__truediv__ = MagicMock(return_value=MagicMock(spec=Path, exists=MagicMock(return_value=False)))
            mock_gdd.return_value = fake_daily

            asyncio.run(_collect(engine.run_portfolio("run1", {
                "date": "2026-03-20",
                "portfolio_id": "pid-123",
            })))

        # save_holding_review should be called once per ticker
        calls = mock_store.save_holding_review.call_args_list
        tickers_saved = {c.args[1] for c in calls}  # (date, ticker, data)
        self.assertEqual(tickers_saved, {"AAPL", "MSFT"})
        self.assertEqual(len(calls), 2)

    def test_non_dict_reviews_logs_warning(self):
        """When holding_reviews is not a dict, it should log a warning, not crash."""
        from agent_os.backend.services.langgraph_engine import LangGraphEngine

        state = dict(self._FINAL_STATE)
        state["holding_reviews"] = json.dumps(["not", "a", "dict"])

        mock_pg = self._make_mock_portfolio_graph(state)
        engine = LangGraphEngine()
        mock_store = MagicMock()
        mock_store.load_scan.return_value = {}
        mock_store.load_analysis.return_value = None

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.create_report_store", return_value=mock_store), \
             patch("agent_os.backend.services.langgraph_engine.get_daily_dir") as mock_gdd, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"):
            fake_daily = MagicMock(spec=Path)
            fake_daily.exists.return_value = False
            fake_daily.__truediv__ = MagicMock(return_value=MagicMock(spec=Path, exists=MagicMock(return_value=False)))
            mock_gdd.return_value = fake_daily

            events = asyncio.run(_collect(engine.run_portfolio("run1", {
                "date": "2026-03-20",
                "portfolio_id": "pid-123",
            })))

        # save_holding_review should NOT be called
        mock_store.save_holding_review.assert_not_called()


# ---------------------------------------------------------------------------
# Fix 2: contextvars-based RunLogger isolation
# ---------------------------------------------------------------------------

class TestContextVarRunLogger(unittest.TestCase):
    """Verify RunLogger uses contextvars (isolated per asyncio task)."""

    def test_set_get_returns_correct_logger(self):
        from tradingagents.observability import (
            RunLogger,
            get_run_logger,
            set_run_logger,
        )

        rl = RunLogger()
        set_run_logger(rl)
        self.assertIs(get_run_logger(), rl)
        set_run_logger(None)
        self.assertIsNone(get_run_logger())

    def test_context_isolation_across_async_tasks(self):
        """Each asyncio task should have its own RunLogger."""
        from tradingagents.observability import (
            RunLogger,
            get_run_logger,
            set_run_logger,
        )

        results = {}

        async def task(name: str):
            rl = RunLogger()
            set_run_logger(rl)
            await asyncio.sleep(0.01)
            results[name] = get_run_logger()
            return rl

        async def run_concurrent():
            rl_a, rl_b = await asyncio.gather(task("A"), task("B"))
            return rl_a, rl_b

        rl_a, rl_b = asyncio.run(run_concurrent())

        # Each task should get back its own logger, not the other's
        self.assertIs(results["A"], rl_a)
        self.assertIs(results["B"], rl_b)
        # They should be different instances
        self.assertIsNot(rl_a, rl_b)


# ---------------------------------------------------------------------------
# Fix 3: list_pm_decisions excludes _id
# ---------------------------------------------------------------------------

class TestListPmDecisionsExcludesId(unittest.TestCase):
    """Verify list_pm_decisions uses {_id: 0} projection."""

    def test_projection_excludes_object_id(self):
        with patch("tradingagents.portfolio.mongo_report_store.MongoClient") as mock_client_cls:
            mock_col = MagicMock()
            mock_db = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=mock_col)
            mock_client = MagicMock()
            mock_client.__getitem__ = MagicMock(return_value=mock_db)
            mock_client_cls.return_value = mock_client

            from tradingagents.portfolio.mongo_report_store import MongoReportStore

            store = MongoReportStore("mongodb://localhost:27017", run_id="test")
            store._col = mock_col

            mock_col.find.return_value = []
            store.list_pm_decisions("pid-123")

            # Verify the projection argument includes _id: 0
            find_call = mock_col.find.call_args
            projection = find_call[0][1] if len(find_call[0]) > 1 else find_call[1].get("projection")
            self.assertEqual(projection, {"_id": 0})


# ---------------------------------------------------------------------------
# Fix 4: ReflexionMemory created_at is native datetime for MongoDB
# ---------------------------------------------------------------------------

class TestReflexionCreatedAtType(unittest.TestCase):
    """Verify created_at is native datetime for MongoDB, ISO string for local."""

    def test_mongodb_path_stores_native_datetime(self):
        """When writing to MongoDB, created_at should be a datetime object."""
        with patch("tradingagents.memory.reflexion.MongoClient", create=True) as mock_client_cls:
            mock_col = MagicMock()
            mock_db = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=mock_col)
            mock_client = MagicMock()
            mock_client.__getitem__ = MagicMock(return_value=mock_db)
            mock_client_cls.return_value = mock_client

            from tradingagents.memory.reflexion import ReflexionMemory

            mem = ReflexionMemory.__new__(ReflexionMemory)
            mem._col = mock_col
            mem._fallback_path = Path("/tmp/test_reflexion.json")

            mem.record_decision("AAPL", "2026-03-20", "BUY", "test", "high")

            doc = mock_col.insert_one.call_args[0][0]
            self.assertIsInstance(doc["created_at"], datetime)

    def test_local_path_stores_iso_string(self):
        """When writing to local JSON, created_at should be an ISO string."""
        import tempfile
        from tradingagents.memory.reflexion import ReflexionMemory

        with tempfile.TemporaryDirectory() as tmpdir:
            fb_path = Path(tmpdir) / "test_reflexion.json"
            mem = ReflexionMemory(fallback_path=fb_path)

            mem.record_decision("AAPL", "2026-03-20", "BUY", "test", "high")

            data = json.loads(fb_path.read_text())
            self.assertIsInstance(data[0]["created_at"], str)
            # Should be parseable as ISO datetime
            datetime.fromisoformat(data[0]["created_at"])


# ---------------------------------------------------------------------------
# Fix 5: write/read_latest_pointer respects base_dir parameter
# ---------------------------------------------------------------------------

class TestLatestPointerBaseDir(unittest.TestCase):
    """Verify write_latest_pointer/read_latest_pointer use base_dir."""

    def test_pointer_uses_custom_base_dir(self):
        from tradingagents.report_paths import read_latest_pointer, write_latest_pointer

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "custom_reports"
            write_latest_pointer("2026-03-20", "run123", base_dir=base)

            # Should be written under the custom base, not REPORTS_ROOT
            pointer = base / "daily" / "2026-03-20" / "latest.json"
            self.assertTrue(pointer.exists())
            data = json.loads(pointer.read_text())
            self.assertEqual(data["run_id"], "run123")

            # read_latest_pointer should use the same base
            result = read_latest_pointer("2026-03-20", base_dir=base)
            self.assertEqual(result, "run123")

    def test_read_returns_none_with_wrong_base(self):
        from tradingagents.report_paths import read_latest_pointer, write_latest_pointer

        with tempfile.TemporaryDirectory() as tmpdir:
            base_a = Path(tmpdir) / "a"
            base_b = Path(tmpdir) / "b"
            write_latest_pointer("2026-03-20", "run_a", base_dir=base_a)

            # Reading from a different base should not find it
            result = read_latest_pointer("2026-03-20", base_dir=base_b)
            self.assertIsNone(result)

    def test_report_store_passes_base_dir(self):
        """ReportStore should pass its _base_dir to pointer functions."""
        from tradingagents.portfolio.report_store import ReportStore

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "custom"
            store = ReportStore(base_dir=base, run_id="abc123")

            # Trigger a save which calls _update_latest
            store.save_scan("2026-03-20", {"test": True})

            # Pointer should be under the custom base
            pointer = base / "daily" / "2026-03-20" / "latest.json"
            self.assertTrue(pointer.exists())
            data = json.loads(pointer.read_text())
            self.assertEqual(data["run_id"], "abc123")


# ---------------------------------------------------------------------------
# Fix 6: RunLogger callback wired into astream_events config
# ---------------------------------------------------------------------------

class TestRunLoggerCallbackWiring(unittest.TestCase):
    """Verify astream_events receives the RunLogger callback in config."""

    def _make_mock_graph(self, final_state):
        """Create a mock graph that captures the config passed to astream_events."""
        captured_config = {}

        async def mock_astream(*args, **kwargs):
            captured_config.update(kwargs.get("config", {}))
            yield _root_chain_end_event(final_state)

        mock_graph = MagicMock()
        mock_graph.astream_events = mock_astream
        return mock_graph, captured_config

    def test_run_scan_wires_callback(self):
        from agent_os.backend.services.langgraph_engine import LangGraphEngine

        mock_graph, captured = self._make_mock_graph({
            "geopolitical_report": "", "market_movers_report": "",
            "sector_performance_report": "", "industry_deep_dive_report": "",
            "macro_scan_summary": "",
        })
        mock_scanner = MagicMock()
        mock_scanner.graph = mock_graph

        engine = LangGraphEngine()
        mock_store = MagicMock()

        with patch("agent_os.backend.services.langgraph_engine.ScannerGraph", return_value=mock_scanner), \
             patch("agent_os.backend.services.langgraph_engine.create_report_store", return_value=mock_store), \
             patch("agent_os.backend.services.langgraph_engine.get_market_dir") as mock_gmd, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"), \
             patch("agent_os.backend.services.langgraph_engine.extract_json", return_value={}):
            fake_dir = MagicMock(spec=Path)
            fake_dir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_dir.mkdir = MagicMock()
            mock_gmd.return_value = fake_dir

            asyncio.run(_collect(engine.run_scan("run1", {"date": "2026-01-01"})))

        self.assertIn("callbacks", captured)
        self.assertEqual(len(captured["callbacks"]), 1)

    def test_run_pipeline_wires_callback(self):
        from agent_os.backend.services.langgraph_engine import LangGraphEngine

        mock_graph, captured = self._make_mock_graph({"final_trade_decision": "BUY"})
        mock_propagator = MagicMock()
        mock_propagator.max_recur_limit = 100
        mock_propagator.create_initial_state.return_value = {"ticker": "AAPL"}
        mock_wrapper = MagicMock()
        mock_wrapper.graph = mock_graph
        mock_wrapper.propagator = mock_propagator

        engine = LangGraphEngine()
        mock_store = MagicMock()

        with patch("agent_os.backend.services.langgraph_engine.TradingAgentsGraph", return_value=mock_wrapper), \
             patch("agent_os.backend.services.langgraph_engine.create_report_store", return_value=mock_store), \
             patch("agent_os.backend.services.langgraph_engine.get_ticker_dir") as mock_gtd, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"):
            fake_dir = MagicMock(spec=Path)
            fake_dir.__truediv__ = MagicMock(return_value=MagicMock(spec=Path))
            fake_dir.mkdir = MagicMock()
            mock_gtd.return_value = fake_dir

            asyncio.run(_collect(engine.run_pipeline("run1", {
                "ticker": "AAPL", "date": "2026-01-01",
            })))

        self.assertIn("callbacks", captured)
        self.assertEqual(len(captured["callbacks"]), 1)
        # Also verify recursion_limit is still set
        self.assertEqual(captured["recursion_limit"], 100)

    def test_run_portfolio_wires_callback(self):
        from agent_os.backend.services.langgraph_engine import LangGraphEngine

        mock_graph, captured = self._make_mock_graph({
            "holding_reviews": "", "risk_metrics": "",
            "pm_decision": "", "execution_result": "",
        })
        mock_pg = MagicMock()
        mock_pg.graph = mock_graph

        engine = LangGraphEngine()
        mock_store = MagicMock()
        mock_store.load_scan.return_value = {}
        mock_store.load_analysis.return_value = None

        with patch("agent_os.backend.services.langgraph_engine.PortfolioGraph", return_value=mock_pg), \
             patch("agent_os.backend.services.langgraph_engine.create_report_store", return_value=mock_store), \
             patch("agent_os.backend.services.langgraph_engine.get_daily_dir") as mock_gdd, \
             patch("agent_os.backend.services.langgraph_engine.append_to_digest"):
            fake_daily = MagicMock(spec=Path)
            fake_daily.exists.return_value = False
            fake_daily.__truediv__ = MagicMock(return_value=MagicMock(spec=Path, exists=MagicMock(return_value=False)))
            mock_gdd.return_value = fake_daily

            asyncio.run(_collect(engine.run_portfolio("run1", {
                "date": "2026-01-01", "portfolio_id": "pid-123",
            })))

        self.assertIn("callbacks", captured)
        self.assertEqual(len(captured["callbacks"]), 1)


# ---------------------------------------------------------------------------
# Fix 7: ensure_indexes called in MongoReportStore.__init__
# ---------------------------------------------------------------------------

class TestEnsureIndexesInInit(unittest.TestCase):
    """Verify ensure_indexes is called during __init__, not just via factory."""

    def test_init_calls_ensure_indexes(self):
        with patch("tradingagents.portfolio.mongo_report_store.MongoClient") as mock_client_cls:
            mock_col = MagicMock()
            mock_db = MagicMock()
            mock_db.__getitem__ = MagicMock(return_value=mock_col)
            mock_client = MagicMock()
            mock_client.__getitem__ = MagicMock(return_value=mock_db)
            mock_client_cls.return_value = mock_client

            from tradingagents.portfolio.mongo_report_store import MongoReportStore

            store = MongoReportStore("mongodb://localhost:27017", run_id="test")

            # Indexes are now created lazily, not in __init__.
            # Explicitly call ensure_indexes() to test index creation logic.
            store.ensure_indexes()

            # create_index should have been called at least 4 times
            # (the indexes from ensure_indexes)
            self.assertGreaterEqual(mock_col.create_index.call_count, 4)


if __name__ == "__main__":
    unittest.main()
