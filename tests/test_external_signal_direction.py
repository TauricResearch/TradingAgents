"""TradingAgents#30 -- the external signal's direction is carried as a prior.

Incident: news-gap-ml's sector leg passed {"sector_theme", "sector_direction",
"sector_headline"} as --context; decide.py's formatter only knew the technical
shape, so the passage rendered as "flagged this stock today (unknown signal,
score ?/100)" and the direction never reached any agent. 93 sector-fired
decisions: up -> 43 Hold / 11 Underweight / 0 bullish.

These tests pin, without any LLM call:
  * the sector payload is parsed (theme, headline, direction) and the
    technical payload still is;
  * the direction threads through Propagator -> state;
  * structured mode: direction=up with neutral factors is NOT Underweight
    (the issue's unit-test acceptance criterion), and the prior is bounded;
  * every reasoning agent's *rendered* prompt states the signal, and the
    Trader / Research Manager / PM prompts carry the justify-if-you-disagree
    clause;
  * decide.py reports external_signal_direction + a deterministic
    agrees_with_external_signal.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.agents.managers.decision_model import (
    _EXTERNAL_SIGNAL_PRIOR_WEIGHT,
    compute_rating,
    score_factors,
)
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.schemas import (
    FactorExtraction,
    HoldingRecommendation,
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    render_pm_decision,
)
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.agent_utils import (
    external_signal_prompt_block,
    get_external_signal_direction_from_state,
)
from tradingagents.graph.propagation import Propagator

SECTOR_CONTEXT = "news-gap-ml's sector/theme leg flagged this stock today: GST rate cuts boost FMCG."


def _load_decide():
    path = Path(__file__).parent.parent / "scripts" / "decide.py"
    spec = importlib.util.spec_from_file_location("decide_dir_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _factors(**overrides):
    base = {
        "dated_catalyst_present": True, "catalyst_hours_to_resolution": 4.0,
        "technical_direction": 0.0, "technical_confidence": 0.0,
        "sentiment_direction": 0.0, "sentiment_confidence": 0.0, "risk_flags": [],
    }
    base.update(overrides)
    return FactorExtraction(**base)


# --- decide.py: parsing ------------------------------------------------------

@pytest.mark.unit
class TestParseExternalSignal:
    def setup_method(self):
        self.decide = _load_decide()

    def test_sector_payload_keeps_theme_headline_and_direction(self):
        raw = ('{"sector_theme": "GST rate cuts boost FMCG", "sector_direction": "up", '
               '"sector_headline": "GST Council slashes rates on packaged foods, soaps"}')
        text, direction = self.decide.parse_external_signal(raw)
        assert direction == "up"
        assert "GST rate cuts boost FMCG" in text
        assert "GST Council slashes rates" in text
        assert "sector-wide" in text
        assert "unknown signal" not in text and "score ?/100" not in text  # the old fall-through

    def test_sector_payload_down(self):
        _, direction = self.decide.parse_external_signal('{"sector_theme": "x", "sector_direction": "down"}')
        assert direction == "down"

    def test_sector_payload_with_unknown_direction_has_no_prior(self):
        text, direction = self.decide.parse_external_signal('{"sector_theme": "x", "sector_direction": "sideways"}')
        assert direction == ""
        assert "expected direction" not in text

    def test_technical_payload_maps_side_to_direction(self):
        text, direction = self.decide.parse_external_signal('{"side": "long", "action": "entry", "score": 78.5}')
        assert direction == "up"
        assert "long entry" in text and "score 78.5/100" in text
        _, direction = self.decide.parse_external_signal('{"side": "short", "action": "entry", "score": 40}')
        assert direction == "down"

    def test_technical_payload_without_side_has_no_direction(self):
        text, direction = self.decide.parse_external_signal("{}")
        assert direction == ""
        assert "A separate technical scanner already flagged this stock today" in text

    def test_invalid_json_and_non_object_are_ignored(self):
        assert self.decide.parse_external_signal("not json") == ("", "")
        assert self.decide.parse_external_signal("[1, 2]") == ("", "")

    def test_legacy_formatter_still_returns_passage_only(self):
        assert isinstance(self.decide._format_external_signal_context('{"side": "long"}'), str)


@pytest.mark.unit
class TestAgreement:
    def setup_method(self):
        self.decide = _load_decide()

    @pytest.mark.parametrize("rating, direction, expected", [
        ("Buy", "up", True), ("Overweight", "up", True),
        ("Hold", "up", False), ("Underweight", "up", False), ("Sell", "up", False),
        ("Sell", "down", True), ("Underweight", "down", True),
        ("Hold", "down", False), ("Buy", "down", False),
        ("Buy", "", None), ("Hold", None, None),
    ])
    def test_agrees_with_external_signal(self, rating, direction, expected):
        assert self.decide.agrees_with_external_signal(rating, direction) is expected

    def test_run_decision_threads_direction_and_reports_agreement(self):
        fake_state = {"final_trade_decision": "**Rating**: Underweight\n**Holding Recommendation**: Hold Overnight"}
        with patch.object(self.decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = (fake_state, "Underweight")
            MockGraph.return_value.debate_first_speaker = "bull"
            result = self.decide.run_decision(
                "ITC.NS", "2026-09-04",
                context='{"sector_theme": "GST rate cuts boost FMCG", "sector_direction": "up", "sector_headline": "h"}',
            )
        kwargs = MockGraph.return_value.propagate.call_args.kwargs
        assert kwargs["external_signal_direction"] == "up"
        assert "GST rate cuts boost FMCG" in kwargs["external_signal_context"]
        assert result["external_signal_direction"] == "up"
        assert result["agrees_with_external_signal"] is False  # the ITC short-PE case, now visible

    def test_run_decision_without_context_reports_nulls(self):
        with patch.object(self.decide, "TradingAgentsGraph") as MockGraph:
            MockGraph.return_value.propagate.return_value = ({"final_trade_decision": "x"}, "Hold")
            MockGraph.return_value.debate_first_speaker = "bear"
            result = self.decide.run_decision("WIPRO.NS", "2026-09-04")
        assert MockGraph.return_value.propagate.call_args.kwargs["external_signal_direction"] == ""
        assert result["external_signal_direction"] is None
        assert result["agrees_with_external_signal"] is None


# --- state plumbing -------------------------------------------------------------

@pytest.mark.unit
class TestStateThreading:
    def test_propagator_threads_direction_and_defaults_empty(self):
        assert Propagator().create_initial_state("ITC.NS", "2026-09-04")["external_signal_direction"] == ""
        state = Propagator().create_initial_state("ITC.NS", "2026-09-04", external_signal_context="c",
                                                  external_signal_direction="up")
        assert state["external_signal_direction"] == "up"

    def test_propagator_normalises_garbage_direction(self):
        state = Propagator().create_initial_state("ITC.NS", "2026-09-04", external_signal_direction="bullish")
        assert state["external_signal_direction"] == ""

    def test_direction_getter(self):
        assert get_external_signal_direction_from_state({"external_signal_direction": "down"}) == "down"
        assert get_external_signal_direction_from_state({"external_signal_direction": "x"}) == ""
        assert get_external_signal_direction_from_state({}) == ""

    def test_prompt_block_empty_without_context(self):
        assert external_signal_prompt_block({"external_signal_direction": "up"}) == ""

    def test_prompt_block_states_direction_and_optionally_justification(self):
        state = {"external_signal_context": SECTOR_CONTEXT, "external_signal_direction": "up"}
        plain = external_signal_prompt_block(state)
        assert SECTOR_CONTEXT in plain and "BULLISH (up)" in plain
        assert "must state explicitly" not in plain
        strict = external_signal_prompt_block(state, require_justification=True)
        assert "must state explicitly" in strict and "or is Hold" in strict

    def test_prompt_block_without_direction_has_no_stance_line(self):
        block = external_signal_prompt_block({"external_signal_context": "scanner text"}, require_justification=True)
        assert "scanner text" in block and "Upstream direction" not in block


# --- structured mode: signed prior --------------------------------------------------

@pytest.mark.unit
class TestDecisionModelPrior:
    def test_up_with_neutral_factors_is_not_underweight(self):
        """The issue's acceptance criterion."""
        rating, score, reason = compute_rating(_factors(), external_direction="up")
        assert rating not in (PortfolioRating.UNDERWEIGHT, PortfolioRating.SELL)
        assert rating == PortfolioRating.OVERWEIGHT
        assert score == pytest.approx(_EXTERNAL_SIGNAL_PRIOR_WEIGHT)
        assert "external signal up prior +0.25" in reason

    def test_down_with_neutral_factors_is_underweight(self):
        rating, score, _ = compute_rating(_factors(), external_direction="down")
        assert rating == PortfolioRating.UNDERWEIGHT
        assert score == pytest.approx(-_EXTERNAL_SIGNAL_PRIOR_WEIGHT)

    def test_no_direction_is_unchanged(self):
        assert compute_rating(_factors()) == compute_rating(_factors(), external_direction=None)
        assert compute_rating(_factors())[0] == PortfolioRating.HOLD
        assert compute_rating(_factors(), external_direction="sideways") == compute_rating(_factors())

    def test_prior_is_a_tiebreak_not_an_override(self):
        # Contrary evidence of equal weight cancels it back to Hold...
        rating, score, _ = compute_rating(
            _factors(technical_direction=-0.5, technical_confidence=0.5), external_direction="up")
        assert score == pytest.approx(0.0) and rating == PortfolioRating.HOLD
        # ...and clearly stronger contrary evidence still flips the call
        # (-0.81 + 0.25 = -0.56 -> Sell; the prior only softened it).
        rating, score, _ = compute_rating(
            _factors(technical_direction=-0.9, technical_confidence=0.9), external_direction="up")
        assert score == pytest.approx(-0.56)
        assert rating in (PortfolioRating.UNDERWEIGHT, PortfolioRating.SELL)
        _, unprior_score, _ = compute_rating(_factors(technical_direction=-0.9, technical_confidence=0.9))
        assert score > unprior_score

    def test_aligned_evidence_reinforces_and_clamps(self):
        rating, score, _ = compute_rating(
            _factors(technical_direction=0.9, technical_confidence=0.9), external_direction="up")
        assert rating == PortfolioRating.BUY and score == 1.0

    def test_catalyst_gate_is_not_bypassed_by_prior(self):
        rating, score, reason = compute_rating(_factors(dated_catalyst_present=False), external_direction="up")
        assert rating == PortfolioRating.HOLD and score == 0.0
        assert "No dated catalyst" in reason

    def test_risk_flags_damp_the_prior_too(self):
        _, score, _ = compute_rating(_factors(risk_flags=["a", "b"]), external_direction="up")
        assert score == pytest.approx(_EXTERNAL_SIGNAL_PRIOR_WEIGHT * 0.7)

    def test_score_factors_renders_long_plan_for_up_prior(self):
        plan = score_factors(_factors(), company_name="ITC.NS", external_direction="up")
        assert "**Recommendation**: Overweight" in plan and "long" in plan.lower()


