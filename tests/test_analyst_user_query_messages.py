"""Regression guard for providers that require at least one user query message.

Some OpenAI-compatible gateways reject requests that contain only system/tool/
assistant content (500: "no user query found in messages"). Analysts should
always pass at least one human/user message to the model.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.analysts.sentiment_analyst import create_sentiment_analyst


class _CaptureToolModel(BaseChatModel):
    """Tool-capable model that records the message list it receives."""

    seen_messages: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "capture-tool-model"

    def bind_tools(self, tools, **kwargs):
        return self.model_copy(update={"seen_messages": self.seen_messages})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen_messages[:] = list(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])


@pytest.mark.unit
@pytest.mark.parametrize(
    "factory",
    [create_market_analyst, create_news_analyst, create_fundamentals_analyst],
    ids=["market", "news", "fundamentals"],
)
def test_tool_using_analysts_add_a_user_message_if_missing(factory):
    model = _CaptureToolModel()
    node = factory(model)

    node(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-09",
            "asset_type": "stock",
            "messages": [AIMessage(content="Prior assistant-only context")],
        }
    )

    assert any(getattr(m, "type", "") in {"human", "user"} for m in model.seen_messages)


@pytest.mark.unit
def test_sentiment_analyst_adds_a_user_message_if_missing(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "news", raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "st")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "rd")

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("unsupported")

    captured = {}

    def _invoke(prompt):
        captured["prompt"] = prompt
        return AIMessage(content="sentiment report")

    llm.invoke.side_effect = _invoke

    node = create_sentiment_analyst(llm)
    node(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-09",
            "asset_type": "stock",
            "messages": [AIMessage(content="Prior assistant-only context")],
        }
    )

    assert any(getattr(m, "type", "") in {"human", "user"} for m in captured["prompt"])


@pytest.mark.unit
def test_sentiment_analyst_does_not_add_duplicate_user_message(monkeypatch):
    from tradingagents.agents.analysts import sentiment_analyst as sentiment

    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "news", raising=False)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "st")
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", lambda *a, **k: "rd")

    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError("unsupported")

    captured = {}

    def _invoke(prompt):
        captured["prompt"] = prompt
        return AIMessage(content="sentiment report")

    llm.invoke.side_effect = _invoke

    node = create_sentiment_analyst(llm)
    node(
        {
            "company_of_interest": "NVDA",
            "trade_date": "2026-01-09",
            "asset_type": "stock",
            "messages": [HumanMessage(content="Please analyze NVDA sentiment")],
        }
    )

    human_count = sum(1 for m in captured["prompt"] if getattr(m, "type", "") in {"human", "user"})
    assert human_count == 1
