from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating
from tradingagents.agents.utils.agent_utils import (
    format_risk_constraints,
    resolve_risk_constraints,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


RISK_CONSTRAINTS = {
    "max_position_size_pct": 3.5,
    "max_risk_per_trade_pct": 1.0,
    "stop_loss_pct": 4.0,
    "risk_tolerance": "conservative",
}


def _base_risk_state():
    return {
        "company_of_interest": "NVDA",
        "asset_type": "stock",
        "instrument_context": "The instrument to analyze is `NVDA`.",
        "market_report": "Market report.",
        "sentiment_report": "Sentiment report.",
        "news_report": "News report.",
        "fundamentals_report": "Fundamentals report.",
        "investment_plan": "Research plan.",
        "trader_investment_plan": "Trader plan.",
        "past_context": "",
        "risk_constraints": RISK_CONSTRAINTS,
        "risk_debate_state": {
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "history": "Prior risk debate.",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 0,
        },
    }


def _assert_constraints_at_prompt_top(prompt: str):
    assert prompt.startswith("Session Risk Constraints")
    assert "Max position size: 3.5% of portfolio" in prompt
    assert "Max risk per trade: 1.0% of portfolio" in prompt
    assert "Stop loss: 4.0%" in prompt
    assert "Risk tolerance: conservative" in prompt


@pytest.mark.unit
def test_default_config_exposes_risk_constraints():
    assert DEFAULT_CONFIG["max_position_size_pct"] == 10.0
    assert DEFAULT_CONFIG["max_risk_per_trade_pct"] == 2.0
    assert DEFAULT_CONFIG["stop_loss_pct"] == 5.0
    assert DEFAULT_CONFIG["risk_tolerance"] == "moderate"


@pytest.mark.unit
def test_format_risk_constraints_omits_empty_block():
    assert format_risk_constraints({}) == ""


@pytest.mark.unit
def test_format_risk_constraints_renders_all_limits():
    _assert_constraints_at_prompt_top(format_risk_constraints(RISK_CONSTRAINTS))


@pytest.mark.unit
def test_resolve_risk_constraints_falls_back_for_none_values():
    constraints = resolve_risk_constraints(
        {
            "max_position_size_pct": None,
            "max_risk_per_trade_pct": None,
            "stop_loss_pct": None,
            "risk_tolerance": None,
        }
    )
    assert constraints == {
        "max_position_size_pct": 10.0,
        "max_risk_per_trade_pct": 2.0,
        "stop_loss_pct": 5.0,
        "risk_tolerance": "moderate",
    }


@pytest.mark.unit
def test_format_risk_constraints_falls_back_for_none_values():
    prompt = format_risk_constraints(
        {
            "max_position_size_pct": None,
            "max_risk_per_trade_pct": None,
            "stop_loss_pct": None,
            "risk_tolerance": None,
        }
    )
    assert "None" not in prompt
    assert "Max position size: 10.0% of portfolio" in prompt
    assert "Max risk per trade: 2.0% of portfolio" in prompt
    assert "Stop loss: 5.0%" in prompt
    assert "Risk tolerance: moderate" in prompt


@pytest.mark.unit
def test_propagator_carries_risk_constraints_in_initial_state():
    state = Propagator().create_initial_state(
        "NVDA",
        "2026-01-10",
        risk_constraints=RISK_CONSTRAINTS,
    )
    assert state["risk_constraints"] == RISK_CONSTRAINTS


@pytest.mark.unit
def test_propagator_defaults_risk_constraints_to_empty_dict():
    state = Propagator().create_initial_state("NVDA", "2026-01-10")
    assert state["risk_constraints"] == {}


@pytest.mark.unit
def test_graph_extracts_risk_constraints_from_config_with_defaults():
    graph = MagicMock(spec=TradingAgentsGraph)
    graph.config = {"max_risk_per_trade_pct": 0.75}

    constraints = TradingAgentsGraph._risk_constraints_from_config(graph)

    assert constraints == {
        "max_position_size_pct": 10.0,
        "max_risk_per_trade_pct": 0.75,
        "stop_loss_pct": 5.0,
        "risk_tolerance": "moderate",
    }


@pytest.mark.unit
def test_graph_extracts_risk_constraints_falls_back_for_none_values():
    graph = MagicMock(spec=TradingAgentsGraph)
    graph.config = {
        "max_position_size_pct": None,
        "max_risk_per_trade_pct": None,
        "stop_loss_pct": None,
        "risk_tolerance": None,
    }

    constraints = TradingAgentsGraph._risk_constraints_from_config(graph)

    assert constraints == {
        "max_position_size_pct": 10.0,
        "max_risk_per_trade_pct": 2.0,
        "stop_loss_pct": 5.0,
        "risk_tolerance": "moderate",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "factory",
    [
        create_aggressive_debator,
        create_conservative_debator,
        create_neutral_debator,
    ],
)
def test_risk_debater_prompts_start_with_constraints(factory):
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="Risk argument.")

    factory(llm)(_base_risk_state())

    _assert_constraints_at_prompt_top(llm.invoke.call_args[0][0])


@pytest.mark.unit
def test_portfolio_manager_prompt_starts_with_constraints():
    captured = {}
    decision = PortfolioDecision(
        rating=PortfolioRating.HOLD,
        executive_summary="Stay within risk budget.",
        investment_thesis="Constraints cap the position.",
    )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt) or decision
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured

    create_portfolio_manager(llm)(_base_risk_state())

    _assert_constraints_at_prompt_top(captured["prompt"])
