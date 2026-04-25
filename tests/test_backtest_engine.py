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

"""Tests for tradingagents.backtest.engine."""

from unittest.mock import MagicMock, patch
import pytest

from tradingagents.backtest.engine import BacktestEngine
from tradingagents.backtest.models import TradeRecord, BacktestResult
from tradingagents.default_config import DEFAULT_CONFIG


def _make_config():
    config = DEFAULT_CONFIG.copy()
    config["results_dir"] = "/tmp/test_backtest_results"
    return config


def _mock_graph_propagate(ticker, date):
    state = {
        "company_of_interest": ticker,
        "trade_date": date,
        "market_report": "Mock market report",
        "sentiment_report": "Mock sentiment",
        "news_report": "Mock news",
        "fundamentals_report": "Mock fundamentals",
        "investment_debate_state": {
            "bull_history": "Bull case",
            "bear_history": "Bear case",
            "judge_decision": "BUY recommended",
        },
        "risk_debate_state": {
            "judge_decision": "Risk acceptable",
        },
        "final_trade_decision": "FINAL TRANSACTION PROPOSAL: **BUY**",
    }
    return state, "BUY"


class TestRebalanceDates:
    def test_monthly_dates(self):
        engine = BacktestEngine(_make_config())
        dates = engine._generate_rebalance_dates("2024-04-01", "2024-07-01", "monthly")
        assert len(dates) >= 3
        assert dates[0].month == 4

    def test_weekly_dates(self):
        engine = BacktestEngine(_make_config())
        dates = engine._generate_rebalance_dates("2024-04-01", "2024-05-01", "weekly")
        assert len(dates) >= 4


class TestBacktestEngine:
    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_run_returns_backtest_result(self, mock_yf, mock_graph_cls):
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = _mock_graph_propagate
        mock_graph_cls.return_value = mock_graph

        engine = BacktestEngine(_make_config())
        result = engine.run(
            ticker="NVDA",
            start_date="2024-04-01",
            end_date="2024-07-01",
            rebalance_freq="monthly",
            benchmark="SPY",
            initial_capital=100_000.0,
        )
        assert isinstance(result, BacktestResult)
        assert result.ticker == "NVDA"
        assert result.metrics.total_trades >= 0

    @patch("tradingagents.backtest.engine.TradingAgentsGraph")
    @patch("tradingagents.backtest.engine.yf")
    def test_signals_cached(self, mock_yf, mock_graph_cls):
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = MagicMock(return_value=MagicMock(
            iloc=MagicMock(__getitem__=MagicMock(return_value=100.0))
        ))
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        mock_graph = MagicMock()
        mock_graph.propagate.side_effect = _mock_graph_propagate
        mock_graph_cls.return_value = mock_graph

        engine = BacktestEngine(_make_config())
        result = engine.run(
            ticker="NVDA",
            start_date="2024-04-01",
            end_date="2024-06-01",
            rebalance_freq="monthly",
            benchmark="SPY",
            initial_capital=100_000.0,
            save_signals=True,
        )
        assert engine._signal_cache is not None
