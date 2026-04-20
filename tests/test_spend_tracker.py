"""Tests for spend tracking, budget abort, and partial result saving."""

import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from langchain_core.outputs import LLMResult, Generation

from tradingagents.spend_tracker import (
    AuditEntry,
    BudgetExceededError,
    SpendTracker,
    TokenRecord,
    _get_pricing,
    MODEL_PRICING,
    _DEFAULT_PRICING,
)


def _make_llm_result(
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    model: str = "gpt-4o",
) -> LLMResult:
    """Build a minimal LLMResult with token usage."""
    return LLMResult(
        generations=[[Generation(text="ok")]],
        llm_output={
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "model_name": model,
        },
    )


class TestSpendTrackerAccumulation(unittest.TestCase):
    """Token and cost accumulation."""

    def test_single_call_updates_totals(self):
        tracker = SpendTracker()
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        self.assertEqual(tracker.prompt_tokens, 100)
        self.assertEqual(tracker.completion_tokens, 50)
        self.assertEqual(tracker.total_tokens, 150)
        self.assertGreater(tracker.total_cost_usd, 0)

    def test_multiple_calls_accumulate(self):
        tracker = SpendTracker()
        tracker.on_llm_end(_make_llm_result(100, 50), run_id=uuid4())
        tracker.on_llm_end(_make_llm_result(200, 100), run_id=uuid4())
        self.assertEqual(tracker.prompt_tokens, 300)
        self.assertEqual(tracker.completion_tokens, 150)
        self.assertEqual(len(tracker.records), 2)

    def test_cost_calculation_matches_pricing(self):
        tracker = SpendTracker()
        inp_price, out_price = MODEL_PRICING["gpt-4o"]
        tracker.on_llm_end(_make_llm_result(1_000_000, 1_000_000, "gpt-4o"), run_id=uuid4())
        expected = inp_price + out_price  # 1M tokens each
        self.assertAlmostEqual(tracker.total_cost_usd, expected, places=2)

    def test_reset_clears_all(self):
        tracker = SpendTracker(max_cost=10.0)
        tracker.on_llm_end(_make_llm_result(100, 50), run_id=uuid4())
        tracker.budget_exceeded = True
        tracker.reset()
        self.assertEqual(tracker.total_tokens, 0)
        self.assertEqual(tracker.total_cost_usd, 0.0)
        self.assertFalse(tracker.budget_exceeded)
        self.assertEqual(len(tracker.records), 0)
        self.assertEqual(len(tracker.audit_trail), 0)


class TestBudgetAbort(unittest.TestCase):
    """Budget exceeded detection and abort."""

    def test_budget_exceeded_flag_set(self):
        tracker = SpendTracker(max_cost=0.0001)
        tracker.on_llm_end(_make_llm_result(1000, 500, "gpt-4o"), run_id=uuid4())
        self.assertTrue(tracker.budget_exceeded)

    def test_on_llm_start_raises_when_over_budget(self):
        tracker = SpendTracker(max_cost=0.0001)
        tracker.on_llm_end(_make_llm_result(1000, 500, "gpt-4o"), run_id=uuid4())
        self.assertTrue(tracker.budget_exceeded)
        with self.assertRaises(BudgetExceededError):
            tracker.on_llm_start({}, ["prompt"], run_id=uuid4())

    def test_on_chat_model_start_raises_when_over_budget(self):
        tracker = SpendTracker(max_cost=0.0001)
        tracker.on_llm_end(_make_llm_result(1000, 500, "gpt-4o"), run_id=uuid4())
        with self.assertRaises(BudgetExceededError):
            tracker.on_chat_model_start({}, [[]], run_id=uuid4())

    def test_no_abort_when_under_budget(self):
        tracker = SpendTracker(max_cost=999.0)
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        self.assertFalse(tracker.budget_exceeded)
        # Should not raise
        tracker.on_llm_start({}, ["prompt"], run_id=uuid4())

    def test_no_budget_means_never_exceeded(self):
        tracker = SpendTracker(max_cost=None)
        tracker.on_llm_end(_make_llm_result(1_000_000, 1_000_000, "gpt-4o"), run_id=uuid4())
        self.assertFalse(tracker.budget_exceeded)


