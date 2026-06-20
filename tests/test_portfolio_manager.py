"""Tests for the Portfolio Manager agent.

Covers:
1. ``_extract_snapshot_close`` — parsing the latest Close from the snapshot
2. ``create_portfolio_manager`` — factory that returns a LangGraph node
3. The portfolio manager node's prompt construction and decision flow
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from tradingagents.agents.managers.portfolio_manager import (
    _extract_snapshot_close,
    create_portfolio_manager,
)


# ---------------------------------------------------------------------------
# _extract_snapshot_close
# ---------------------------------------------------------------------------

SNAPSHOT_WITH_CLOSE = """\
| Field | Value |
|---|---:|
| Open | 150.00 |
| High | 155.00 |
| Low | 149.50 |
| Close | 152.35 |
| Volume | 1234567 |
"""

SNAPSHOT_MISSING_CLOSE = """\
| Field | Value |
|---|---:|
| Open | 150.00 |
| High | 155.00 |
"""

SNAPSHOT_MULTIPLE_CLOSE = """\
| Field | Value |
|---|---:|
| Close | 100.00 |
| Some | other |
| Close | 200.00 |
"""

SNAPSHOT_BAD_CLOSE = """\
| Field | Value |
|---|---:|
| Close | N/A |
"""


@pytest.mark.unit
class ExtractSnapshotCloseTests(unittest.TestCase):
    """_extract_snapshot_close edge cases."""

    def test_returns_none_when_snapshot_is_none(self):
        self.assertIsNone(_extract_snapshot_close(None))

    def test_returns_none_when_snapshot_is_empty_string(self):
        self.assertIsNone(_extract_snapshot_close(""))

    def test_parses_close_correctly(self):
        result = _extract_snapshot_close(SNAPSHOT_WITH_CLOSE)
        self.assertAlmostEqual(result, 152.35)

    def test_returns_none_when_close_row_missing(self):
        self.assertIsNone(_extract_snapshot_close(SNAPSHOT_MISSING_CLOSE))

    def test_uses_first_close_when_multiple_present(self):
        result = _extract_snapshot_close(SNAPSHOT_MULTIPLE_CLOSE)
        self.assertAlmostEqual(result, 100.00)

    def test_returns_none_when_close_value_not_a_number(self):
        self.assertIsNone(_extract_snapshot_close(SNAPSHOT_BAD_CLOSE))

    def test_parses_close_without_decimal(self):
        snapshot = "| Close | 150 |"
        self.assertAlmostEqual(_extract_snapshot_close(snapshot), 150.0)

    def test_handles_whitespace_variations(self):
        snapshot = "|Close|152.35|"
        self.assertAlmostEqual(_extract_snapshot_close(snapshot), 152.35)

    def test_returns_none_on_value_error(self):
        snapshot = "| Close | 1e999 |"
        self.assertIsNone(_extract_snapshot_close(snapshot))


# ---------------------------------------------------------------------------
# create_portfolio_manager
# ---------------------------------------------------------------------------


def _make_state(**overrides):
    """Build a minimal state dict suitable for the portfolio manager node."""
    default_risk = {
        "history": "Bull argued X; Bear countered Y.",
        "aggressive_history": "",
        "conservative_history": "",
        "neutral_history": "",
        "latest_speaker": "Neutral",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "Neutral suggests Z.",
        "count": 2,
    }
    state = {
        "risk_debate_state": dict(default_risk),
        "investment_plan": "Buy: strong fundamentals",
        "trader_investment_plan": "Buy 100 shares at 150.00, stop at 142.00",
        "company_of_interest": "AAPL",
        "trade_date": "2026-06-20",
        "instrument_context": "The instrument to analyze is `AAPL`.",
        "past_context": "",
        "holdings_context": {},
        "transactions_context": [],
    }
    state.update(overrides)
    return state


def _make_mock_llm(response: str = "mock response"):
    """Return a mock LLM whose ``.invoke()`` returns a fake response."""
    llm = MagicMock()
    llm.invoke.return_value.content = response
    return llm


SAMPLE_SNAPSHOT = """\
| Field | Value |
|---|---:|
| Close | 152.35 |
"""


@pytest.mark.unit
class CreatePortfolioManagerTests(unittest.TestCase):
    """create_portfolio_manager factory."""

    def test_returns_callable(self):
        node = create_portfolio_manager(_make_mock_llm())
        self.assertTrue(callable(node))

    def test_returns_dict_from_node(self):
        llm = _make_mock_llm()
        node = create_portfolio_manager(llm)
        state = _make_state()
        result = node(state)
        self.assertIsInstance(result, dict)
        self.assertIn("final_trade_decision", result)
        self.assertIn("risk_debate_state", result)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_prompt_contains_instrument_context(
        self,
        mock_get_ctx,
        mock_build_snapshot,
        mock_bind,
        mock_invoke,
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        llm = _make_mock_llm()
        node = create_portfolio_manager(llm)
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("AAPL", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_prompt_includes_research_plan(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Buy: strong fundamentals", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_prompt_includes_trader_proposal(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Buy 100 shares at 150.00", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_prompt_includes_risk_debate_history(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Bull argued X; Bear countered Y.", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_prompt_includes_snapshot(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Verified Market Snapshot", prompt)
        self.assertIn("152.35", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        side_effect=RuntimeError("API error"),
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_snapshot_failure_uses_fallback_text(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state(trade_date="2026-06-20"))
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Verified market data is unavailable", prompt)
        self.assertIn("2026-06-20", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=None,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_snapshot_none_uses_fallback_text(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state(trade_date="2026-06-20"))
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Verified market data is unavailable", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_past_context_included_when_present(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state(past_context="Previous trade lost 5%."))
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Previous trade lost 5%", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_past_context_omitted_when_empty(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state(past_context=""))
        prompt = mock_invoke.call_args[0][2]
        self.assertNotIn("prior decisions", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_risk_debate_state_preserved_in_output(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        result = node(_make_state())
        rds = result["risk_debate_state"]
        self.assertEqual(rds["judge_decision"], "**Rating**: Hold\n")
        self.assertEqual(rds["latest_speaker"], "Judge")
        self.assertEqual(rds["count"], 2)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_holdings_context_included_when_present(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        holdings = {
            "AAPL": {"ticker": "AAPL", "shares": 100, "avg_cost": 150.0, "market_price": 165.0},
        }

        with (
            patch("tradingagents.portfolio.Holding") as MockHolding,
            patch("tradingagents.portfolio.Portfolio") as MockPortfolio,
            patch(
                "tradingagents.portfolio.build_pm_prompt",
                return_value="Current position details.",
            ),
        ):
            MockHolding.from_dict.return_value = MagicMock()
            MockPortfolio.return_value = MagicMock()
            node = create_portfolio_manager(_make_mock_llm())
            node(_make_state(holdings_context=holdings))

        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Current position", prompt)
        self.assertIn("Current Position", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_holdings_context_omitted_when_empty(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state(holdings_context={}))
        prompt = mock_invoke.call_args[0][2]
        self.assertNotIn("Current Position", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_output_contains_final_trade_decision(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n**Executive Summary**: No action.\n"
        node = create_portfolio_manager(_make_mock_llm())
        result = node(_make_state())
        self.assertEqual(
            result["final_trade_decision"],
            "**Rating**: Hold\n**Executive Summary**: No action.\n",
        )

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_bind_structured_called_with_portfolio_decision(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        from tradingagents.agents.schemas import PortfolioDecision

        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        mock_bind.assert_called_once()
        args, _ = mock_bind.call_args
        self.assertIs(args[1], PortfolioDecision)
        self.assertEqual(args[2], "Portfolio Manager")

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_invoke_called_with_correct_arguments(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        from tradingagents.agents.schemas import render_pm_decision

        mock_structured_llm = MagicMock()
        mock_bind.return_value = mock_structured_llm
        mock_invoke.return_value = "**Rating**: Hold\n"

        plain_llm = _make_mock_llm()
        node = create_portfolio_manager(plain_llm)
        node(_make_state())

        mock_invoke.assert_called_once()
        args = mock_invoke.call_args
        self.assertIs(args[0][0], mock_structured_llm)
        self.assertIs(args[0][1], plain_llm)
        self.assertIs(args[0][3], render_pm_decision)
        self.assertEqual(args[0][4], "Portfolio Manager")


@pytest.mark.unit
class PortfolioManagerEndToEndTests(unittest.TestCase):
    """Higher-level integration tests with mocked LLM responses."""

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_rating_scale_in_prompt(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        for rating in ("**Buy**", "**Overweight**", "**Hold**", "**Underweight**", "**Sell**"):
            self.assertIn(rating, prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_decision_requirements_in_prompt(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"
        node = create_portfolio_manager(_make_mock_llm())
        node(_make_state())
        prompt = mock_invoke.call_args[0][2]
        self.assertIn("Decision Requirements", prompt)
        self.assertIn("25%", prompt)

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured", return_value=None)
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_works_when_structured_output_unavailable(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "Free-text fallback response."
        node = create_portfolio_manager(_make_mock_llm())
        result = node(_make_state())
        self.assertEqual(result["final_trade_decision"], "Free-text fallback response.")

    @patch("tradingagents.agents.managers.portfolio_manager.invoke_structured_or_freetext")
    @patch("tradingagents.agents.managers.portfolio_manager.bind_structured")
    @patch(
        "tradingagents.agents.managers.portfolio_manager.build_verified_market_snapshot",
        return_value=SAMPLE_SNAPSHOT,
    )
    @patch(
        "tradingagents.agents.managers.portfolio_manager.get_instrument_context_from_state",
        return_value="The instrument to analyze is `AAPL`.",
    )
    def test_language_instruction_appended_when_non_english(
        self, mock_get_ctx, mock_build_snapshot, mock_bind, mock_invoke
    ):
        mock_invoke.return_value = "**Rating**: Hold\n"

        with patch(
            "tradingagents.agents.managers.portfolio_manager.get_language_instruction",
            return_value=" Write your entire response in 中文.",
        ):
            node = create_portfolio_manager(_make_mock_llm())
            node(_make_state())

        prompt = mock_invoke.call_args[0][2]
        self.assertIn("中文", prompt)


if __name__ == "__main__":
    unittest.main()
