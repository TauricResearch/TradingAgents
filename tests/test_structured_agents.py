"""Tests for structured-output agents (Trader and Research Manager).

The Portfolio Manager has its own coverage in tests/test_memory_log.py
(which exercises the full memory-log → PM injection cycle).  This file
covers the parallel schemas, render functions, and graceful-fallback
behavior we added for the Trader and Research Manager so all three
decision-making agents share the same shape.
"""

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.schemas import (
    PortfolioRating,
    ResearchPlan,
    SentimentBand,
    SentimentReport,
    TraderAction,
    TraderProposal,
    render_research_plan,
    render_sentiment_report,
    render_trader_proposal,
)
from tradingagents.agents.trader.trader import create_trader


# ---------------------------------------------------------------------------
# Render functions
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderTraderProposal:
    def test_minimal_required_fields(self):
        p = TraderProposal(action=TraderAction.HOLD, reasoning="Balanced setup; no edge.")
        md = render_trader_proposal(p)
        assert "**Action**: Hold" in md
        assert "**Reasoning**: Balanced setup; no edge." in md
        # The trailing FINAL TRANSACTION PROPOSAL line is preserved for the
        # analyst stop-signal text and any external code that greps for it.
        assert "FINAL TRANSACTION PROPOSAL: **HOLD**" in md

    def test_optional_fields_included_when_present(self):
        p = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong technicals + fundamentals.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        md = render_trader_proposal(p)
        assert "**Action**: Buy" in md
        assert "**Entry Price**: 189.5" in md
        assert "**Stop Loss**: 178.0" in md
        assert "**Position Sizing**: 6% of portfolio" in md
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in md

    def test_optional_fields_omitted_when_absent(self):
        p = TraderProposal(action=TraderAction.SELL, reasoning="Guidance cut.")
        md = render_trader_proposal(p)
        assert "Entry Price" not in md
        assert "Stop Loss" not in md
        assert "Position Sizing" not in md
        assert "FINAL TRANSACTION PROPOSAL: **SELL**" in md


@pytest.mark.unit
class TestRenderResearchPlan:
    def test_required_fields(self):
        p = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case carried; tailwinds intact.",
            strategic_actions="Build position over two weeks; cap at 5%.",
        )
        md = render_research_plan(p)
        assert "**Recommendation**: Overweight" in md
        assert "**Rationale**: Bull case carried" in md
        assert "**Strategic Actions**: Build position" in md

    def test_all_5_tier_ratings_render(self):
        for rating in PortfolioRating:
            p = ResearchPlan(
                recommendation=rating,
                rationale="r",
                strategic_actions="s",
            )
            md = render_research_plan(p)
            assert f"**Recommendation**: {rating.value}" in md


# ---------------------------------------------------------------------------
# Trader agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_trader_state():
    return {
        "company_of_interest": "NVDA",
        "investment_plan": "**Recommendation**: Buy\n**Rationale**: ...\n**Strategic Actions**: ...",
    }


