from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import PortfolioDecision, PortfolioRating, TraderAction


class _StructuredLlm:
    def with_structured_output(self, _schema):
        return self

    def invoke(self, _prompt):
        return PortfolioDecision(
            rating=PortfolioRating.BUY,
            executive_summary="Buy because the evidence is favorable.",
            investment_thesis="The positive case dominates the risk debate.",
            execution_action=TraderAction.BUY,
            requested_quantity=9_999,
        )


def _state(portfolio_context):
    return {
        "company_of_interest": "600000.SH",
        "instrument_context": "Instrument: 600000.SH",
        "investment_plan": "Buy",
        "trader_investment_plan": "Buy",
        "past_context": "",
        "portfolio_context": portfolio_context,
        "risk_debate_state": {
            "history": "Risk discussion",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 1,
        },
    }


def test_portfolio_manager_clamps_requested_quantity_and_records_audit():
    node = create_portfolio_manager(_StructuredLlm())
    state = _state(
        {
            "cash": 10_000,
            "positions": [],
            "mark_prices": {"600000.SH": 10},
            "currency": "CNY",
            "limits": {
                "max_position_weight": 0.20,
                "lot_size": 100,
                "fee_rate": 0.001,
                "minimum_fee": 5,
                "allow_short": False,
            },
        }
    )

    result = node(state)

    assert "**Execution Constraint**: BUY 200" in result["final_trade_decision"]
    assert result["clamp_events"][0]["reason"] == "requested_quantity_clamped"
    assert result["allowed_actions"][1]["max_quantity"] == 200


def test_portfolio_manager_without_inputs_cannot_issue_a_trade():
    node = create_portfolio_manager(_StructuredLlm())

    result = node(_state(None))

    assert result["allowed_actions"] == [
        {"action": "hold", "max_quantity": 0, "price": None, "reason": "portfolio_not_provided"}
    ]
    assert result["clamp_events"] == []
