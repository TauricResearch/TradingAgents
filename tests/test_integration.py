# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration test: backtest -> tracker -> dashboard pipeline."""

import tempfile
import os
from unittest.mock import MagicMock, patch

from tradingagents.backtest.engine import BacktestEngine
from tradingagents.backtest.models import TradeRecord, BacktestResult
from tradingagents.tracker.tracker import TradeTracker
from tradingagents.dashboard.builder import DashboardBuilder
from tradingagents.default_config import DEFAULT_CONFIG


class TestFullPipeline:
    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_backtest_to_dashboard(self, mock_yf, mock_graph_cls):
        """Full pipeline: backtest -> dashboard HTML."""
        # Mock price data
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        # Mock graph: alternates BUY/SELL
        call_count = {"n": 0}
        def mock_propagate(ticker, date):
            call_count["n"] += 1
            signal = "BUY" if call_count["n"] % 2 == 1 else "SELL"
            state = {
                "market_report": "test", "sentiment_report": "test",
                "news_report": "test", "fundamentals_report": "test",
                "investment_debate_state": {"bull_history": "", "bear_history": "", "judge_decision": ""},
                "risk_debate_state": {"judge_decision": ""},
                "final_trade_decision": f"FINAL TRANSACTION PROPOSAL: **{signal}**",
            }
            return state, signal

        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = mock_propagate
        mock_graph_cls.return_value = mock_graph

        with tempfile.TemporaryDirectory() as tmp:
            config = DEFAULT_CONFIG.copy()
            config["results_dir"] = tmp

            # 1. Run backtest
            engine = BacktestEngine(config)
            result = engine.run(
                ticker="TEST", start_date="2024-04-01", end_date="2024-10-01",
                rebalance_freq="monthly", benchmark="SPY", initial_capital=100_000.0,
            )
            assert isinstance(result, BacktestResult)

            # 2. Generate dashboard
            builder = DashboardBuilder(output_dir=os.path.join(tmp, "dashboard"))
            html_path = builder.build(
                metrics=result.metrics,
                trades=result.trades,
                backtest_results=[result],
                title="Integration Test",
            )
            assert os.path.exists(html_path)
            with open(html_path) as f:
                html = f.read()
            assert "plotly" in html.lower()

    def test_tracker_to_dashboard(self):
        """Pipeline: tracker records -> dashboard HTML."""
        with tempfile.TemporaryDirectory() as tmp:
            config = DEFAULT_CONFIG.copy()
            config["results_dir"] = tmp

            tracker = TradeTracker(config)
            tracker.record_trade("TEST", "2026-04-01", "BUY", 100.0, 100, "paper", {})
            tracker.close_position("TEST", "2026-04-15", 110.0)
            tracker.record_trade("TEST", "2026-04-15", "BUY", 110.0, 100, "paper", {})
            tracker.close_position("TEST", "2026-04-25", 105.0)

            metrics = tracker.get_performance(ticker="TEST")
            trades = tracker.get_trades(ticker="TEST")

            builder = DashboardBuilder(output_dir=os.path.join(tmp, "dashboard"))
            html_path = builder.build(metrics=metrics, trades=trades)
            assert os.path.exists(html_path)
