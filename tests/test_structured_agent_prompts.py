"""Agents on the schema-only structured-output path must not invite tool calls (#1130).

`with_structured_output` binds exactly one tool (the schema). A prompt that
primes tool use makes models emit an unknown `web_search` call, which discards
the structured attempt and forces a free-text retry — an extra LLM round trip
and the loss of typed output.

These assert the constraint reaches the *rendered* prompt each agent actually
sends, not merely that the constant is referenced in the module.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

import tradingagents.agents.analysts.sentiment_analyst as sentiment
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.trader.trader import create_trader
from tradingagents.agents.utils.structured import NO_EXTERNAL_TOOLS


def _capturing_llm(captured: dict, result):
    """LLM whose structured binding records the prompt it was handed."""
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: captured.__setitem__("prompt", prompt) or result
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _prompt_text(prompt) -> str:
    """Flatten a captured prompt (str, message list, or objects) to text."""
    if isinstance(prompt, str):
        return prompt
    parts = []
    for m in prompt:
        parts.append(m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))
    return "\n".join(str(p) for p in parts)


def _message_content(prompt, role):
    return next(message["content"] for message in prompt if message["role"] == role)


def _assert_stable_split(factory, first_state, second_state, result, dynamic_values):
    prompts = []
    llm = _capturing_llm({}, result)
    llm.with_structured_output.return_value.invoke.side_effect = lambda prompt: (
        prompts.append(prompt) or result
    )
    node = factory(llm)
    node(first_state)
    node(second_state)

    first_system = _message_content(prompts[0], "system")
    second_system = _message_content(prompts[1], "system")
    first_human = _message_content(prompts[0], "user")
    second_human = _message_content(prompts[1], "user")
    assert first_system == second_system
    for first_value, second_value in dynamic_values:
        assert first_value not in str(first_system)
        assert second_value not in str(second_system)
        assert first_value in first_human
        assert second_value in second_human


@pytest.mark.unit
def test_trader_prompt_states_constraint():
    from tradingagents.agents.schemas import TraderAction, TraderProposal

    captured = {}
    llm = _capturing_llm(captured, TraderProposal(action=TraderAction.BUY, reasoning="x"))
    create_trader(llm)(
        {
            "company_of_interest": "NVDA",
            "investment_plan": "**Recommendation**: Buy",
        }
    )
    assert NO_EXTERNAL_TOOLS in _prompt_text(captured["prompt"])


@pytest.mark.unit
def test_research_manager_prompt_states_constraint():
    from tradingagents.agents.schemas import PortfolioRating, ResearchPlan

    captured = {}
    llm = _capturing_llm(
        captured,
        ResearchPlan(recommendation=PortfolioRating.BUY, rationale="x", strategic_actions="y"),
    )
    create_research_manager(llm)(
        {
            "company_of_interest": "NVDA",
            "investment_debate_state": {
                "history": "h",
                "bull_history": "b",
                "bear_history": "r",
                "current_response": "",
                "judge_decision": "",
                "count": 1,
            },
        }
    )
    assert NO_EXTERNAL_TOOLS in _prompt_text(captured["prompt"])


@pytest.mark.unit
def test_portfolio_manager_prompt_states_constraint():
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    captured = {}
    llm = _capturing_llm(
        captured,
        PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="x",
            investment_thesis="y",
        ),
    )
    risk = {
        "history": "h",
        "aggressive_history": "a",
        "conservative_history": "c",
        "neutral_history": "n",
        "current_aggressive_response": "",
        "current_conservative_response": "",
        "current_neutral_response": "",
        "latest_speaker": "Neutral",
        "count": 1,
    }
    create_portfolio_manager(llm)(
        {
            "company_of_interest": "NVDA",
            "risk_debate_state": risk,
            "investment_plan": "plan",
            "trader_investment_plan": "trader plan",
        }
    )
    assert NO_EXTERNAL_TOOLS in _prompt_text(captured["prompt"])


@pytest.mark.unit
def test_sentiment_prompt_states_constraint(monkeypatch):
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    # Pre-fetched sources are stubbed so the prompt builds without network I/O.
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "st")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "rd")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "news", raising=False)

    captured = {}
    llm = _capturing_llm(
        captured,
        SentimentReport(
            overall_band=SentimentBand.BULLISH,
            overall_score=7.5,
            confidence="high",
            narrative="n",
        ),
    )
    sentiment.create_sentiment_analyst(llm)(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-15",
            "asset_type": "stock",
            "messages": [],
        }
    )
    text = _prompt_text(captured["prompt"])
    assert NO_EXTERNAL_TOOLS in text
    system_text = next(
        message.content
        for message in captured["prompt"]
        if getattr(message, "type", None) == "system"
    )
    assert "collaborating with other assistants" in system_text
    assert "FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**" in system_text
    assert "so the team knows to stop" in system_text
    # This agent binds no tools, so tool-range wording must not reappear.
    assert "tool-call date ranges" not in text


@pytest.mark.unit
def test_tool_using_analysts_keep_their_date_guidance():
    # The analysts that really do call tools keep the wording that anchors their
    # tool date ranges (#836) — this fix is scoped to no-tool agents.
    import tradingagents.agents.analysts.market_analyst as market
    import tradingagents.agents.analysts.news_analyst as news

    for module in (market, news):
        assert "tool-call date ranges" in inspect.getsource(module)


@pytest.mark.unit
def test_constraint_text_is_unambiguous():
    assert "do not call external tools" in NO_EXTERNAL_TOOLS.lower()
    # No template braces: it is embedded in ChatPromptTemplate strings, where
    # braces would be parsed as input variables.
    assert "{" not in NO_EXTERNAL_TOOLS and "}" not in NO_EXTERNAL_TOOLS


@pytest.mark.unit
def test_trader_system_prompt_is_stable_across_states():
    from tradingagents.agents.schemas import TraderAction, TraderProposal

    _assert_stable_split(
        create_trader,
        {"company_of_interest": "AAA", "investment_plan": "plan one"},
        {"company_of_interest": "BBB", "investment_plan": "plan two"},
        TraderProposal(action=TraderAction.HOLD, reasoning="x"),
        (("AAA", "BBB"), ("plan one", "plan two")),
    )


@pytest.mark.unit
def test_research_manager_system_prompt_is_stable_across_states():
    from tradingagents.agents.schemas import PortfolioRating, ResearchPlan

    def state(ticker, history):
        return {
            "company_of_interest": ticker,
            "investment_debate_state": {
                "history": history,
                "bull_history": "bull",
                "bear_history": "bear",
                "count": 1,
            },
        }

    _assert_stable_split(
        create_research_manager,
        state("AAA", "debate one"),
        state("BBB", "debate two"),
        ResearchPlan(
            recommendation=PortfolioRating.HOLD,
            rationale="x",
            strategic_actions="y",
        ),
        (("AAA", "BBB"), ("debate one", "debate two")),
    )


@pytest.mark.unit
def test_portfolio_manager_system_prompt_is_stable_across_states():
    from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating

    def state(ticker, suffix):
        return {
            "company_of_interest": ticker,
            "risk_debate_state": {
                "history": f"risk debate {suffix}",
                "aggressive_history": "a",
                "conservative_history": "c",
                "neutral_history": "n",
                "current_aggressive_response": "",
                "current_conservative_response": "",
                "current_neutral_response": "",
                "count": 1,
            },
            "investment_plan": f"research plan {suffix}",
            "trader_investment_plan": f"trader plan {suffix}",
            "past_context": f"past lesson {suffix}",
        }

    _assert_stable_split(
        create_portfolio_manager,
        state("AAA", "one"),
        state("BBB", "two"),
        PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="x",
            investment_thesis="y",
        ),
        (
            ("AAA", "BBB"),
            ("risk debate one", "risk debate two"),
            ("research plan one", "research plan two"),
            ("trader plan one", "trader plan two"),
            ("past lesson one", "past lesson two"),
        ),
    )
