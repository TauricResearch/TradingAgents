"""Tests for the Propagator class (graph state initialization and config)."""

import pytest

from tradingagents.graph.propagation import Propagator


@pytest.mark.unit
class TestCreateInitialState:
    def test_basic_state_shape(self):
        p = Propagator()
        state = p.create_initial_state("AAPL", "2026-01-15")
        assert state["company_of_interest"] == "AAPL"
        assert state["trade_date"] == "2026-01-15"
        assert state["asset_type"] == "stock"
        assert state["instrument_context"] == ""
        assert state["past_context"] == ""

    def test_crypto_asset_type(self):
        p = Propagator()
        state = p.create_initial_state("BTC-USD", "2026-01-15", asset_type="crypto")
        assert state["asset_type"] == "crypto"

    def test_with_past_context(self):
        p = Propagator()
        state = p.create_initial_state("NVDA", "2026-01-15", past_context="Prior decision: Hold")
        assert state["past_context"] == "Prior decision: Hold"

    def test_with_instrument_context(self):
        p = Propagator()
        ctx = "The instrument to analyze is `NVDA`. Company: NVIDIA Corp."
        state = p.create_initial_state("NVDA", "2026-01-15", instrument_context=ctx)
        assert state["instrument_context"] == ctx

    def test_investment_debate_state_initialized(self):
        p = Propagator()
        state = p.create_initial_state("AAPL", "2026-01-15")
        ids = state["investment_debate_state"]
        assert ids["bull_history"] == ""
        assert ids["bear_history"] == ""
        assert ids["history"] == ""
        assert ids["current_response"] == ""
        assert ids["judge_decision"] == ""
        assert ids["count"] == 0

    def test_risk_debate_state_initialized(self):
        p = Propagator()
        state = p.create_initial_state("AAPL", "2026-01-15")
        rds = state["risk_debate_state"]
        assert rds["aggressive_history"] == ""
        assert rds["conservative_history"] == ""
        assert rds["neutral_history"] == ""
        assert rds["history"] == ""
        assert rds["latest_speaker"] == ""
        assert rds["current_aggressive_response"] == ""
        assert rds["current_conservative_response"] == ""
        assert rds["current_neutral_response"] == ""
        assert rds["judge_decision"] == ""
        assert rds["count"] == 0

    def test_report_fields_empty(self):
        p = Propagator()
        state = p.create_initial_state("AAPL", "2026-01-15")
        assert state["market_report"] == ""
        assert state["fundamentals_report"] == ""
        assert state["sentiment_report"] == ""
        assert state["news_report"] == ""

    def test_messages_contains_human_message(self):
        p = Propagator()
        state = p.create_initial_state("TSLA", "2026-06-01")
        assert state["messages"] == [("human", "TSLA")]

    def test_trade_date_coerced_to_string(self):
        p = Propagator()
        state = p.create_initial_state("AAPL", 20260115)
        assert state["trade_date"] == "20260115"
        assert isinstance(state["trade_date"], str)


@pytest.mark.unit
class TestGetGraphArgs:
    def test_default_args(self):
        p = Propagator()
        args = p.get_graph_args()
        assert args["stream_mode"] == "values"
        assert args["config"]["recursion_limit"] == 100

    def test_custom_recursion_limit(self):
        p = Propagator(max_recur_limit=50)
        args = p.get_graph_args()
        assert args["config"]["recursion_limit"] == 50

    def test_with_callbacks(self):
        cb = [lambda x: x]
        p = Propagator()
        args = p.get_graph_args(callbacks=cb)
        assert args["config"]["callbacks"] is cb

    def test_without_callbacks(self):
        p = Propagator()
        args = p.get_graph_args()
        assert "callbacks" not in args["config"]

    def test_without_callbacks_none(self):
        p = Propagator()
        args = p.get_graph_args(callbacks=None)
        assert "callbacks" not in args["config"]

    def test_without_callbacks_empty(self):
        p = Propagator()
        args = p.get_graph_args(callbacks=[])
        assert "callbacks" not in args["config"]
