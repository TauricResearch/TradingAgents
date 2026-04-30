from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, ResearchPlan, TraderAction, TraderProposal
from tradingagents.agents.trader.trader import create_trader
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def _reset_output_language():
    set_config({"output_language": "English"})
    yield
    set_config({"output_language": "English"})


def _korean_instruction() -> str:
    return "Write your entire response in Korean."


def _anti_mixed_script_instruction() -> str:
    return "Do not use words or characters from other writing systems"


def _make_analysis_state():
    return {
        "company_of_interest": "NVDA",
        "market_report": "Market report",
        "sentiment_report": "Sentiment report",
        "news_report": "News report",
        "fundamentals_report": "Fundamentals report",
        "investment_debate_state": {
            "history": "Debate history.",
            "bull_history": "Bull says...",
            "bear_history": "Bear says...",
            "current_response": "Previous response.",
            "judge_decision": "",
            "count": 1,
        },
        "investment_plan": "**Recommendation**: Buy\n\n**Rationale**: Strong setup.\n\n**Strategic Actions**: Build position.",
        "trader_investment_plan": "**Action**: Buy\n\n**Reasoning**: Momentum intact.\n\nFINAL TRANSACTION PROPOSAL: **BUY**",
        "risk_debate_state": {
            "history": "Risk debate history.",
            "aggressive_history": "Aggressive says...",
            "conservative_history": "Conservative says...",
            "neutral_history": "Neutral says...",
            "judge_decision": "",
            "current_aggressive_response": "Aggressive response.",
            "current_conservative_response": "Conservative response.",
            "current_neutral_response": "Neutral response.",
            "count": 1,
            "latest_speaker": "Neutral",
        },
    }


def _capture_prompt_invoke_llm(captured: dict, content: str = "ok"):
    llm = MagicMock()
    llm.invoke.side_effect = lambda prompt: captured.__setitem__("prompt", prompt) or MagicMock(content=content)
    return llm


def _capture_structured_llm(captured: dict, structured_response):
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: captured.__setitem__("prompt", prompt) or structured_response
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.unit
@pytest.mark.parametrize(
    ("factory", "state_key"),
    [
        (create_bull_researcher, "investment_debate_state"),
        (create_bear_researcher, "investment_debate_state"),
        (create_aggressive_debator, "risk_debate_state"),
        (create_conservative_debator, "risk_debate_state"),
        (create_neutral_debator, "risk_debate_state"),
    ],
)
def test_freeform_agent_prompts_include_korean_instruction(factory, state_key):
    set_config({"output_language": "Korean"})
    captured = {}
    llm = _capture_prompt_invoke_llm(captured)
    node = factory(llm)
    result = node(_make_analysis_state())
    assert state_key in result
    assert _korean_instruction() in captured["prompt"]
    assert _anti_mixed_script_instruction() in captured["prompt"]


@pytest.mark.unit
def test_research_manager_prompt_includes_korean_instruction():
    set_config({"output_language": "Korean"})
    captured = {}
    llm = _capture_structured_llm(
        captured,
        ResearchPlan(
            recommendation=PortfolioRating.BUY,
            rationale="근거 요약",
            strategic_actions="비중 확대",
        ),
    )
    node = create_research_manager(llm)
    result = node(_make_analysis_state())
    assert "investment_plan" in result
    assert _korean_instruction() in captured["prompt"]
    assert _anti_mixed_script_instruction() in captured["prompt"]


@pytest.mark.unit
def test_trader_prompt_includes_korean_instruction():
    set_config({"output_language": "Korean"})
    captured = {}
    llm = _capture_structured_llm(
        captured,
        TraderProposal(action=TraderAction.BUY, reasoning="근거 요약"),
    )
    node = create_trader(llm)
    result = node(_make_analysis_state())
    assert "trader_investment_plan" in result
    assert any(_korean_instruction() in message["content"] for message in captured["prompt"])
    assert any(_anti_mixed_script_instruction() in message["content"] for message in captured["prompt"])


@pytest.mark.unit
def test_portfolio_manager_prompt_includes_korean_instruction():
    set_config({"output_language": "Korean"})
    captured = {}
    llm = _capture_structured_llm(
        captured,
        PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="요약",
            investment_thesis="투자 논리",
        ),
    )
    node = create_portfolio_manager(llm)
    result = node(_make_analysis_state())
    assert "final_trade_decision" in result
    assert _korean_instruction() in captured["prompt"]
    assert _anti_mixed_script_instruction() in captured["prompt"]
