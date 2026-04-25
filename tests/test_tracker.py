"""Tests for tradingagents.tracker.tracker."""

import json
import tempfile
import os
import pytest

from tradingagents.tracker.tracker import TradeTracker
from tradingagents.backtest.models import TradeRecord


def _make_config(tmp_dir):
    return {"results_dir": tmp_dir, "persona": "warren_buffett"}


def _make_agent_state():
    return {
        "market_report": "Strong uptrend",
        "sentiment_report": "Bullish sentiment",
        "news_report": "Positive earnings",
        "fundamentals_report": "Revenue growing 20%",
        "investment_debate_state": {
            "bull_history": "Bull: strong moat",
            "bear_history": "Bear: high valuation",
            "judge_decision": "BUY recommended",
        },
        "risk_debate_state": {
            "judge_decision": "Risk acceptable, 5% position",
        },
    }


class TestRecordTrade:
    def test_record_buy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            rec = tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            assert rec.ticker == "005930"
            assert rec.signal == "BUY"
            assert rec.source == "paper"
            assert rec.exit_price is None

    def test_record_persists_to_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            filepath = os.path.join(tmp, "trades", "005930", "trades.json")
            assert os.path.exists(filepath)
            with open(filepath) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["ticker"] == "005930"


class TestClosePosition:
    def test_close_updates_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade(
                ticker="005930", trade_date="2026-04-25", signal="BUY",
                price=58000.0, quantity=100, source="paper",
                agent_state=_make_agent_state(),
            )
            closed = tracker.close_position("005930", "2026-04-28", 61000.0)
            assert closed.exit_price == 61000.0
            assert closed.pnl == pytest.approx(300000.0)
            assert closed.pnl_pct == pytest.approx(5.17, abs=0.1)


class TestGetTrades:
    def test_filter_by_ticker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("NVDA", "2026-04-25", "BUY", 130, 50, "paper", {})
            trades = tracker.get_trades(ticker="005930")
            assert len(trades) == 1
            assert trades[0].ticker == "005930"

    def test_filter_by_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("005930", "2026-04-26", "BUY", 59000, 100, "real", {})
            trades = tracker.get_trades(source="paper")
            assert len(trades) == 1


class TestOpenPositions:
    def test_returns_unclosed_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = TradeTracker(_make_config(tmp))
            tracker.record_trade("005930", "2026-04-25", "BUY", 58000, 100, "paper", {})
            tracker.record_trade("NVDA", "2026-04-25", "BUY", 130, 50, "paper", {})
            tracker.close_position("005930", "2026-04-28", 61000.0)
            open_pos = tracker.get_open_positions()
            assert len(open_pos) == 1
            assert open_pos[0].ticker == "NVDA"
