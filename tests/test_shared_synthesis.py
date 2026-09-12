from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.schemas import PortfolioRating, ResearchPlan, TraderAction, TraderProposal


def test_bull_update_preserves_state():
    from tradingagents.agents.researchers.bull_researcher import apply_bull_output

    state = {
        "investment_debate_state": {
            "history": "prior",
            "bull_history": "",
            "bear_history": "bear",
            "count": 2,
        }
    }
    before = deepcopy(state)

    result = apply_bull_output(state, "new case")["investment_debate_state"]

    assert state == before
    assert result == {
        "history": "prior\nBull Analyst: new case",
        "bull_history": "\nBull Analyst: new case",
        "bear_history": "bear",
        "current_response": "Bull Analyst: new case",
        "count": 3,
    }


def _research_state(*, asset_type="stock", current_response="Bear case"):
    return {
        "company_of_interest": "BTC-USD",
        "asset_type": asset_type,
        "market_report": "MARKET_SENTINEL",
        "sentiment_report": "SENTIMENT_SENTINEL",
        "news_report": "NEWS_SENTINEL",
        "fundamentals_report": "FUNDAMENTALS_SENTINEL",
        "investment_debate_state": {
            "history": "DEBATE_SENTINEL",
            "bull_history": "bull prior",
            "bear_history": "bear prior",
            "current_response": current_response,
            "count": 2,
        },
    }


def _manager_state():
    return {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "investment_debate_state": {
            "history": "DEBATE_SENTINEL",
            "bull_history": "bull prior",
            "bear_history": "bear prior",
            "current_response": "last response",
            "judge_decision": "old decision",
            "count": 2,
        },
    }


def _trader_state(market_report="TECHNICAL_SENTINEL"):
    return {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "investment_plan": "PLAN_SENTINEL",
        "market_report": market_report,
    }


@pytest.mark.parametrize(
    ("builder_name", "expected_opponent"),
    [("build_bull_prompt", "Last bear argument"), ("build_bear_prompt", "Last bull argument")],
)
def test_research_prompts_keep_evidence_crypto_language_and_opening_marker(
    monkeypatch, builder_name, expected_opponent
):
    from tradingagents.agents.researchers import bear_researcher, bull_researcher

    module = bull_researcher if builder_name == "build_bull_prompt" else bear_researcher
    monkeypatch.setattr(module.config, "get_config", lambda: pytest.fail("global config read"))

    prompt = getattr(module, builder_name)(
        _research_state(asset_type="crypto", current_response=""), output_language="French"
    )

    for sentinel in ("MARKET_SENTINEL", "SENTIMENT_SENTINEL", "NEWS_SENTINEL", "FUNDAMENTALS_SENTINEL"):
        assert sentinel in prompt
    assert expected_opponent in prompt
    assert "has not spoken yet" in prompt
    assert "investing in the asset" in prompt
    assert "Asset fundamentals report (may be unavailable for crypto)" in prompt
    assert "French" in prompt


def test_bear_update_uses_bear_prefix_and_preserves_state():
    from tradingagents.agents.researchers.bear_researcher import apply_bear_output

    state = _research_state()
    before = deepcopy(state)

    result = apply_bear_output(state, "new case")["investment_debate_state"]

    assert state == before
    assert result["history"] == "DEBATE_SENTINEL\nBear Analyst: new case"
    assert result["bear_history"] == "bear prior\nBear Analyst: new case"
    assert result["bull_history"] == "bull prior"
    assert result["current_response"] == "Bear Analyst: new case"
    assert result["count"] == 3


def test_research_manager_prompt_and_update_are_pure(monkeypatch):
    from tradingagents.agents.managers import research_manager

    state = _manager_state()
    before = deepcopy(state)
    monkeypatch.setattr(research_manager.config, "get_config", lambda: pytest.fail("global config read"))

    prompt = research_manager.build_research_manager_prompt(state, output_language="French")
    result = research_manager.apply_research_manager_output(state, "PLAN_OUTPUT")

    assert "DEBATE_SENTINEL" in prompt and "French" in prompt
    assert state == before
    assert result == {
        "investment_debate_state": {
            "judge_decision": "PLAN_OUTPUT",
            "history": "DEBATE_SENTINEL",
            "bear_history": "bear prior",
            "bull_history": "bull prior",
            "current_response": "PLAN_OUTPUT",
            "count": 2,
        },
        "investment_plan": "PLAN_OUTPUT",
    }


