"""Tests for trading_graph: constructor, fetch returns, resolve pending entries,
log state, run graph, propagate checkpoint paths, and helper methods."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from langgraph.prebuilt import ToolNode

from tradingagents.default_config import DEFAULT_CONFIG


def _minimal_config():
    """Return a config that safely passes through constructor checks."""
    c = dict(DEFAULT_CONFIG)
    c["data_cache_dir"] = "/tmp/tradingagents_test_cache"
    c["results_dir"] = "/tmp/tradingagents_test_results"
    return c


def _construct_graph(config_override=None, callbacks=None):
    """Helper: build a TradingAgentsGraph with extensive mocking."""
    config = {**(_minimal_config()), **(config_override or {})}
    with (
        patch("tradingagents.graph.trading_graph.set_config") as mock_set_config,
        patch("tradingagents.graph.trading_graph.os.makedirs"),
        patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
        patch("tradingagents.graph.trading_graph.TradingMemoryLog") as mock_memory_log,
        patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
        patch("tradingagents.graph.trading_graph.Propagator") as mock_propagator,
        patch("tradingagents.graph.trading_graph.Reflector") as mock_reflector,
        patch("tradingagents.graph.trading_graph.SignalProcessor") as mock_signal_proc,
    ):
        mock_llm_instance = MagicMock()
        mock_llm_instance.get_llm.return_value = MagicMock()
        mock_create_llm.return_value = mock_llm_instance

        mock_workflow = MagicMock()
        mock_graph_setup_instance = MagicMock()
        mock_graph_setup_instance.setup_graph.return_value = mock_workflow
        mock_graph_setup.return_value = mock_graph_setup_instance

        mock_propagator_instance = MagicMock()
        mock_propagator.return_value = mock_propagator_instance

        mock_reflector_instance = MagicMock()
        mock_reflector.return_value = mock_reflector_instance

        mock_signal_proc_instance = MagicMock()
        mock_signal_processor.return_value = mock_signal_proc_instance

        mock_memory_log_instance = MagicMock()
        mock_memory_log.return_value = mock_memory_log_instance

        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = TradingAgentsGraph(
            selected_analysts=["market", "social"],
            debug=False,
            config=config,
            callbacks=callbacks,
        )
        # Store mocks for verification
        g._mocks = {
            "set_config": mock_set_config,
            "create_llm": mock_create_llm,
            "memory_log": mock_memory_log,
            "graph_setup": mock_graph_setup,
            "propagator": mock_propagator,
            "reflector": mock_reflector,
            "signal_processor": mock_signal_proc,
            "llm_instance": mock_llm_instance,
            "workflow": mock_workflow,
            "graph_setup_instance": mock_graph_setup_instance,
            "propagator_instance": mock_propagator_instance,
        }
        return g


def _make_graph():
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    with patch.object(TradingAgentsGraph, "__init__", return_value=None):
        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        g.config = {
            "data_cache_dir": "/tmp/tradingagents_test_cache",
            "results_dir": "/tmp/tradingagents_test_results",
            "benchmark_map": {"": "SPY"},
            "checkpoint_enabled": False,
        }
        g.memory_log = MagicMock()
        g.reflector = MagicMock()
        g.log_states_dict = {}
        g.ticker = "AAPL"
        g.debug = False
        g.node_timings = []
        g.analyst_wall_times = {}
        g.analyst_wall_time_summary = ""
        g.total_stream_time = 0.0
        g.signal_processor = MagicMock()
        g.signal_processor.process_signal.return_value = "Buy"
        g.propagator = MagicMock()
        g.propagator.create_initial_state.return_value = {
            "company_of_interest": "AAPL",
            "trade_date": "2026-06-15",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "governance_report": "",
            "industry_report": "",
            "investment_debate_state": {
                "bull_history": [], "bear_history": [],
                "history": [], "current_response": "",
                "judge_decision": "",
            },
            "trader_investment_plan": {},
            "risk_debate_state": {
                "aggressive_history": [], "conservative_history": [],
                "neutral_history": [], "history": [],
                "judge_decision": "",
            },
            "investment_plan": {},
            "final_trade_decision": "Hold",
        }
        g.propagator.get_graph_args.return_value = {"config": {}}
        g.selected_analysts = ["market"]
        g.graph = MagicMock()
        g.workflow = MagicMock()
        g.graph_setup = MagicMock()
        g.graph_setup.setup_graph.return_value = MagicMock()
        g.resolve_instrument_context = MagicMock(return_value="context")
        g._checkpointer_ctx = None
        return g


# ---------------------------------------------------------------------------
# _resolve_benchmark
# ---------------------------------------------------------------------------


@pytest.mark.unit
class ResolveBenchmarkTests(unittest.TestCase):
    def _make_graph(self, config):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)
            g.config = config
            return g

    def test_uses_explicit_benchmark(self):
        g = self._make_graph({"benchmark_ticker": "^N225", "benchmark_map": {"": "SPY"}})
        self.assertEqual(g._resolve_benchmark("7203.T"), "^N225")

    def test_matches_by_suffix(self):
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {".T": "^N225", ".HK": "^HSI", "": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("7203.T"), "^N225")

    def test_case_insensitive_suffix_match(self):
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {".to": "^GSPTSE", "": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("BNS.TO"), "^GSPTSE")

    def test_falls_back_to_empty_suffix(self):
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {"": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("AAPL"), "SPY")

    def test_unknown_suffix_falls_back_to_empty(self):
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {".T": "^N225", "": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("FOO.XX"), "SPY")

    def test_no_suffix_on_ticker_with_dot(self):
        """Tickers like BRK.B have a dot but no mapped suffix -> fallback."""
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {"": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("BRK.B"), "SPY")

    def test_empty_benchmark_map_uses_default(self):
        g = self._make_graph({
            "benchmark_ticker": None,
            "benchmark_map": {},
        })
        self.assertEqual(g._resolve_benchmark("AAPL"), "SPY")

    def test_explicit_benchmark_wins_over_suffix(self):
        g = self._make_graph({
            "benchmark_ticker": "SPY",
            "benchmark_map": {".T": "^N225", "": "SPY"},
        })
        self.assertEqual(g._resolve_benchmark("7203.T"), "SPY")


# ---------------------------------------------------------------------------
# _get_provider_kwargs
# ---------------------------------------------------------------------------


@pytest.mark.unit
class GetProviderKwargsTests(unittest.TestCase):
    def _make_graph(self, config):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)
            g.config = config
            return g

    def test_temperature_conversion(self):
        g = self._make_graph({"llm_provider": "openai", "temperature": "0.5"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["temperature"], 0.5)

    def test_temperature_as_float_passthrough(self):
        g = self._make_graph({"llm_provider": "openai", "temperature": 0.7})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["temperature"], 0.7)

    def test_no_temperature_when_none(self):
        g = self._make_graph({"llm_provider": "openai", "temperature": None})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("temperature", kwargs)

    def test_no_temperature_when_empty_string(self):
        g = self._make_graph({"llm_provider": "openai", "temperature": ""})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("temperature", kwargs)

    def test_temperature_missing_key(self):
        g = self._make_graph({"llm_provider": "openai"})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("temperature", kwargs)

    def test_google_thinking_level(self):
        g = self._make_graph({"llm_provider": "google", "google_thinking_level": "high"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["thinking_level"], "high")

    def test_google_no_thinking_level(self):
        g = self._make_graph({"llm_provider": "google"})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("thinking_level", kwargs)

    def test_openai_reasoning_effort(self):
        g = self._make_graph({"llm_provider": "openai", "openai_reasoning_effort": "high"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["reasoning_effort"], "high")

    def test_openai_no_reasoning_effort(self):
        g = self._make_graph({"llm_provider": "openai"})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("reasoning_effort", kwargs)

    def test_anthropic_effort(self):
        g = self._make_graph({"llm_provider": "anthropic", "anthropic_effort": "high"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["effort"], "high")

    def test_anthropic_no_effort(self):
        g = self._make_graph({"llm_provider": "anthropic"})
        kwargs = g._get_provider_kwargs()
        self.assertNotIn("effort", kwargs)

    def test_unknown_provider_no_extra_kwargs(self):
        g = self._make_graph({"llm_provider": "unknown_provider"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs, {})

    def test_provider_case_insensitive(self):
        g = self._make_graph({"llm_provider": "OpenAI", "openai_reasoning_effort": "medium"})
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["reasoning_effort"], "medium")

    def test_temperature_with_google(self):
        g = self._make_graph({
            "llm_provider": "google",
            "google_thinking_level": "high",
            "temperature": "0.3",
        })
        kwargs = g._get_provider_kwargs()
        self.assertEqual(kwargs["thinking_level"], "high")
        self.assertEqual(kwargs["temperature"], 0.3)


# ---------------------------------------------------------------------------
# _create_tool_nodes
# ---------------------------------------------------------------------------


@pytest.mark.unit
class CreateToolNodesTests(unittest.TestCase):
    def _make_graph(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)
            return g

    def test_returns_dict_with_all_keys(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        expected_keys = {"market", "social", "news", "governance", "industry", "fundamentals"}
        self.assertEqual(set(nodes.keys()), expected_keys)

    def test_all_values_are_tool_nodes(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        for key, node in nodes.items():
            with self.subTest(key=key):
                self.assertIsInstance(node, ToolNode)

    def test_market_node_has_stock_data_and_indicators(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["market"].tools_by_name.keys())
        self.assertIn("get_stock_data", tool_names)
        self.assertIn("get_indicators", tool_names)

    def test_social_node_has_news(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["social"].tools_by_name.keys())
        self.assertIn("get_news", tool_names)

    def test_news_node_has_multiple_tools(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["news"].tools_by_name.keys())
        for name in ("get_news", "get_global_news", "get_insider_transactions", "get_company_announcements"):
            with self.subTest(tool=name):
                self.assertIn(name, tool_names)

    def test_governance_node_has_governance_tools(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["governance"].tools_by_name.keys())
        for name in ("get_company_announcements", "get_insider_transactions",
                      "get_news", "get_restricted_release",
                      "get_institutional_holdings", "get_northbound_hold"):
            with self.subTest(tool=name):
                self.assertIn(name, tool_names)

    def test_industry_node_has_industry_valuation(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["industry"].tools_by_name.keys())
        self.assertIn("get_industry_valuation", tool_names)

    def test_fundamentals_node_has_fundamental_tools(self):
        g = self._make_graph()
        nodes = g._create_tool_nodes()
        tool_names = list(nodes["fundamentals"].tools_by_name.keys())
        for name in ("get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"):
            with self.subTest(tool=name):
                self.assertIn(name, tool_names)


# ---------------------------------------------------------------------------
# process_signal
# ---------------------------------------------------------------------------


@pytest.mark.unit
class ProcessSignalTests(unittest.TestCase):
    def test_delegates_to_signal_processor(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        mock_processor = MagicMock()
        mock_processor.process_signal.return_value = "Buy"
        g.signal_processor = mock_processor
        result = g.process_signal("**Rating**: Buy")
        self.assertEqual(result, "Buy")
        mock_processor.process_signal.assert_called_once_with("**Rating**: Buy")


# ---------------------------------------------------------------------------
# resolve_instrument_context
# ---------------------------------------------------------------------------


@pytest.mark.unit
class ResolveInstrumentContextTests(unittest.TestCase):
    def test_delegates_to_agent_utils(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        with (
            patch("tradingagents.graph.trading_graph.resolve_instrument_identity") as mock_resolve,
            patch("tradingagents.graph.trading_graph.build_instrument_context") as mock_build,
        ):
            mock_resolve.return_value = {"company_name": "Apple Inc.", "sector": "Technology"}
            mock_build.return_value = "Instrument: AAPL (Apple Inc.)"

            result = g.resolve_instrument_context("AAPL", asset_type="stock")

            mock_resolve.assert_called_once_with("AAPL")
            mock_build.assert_called_once_with("AAPL", "stock", {"company_name": "Apple Inc.", "sector": "Technology"})
            self.assertEqual(result, "Instrument: AAPL (Apple Inc.)")

    def test_defaults_to_stock_asset_type(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        with (
            patch("tradingagents.graph.trading_graph.resolve_instrument_identity") as mock_resolve,
            patch("tradingagents.graph.trading_graph.build_instrument_context") as mock_build,
        ):
            mock_resolve.return_value = {}
            mock_build.return_value = "Instrument: BTC"

            result = g.resolve_instrument_context("BTC", asset_type="crypto")

            mock_build.assert_called_once_with("BTC", "crypto", {})
            self.assertEqual(result, "Instrument: BTC")

    def test_identity_lookup_failure_returns_ticker_only_context(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        g = TradingAgentsGraph.__new__(TradingAgentsGraph)
        with (
            patch("tradingagents.graph.trading_graph.resolve_instrument_identity") as mock_resolve,
            patch("tradingagents.graph.trading_graph.build_instrument_context") as mock_build,
        ):
            mock_resolve.return_value = {}
            mock_build.return_value = "Instrument: `XYZ`."

            result = g.resolve_instrument_context("XYZ")
            self.assertEqual(result, "Instrument: `XYZ`.")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


@pytest.mark.unit
class ConstructorTests(unittest.TestCase):
    def setUp(self):
        self.config = _minimal_config()

    def test_default_analysts(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config)

            self.assertEqual(g.selected_analysts, ["market", "social", "news", "fundamentals"])
            self.assertFalse(g.debug)
            self.assertEqual(g.config["data_cache_dir"], self.config["data_cache_dir"])
            mock_setup_instance.setup_graph.assert_called_once_with(
                ["market", "social", "news", "fundamentals"]
            )

    def test_custom_analysts(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(
                selected_analysts=["market", "news"],
                config=self.config,
            )

            self.assertEqual(g.selected_analysts, ["market", "news"])
            mock_setup_instance.setup_graph.assert_called_once_with(["market", "news"])

    def test_callbacks_passed_to_llm(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        callback_obj = MagicMock()

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config, callbacks=[callback_obj])

            # Both LLM clients should have received callbacks in kwargs
            for call_args in mock_create_llm.call_args_list:
                self.assertIn("callbacks", call_args.kwargs)
                self.assertEqual(call_args.kwargs["callbacks"], [callback_obj])

            self.assertEqual(g.callbacks, [callback_obj])

    def test_no_callbacks_empty_list(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config)

            for call_args in mock_create_llm.call_args_list:
                self.assertNotIn("callbacks", call_args.kwargs)

            self.assertEqual(g.callbacks, [])

    def test_creates_deep_and_quick_llms(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_deep = MagicMock()
            mock_quick = MagicMock()
            mock_deep.get_llm.return_value = "deep_llm_obj"
            mock_quick.get_llm.return_value = "quick_llm_obj"

            def _side_effect(*args, **kwargs):
                model = kwargs.get("model", "")
                if "deep" in model:
                    return mock_deep
                return mock_quick

            mock_create_llm.side_effect = _side_effect

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config)

            self.assertEqual(mock_create_llm.call_count, 2)
            self.assertEqual(g.deep_thinking_llm, "deep_llm_obj")
            self.assertEqual(g.quick_thinking_llm, "quick_llm_obj")

    def test_creates_components(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog") as mock_memory_log,
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator") as mock_propagator,
            patch("tradingagents.graph.trading_graph.Reflector") as mock_reflector,
            patch("tradingagents.graph.trading_graph.SignalProcessor") as mock_signal,
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_memory_log_instance = MagicMock()
            mock_memory_log.return_value = mock_memory_log_instance

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            mock_propagator_instance = MagicMock()
            mock_propagator.return_value = mock_propagator_instance

            mock_reflector_instance = MagicMock()
            mock_reflector.return_value = mock_reflector_instance

            mock_signal_instance = MagicMock()
            mock_signal.return_value = mock_signal_instance

            g = TradingAgentsGraph(config=self.config)

            self.assertIs(g.memory_log, mock_memory_log_instance)
            self.assertIs(g.propagator, mock_propagator_instance)
            self.assertIs(g.reflector, mock_reflector_instance)
            self.assertIs(g.signal_processor, mock_signal_instance)
            self.assertIs(g.graph_setup, mock_setup_instance)
            self.assertIs(g.graph, mock_workflow.compile())

    def test_config_used_for_set_config(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config") as mock_set_config,
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config)

            mock_set_config.assert_called_once_with(self.config)

    def test_directories_created(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs") as mock_makedirs,
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config)

            self.assertEqual(mock_makedirs.call_count, 2)
            mock_makedirs.assert_any_call(self.config["data_cache_dir"], exist_ok=True)
            mock_makedirs.assert_any_call(self.config["results_dir"], exist_ok=True)

    def test_conditional_logic_created_with_config_values(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        custom_config = dict(self.config)
        custom_config["max_debate_rounds"] = 3
        custom_config["max_risk_discuss_rounds"] = 2

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
            patch("tradingagents.graph.trading_graph.ConditionalLogic") as mock_cl,
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=custom_config)

            mock_cl.assert_called_once_with(
                max_debate_rounds=3, max_risk_discuss_rounds=2
            )

    def test_propagator_created_with_recur_limit(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        custom_config = dict(self.config)
        custom_config["max_recur_limit"] = 200

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator") as mock_propagator,
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=custom_config)

            mock_propagator.assert_called_once_with(max_recur_limit=200)

    def test_debug_mode_stored(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with (
            patch("tradingagents.graph.trading_graph.set_config"),
            patch("tradingagents.graph.trading_graph.os.makedirs"),
            patch("tradingagents.graph.trading_graph.create_llm_client") as mock_create_llm,
            patch("tradingagents.graph.trading_graph.TradingMemoryLog"),
            patch("tradingagents.graph.trading_graph.GraphSetup") as mock_graph_setup,
            patch("tradingagents.graph.trading_graph.Propagator"),
            patch("tradingagents.graph.trading_graph.Reflector"),
            patch("tradingagents.graph.trading_graph.SignalProcessor"),
        ):
            mock_llm = MagicMock()
            mock_llm.get_llm.return_value = MagicMock()
            mock_create_llm.return_value = mock_llm

            mock_setup_instance = MagicMock()
            mock_workflow = MagicMock()
            mock_setup_instance.setup_graph.return_value = mock_workflow
            mock_graph_setup.return_value = mock_setup_instance

            g = TradingAgentsGraph(config=self.config, debug=True)

            self.assertTrue(g.debug)


# ---------------------------------------------------------------------------
# _fetch_crypto_returns (pure logic via patching network calls)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class FetchCryptoReturnsTests(unittest.TestCase):
    def _make_graph(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)
            return g

    def test_btc_to_eth_alpha(self):
        g = self._make_graph()
        btc_prices = json.dumps({"prices": [[1000000, 40000.0], [2000000, 44000.0]]}).encode()
        eth_prices = json.dumps({"prices": [[1000000, 3000.0], [2000000, 3150.0]]}).encode()

        def _urlopen(url, timeout=15):
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            if "bitcoin" in url:
                mock_resp.read.return_value = btc_prices
            else:
                mock_resp.read.return_value = eth_prices
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            raw, alpha, days = g._fetch_crypto_returns(
                "BTC", "2000-01-01", "2000-02-01", holding_days=5, benchmark="ETH"
            )
        self.assertIsNotNone(raw)
        self.assertIsNotNone(alpha)
        self.assertEqual(days, 5)
        self.assertAlmostEqual(raw, 0.1)  # (44000 - 40000) / 40000
        self.assertAlmostEqual(alpha, 0.1 - 0.05)  # raw - bench(0.05)

    def test_crypto_benchmark_not_in_map_returns_none_alpha(self):
        g = self._make_graph()
        mock_data = json.dumps({"prices": [[1000000, 40000.0], [2000000, 44000.0]]}).encode()

        def _urlopen(url, timeout=15):
            mock_resp = MagicMock()
            mock_resp.read.return_value = mock_data
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=_urlopen):
            raw, alpha, days = g._fetch_crypto_returns(
                "SOL", "2000-01-01", "2000-02-01", holding_days=5, benchmark="UNKNOWN"
            )
        self.assertIsNotNone(raw)
        self.assertIsNone(alpha)
        self.assertEqual(days, 5)


# ---------------------------------------------------------------------------
# Helper function tests for coin_id mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
class FetchCryptoCoinIdTests(unittest.TestCase):
    def test_coin_id_mapping(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)

        # Test the coin_map logic via _fetch_crypto_returns by inspecting
        # the first urlopen call: we verify the coin_id resolution indirectly
        # by patching urlopen and checking the URL.
        urls_called = []

        def _capture_url(url, timeout=15):
            urls_called.append(url)
            mock_resp = MagicMock()
            mock_resp.__enter__.return_value = mock_resp
            mock_resp.read.return_value = json.dumps({"prices": [[1, 100], [2, 110]]}).encode()
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=_capture_url):
            g._fetch_crypto_returns(
                "BTC-USD", "2000-01-01", "2000-01-02", holding_days=1, benchmark="SPY"
            )
        self.assertTrue(any("bitcoin" in url for url in urls_called))


# ---------------------------------------------------------------------------
# _fetch_returns
# ---------------------------------------------------------------------------


@pytest.mark.unit
class FetchReturnsTests(unittest.TestCase):
    def _make_graph(self):
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        with patch.object(TradingAgentsGraph, "__init__", return_value=None):
            g = TradingAgentsGraph.__new__(TradingAgentsGraph)
            g.config = {}
            return g

    def test_successful_returns(self):
        g = self._make_graph()
        mock_stock = pd.DataFrame({
            "Close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
        })
        mock_bench = pd.DataFrame({
            "Close": [200.0, 201.0, 202.0, 203.0, 204.0, 205.0],
        })

        with (
            patch("yfinance.Ticker") as mock_ticker,
        ):
            mock_stock_obj = MagicMock()
            mock_stock_obj.history.return_value = mock_stock
            mock_bench_obj = MagicMock()
            mock_bench_obj.history.return_value = mock_bench
            mock_ticker.side_effect = lambda t: mock_stock_obj if t == "AAPL" else mock_bench_obj

            raw, alpha, days = g._fetch_returns("AAPL", "2026-06-15", holding_days=5, benchmark="SPY")

        self.assertIsNotNone(raw)
        self.assertIsNotNone(alpha)
        self.assertEqual(days, 5)
        self.assertAlmostEqual(raw, (105.0 - 100.0) / 100.0)
        bench_ret = (205.0 - 200.0) / 200.0
        self.assertAlmostEqual(alpha, raw - bench_ret)

    def test_insufficient_data_returns_none(self):
        g = self._make_graph()
        with patch("yfinance.Ticker") as mock_ticker:
            mock_obj = MagicMock()
            mock_obj.history.return_value = pd.DataFrame({"Close": [100.0]})
            mock_ticker.return_value = mock_obj

            raw, alpha, days = g._fetch_returns("AAPL", "2026-06-15")
        self.assertIsNone(raw)
        self.assertIsNone(alpha)
        self.assertIsNone(days)

    def test_exception_returns_none(self):
        g = self._make_graph()
        with patch("yfinance.Ticker", side_effect=Exception("Network error")):
            raw, alpha, days = g._fetch_returns("AAPL", "2026-06-15")
        self.assertIsNone(raw)
        self.assertIsNone(alpha)
        self.assertIsNone(days)

    def test_crypto_returns_delegates(self):
        g = self._make_graph()
        with (
            patch.object(g, "_fetch_crypto_returns", return_value=(0.1, 0.05, 5)) as mock_crypto,
        ):
            raw, alpha, days = g._fetch_returns("BTC", "2026-06-15", asset_type="crypto")
        self.assertEqual((raw, alpha, days), (0.1, 0.05, 5))
        mock_crypto.assert_called_once()

    def test_holding_days_clamped_by_data_length(self):
        g = self._make_graph()
        mock_stock = pd.DataFrame({
            "Close": [100.0, 101.0],
        })
        mock_bench = pd.DataFrame({
            "Close": [200.0, 201.0, 202.0],
        })
        with patch("yfinance.Ticker") as mock_ticker:
            mock_stock_obj = MagicMock()
            mock_stock_obj.history.return_value = mock_stock
            mock_bench_obj = MagicMock()
            mock_bench_obj.history.return_value = mock_bench
            mock_ticker.side_effect = lambda t: mock_stock_obj if t == "AAPL" else mock_bench_obj

            raw, alpha, days = g._fetch_returns("AAPL", "2026-06-15", holding_days=10, benchmark="SPY")

        self.assertEqual(days, 1)
        self.assertAlmostEqual(raw, (101.0 - 100.0) / 100.0)


# ---------------------------------------------------------------------------
# _resolve_pending_entries
# ---------------------------------------------------------------------------


@pytest.mark.unit
class ResolvePendingEntriesTests(unittest.TestCase):
    def test_no_pending_entries_does_nothing(self):
        g = _make_graph()
        g.memory_log.get_pending_entries.return_value = []
        g._resolve_pending_entries("AAPL")
        g.memory_log.batch_update_with_outcomes.assert_not_called()

    def test_skips_entries_for_other_tickers(self):
        g = _make_graph()
        g.memory_log.get_pending_entries.return_value = [
            {"ticker": "MSFT", "date": "2026-06-10", "decision": "Buy"},
        ]
        g._resolve_pending_entries("AAPL")
        g.memory_log.batch_update_with_outcomes.assert_not_called()

    def test_updates_same_ticker_entries(self):
        g = _make_graph()
        g.memory_log.get_pending_entries.return_value = [
            {"ticker": "AAPL", "date": "2026-06-10", "decision": "Buy"},
        ]
        g.reflector.reflect_on_final_decision.return_value = "Good call"

        with patch.object(g, "_fetch_returns", return_value=(0.05, 0.02, 5)):
            g._resolve_pending_entries("AAPL")

        g.memory_log.batch_update_with_outcomes.assert_called_once_with([
            {
                "ticker": "AAPL",
                "trade_date": "2026-06-10",
                "raw_return": 0.05,
                "alpha_return": 0.02,
                "holding_days": 5,
                "reflection": "Good call",
            }
        ])

    def test_skips_entry_when_returns_not_available(self):
        g = _make_graph()
        g.memory_log.get_pending_entries.return_value = [
            {"ticker": "AAPL", "date": "2026-06-10", "decision": "Buy"},
        ]

        with patch.object(g, "_fetch_returns", return_value=(None, None, None)):
            g._resolve_pending_entries("AAPL")

        g.memory_log.batch_update_with_outcomes.assert_not_called()

    def test_multiple_entries_partial_resolution(self):
        g = _make_graph()
        g.memory_log.get_pending_entries.return_value = [
            {"ticker": "AAPL", "date": "2026-06-10", "decision": "Buy"},
            {"ticker": "AAPL", "date": "2026-06-11", "decision": "Sell"},
        ]
        g.reflector.reflect_on_final_decision.return_value = "reflection"

        # Only first entry resolves; second returns None
        returns_side_effects = [
            (0.05, 0.02, 5),
            (None, None, None),
        ]

        with patch.object(g, "_fetch_returns", side_effect=returns_side_effects):
            g._resolve_pending_entries("AAPL")

        g.memory_log.batch_update_with_outcomes.assert_called_once()
        call_args = g.memory_log.batch_update_with_outcomes.call_args[0][0]
        self.assertEqual(len(call_args), 1)
        self.assertEqual(call_args[0]["trade_date"], "2026-06-10")


# ---------------------------------------------------------------------------
# _log_state
# ---------------------------------------------------------------------------


@pytest.mark.unit
class LogStateTests(unittest.TestCase):
    def _make_graph(self):
        g = _make_graph()
        g.results_dir = tempfile.mkdtemp()
        g.config["results_dir"] = g.results_dir
        return g

    def test_writes_json_file(self):
        g = self._make_graph()
        final_state = g.propagator.create_initial_state.return_value
        final_state["company_of_interest"] = "AAPL"
        final_state["trade_date"] = "2026-06-15"

        g._log_state("2026-06-15", final_state)

        safe_ticker = "AAPL"
        log_dir = Path(g.config["results_dir"]) / safe_ticker / "TradingAgentsStrategy_logs"
        log_path = log_dir / "full_states_log_2026-06-15.json"
        self.assertTrue(log_path.exists())
        with open(log_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["company_of_interest"], "AAPL")
        self.assertEqual(data["final_trade_decision"], "Hold")

    def test_updates_log_states_dict(self):
        g = self._make_graph()
        final_state = g.propagator.create_initial_state.return_value
        g._log_state("2026-06-15", final_state)
        self.assertIn("2026-06-15", g.log_states_dict)

    def test_writes_safe_ticker_path(self):
        g = self._make_graph()
        g.ticker = "../../evil"
        final_state = g.propagator.create_initial_state.return_value
        with patch("tradingagents.graph.trading_graph.safe_ticker_component", return_value="..__..__evil"):
            g._log_state("2026-06-15", final_state)
        log_dir = Path(g.config["results_dir"]) / "..__..__evil" / "TradingAgentsStrategy_logs"
        self.assertTrue((log_dir / "full_states_log_2026-06-15.json").exists())


# ---------------------------------------------------------------------------
# _run_graph
# ---------------------------------------------------------------------------


@pytest.mark.unit
class RunGraphTests(unittest.TestCase):
    def test_streams_graph_and_returns_signal(self):
        g = _make_graph()
        g.memory_log.get_past_context.return_value = "past context"
        g.resolve_instrument_context = MagicMock(return_value="instrument context")

        # Simulate a stream yielding chunks that build up the full state
        def mock_stream(init_state, **kwargs):
            yield {"analyst_market": {"market_report": "report1"}}
            yield {"final_node": {
                "market_report": "report1",
                "sentiment_report": "neutral",
                "news_report": "positive",
                "fundamentals_report": "strong",
                "governance_report": "fair",
                "industry_report": "growing",
                "investment_debate_state": {
                    "bull_history": [], "bear_history": [],
                    "history": [], "current_response": "",
                    "judge_decision": "bull",
                },
                "trader_investment_plan": {"action": "buy"},
                "risk_debate_state": {
                    "aggressive_history": [], "conservative_history": [],
                    "neutral_history": [], "history": [],
                    "judge_decision": "approve",
                },
                "investment_plan": {"size": 1000},
                "final_trade_decision": "Buy",
            }}

        g.graph.stream = mock_stream

        state, signal = g._run_graph("AAPL", "2026-06-15")

        self.assertEqual(state["final_trade_decision"], "Buy")
        self.assertEqual(signal, "Buy")
        # Verify state was stored
        self.assertEqual(g.curr_state, state)
        # Verify timings were collected
        self.assertEqual(len(g.node_timings), 2)
        # Verify memory log was called
        g.memory_log.store_decision.assert_called_once_with(
            ticker="AAPL", trade_date="2026-06-15",
            final_trade_decision="Buy",
        )

    def test_streams_with_non_dict_chunk(self):
        g = _make_graph()
        g.memory_log.get_past_context.return_value = "past"

        def mock_stream(init_state, **kwargs):
            yield {"node1": None}
            yield {"node2": {
                "market_report": "",
                "sentiment_report": "",
                "news_report": "",
                "fundamentals_report": "",
                "governance_report": "",
                "industry_report": "",
                "investment_debate_state": {
                    "bull_history": [], "bear_history": [],
                    "history": [], "current_response": "",
                    "judge_decision": "",
                },
                "trader_investment_plan": {},
                "risk_debate_state": {
                    "aggressive_history": [], "conservative_history": [],
                    "neutral_history": [], "history": [],
                    "judge_decision": "",
                },
                "investment_plan": {},
                "final_trade_decision": "Sell",
            }}

        g.graph.stream = mock_stream
        g.resolve_instrument_context = MagicMock(return_value="ctx")

        state, signal = g._run_graph("AAPL", "2026-06-15")
        self.assertEqual(state["final_trade_decision"], "Sell")

    def test_checkpoint_thread_id_injected(self):
        g = _make_graph()
        g.config["checkpoint_enabled"] = True
        g.memory_log.get_past_context.return_value = "past"
        g.resolve_instrument_context = MagicMock(return_value="ctx")

        def mock_stream(init_state, **kwargs):
            yield {"n1": {"final_trade_decision": "Buy", "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "", "governance_report": "", "industry_report": "", "investment_debate_state": {"bull_history": [], "bear_history": [], "history": [], "current_response": "", "judge_decision": ""}, "trader_investment_plan": {}, "risk_debate_state": {"aggressive_history": [], "conservative_history": [], "neutral_history": [], "history": [], "judge_decision": ""}, "investment_plan": {}}}

        g.graph.stream = mock_stream

        with (
            patch("tradingagents.graph.trading_graph.thread_id", return_value="tid123"),
        ):
            g._run_graph("AAPL", "2026-06-15")

        self.assertEqual(g.propagator.get_graph_args.return_value["config"]["configurable"]["thread_id"], "tid123")

    def test_stream_with_debug_mode(self):
        g = _make_graph()
        g.debug = True
        g.memory_log.get_past_context.return_value = "past"
        g.resolve_instrument_context = MagicMock(return_value="ctx")

        mock_message = MagicMock()
        mock_message.pretty_print = MagicMock()

        def mock_stream(init_state, **kwargs):
            yield {"n1": {"messages": [mock_message], "final_trade_decision": "Buy", "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "", "governance_report": "", "industry_report": "", "investment_debate_state": {"bull_history": [], "bear_history": [], "history": [], "current_response": "", "judge_decision": ""}, "trader_investment_plan": {}, "risk_debate_state": {"aggressive_history": [], "conservative_history": [], "neutral_history": [], "history": [], "judge_decision": ""}, "investment_plan": {}}}

        g.graph.stream = mock_stream
        g._run_graph("AAPL", "2026-06-15")
        mock_message.pretty_print.assert_called_once()

    def test_checkpoint_cleared_on_success(self):
        g = _make_graph()
        g.config["checkpoint_enabled"] = True
        g.memory_log.get_past_context.return_value = "past"
        g.resolve_instrument_context = MagicMock(return_value="ctx")

        def mock_stream(init_state, **kwargs):
            yield {"n1": {"final_trade_decision": "Hold", "market_report": "", "sentiment_report": "", "news_report": "", "fundamentals_report": "", "governance_report": "", "industry_report": "", "investment_debate_state": {"bull_history": [], "bear_history": [], "history": [], "current_response": "", "judge_decision": ""}, "trader_investment_plan": {}, "risk_debate_state": {"aggressive_history": [], "conservative_history": [], "neutral_history": [], "history": [], "judge_decision": ""}, "investment_plan": {}}}

        g.graph.stream = mock_stream

        with (
            patch("tradingagents.graph.trading_graph.thread_id", return_value="tid"),
            patch("tradingagents.graph.trading_graph.clear_checkpoint") as mock_clear,
        ):
            g._run_graph("AAPL", "2026-06-15")
            mock_clear.assert_called_once_with(
                "/tmp/tradingagents_test_cache", "AAPL", "2026-06-15"
            )


# ---------------------------------------------------------------------------
# propagate — checkpoint paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class PropagateTests(unittest.TestCase):
    def setUp(self):
        self.g = _make_graph()
        self.tmp_results = tempfile.mkdtemp()
        self.g.config["results_dir"] = self.tmp_results
        self.g.config["data_cache_dir"] = tempfile.mkdtemp()
        self.g.config["checkpoint_enabled"] = False

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_results, ignore_errors=True)
        shutil.rmtree(self.g.config["data_cache_dir"], ignore_errors=True)

    def test_without_checkpoint_resolves_ticker_and_runs(self):
        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch.object(self.g, "_resolve_pending_entries") as mock_pending,
            patch.object(self.g, "_run_graph", return_value=({"final_trade_decision": "Buy"}, "Buy")) as mock_run,
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}
            state, signal = self.g.propagate("AAPL", "2026-06-15")
            self.assertEqual(self.g.ticker, "AAPL")
            mock_pending.assert_called_once_with("AAPL", asset_type="stock")
            mock_run.assert_called_once_with("AAPL", "2026-06-15", asset_type="stock")

    def test_with_checkpoint_enabled_and_cached_result(self):
        self.g.config["checkpoint_enabled"] = True
        cached_state = {
            "final_trade_decision": "Buy",
            "company_of_interest": "AAPL",
            "trade_date": "2026-06-15",
            "market_report": "",
            "sentiment_report": "",
            "news_report": "",
            "fundamentals_report": "",
            "governance_report": "",
            "industry_report": "",
            "investment_debate_state": {
                "bull_history": [], "bear_history": [],
                "history": [], "current_response": "",
                "judge_decision": "",
            },
            "trader_investment_plan": {},
            "risk_debate_state": {
                "aggressive_history": [], "conservative_history": [],
                "neutral_history": [], "history": [],
                "judge_decision": "",
            },
            "investment_plan": {},
        }
        # Create the actual state log file on disk
        log_dir = Path(self.tmp_results) / "AAPL" / "TradingAgentsStrategy_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "full_states_log_2026-06-15.json"
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(cached_state, f)

        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch("tradingagents.dataflows.utils.safe_ticker_component", return_value="AAPL"),
            patch.object(self.g, "_resolve_pending_entries"),
            patch("tradingagents.graph.trading_graph.clear_checkpoint") as mock_clear,
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}

            state, signal = self.g.propagate("AAPL", "2026-06-15")
            self.assertEqual(state["final_trade_decision"], "Buy")
            self.assertEqual(signal, "Buy")
            mock_clear.assert_called_once()

    def test_with_checkpoint_enabled_resumes_from_step(self):
        self.g.config["checkpoint_enabled"] = True

        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch("tradingagents.dataflows.utils.safe_ticker_component", return_value="AAPL"),
            patch.object(self.g, "_resolve_pending_entries"),
            patch.object(self.g, "_run_graph", return_value=({"final_trade_decision": "Sell"}, "Sell")) as mock_run,
            patch("tradingagents.graph.trading_graph.get_checkpointer") as mock_get_cp,
            patch("tradingagents.graph.trading_graph.checkpoint_step", return_value=3),
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}
            mock_cm = MagicMock()
            mock_cm.__enter__.return_value = MagicMock()
            mock_get_cp.return_value = mock_cm

            state, signal = self.g.propagate("AAPL", "2026-06-15")
            self.assertEqual(state["final_trade_decision"], "Sell")
            mock_run.assert_called_once()

    def test_checkpointer_exit_on_exception(self):
        self.g.config["checkpoint_enabled"] = True

        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch("tradingagents.dataflows.utils.safe_ticker_component", return_value="AAPL"),
            patch.object(self.g, "_resolve_pending_entries"),
            patch.object(self.g, "_run_graph", side_effect=ValueError("test error")),
            patch("tradingagents.graph.trading_graph.get_checkpointer") as mock_get_cp,
            patch("tradingagents.graph.trading_graph.checkpoint_step", return_value=None),
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}
            mock_cm = MagicMock()
            mock_get_cp.return_value = mock_cm

            with self.assertRaises(ValueError):
                self.g.propagate("AAPL", "2026-06-15")

            mock_cm.__exit__.assert_called_once()

    def test_cached_state_log_exception_continues(self):
        self.g.config["checkpoint_enabled"] = True
        # Create a corrupted state log file
        log_dir = Path(self.tmp_results) / "AAPL" / "TradingAgentsStrategy_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "full_states_log_2026-06-15.json"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("not valid json{{{")

        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch("tradingagents.dataflows.utils.safe_ticker_component", return_value="AAPL"),
            patch.object(self.g, "_resolve_pending_entries"),
            patch.object(self.g, "_run_graph", return_value=({"final_trade_decision": "Buy"}, "Buy")) as mock_run,
            patch("tradingagents.graph.trading_graph.get_checkpointer") as mock_get_cp,
            patch("tradingagents.graph.trading_graph.checkpoint_step", return_value=None),
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}
            mock_cm = MagicMock()
            mock_cm.__enter__.return_value = MagicMock()
            mock_get_cp.return_value = mock_cm

            state, signal = self.g.propagate("AAPL", "2026-06-15")
            self.assertEqual(state["final_trade_decision"], "Buy")
            mock_run.assert_called_once()

    def test_propagate_with_resolved_company_name(self):
        g = _make_graph()
        g.config["checkpoint_enabled"] = False
        g.config["results_dir"] = self.tmp_results
        with (
            patch("tradingagents.ticker_resolver.resolve_ticker") as mock_resolve,
            patch.object(g, "_resolve_pending_entries"),
            patch.object(g, "_run_graph", return_value=({"final_trade_decision": "Hold"}, "Hold")),
        ):
            mock_resolve.return_value = {"ticker": "AAPL", "company_name": "Apple Inc."}
            state, signal = g.propagate("Apple Inc.", "2026-06-15")
            self.assertEqual(g.ticker, "AAPL")


if __name__ == "__main__":
    unittest.main()
