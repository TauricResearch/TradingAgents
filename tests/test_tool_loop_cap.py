"""An analyst whose model keeps requesting tools is stopped after max_tool_rounds (#1420).

Before the cap, only the run's recursion limit stopped such an analyst, and
reaching it raised GraphRecursionError and ended the run with no decision.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS
from tradingagents.graph.setup import _tools_or_done


def _tool_turn(i):
    return AIMessage(content="", tool_calls=[{"name": "get_stock_data", "id": f"c{i}", "args": {}}])


@pytest.mark.unit
def test_the_router_stops_an_analyst_once_the_cap_is_exceeded():
    route = _tools_or_done(ANALYST_NODE_SPECS["market"], max_tool_rounds=2)
    opening = [HumanMessage(content="go")]

    assert route({"messages": [*opening, AIMessage(content="report")]}) == END
    assert route({"messages": [*opening, _tool_turn(1)]}) == "tools"
    assert route({"messages": [*opening, _tool_turn(1), _tool_turn(2)]}) == "tools"
    assert route({"messages": [*opening, _tool_turn(1), _tool_turn(2), _tool_turn(3)]}) == END
