import asyncio
import importlib.util
import sys
import types
from pathlib import Path


class _HumanMessage:
    def __init__(self, content=None, id="msg-1"):
        self.content = content
        self.id = id


class _RemoveMessage:
    def __init__(self, id):
        self.id = id


class _MessagesPlaceholder:
    def __init__(self, variable_name):
        self.variable_name = variable_name


class _Result:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _FakeChain:
    def __init__(self):
        self.ainvoke_calls = 0
        self.invoke_calls = 0

    async def ainvoke(self, messages):
        self.ainvoke_calls += 1
        return _Result("async report", [])

    def invoke(self, messages):
        self.invoke_calls += 1
        return _Result("sync report", [])


class _FakePrompt:
    def __init__(self, chain):
        self.chain = chain

    def partial(self, **kwargs):
        return self

    def __or__(self, other):
        return self.chain


class _FakeChatPromptTemplate:
    chain = None

    @classmethod
    def from_messages(cls, messages):
        return _FakePrompt(cls.chain)


class _FakeTool:
    def __init__(self, name):
        self.name = name


class _FakeLLM:
    def bind_tools(self, tools):
        return self


def _load_market_module(chain):
    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = _HumanMessage
    fake_messages.RemoveMessage = _RemoveMessage
    sys.modules["langchain_core.messages"] = fake_messages

    fake_prompts = types.ModuleType("langchain_core.prompts")
    _FakeChatPromptTemplate.chain = chain
    fake_prompts.ChatPromptTemplate = _FakeChatPromptTemplate
    fake_prompts.MessagesPlaceholder = _MessagesPlaceholder
    sys.modules["langchain_core.prompts"] = fake_prompts

    fake_agent_utils = types.ModuleType("tradingagents.agents.utils.agent_utils")
    fake_agent_utils.build_instrument_context = lambda ticker: f"context for {ticker}"
    fake_agent_utils.get_language_instruction = lambda: ""
    fake_agent_utils.get_stock_data = _FakeTool("get_stock_data")
    fake_agent_utils.get_indicators = _FakeTool("get_indicators")
    sys.modules["tradingagents.agents.utils.agent_utils"] = fake_agent_utils

    fake_config = types.ModuleType("tradingagents.dataflows.config")
    fake_config.get_config = lambda: {}
    sys.modules["tradingagents.dataflows.config"] = fake_config

    module_path = (
        Path(__file__).resolve().parents[1]
        / "tradingagents"
        / "agents"
        / "analysts"
        / "market_analyst.py"
    )
    spec = importlib.util.spec_from_file_location("market_analyst_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_market_analyst_uses_ainvoke():
    chain = _FakeChain()
    module = _load_market_module(chain)
    analyst = module.create_market_analyst(_FakeLLM())

    state = {
        "trade_date": "2026-05-15",
        "company_of_interest": "SHOP",
        "market_messages": [_HumanMessage("SHOP")],
    }

    result = asyncio.run(analyst(state))

    assert chain.ainvoke_calls == 1
    assert chain.invoke_calls == 0
    assert result["market_report"] == "async report"
