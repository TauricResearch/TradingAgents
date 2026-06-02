from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage


@pytest.mark.unit
def test_news_analyst_prompt_names_get_news_ticker():
    from pathlib import Path

    source = Path("tradingagents/agents/analysts/news_analyst.py").read_text()
    assert "get_news(ticker, start_date, end_date)" in source
    assert "get_news(query, start_date, end_date)" not in source


@pytest.mark.unit
def test_structured_fallback_normalizes_free_text_list_content():
    from tradingagents.agents.utils.structured import invoke_structured_or_freetext

    plain_llm = MagicMock()
    plain_llm.invoke.return_value = AIMessage(content=[{"type": "text", "text": "hello"}])

    out = invoke_structured_or_freetext(
        structured_llm=None,
        plain_llm=plain_llm,
        prompt="prompt",
        render=lambda result: "unused",
        agent_name="TestAgent",
    )

    assert out == "hello"


@pytest.mark.unit
def test_market_analyst_preserves_partial_content_with_tool_calls(monkeypatch):
    from tradingagents.agents.analysts.market_analyst import create_market_analyst

    class Chain:
        def invoke(self, messages):
            msg = AIMessage(content="partial market note")
            msg.tool_calls = [{"name": "get_stock_data", "args": {"symbol": "AAPL"}, "id": "1"}]
            return msg

    class Prompt:
        def partial(self, **kwargs):
            return self

        def __or__(self, other):
            return Chain()

    class FakePromptTemplate:
        @staticmethod
        def from_messages(messages):
            return Prompt()

    monkeypatch.setattr(
        "tradingagents.agents.analysts.market_analyst.ChatPromptTemplate",
        FakePromptTemplate,
    )

    llm = MagicMock()
    llm.bind_tools.return_value = object()
    node = create_market_analyst(llm)
    out = node({"trade_date": "2024-01-02", "messages": [], "company_of_interest": "AAPL", "asset_type": "stock"})

    assert out["market_report"] == "partial market note"
