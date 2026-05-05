from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager


def _base_state():
    return {
        "company_of_interest": "AAPL",
        "trade_date": "2026-01-01",
        "past_context": "",
        "investment_plan": "**Recommendation**: Buy\n\n**Rationale**: ...\n\n**Strategic Actions**: ...",
        "trader_investment_plan": "**Action**: BUY\n\nFINAL TRANSACTION PROPOSAL: **BUY**",
        "risk_debate_state": {
            "history": "Aggressive Analyst: ...\nConservative Analyst: ...\nNeutral Analyst: ...",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "judge_decision": "",
            "count": 3,
        },
        "research_manager_structured_valid": True,
        "trader_structured_valid": True,
        "error_count": 0,
    }


@pytest.mark.unit
def test_forces_hold_when_error_count_is_very_high():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content="**Rating**: Buy\n\n**Executive Summary**: ...\n\n**Investment Thesis**: ...")
    pm = create_portfolio_manager(llm)

    state = _base_state()
    state["error_count"] = 5
    out = pm(state)
    assert "**Rating**: Hold" in out["final_trade_decision"]
    assert out["data_quality"] == "low"
    assert out["error_count"] == 5


@pytest.mark.unit
def test_blocks_buy_and_sell_when_data_quality_low():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("no structured")
    llm.invoke.return_value = MagicMock(content="**Rating**: Sell\n\n**Executive Summary**: ...\n\n**Investment Thesis**: ...")
    pm = create_portfolio_manager(llm)

    state = _base_state()
    state["error_count"] = 3
    out = pm(state)
    rating_line = next(line for line in out["final_trade_decision"].splitlines() if "Rating" in line)
    assert "Sell" not in rating_line
    assert out["data_quality"] == "low"
