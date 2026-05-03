from langchain_core.messages import AIMessage, HumanMessage

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
