"""Tests for observability integration in LangGraphEngine.

Covers:
- RunLogger lifecycle (_start_run_logger / _finish_run_logger)
- Enriched tool events (service, status, error fields)
- Run log JSONL persistence
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent_os.backend.services.langgraph_engine import (
    LangGraphEngine,
    _TOOL_SERVICE_MAP,
)
from tradingagents.observability import RunLogger, get_run_logger, set_run_logger


class TestToolServiceMap(unittest.TestCase):
    """Verify the static tool→service mapping is populated."""

    def test_known_tools_have_services(self):
        self.assertEqual(_TOOL_SERVICE_MAP["get_stock_data"], "yfinance")
        self.assertEqual(_TOOL_SERVICE_MAP["get_insider_transactions"], "finnhub")
        self.assertEqual(_TOOL_SERVICE_MAP["get_insider_buying_stocks"], "finviz")
        self.assertEqual(_TOOL_SERVICE_MAP["get_enriched_holdings"], "local")

    def test_map_is_non_empty(self):
        self.assertGreater(len(_TOOL_SERVICE_MAP), 20)


class TestRunLoggerLifecycle(unittest.TestCase):
    """Test _start_run_logger and _finish_run_logger."""

    def setUp(self):
        self.engine = LangGraphEngine()
        # Clean up any leftover thread-local state
        set_run_logger(None)

    def tearDown(self):
        set_run_logger(None)

    def test_start_creates_logger_and_sets_thread_local(self):
        rl = self.engine._start_run_logger("test-run-1")
        self.assertIsInstance(rl, RunLogger)
        self.assertIs(self.engine._run_loggers.get("test-run-1"), rl)
        self.assertIs(get_run_logger(), rl)

    def test_finish_writes_log_and_cleans_up(self):
        rl = self.engine._start_run_logger("test-run-2")
        # Add a synthetic event
        rl.log_tool_call("get_stock_data", "AAPL", True, 123.4)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "sub"
            self.engine._finish_run_logger("test-run-2", log_dir)

            # Logger removed from tracking
            self.assertNotIn("test-run-2", self.engine._run_loggers)
            # Thread-local cleared
            self.assertIsNone(get_run_logger())

            # JSONL file written
            log_file = log_dir / "run_log.jsonl"
            self.assertTrue(log_file.exists())
            lines = log_file.read_text().strip().split("\n")
            self.assertGreaterEqual(len(lines), 2)  # event + summary

            # Verify first line is the tool event
            evt = json.loads(lines[0])
            self.assertEqual(evt["kind"], "tool")
            self.assertEqual(evt["tool"], "get_stock_data")

            # Last line should be summary
            summary = json.loads(lines[-1])
            self.assertEqual(summary["kind"], "summary")
            self.assertEqual(summary["tool_calls"], 1)

    def test_finish_noop_for_unknown_run(self):
        """_finish_run_logger should silently do nothing for unknown run IDs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.engine._finish_run_logger("nonexistent", Path(tmpdir))
            # No file written, no crash
            self.assertEqual(list(Path(tmpdir).iterdir()), [])


class TestToolEventMapping(unittest.TestCase):
    """Test enriched tool events in _map_langgraph_event."""

    def setUp(self):
        self.engine = LangGraphEngine()
        self.run_id = "test-tool-run"
        self.engine._node_start_times[self.run_id] = {}
        self.engine._run_identifiers[self.run_id] = "AAPL"
        self.engine._node_prompts[self.run_id] = {}

    def tearDown(self):
        self.engine._node_start_times.pop(self.run_id, None)
        self.engine._run_identifiers.pop(self.run_id, None)
        self.engine._node_prompts.pop(self.run_id, None)

    def test_tool_start_includes_service(self):
        event = {
            "event": "on_tool_start",
            "name": "get_stock_data",
            "data": {"input": {"ticker": "AAPL"}},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "market_analyst"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tool")
        self.assertEqual(result["service"], "yfinance")
        self.assertEqual(result["status"], "running")

    def test_tool_start_unknown_tool_has_empty_service(self):
        event = {
            "event": "on_tool_start",
            "name": "some_custom_tool",
            "data": {"input": "test"},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "custom_node"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["service"], "")

    def test_tool_end_success(self):
        event = {
            "event": "on_tool_end",
            "name": "get_fundamentals",
            "data": {"output": MagicMock(content="PE ratio: 25.3, Revenue: $100B")},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "fundamentals_analyst"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tool_result")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["service"], "yfinance")
        self.assertIsNone(result["error"])
        self.assertIn("✓", result["message"])

    def test_tool_end_error_detected(self):
        mock_output = MagicMock()
        mock_output.content = "Error calling get_stock_data: ConnectionError: timeout"
        event = {
            "event": "on_tool_end",
            "name": "get_stock_data",
            "data": {"output": mock_output},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "market_analyst"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertIn("Error", result["error"])
        self.assertIn("✗", result["message"])

    def test_tool_end_graceful_skip(self):
        mock_output = MagicMock()
        mock_output.content = "Data gracefully skipped due to rate limit"
        event = {
            "event": "on_tool_end",
            "name": "get_insider_transactions",
            "data": {"output": mock_output},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "news_analyst"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "graceful_skip")
        self.assertEqual(result["service"], "finnhub")
        self.assertIn("⚠", result["message"])

    def test_tool_end_event_status_error(self):
        """When the event itself has status='error', detect it."""
        event = {
            "event": "on_tool_end",
            "name": "get_earnings_calendar",
            "data": {"output": MagicMock(content=""), "status": "error"},
            "run_id": "abc123",
            "metadata": {"langgraph_node": "sector_scanner"},
        }
        result = self.engine._map_langgraph_event(self.run_id, event)
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["service"], "finnhub")


if __name__ == "__main__":
    unittest.main()
