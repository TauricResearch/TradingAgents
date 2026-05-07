from langchain_core.messages import AIMessage, HumanMessage
import pytest

from tradingagents.graph.conditional_logic import ConditionalLogic


def test_market_conditional_routes_to_tools_when_ai_message_has_tool_calls():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "get_stock_data", "args": {"ticker": "AAPL"}, "id": "1"}
                ],
            )
        ]
    }

    assert ConditionalLogic().should_continue_market(state) == "tools_market"


def test_market_conditional_clears_when_last_message_has_no_tool_calls():
    state = {"messages": [HumanMessage(content="Continue")]}

    assert ConditionalLogic().should_continue_market(state) == "Msg Clear Market"


def test_market_conditional_clears_when_messages_empty():
    state = {"messages": []}

    assert ConditionalLogic().should_continue_market(state) == "Msg Clear Market"


def test_debate_conditional_rejects_unexpected_current_response():
    state = {
        "investment_debate_state": {
            "count": 1,
            "current_response": "",
        }
    }

    with pytest.raises(ValueError, match="Unexpected investment debate state"):
        ConditionalLogic(max_debate_rounds=2).should_continue_debate(state)