@pytest.mark.parametrize("market_report", ["TECHNICAL_SENTINEL", ""])
def test_trader_messages_keep_conditional_report_and_explicit_language(monkeypatch, market_report):
    from tradingagents.agents.trader import trader

    monkeypatch.setattr(trader.config, "get_config", lambda: pytest.fail("global config read"))
    messages = trader.build_trader_messages(_trader_state(market_report), output_language="French")
    text = "\n".join(message["content"] for message in messages)

    assert len(messages) == 2
    assert "PLAN_SENTINEL" in text and "French" in text
    assert "absolute price levels" in text and "never a percentage" in text
    assert ("Technical Market Report:" in text) is bool(market_report)
    assert ("Ground concrete price levels" in text) is bool(market_report)
    assert "TECHNICAL_SENTINEL" in text if market_report else "TECHNICAL_SENTINEL" not in text


@pytest.mark.parametrize(
    ("module_name", "factory_name", "builder_name", "updater_name", "output"),
    [
        ("bull_researcher", "create_bull_researcher", "build_bull_prompt", "apply_bull_output", "bull output"),
        ("bear_researcher", "create_bear_researcher", "build_bear_prompt", "apply_bear_output", "bear output"),
    ],
)
def test_researcher_factories_use_shared_prompt_and_update(
    monkeypatch, module_name, factory_name, builder_name, updater_name, output
):
    module = __import__(f"tradingagents.agents.researchers.{module_name}", fromlist=["*"])
    monkeypatch.setattr(module.config, "get_config", lambda: {"output_language": "French"})
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=output)
    state = _research_state()

    result = getattr(module, factory_name)(llm)(state)

    assert llm.invoke.call_args.args[0] == getattr(module, builder_name)(
        state, output_language="French"
    )
    assert result == getattr(module, updater_name)(state, output)


def _structured_llm(captured, result):
    structured = MagicMock()
    def capture_prompt(prompt):
        captured["prompt"] = prompt
        return result

    structured.invoke.side_effect = capture_prompt
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


@pytest.mark.parametrize(
    ("factory_name", "builder_name", "updater_name", "state", "schema_output"),
    [
        (
            "create_research_manager",
            "build_research_manager_prompt",
            "apply_research_manager_output",
            _manager_state(),
            ResearchPlan(
                recommendation=PortfolioRating.BUY, rationale="rationale", strategic_actions="actions"
            ),
        ),
        (
            "create_trader",
            "build_trader_messages",
            "apply_trader_output",
            _trader_state(),
            TraderProposal(action=TraderAction.BUY, reasoning="reasoning"),
        ),
    ],
)
def test_structured_factories_use_shared_prompt_and_update(
    monkeypatch, factory_name, builder_name, updater_name, state, schema_output
):
    module_name = "research_manager" if "manager" in factory_name else "trader"
    module = __import__(f"tradingagents.agents.{('managers.' if module_name == 'research_manager' else 'trader.')}{module_name}", fromlist=["*"])
    monkeypatch.setattr(module.config, "get_config", lambda: {"output_language": "French"})
    captured = {}
    llm = _structured_llm(captured, schema_output)

    result = getattr(module, factory_name)(llm)(state)
    output = result["investment_plan"] if module_name == "research_manager" else result["trader_investment_plan"]

    assert captured["prompt"] == getattr(module, builder_name)(state, output_language="French")
    assert result.items() >= getattr(module, updater_name)(state, output).items()
    if module_name == "trader":
        assert result["messages"][0].content == output
        assert result["sender"] == "Trader"


@pytest.mark.parametrize("failure", ["unsupported", "none", "exception"])
@pytest.mark.parametrize("factory_name", ["create_research_manager", "create_trader"])
def test_structured_factories_fall_back_to_freetext(monkeypatch, factory_name, failure):
    module_name = "research_manager" if "manager" in factory_name else "trader"
    module = __import__(f"tradingagents.agents.{('managers.' if module_name == 'research_manager' else 'trader.')}{module_name}", fromlist=["*"])
    monkeypatch.setattr(module.config, "get_config", lambda: {"output_language": "English"})
    llm = MagicMock()
    if failure == "unsupported":
        llm.with_structured_output.side_effect = NotImplementedError
    else:
        llm.with_structured_output.return_value.invoke.side_effect = (
            None if failure == "none" else RuntimeError("broken structured call")
        )
        if failure == "none":
            llm.with_structured_output.return_value.invoke.return_value = None
    llm.invoke.return_value = MagicMock(content="FREETEXT_OUTPUT")

    result = getattr(module, factory_name)(llm)(
        _manager_state() if module_name == "research_manager" else _trader_state()
    )

    field = "investment_plan" if module_name == "research_manager" else "trader_investment_plan"
    assert result[field] == "FREETEXT_OUTPUT"