# --- rendered prompts ---------------------------------------------------------------

def _capturing_llm(captured: dict, result):
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: captured.__setitem__("prompt", prompt) or result
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    llm.invoke.side_effect = lambda prompt: captured.__setitem__("prompt", prompt) or MagicMock(content="arg")
    return llm


def _text(prompt) -> str:
    if isinstance(prompt, str):
        return prompt
    return "\n".join(str(m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")) for m in prompt)


_SIGNAL_STATE = {
    "company_of_interest": "ITC.NS",
    "external_signal_context": SECTOR_CONTEXT,
    "external_signal_direction": "up",
    "market_report": "m", "sentiment_report": "s", "news_report": "n", "fundamentals_report": "f",
    "investment_plan": "**Recommendation**: Hold",
    "trader_investment_plan": "tp",
    "investment_debate_state": {"history": "h", "bull_history": "b", "bear_history": "r",
                                "current_response": "", "judge_decision": "", "count": 1},
    "risk_debate_state": {"history": "h", "aggressive_history": "a", "conservative_history": "c",
                          "neutral_history": "n", "current_aggressive_response": "",
                          "current_conservative_response": "", "current_neutral_response": "",
                          "latest_speaker": "Neutral", "count": 1},
}
_PM_RESULT = PortfolioDecision(rating=PortfolioRating.HOLD, executive_summary="x", investment_thesis="y",
                               holding_recommendation=HoldingRecommendation.HOLD_OVERNIGHT, holding_rationale="z")


@pytest.mark.unit
class TestPromptsCarryTheSignal:
    @pytest.mark.parametrize("debate_enabled", [True, False])
    def test_trader_states_signal_and_requires_justification(self, debate_enabled):
        captured = {}
        create_trader(_capturing_llm(captured, TraderProposal(action=TraderAction.HOLD, reasoning="r")),
                      debate_enabled=debate_enabled)(dict(_SIGNAL_STATE))
        text = _text(captured["prompt"])
        assert SECTOR_CONTEXT in text and "BULLISH (up)" in text and "must state explicitly" in text

    def test_portfolio_manager_states_signal_and_names_the_schema_field(self):
        captured = {}
        create_portfolio_manager(_capturing_llm(captured, _PM_RESULT))(dict(_SIGNAL_STATE))
        text = _text(captured["prompt"])
        assert SECTOR_CONTEXT in text and "BULLISH (up)" in text
        assert "external_signal_disagreement_reason" in text

    def test_research_manager_states_signal(self):
        captured = {}
        create_research_manager(_capturing_llm(
            captured, ResearchPlan(recommendation=PortfolioRating.HOLD, rationale="x", strategic_actions="y"),
        ))(dict(_SIGNAL_STATE))
        text = _text(captured["prompt"])
        assert SECTOR_CONTEXT in text and "must state explicitly" in text

    @pytest.mark.parametrize("factory", [create_bull_researcher, create_bear_researcher])
    def test_researchers_see_signal_as_a_resource(self, factory):
        captured = {}
        factory(_capturing_llm(captured, None))(dict(_SIGNAL_STATE))
        assert SECTOR_CONTEXT in _text(captured["prompt"]) and "BULLISH (up)" in _text(captured["prompt"])

    def test_prompts_are_unchanged_without_a_signal(self):
        state = {k: v for k, v in _SIGNAL_STATE.items() if not k.startswith("external_signal")}
        captured = {}
        create_portfolio_manager(_capturing_llm(captured, _PM_RESULT))(state)
        text = _text(captured["prompt"])
        assert "External signal" not in text and "external_signal_disagreement_reason" not in text
        captured = {}
        create_trader(_capturing_llm(captured, TraderProposal(action=TraderAction.HOLD, reasoning="r")))(state)
        assert "External signal" not in _text(captured["prompt"])

    def test_factor_extractor_shows_signal_and_scores_with_prior(self):
        from tradingagents.agents.managers.factor_extractor import create_factor_extractor
        captured = {}
        llm = _capturing_llm(captured, _factors())  # neutral factors, catalyst present
        out = create_factor_extractor(llm)(dict(_SIGNAL_STATE))
        text = _text(captured["prompt"])
        assert SECTOR_CONTEXT in text and "count it towards dated_catalyst_present" in text
        assert "Do NOT fold its direction" in text
        assert "**Recommendation**: Overweight" in out["investment_plan"]  # prior applied, not Underweight


@pytest.mark.unit
class TestPortfolioDecisionSchema:
    def test_disagreement_reason_defaults_none_and_renders_when_set(self):
        assert _PM_RESULT.external_signal_disagreement_reason is None
        assert "External Signal Disagreement" not in render_pm_decision(_PM_RESULT)
        with_reason = _PM_RESULT.model_copy(update={"external_signal_disagreement_reason": "Q1 miss"})
        assert "**External Signal Disagreement**: Q1 miss" in render_pm_decision(with_reason)

    def test_nullish_reason_strings_coerce_to_none(self):
        d = PortfolioDecision(rating=PortfolioRating.BUY, executive_summary="x", investment_thesis="y",
                              holding_recommendation=HoldingRecommendation.HOLD_OVERNIGHT, holding_rationale="z",
                              external_signal_disagreement_reason="N/A")
        assert d.external_signal_disagreement_reason is None