def _structured_trader_llm(captured: dict, proposal: TraderProposal | None = None):
    """Build a MagicMock LLM whose with_structured_output binding captures the
    prompt and returns a real TraderProposal so render_trader_proposal works.
    """
    if proposal is None:
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="Strong setup.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or proposal
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestTraderAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        proposal = TraderProposal(
            action=TraderAction.BUY,
            reasoning="AI capex cycle intact; institutional flows constructive.",
            entry_price=189.5,
            stop_loss=178.0,
            position_sizing="6% of portfolio",
        )
        llm = _structured_trader_llm(captured, proposal)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        plan = result["trader_investment_plan"]
        assert "**Action**: Buy" in plan
        assert "**Entry Price**: 189.5" in plan
        assert "FINAL TRANSACTION PROPOSAL: **BUY**" in plan
        # The same rendered markdown is also added to messages for downstream agents.
        assert plan in result["messages"][0].content

    def test_prompt_includes_investment_plan(self):
        captured = {}
        llm = _structured_trader_llm(captured)
        trader = create_trader(llm)
        trader(_make_trader_state())
        # The investment plan is in the user message of the captured prompt.
        prompt = captured["prompt"]
        assert any("Proposed Investment Plan" in m["content"] for m in prompt)

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = (
            "**Action**: Sell\n\nGuidance cut hits margins.\n\n"
            "FINAL TRANSACTION PROPOSAL: **SELL**"
        )
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        trader = create_trader(llm)
        result = trader(_make_trader_state())
        assert result["trader_investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# Research Manager agent: structured happy path + fallback
# ---------------------------------------------------------------------------


def _make_rm_state():
    return {
        "company_of_interest": "NVDA",
        "investment_debate_state": {
            "history": "Bull and bear arguments here.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
    }


def _structured_rm_llm(captured: dict, plan: ResearchPlan | None = None):
    if plan is None:
        plan = ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="Balanced view across both sides.",
            strategic_actions="Hold current position; reassess after earnings.",
        )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or plan
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
class TestResearchManagerAgent:
    def test_structured_path_produces_rendered_markdown(self):
        captured = {}
        plan = ResearchPlan(
            recommendation=PortfolioRating.OVERWEIGHT,
            rationale="Bull case is stronger; AI tailwind intact.",
            strategic_actions="Build position gradually over two weeks.",
        )
        llm = _structured_rm_llm(captured, plan)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        ip = result["investment_plan"]
        assert "**Recommendation**: Overweight" in ip
        assert "**Rationale**: Bull case" in ip
        assert "**Strategic Actions**: Build position" in ip

    def test_prompt_uses_5_tier_rating_scale(self):
        """The RM prompt must list all five tiers so the schema enum matches user expectations."""
        captured = {}
        llm = _structured_rm_llm(captured)
        rm = create_research_manager(llm)
        rm(_make_rm_state())
        prompt = captured["prompt"]
        for tier in ("Buy", "Overweight", "Hold", "Underweight", "Sell"):
            assert f"**{tier}**" in prompt, f"missing {tier} in prompt"

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        plain_response = "**Recommendation**: Sell\n\n**Rationale**: ...\n\n**Strategic Actions**: ..."
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("provider unsupported")
        llm.invoke.return_value = MagicMock(content=plain_response)
        rm = create_research_manager(llm)
        result = rm(_make_rm_state())
        assert result["investment_plan"] == plain_response


# ---------------------------------------------------------------------------
# SentimentReport schema and render
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRenderSentimentReport:
    def test_required_fields_present(self):
        r = SentimentReport(
            overall_score=7.2,
            overall_band=SentimentBand.BULLISH,
            confidence="high",
            narrative="TSLA sentiment is strongly positive driven by retail enthusiasm.",
        )
        md = render_sentiment_report(r)
        assert "**Overall Sentiment:** **Bullish**" in md
        assert "Score: 7.2/10" in md
        assert "Confidence: high" in md
        assert "TSLA sentiment is strongly positive" in md

    def test_score_formatted_to_one_decimal(self):
        r = SentimentReport(
            overall_score=6.0,
            overall_band=SentimentBand.MILDLY_BULLISH,
            confidence="medium",
            narrative="Mixed signals.",
        )
        md = render_sentiment_report(r)
        assert "6.0/10" in md

    def test_all_bands_render(self):
        for band in SentimentBand:
            r = SentimentReport(
                overall_score=5.0,
                overall_band=band,
                confidence="low",
                narrative="Test.",
            )
            md = render_sentiment_report(r)
            assert band.value in md

    def test_narrative_preserved_intact(self):
        narrative = "Line one.\n\nLine two.\n\n| Col | Val |\n|-----|-----|\n| A   | B   |"
        r = SentimentReport(
            overall_score=4.5,
            overall_band=SentimentBand.NEUTRAL,
            confidence="medium",
            narrative=narrative,
        )
        md = render_sentiment_report(r)
        assert narrative in md

    def test_score_bounds(self):
        import pytest as _pytest
        from pydantic import ValidationError
        with _pytest.raises(ValidationError):
            SentimentReport(
                overall_score=11.0,
                overall_band=SentimentBand.BULLISH,
                confidence="high",
                narrative="Out of range.",
            )
        with _pytest.raises(ValidationError):
            SentimentReport(
                overall_score=-1.0,
                overall_band=SentimentBand.BEARISH,
                confidence="low",
                narrative="Out of range.",
            )


# ---------------------------------------------------------------------------
# Sentiment Analyst node
# ---------------------------------------------------------------------------


def _make_analyst_state():
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content="Analyze TSLA sentiment.")],
        "company_of_interest": "TSLA",
        "trade_date": "2024-01-15",
    }


def _make_analyst_llm(structured_result):
    """LLM mock for the sentiment analyst.

    The analyst uses format_messages then invoke_structured_or_freetext, which
    calls structured_llm.invoke(formatted_messages) directly.
    """
    llm = MagicMock()
    llm.with_structured_output.return_value.invoke.return_value = structured_result
    return llm


@pytest.mark.unit
class TestSentimentAnalystStructured:
    def test_structured_output_populates_sentiment_report(self):
        structured = SentimentReport(
            overall_score=7.2,
            overall_band=SentimentBand.BULLISH,
            confidence="high",
            narrative="Retail very bullish on TSLA this week.",
        )
        llm = _make_analyst_llm(structured)
        analyst = create_sentiment_analyst(llm)
        result = analyst(_make_analyst_state())
        assert "Score: 7.2/10" in result["sentiment_report"]
        assert "Bullish" in result["sentiment_report"]
        assert "Retail very bullish" in result["sentiment_report"]

    def test_sentiment_report_in_messages(self):
        """The rendered report should also appear in the messages state."""
        structured = SentimentReport(
            overall_score=5.0,
            overall_band=SentimentBand.NEUTRAL,
            confidence="medium",
            narrative="Mixed signals this week.",
        )
        llm = _make_analyst_llm(structured)
        analyst = create_sentiment_analyst(llm)
        result = analyst(_make_analyst_state())
        assert result["messages"][-1].content == result["sentiment_report"]

    def test_falls_back_to_freetext_when_structured_unavailable(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("unsupported")
        llm.invoke.return_value = MagicMock(content="Raw prose fallback report.")
        analyst = create_sentiment_analyst(llm)
        result = analyst(_make_analyst_state())
        assert "Raw prose fallback report." in result["sentiment_report"]
