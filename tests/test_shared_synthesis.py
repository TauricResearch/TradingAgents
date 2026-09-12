from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.risk_mgmt.aggressive_debator import apply_aggressive_output
from tradingagents.agents.risk_mgmt.conservative_debator import apply_conservative_output
from tradingagents.agents.risk_mgmt.neutral_debator import apply_neutral_output
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


def _risk_state(**responses):
    debate = {
        "history": "RISK_DEBATE_SENTINEL",
        "aggressive_history": "saved aggressive",
        "conservative_history": "saved conservative",
        "neutral_history": "saved neutral",
        "current_aggressive_response": "last aggressive",
        "current_conservative_response": "last conservative",
        "current_neutral_response": "last neutral",
        "count": 4,
    }
    debate.update(responses)
    return {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "market_report": "MARKET_SENTINEL",
        "sentiment_report": "SENTIMENT_SENTINEL",
        "news_report": "NEWS_SENTINEL",
        "fundamentals_report": "FUNDAMENTALS_SENTINEL",
        "trader_investment_plan": "TRADER_PLAN_SENTINEL",
        "risk_debate_state": debate,
    }


def _portfolio_state(past_context=""):
    return {
        **_risk_state(),
        "investment_plan": "INVESTMENT_PLAN_SENTINEL",
        "past_context": past_context,
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


@pytest.mark.parametrize(
    "key,label,apply",
    [
        ("aggressive", "Aggressive", apply_aggressive_output),
        ("conservative", "Conservative", apply_conservative_output),
        ("neutral", "Neutral", apply_neutral_output),
    ],
)
def test_risk_patch(key, label, apply):
    debate = {"history": "prior", "count": 4, "latest_speaker": "prior"}
    for role in ("aggressive", "conservative", "neutral"):
        debate[f"{role}_history"] = f"saved {role}"
        debate[f"current_{role}_response"] = f"last {role}"
    state = {"risk_debate_state": debate}
    before = deepcopy(state)
    result = apply(state, "new")["risk_debate_state"]
    assert state == before
    assert result["count"] == 5 and result["latest_speaker"] == label
    assert result["history"] == f"prior\n{label} Analyst: new"
    assert result[f"{key}_history"] == f"saved {key}\n{label} Analyst: new"
    assert result[f"current_{key}_response"] == f"{label} Analyst: new"
    for other in {"aggressive", "conservative", "neutral"} - {key}:
        assert result[f"{other}_history"] == debate[f"{other}_history"]
        assert result[f"current_{other}_response"] == debate[f"current_{other}_response"]


@pytest.mark.parametrize(
    ("module_name", "builder_name"),
    [
        ("aggressive_debator", "build_aggressive_prompt"),
        ("conservative_debator", "build_conservative_prompt"),
        ("neutral_debator", "build_neutral_prompt"),
    ],
)
def test_risk_builders_are_pure_and_include_all_inputs(monkeypatch, module_name, builder_name):
    module = __import__(f"tradingagents.agents.risk_mgmt.{module_name}", fromlist=["*"])
    monkeypatch.setattr(module.config, "get_config", lambda: pytest.fail("global config read"))
    prompt = getattr(module, builder_name)(
        _risk_state(
            current_aggressive_response="",
            current_conservative_response="",
            current_neutral_response="",
        ),
        output_language="French",
    )
    for sentinel in (
        "MARKET_SENTINEL",
        "SENTIMENT_SENTINEL",
        "NEWS_SENTINEL",
        "FUNDAMENTALS_SENTINEL",
        "TRADER_PLAN_SENTINEL",
        "RISK_DEBATE_SENTINEL",
    ):
        assert sentinel in prompt
    assert prompt.count("has not spoken yet") == 2
    assert "French" in prompt


@pytest.mark.parametrize(
    ("module_name", "factory_name", "builder_name", "updater_name"),
    [
        (
            "aggressive_debator",
            "create_aggressive_debator",
            "build_aggressive_prompt",
            "apply_aggressive_output",
        ),
        (
            "conservative_debator",
            "create_conservative_debator",
            "build_conservative_prompt",
            "apply_conservative_output",
        ),
        (
            "neutral_debator",
            "create_neutral_debator",
            "build_neutral_prompt",
            "apply_neutral_output",
        ),
    ],
)
def test_risk_factories_use_shared_prompt_and_update(
    monkeypatch, module_name, factory_name, builder_name, updater_name
):
    module = __import__(f"tradingagents.agents.risk_mgmt.{module_name}", fromlist=["*"])
    monkeypatch.setattr(module.config, "get_config", lambda: {"output_language": "French"})
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="RISK_OUTPUT")
    state = _risk_state()

    result = getattr(module, factory_name)(llm)(state)

    assert llm.invoke.call_args.args[0] == getattr(module, builder_name)(
        state, output_language="French"
    )
    assert result == getattr(module, updater_name)(state, "RISK_OUTPUT")


