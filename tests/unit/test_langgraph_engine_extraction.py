import sys
import os
import unittest
from unittest.mock import MagicMock

# Ensure project root is on sys.path (works in CI and local)
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from agent_os.backend.services.event_mapper import (
    EventMapper,
    _extract_content,
    _safe_dict,
    is_root_chain_end,
)
from agent_os.backend.services.report_helpers import extract_tickers_from_scan_data


class TestLangGraphEngineExtraction(unittest.TestCase):
    def setUp(self):
        self.mapper = EventMapper()

    # ── _extract_content ────────────────────────────────────────────

    def test_extract_content_string(self):
        mock_obj = MagicMock()
        mock_obj.content = "hello world"
        self.assertEqual(_extract_content(mock_obj), "hello world")

    def test_extract_content_method(self):
        mock_obj = MagicMock()
        mock_obj.content = lambda: "should not be called"
        result = _extract_content(mock_obj)
        # Falls back to str(mock_obj)
        self.assertIsInstance(result, str)

    def test_extract_content_none(self):
        mock_obj = MagicMock()
        mock_obj.content = None
        result = _extract_content(mock_obj)
        self.assertIsInstance(result, str)

    # ── _safe_dict ──────────────────────────────────────────────────

    def test_safe_dict_with_dict(self):
        self.assertEqual(_safe_dict({"a": 1}), {"a": 1})

    def test_safe_dict_with_none(self):
        self.assertEqual(_safe_dict(None), {})

    def test_safe_dict_with_method(self):
        self.assertEqual(_safe_dict(lambda: {}), {})

    def test_safe_dict_with_mock(self):
        self.assertEqual(_safe_dict(MagicMock()), {})

    # ── on_chat_model_end with .text as method ──────────────────────

    def test_map_langgraph_event_llm_end_with_text_method(self):
        mock_output = MagicMock()
        mock_output.text = lambda: "bad"
        mock_output.content = None

        event = {
            "event": "on_chat_model_end",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"output": mock_output},
            "metadata": {"langgraph_node": "test_node"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "result")
        self.assertIsInstance(result.get("response", ""), str)

    def test_map_langgraph_event_llm_end_with_text_string(self):
        mock_output = MagicMock()
        mock_output.text = "good text"
        mock_output.content = None

        event = {
            "event": "on_chat_model_end",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"output": mock_output},
            "metadata": {"langgraph_node": "test_node"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertEqual(result["response"], "good text")

    # ── on_chat_model_end with non-dict metadata ────────────────────

    def test_map_langgraph_event_llm_end_non_dict_metadata(self):
        """response_metadata / usage_metadata being non-dict must not crash."""
        mock_output = MagicMock()
        mock_output.content = "response text"
        # Force non-dict types for metadata
        mock_output.response_metadata = "not-a-dict"
        mock_output.usage_metadata = 42

        event = {
            "event": "on_chat_model_end",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"output": mock_output},
            "metadata": {"langgraph_node": "test_node"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "result")
        self.assertEqual(result["response"], "response text")
        # Metrics should have safe defaults
        self.assertIsInstance(result["metrics"]["tokens_in"], (int, float))

    # ── on_chat_model_start ─────────────────────────────────────────

    def test_map_langgraph_event_llm_start(self):
        event = {
            "event": "on_chat_model_start",
            "run_id": "test_run",
            "name": "test_node",
            "data": {"messages": []},
            "metadata": {"langgraph_node": "test_node"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "thought")
        self.assertIn("prompt", result)

    # ── on_tool_start / on_tool_end ─────────────────────────────────

    def test_map_langgraph_event_tool_start(self):
        event = {
            "event": "on_tool_start",
            "run_id": "test_run",
            "name": "get_market_data",
            "data": {"input": {"ticker": "AAPL"}},
            "metadata": {"langgraph_node": "scanner"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tool")

    def test_map_langgraph_event_tool_end(self):
        event = {
            "event": "on_tool_end",
            "run_id": "test_run",
            "name": "get_market_data",
            "data": {"output": "some data"},
            "metadata": {"langgraph_node": "scanner"},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNotNone(result)
        self.assertEqual(result["type"], "tool_result")

    # ── Unknown event types return None ─────────────────────────────

    def test_map_langgraph_event_unknown(self):
        event = {
            "event": "on_chain_start",
            "run_id": "test_run",
            "name": "test",
            "data": {},
            "metadata": {},
        }

        result = self.mapper.map_event("run_123", event)
        self.assertIsNone(result)

    # ── is_root_chain_end ───────────────────────────────────────────

    def test_is_root_chain_end_true(self):
        """Root graph terminal event: on_chain_end with empty parent_ids and no node."""
        event = {
            "event": "on_chain_end",
            "name": "LangGraph",
            "parent_ids": [],
            "metadata": {},
            "data": {"output": {"x": "final"}},
        }
        self.assertTrue(is_root_chain_end(event))

    def test_is_root_chain_end_false_for_node_event(self):
        """Node on_chain_end should NOT be treated as the root graph end."""
        event = {
            "event": "on_chain_end",
            "name": "geopolitical_scanner",
            "parent_ids": ["some-parent-run-id"],
            "metadata": {"langgraph_node": "geopolitical_scanner"},
            "data": {"output": {"geopolitical_report": "..."}},
        }
        self.assertFalse(is_root_chain_end(event))

    def test_is_root_chain_end_false_for_non_chain_end(self):
        """on_chain_start should never match."""
        event = {
            "event": "on_chain_start",
            "name": "LangGraph",
            "parent_ids": [],
            "metadata": {},
            "data": {},
        }
        self.assertFalse(is_root_chain_end(event))

    def test_is_root_chain_end_false_when_parent_ids_missing(self):
        """If parent_ids is absent (unexpected), should not match."""
        event = {
            "event": "on_chain_end",
            "name": "LangGraph",
            "metadata": {},
            "data": {"output": {"x": "v"}},
        }
        self.assertFalse(is_root_chain_end(event))

    def test_is_root_chain_end_false_when_langgraph_node_present(self):
        """Node-level event with empty parent_ids should still not match."""
        event = {
            "event": "on_chain_end",
            "name": "some_node",
            "parent_ids": [],
            "metadata": {"langgraph_node": "some_node"},
            "data": {"output": {}},
        }
        self.assertFalse(is_root_chain_end(event))

    # ── extract_tickers_from_scan_data ──────────────────────────────

    def test_extract_tickers_list_of_dicts(self):
        scan = {"stocks_to_investigate": [
            {"ticker": "AAPL", "name": "Apple"},
            {"ticker": "tsla", "sector": "EV"},
        ]}
        self.assertEqual(extract_tickers_from_scan_data(scan), ["AAPL", "TSLA"])

    def test_extract_tickers_list_of_strings(self):
        scan = {"watchlist": ["msft", "GOOG", "amzn"]}
        self.assertEqual(extract_tickers_from_scan_data(scan), ["MSFT", "GOOG", "AMZN"])

    def test_extract_tickers_prefers_stocks_to_investigate(self):
        scan = {
            "stocks_to_investigate": [{"ticker": "NVDA"}],
            "watchlist": [{"ticker": "AMD"}],
        }
        self.assertEqual(extract_tickers_from_scan_data(scan), ["NVDA"])

    def test_extract_tickers_deduplicates(self):
        scan = {"stocks_to_investigate": ["AAPL", "aapl", "AAPL"]}
        self.assertEqual(extract_tickers_from_scan_data(scan), ["AAPL"])

    def test_extract_tickers_empty_scan(self):
        self.assertEqual(extract_tickers_from_scan_data(None), [])
        self.assertEqual(extract_tickers_from_scan_data({}), [])

    def test_extract_tickers_symbol_key_fallback(self):
        scan = {"stocks_to_investigate": [{"symbol": "META"}]}
        self.assertEqual(extract_tickers_from_scan_data(scan), ["META"])

    def test_extract_tickers_filters_out_etfs_and_coins(self):
        scan = {"stocks_to_investigate": ["AAPL", "SPY", "BTC", "TSLA"]}
        self.assertEqual(extract_tickers_from_scan_data(scan), ["AAPL", "TSLA"])


if __name__ == "__main__":
    unittest.main()
