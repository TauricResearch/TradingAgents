import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import pytest

import cli.main as cli_main
from cli.models import AnalystType, AssetType
from cli.utils import detect_market_region, normalize_ticker_symbol
from tradingagents.agents.utils.agent_utils import (
    build_a_share_research_focus,
    build_instrument_context,
    build_market_rule_context,
    is_a_share_ticker,
)
from tradingagents.dataflows.a_share_common import get_previous_trade_date


@pytest.mark.unit
class TickerSymbolHandlingTests(unittest.TestCase):
    def test_normalize_ticker_symbol_preserves_exchange_suffix(self):
        self.assertEqual(normalize_ticker_symbol(" cnc.to "), "CNC.TO")

    def test_normalize_ticker_symbol_infers_a_share_exchange(self):
        self.assertEqual(normalize_ticker_symbol("600519"), "600519.SH")
        self.assertEqual(normalize_ticker_symbol("sz000001"), "000001.SZ")
        self.assertEqual(normalize_ticker_symbol("SH600519.SH"), "600519.SH")

    def test_build_instrument_context_mentions_exact_symbol(self):
        context = build_instrument_context("7203.T")
        self.assertIn("7203.T", context)
        self.assertIn("exchange suffix", context)

    def test_detect_market_region_identifies_a_share(self):
        self.assertEqual(detect_market_region("600519"), "cn_a")
        self.assertEqual(detect_market_region("000001.SZ", AssetType.STOCK), "cn_a")
        self.assertEqual(detect_market_region("SPY"), "us")

    def test_a_share_rule_helpers_activate_for_a_share(self):
        self.assertIn("T+1", build_market_rule_context("600519.SH"))
        self.assertIn("policy direction", build_a_share_research_focus("000001.SZ"))
        self.assertEqual(build_market_rule_context("AAPL"), "")
        self.assertTrue(is_a_share_ticker("600519"))
        self.assertTrue(is_a_share_ticker("SH600519"))

    @patch(
        "tradingagents.dataflows.a_share_common.get_trade_calendar",
        return_value=(
            pd.Timestamp("2026-05-16"),
            pd.Timestamp("2026-05-19"),
            pd.Timestamp("2026-05-21"),
        ),
    )
    def test_get_previous_trade_date_returns_latest_trading_day_on_or_before_target(self, _mock_calendar):
        self.assertEqual(get_previous_trade_date("2026-05-20"), "2026-05-19")
        self.assertEqual(get_previous_trade_date("2026-05-21"), "2026-05-21")

    def test_run_analysis_keeps_bj_benchmark_auto_mapping(self):
        captured = {}

        class DummyLive:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class DummyStats:
            pass

        class DummyTracker:
            def __init__(self, *args, **kwargs):
                pass

            def mark_started(self, *args, **kwargs):
                pass

            def format_summary(self):
                return "summary"

        class DummyPropagator:
            def create_initial_state(self, *args, **kwargs):
                return {}

            def get_graph_args(self, **kwargs):
                return {}

        class DummyGraphRunner:
            def stream(self, *args, **kwargs):
                return iter([{"final_trade_decision": "HOLD"}])

        class DummyTradingAgentsGraph:
            def __init__(self, selected_analyst_keys, config, debug, callbacks):
                captured["config"] = config
                self.propagator = DummyPropagator()
                self.graph = DummyGraphRunner()

            def process_signal(self, signal):
                return signal

        with TemporaryDirectory() as tmpdir:
            with patch.object(
                cli_main,
                "get_user_selections",
                return_value={
                    "research_depth": 1,
                    "shallow_thinker": "gpt-5.4-mini",
                    "deep_thinker": "gpt-5.4",
                    "backend_url": None,
                    "llm_provider": "openai",
                    "google_thinking_level": None,
                    "openai_reasoning_effort": None,
                    "anthropic_effort": None,
                    "output_language": "Chinese",
                    "market_region": "cn_a",
                    "ticker": "430047.BJ",
                    "analysis_date": "2026-05-21",
                    "asset_type": AssetType.STOCK,
                    "analysts": [AnalystType.MARKET],
                },
            ), patch.object(cli_main, "StatsCallbackHandler", DummyStats), patch.object(
                cli_main,
                "build_analyst_execution_plan",
                return_value=["market"],
            ), patch.object(
                cli_main,
                "AnalystWallTimeTracker",
                DummyTracker,
            ), patch.object(
                cli_main,
                "get_initial_analyst_node",
                return_value="Market Analyst",
            ), patch.object(
                cli_main,
                "TradingAgentsGraph",
                DummyTradingAgentsGraph,
            ), patch.object(
                cli_main,
                "create_layout",
                return_value=object(),
            ), patch.object(
                cli_main,
                "update_display",
            ), patch.object(
                cli_main,
                "Live",
                DummyLive,
            ), patch.object(
                cli_main,
                "sync_analyst_tracker_from_chunk",
            ), patch.object(
                cli_main.typer,
                "prompt",
                return_value="N",
            ), patch.dict(
                cli_main.DEFAULT_CONFIG,
                {
                    "results_dir": str(Path(tmpdir) / "results"),
                    "data_cache_dir": str(Path(tmpdir) / "cache"),
                },
                clear=False,
            ):
                cli_main.run_analysis(checkpoint=False)

        self.assertIsNone(captured["config"]["benchmark_ticker"])


if __name__ == "__main__":
    unittest.main()
