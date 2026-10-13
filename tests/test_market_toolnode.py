"""The market analyst is bound (and prompt-instructed) to call
get_verified_market_snapshot; if the executor ToolNode doesn't register it, the
call fails and the model reports the tool "unavailable" and skips verification.

Regression guard for that wiring gap (snapshot bound to the LLM but missing from
the market ToolNode).
"""
import pytest

from tradingagents.agents.analysts import market_analyst
from tradingagents.graph.analyst_execution import ANALYST_NODE_SPECS


@pytest.mark.unit
def test_market_toolnode_can_execute_verified_snapshot():
    tool_names = {t.name for t in market_analyst.TOOLS}
    assert "get_verified_market_snapshot" in tool_names, (
        "get_verified_market_snapshot is bound to the market analyst but not "
        "registered in market_analyst.TOOLS, so the model's call fails."
    )
    # the other core market tools must remain too
    assert {"get_stock_data", "get_indicators"} <= tool_names

    spec_tool_names = {t.name for t in ANALYST_NODE_SPECS["market"].tools}
    assert "get_verified_market_snapshot" in spec_tool_names
