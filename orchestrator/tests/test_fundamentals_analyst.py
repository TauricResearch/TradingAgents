import tradingagents.agents.analysts.fundamentals_analyst as fundamentals_module
from types import SimpleNamespace

import pytest


class _FakePrompt:
    def __init__(self):
        self.partials = {}

    def partial(self, **kwargs):
        self.partials.update(kwargs)
        return self

    def __or__(self, _other):
        return _FakeChain(self)


class _FakeChain:
    def __init__(self, prompt):
        self.prompt = prompt

    def invoke(self, _messages):
        return SimpleNamespace(tool_calls=[], content=self.prompt.partials["system_message"])


class _FakePromptTemplate:
    last_prompt = None

    @classmethod
    def from_messages(cls, _messages):
        cls.last_prompt = _FakePrompt()
        return cls.last_prompt


class _FakeLLM:
    def bind_tools(self, _tools):
        return self


@pytest.mark.parametrize("compact_mode", [True, False])
def test_fundamentals_system_message_is_string(monkeypatch, compact_mode):
    monkeypatch.setattr(fundamentals_module, "ChatPromptTemplate", _FakePromptTemplate)
    monkeypatch.setattr(fundamentals_module, "use_compact_analysis_prompt", lambda: compact_mode)
    monkeypatch.setattr(fundamentals_module, "get_language_instruction", lambda: "")

    node = fundamentals_module.create_fundamentals_analyst(_FakeLLM())
    result = node(
        {
            "trade_date": "2026-04-11",
            "company_of_interest": "600519.SS",
            "messages": [],
        }
    )

    system_message = _FakePromptTemplate.last_prompt.partials["system_message"]

    assert isinstance(system_message, str)
    assert result["fundamentals_report"] == system_message
