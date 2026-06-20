import unittest

import pytest

from tradingagents.graph.propagation import Propagator


@pytest.mark.unit
class PropagatorConstructorTests(unittest.TestCase):
    def test_default_max_recur_limit(self):
        p = Propagator()
        self.assertEqual(p.max_recur_limit, 100)

    def test_custom_max_recur_limit(self):
        p = Propagator(max_recur_limit=50)
        self.assertEqual(p.max_recur_limit, 50)


@pytest.mark.unit
class CreateInitialStateTests(unittest.TestCase):
    def _assert_valid_state(self, state):
        self.assertIn("messages", state)
        self.assertIn("company_of_interest", state)
        self.assertIn("asset_type", state)
        self.assertIn("instrument_context", state)
        self.assertIn("trade_date", state)
        self.assertIn("past_context", state)
        self.assertIn("holdings_context", state)
        self.assertIn("transactions_context", state)
        self.assertIn("investment_debate_state", state)
        self.assertIn("risk_debate_state", state)
        self.assertIn("market_report", state)
        self.assertIn("fundamentals_report", state)
        self.assertIn("sentiment_report", state)
        self.assertIn("news_report", state)
        self.assertIn("governance_report", state)
        self.assertIn("industry_report", state)

    def test_creates_state_with_required_fields(self):
        p = Propagator()
        state = p.create_initial_state(
            company_name="Apple Inc.",
            trade_date="2026-06-20",
        )
        self._assert_valid_state(state)
        self.assertEqual(state["company_of_interest"], "Apple Inc.")
        self.assertEqual(state["trade_date"], "2026-06-20")
        self.assertEqual(state["asset_type"], "stock")
        self.assertEqual(state["messages"], [("human", "Apple Inc.")])

    def test_invest_debate_state_defaults(self):
        p = Propagator()
        state = p.create_initial_state(
            company_name="AAPL", trade_date="2026-06-20"
        )
        ds = state["investment_debate_state"]
        self.assertEqual(ds["count"], 0)
        self.assertEqual(ds["bull_history"], "")
        self.assertEqual(ds["bear_history"], "")
        self.assertEqual(ds["history"], "")
        self.assertEqual(ds["current_response"], "")
        self.assertEqual(ds["judge_decision"], "")

    def test_risk_debate_state_defaults(self):
        p = Propagator()
        state = p.create_initial_state(
            company_name="AAPL", trade_date="2026-06-20"
        )
        rs = state["risk_debate_state"]
        self.assertEqual(rs["count"], 0)
        self.assertEqual(rs["aggressive_history"], "")
        self.assertEqual(rs["conservative_history"], "")
        self.assertEqual(rs["neutral_history"], "")
        self.assertEqual(rs["history"], "")
        self.assertEqual(rs["latest_speaker"], "")
        self.assertEqual(rs["judge_decision"], "")

    def test_asset_type_crypto(self):
        p = Propagator()
        state = p.create_initial_state(
            company_name="BTC", trade_date="2026-06-20", asset_type="crypto"
        )
        self.assertEqual(state["asset_type"], "crypto")

    def test_past_context_and_instrument_context(self):
        p = Propagator()
        state = p.create_initial_state(
            company_name="MSFT",
            trade_date="2026-06-20",
            past_context="Previous decision: Buy",
            instrument_context="Microsoft Corporation (MSFT)",
        )
        self.assertEqual(state["past_context"], "Previous decision: Buy")
        self.assertEqual(
            state["instrument_context"], "Microsoft Corporation (MSFT)"
        )

    def test_holdings_context(self):
        p = Propagator()
        holdings = {"AAPL": {"shares": 100, "avg_cost": 150.0}}
        state = p.create_initial_state(
            company_name="AAPL",
            trade_date="2026-06-20",
            holdings_context=holdings,
        )
        self.assertEqual(state["holdings_context"], holdings)

    def test_transactions_context(self):
        p = Propagator()
        txns = [{"ticker": "AAPL", "action": "buy", "shares": 100}]
        state = p.create_initial_state(
            company_name="AAPL",
            trade_date="2026-06-20",
            transactions_context=txns,
        )
        self.assertEqual(state["transactions_context"], txns)


@pytest.mark.unit
class GetGraphArgsTests(unittest.TestCase):
    def test_returns_default_config(self):
        p = Propagator()
        args = p.get_graph_args()
        self.assertEqual(args["stream_mode"], "values")
        self.assertEqual(args["config"]["recursion_limit"], 100)
        self.assertNotIn("callbacks", args["config"])

    def test_includes_callbacks_when_provided(self):
        p = Propagator()
        cb = ["callback1", "callback2"]
        args = p.get_graph_args(callbacks=cb)
        self.assertEqual(args["config"]["callbacks"], cb)

    def test_passes_recursion_limit_from_constructor(self):
        p = Propagator(max_recur_limit=50)
        args = p.get_graph_args()
        self.assertEqual(args["config"]["recursion_limit"], 50)


if __name__ == "__main__":
    unittest.main()