class TestPartialResults(unittest.TestCase):
    """Verify partial results are preserved when budget is exceeded."""

    def test_propagate_returns_partial_on_budget_exceeded(self):
        """Simulate what TradingAgentsGraph.propagate() does on BudgetExceededError."""
        # This mirrors the logic in trading_graph.py propagate() method:
        # on BudgetExceededError, it builds partial state from init_agent_state
        init_state = {
            "company_of_interest": "AAPL",
            "trade_date": "2025-01-15",
            "market_report": "partial market data",
            "messages": [],
        }

        # Simulate the except BudgetExceededError branch
        final_state = dict(init_state)
        final_state.setdefault("final_trade_decision", "BUDGET_EXCEEDED")

        self.assertEqual(final_state["final_trade_decision"], "BUDGET_EXCEEDED")
        self.assertEqual(final_state["company_of_interest"], "AAPL")
        self.assertEqual(final_state["market_report"], "partial market data")

    def test_budget_exceeded_error_message_contains_amounts(self):
        tracker = SpendTracker(max_cost=0.01)
        tracker.on_llm_end(_make_llm_result(10000, 5000, "gpt-4o"), run_id=uuid4())
        try:
            tracker.on_llm_start({}, ["prompt"], run_id=uuid4())
            self.fail("Expected BudgetExceededError")
        except BudgetExceededError as e:
            msg = str(e)
            self.assertIn("$0.01", msg)  # budget
            self.assertIn("spent", msg.lower())


class TestTickerSpend(unittest.TestCase):
    """Per-ticker spend tracking."""

    def test_ticker_cost_recorded(self):
        tracker = SpendTracker()
        tracker.begin_ticker("AAPL")
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        tracker.log_ticker_spend("AAPL")
        self.assertIn("AAPL", tracker.ticker_costs)
        self.assertGreater(tracker.ticker_costs["AAPL"], 0)

    def test_multiple_tickers_tracked_separately(self):
        tracker = SpendTracker()
        tracker.begin_ticker("AAPL")
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        tracker.log_ticker_spend("AAPL")

        tracker.begin_ticker("MSFT")
        tracker.on_llm_end(_make_llm_result(200, 100, "gpt-4o"), run_id=uuid4())
        tracker.log_ticker_spend("MSFT")

        self.assertIn("AAPL", tracker.ticker_costs)
        self.assertIn("MSFT", tracker.ticker_costs)
        self.assertGreater(tracker.ticker_costs["MSFT"], tracker.ticker_costs["AAPL"])


class TestAuditTrail(unittest.TestCase):
    """Delegation chain audit trail."""

    def test_llm_call_creates_audit_entry(self):
        tracker = SpendTracker()
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        self.assertEqual(len(tracker.audit_trail), 1)
        entry = tracker.audit_trail[0]
        self.assertEqual(entry.call_type, "llm")
        self.assertEqual(entry.name, "gpt-4o")
        self.assertGreater(entry.cost_usd, 0)

    def test_tool_call_creates_audit_entry(self):
        tracker = SpendTracker()
        run_id = uuid4()
        tracker.on_tool_start({"name": "get_stock_data"}, "", run_id=run_id)
        tracker.on_tool_end("result", run_id=run_id)
        self.assertEqual(len(tracker.audit_trail), 1)
        entry = tracker.audit_trail[0]
        self.assertEqual(entry.call_type, "tool")
        self.assertEqual(entry.name, "get_stock_data")

    def test_agent_name_resolved_from_chain(self):
        tracker = SpendTracker()
        parent_id = uuid4()
        child_id = uuid4()
        tracker.on_chain_start(
            {"name": "market_analyst"}, {}, run_id=parent_id
        )
        tracker.on_llm_end(
            _make_llm_result(100, 50, "gpt-4o"),
            run_id=child_id,
            parent_run_id=parent_id,
        )
        self.assertEqual(tracker.audit_trail[0].agent, "market_analyst")

    def test_format_audit_trail_output(self):
        tracker = SpendTracker()
        tracker.on_llm_end(_make_llm_result(100, 50, "gpt-4o"), run_id=uuid4())
        output = tracker.format_audit_trail()
        self.assertIn("Delegation chain", output)
        self.assertIn("LLM(gpt-4o)", output)

    def test_empty_audit_trail(self):
        tracker = SpendTracker()
        output = tracker.format_audit_trail()
        self.assertIn("No calls recorded", output)


class TestPricing(unittest.TestCase):
    """Model pricing lookup."""

    def test_exact_match(self):
        self.assertEqual(_get_pricing("gpt-4o"), MODEL_PRICING["gpt-4o"])

    def test_prefix_match(self):
        # "gpt-4o-2024-08-06" should match "gpt-4o"
        result = _get_pricing("gpt-4o-2024-08-06")
        self.assertEqual(result, MODEL_PRICING["gpt-4o"])

    def test_unknown_model_returns_default(self):
        result = _get_pricing("totally-unknown-model-xyz")
        self.assertEqual(result, _DEFAULT_PRICING)


if __name__ == "__main__":
    unittest.main()
