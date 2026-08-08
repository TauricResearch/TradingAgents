"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)`` while the tool takes a
``ticker``, tricking the LLM into hallucinating free-text query calls.
"""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

import tradingagents.agents.analysts.news_analyst as na
from tradingagents.agents.utils.news_data_tools import get_news


@pytest.mark.unit
def test_get_news_takes_ticker_not_query():
    arg_names = set(get_news.args.keys())
    assert "ticker" in arg_names
    assert "query" not in arg_names


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature(monkeypatch):
    captured = {}
    llm = MagicMock()

    def respond(prompt):
        captured["text"] = "\n".join(
            str(message.content) for message in prompt.to_messages()
        )
        return AIMessage(content="done")

    llm.bind_tools.return_value = RunnableLambda(respond)
    monkeypatch.setattr(na, "collected_media_enabled", lambda: False)

    na.create_news_analyst(llm)({
        "company_of_interest": "NVDA",
        "trade_date": "2026-01-15",
        "asset_type": "stock",
        "messages": [],
    })

    assert "get_news(ticker, start_date, end_date)" in captured["text"]
    assert "get_news(query" not in captured["text"]


@pytest.mark.unit
def test_historical_news_mode_exposes_no_revised_or_live_tools():
    historical = {tool.name for tool in na._tools_for_mode(True)}
    live = {tool.name for tool in na._tools_for_mode(False)}
    assert historical == {"get_news", "get_global_news"}
    assert {"get_macro_indicators", "get_insider_transactions", "get_prediction_markets"} \
        <= live


@pytest.mark.unit
def test_global_topics_only_exposes_no_ticker_news_tool():
    historical = {tool.name for tool in na._tools_for_mode(True, global_topics_only=True)}
    assert historical == {"get_global_news"}