@pytest.mark.parametrize("past_context", ["", "PRIOR_LESSON_SENTINEL"])
def test_portfolio_builder_and_update_are_pure(monkeypatch, past_context):
    from tradingagents.agents.managers import portfolio_manager

    state = _portfolio_state(past_context)
    before = deepcopy(state)
    monkeypatch.setattr(portfolio_manager.config, "get_config", lambda: pytest.fail("global config read"))
    prompt = portfolio_manager.build_portfolio_manager_prompt(state, output_language="French")
    result = portfolio_manager.apply_portfolio_manager_output(state, "DECISION_OUTPUT")

    assert state == before
    assert "RISK_DEBATE_SENTINEL" in prompt and "INVESTMENT_PLAN_SENTINEL" in prompt
    assert "TRADER_PLAN_SENTINEL" in prompt and "French" in prompt
    assert ("PRIOR_LESSON_SENTINEL" in prompt) is bool(past_context)
    assert result == {
        "risk_debate_state": {
            "judge_decision": "DECISION_OUTPUT",
            "history": "RISK_DEBATE_SENTINEL",
            "aggressive_history": "saved aggressive",
            "conservative_history": "saved conservative",
            "neutral_history": "saved neutral",
            "latest_speaker": "Judge",
            "current_aggressive_response": "last aggressive",
            "current_conservative_response": "last conservative",
            "current_neutral_response": "last neutral",
            "count": 4,
        },
        "final_trade_decision": "DECISION_OUTPUT",
    }


def test_portfolio_factory_uses_shared_prompt_and_update(monkeypatch):
    from tradingagents.agents.managers import portfolio_manager

    monkeypatch.setattr(portfolio_manager.config, "get_config", lambda: {"output_language": "French"})
    captured = {}
    llm = _structured_llm(
        captured,
        PortfolioRating.HOLD,
    )
    state = _portfolio_state()
    monkeypatch.setattr(portfolio_manager, "render_pm_decision", lambda output: "DECISION_OUTPUT")

    result = portfolio_manager.create_portfolio_manager(llm)(state)

    assert captured["prompt"] == portfolio_manager.build_portfolio_manager_prompt(
        state, output_language="French"
    )
    assert result == portfolio_manager.apply_portfolio_manager_output(state, "DECISION_OUTPUT")


def test_reflection_builder_and_adapter_match():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from tradingagents.graph.reflection import Reflector, build_reflection_messages

    model = Mock()
    model.invoke.return_value = SimpleNamespace(content="lesson")
    reflector = Reflector(model)
    assert reflector.reflect_on_final_decision("decision", 0.042, 0.021, "^N225") == "lesson"
    messages = build_reflection_messages("decision", 0.042, 0.021, "^N225")
    model.invoke.assert_called_once_with(messages)
    assert "+4.2%" in messages[1][1] and "Alpha vs ^N225: +2.1%" in messages[1][1]


def test_reflection_builder_honors_custom_prompt_and_negative_default_returns():
    from tradingagents.graph.reflection import (
        Reflector,
        build_reflection_messages,
        get_log_reflection_prompt,
    )

    messages = build_reflection_messages("decision", -0.042, -0.021)
    assert messages[0] == ("system", get_log_reflection_prompt())
    assert "Raw return: -4.2%" in messages[1][1]
    assert "Alpha vs SPY: -2.1%" in messages[1][1]

    model = MagicMock()
    model.invoke.return_value = MagicMock(content="lesson")
    reflector = Reflector(model)
    reflector.log_reflection_prompt = "CUSTOM_PROMPT"
    reflector.reflect_on_final_decision("decision", 0.0, 0.0)
    assert model.invoke.call_args.args[0][0] == ("system", "CUSTOM_PROMPT")
