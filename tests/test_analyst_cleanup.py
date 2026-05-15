import importlib.util
import sys
import types
from pathlib import Path


class _HumanMessage:
    def __init__(self, content):
        self.content = content


class _RemoveMessage:
    def __init__(self, id):
        self.id = id


class _Msg:
    def __init__(self, id):
        self.id = id


def _load_agent_utils():
    fake_messages = types.ModuleType("langchain_core.messages")
    fake_messages.HumanMessage = _HumanMessage
    fake_messages.RemoveMessage = _RemoveMessage
    sys.modules["langchain_core.messages"] = fake_messages

    for module_name, attrs in {
        "tradingagents.agents.utils.core_stock_tools": {"get_stock_data": object()},
        "tradingagents.agents.utils.technical_indicators_tools": {"get_indicators": object()},
        "tradingagents.agents.utils.fundamental_data_tools": {
            "get_fundamentals": object(),
            "get_balance_sheet": object(),
            "get_cashflow": object(),
            "get_income_statement": object(),
        },
        "tradingagents.agents.utils.news_data_tools": {
            "get_news": object(),
            "get_insider_transactions": object(),
            "get_global_news": object(),
        },
    }.items():
        mod = types.ModuleType(module_name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[module_name] = mod

    module_path = (
        Path(__file__).resolve().parents[1]
        / "tradingagents"
        / "agents"
        / "utils"
        / "agent_utils.py"
    )
    spec = importlib.util.spec_from_file_location("agent_utils_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_create_msg_delete_does_not_increment_analyst_count():
    module = _load_agent_utils()
    delete_messages = module.create_msg_delete("market_messages")

    result = delete_messages({"market_messages": [_Msg("1"), _Msg("2")]})

    assert "analyst_count" not in result
    assert len(result["market_messages"]) == 3
    assert isinstance(result["market_messages"][-1], _HumanMessage)
