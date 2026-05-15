import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture()
def conditional_logic_module(monkeypatch):
    fake_agent_states = types.ModuleType("tradingagents.agents.utils.agent_states")
    fake_agent_states.AgentState = dict
    monkeypatch.setitem(
        sys.modules,
        "tradingagents.agents.utils.agent_states",
        fake_agent_states,
    )

    module_path = (
        Path(__file__).resolve().parents[1]
        / "tradingagents"
        / "graph"
        / "conditional_logic.py"
    )
    spec = importlib.util.spec_from_file_location("conditional_logic_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _HumanMessage:
    def __init__(self, content):
        self.content = content


class _MessageWithTools:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


def test_market_router_treats_human_message_as_no_tool_call(conditional_logic_module):
    logic = conditional_logic_module.ConditionalLogic()
    state = {"market_messages": [_HumanMessage(content="Continue")]}

    assert logic.should_continue_market(state) == "Msg Clear Market"


def test_news_router_continues_when_tool_calls_exist(conditional_logic_module):
    logic = conditional_logic_module.ConditionalLogic()
    state = {"news_messages": [_MessageWithTools([{"name": "get_news"}])]}

    assert logic.should_continue_news(state) == "tools_news"
