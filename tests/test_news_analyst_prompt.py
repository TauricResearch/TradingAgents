"""Guard the news analyst prompt against tool-signature drift (#1116).

The prompt used to advertise ``get_news(query, ...)``, tricking the LLM into
hallucinating free-text query calls. The instrument now comes from the run's
state, so the model passes only the window.
"""
import inspect

import pytest

import tradingagents.agents.analysts.news_analyst as na
from tradingagents.agents.tools import get_news


@pytest.mark.unit
def test_get_news_takes_the_window_not_a_query():
    arg_names = set(get_news.tool_call_schema.model_json_schema()["properties"])
    assert arg_names == {"start_date", "end_date"}


@pytest.mark.unit
def test_news_prompt_matches_get_news_signature():
    src = inspect.getsource(na)
    assert "get_news(start_date, end_date)" in src
    assert "get_news(query" not in src


@pytest.mark.unit
def test_news_prompt_uses_configured_lookback(monkeypatch):
    from types import SimpleNamespace

    captured = {}

    def fake_take_turn(prompt, llm, tools, messages):
        captured["system"] = prompt.partial_variables["system_message"]
        return SimpleNamespace(content=""), ""

    monkeypatch.setattr(na, "get_config", lambda: {"news_lookback_days": 30})
    monkeypatch.setattr(na, "take_turn", fake_take_turn)
    monkeypatch.setattr(na, "get_instrument_context_from_state", lambda state: "")
    na.create_news_analyst(llm=None)({"trade_date": "2026-10-13", "messages": []})
    assert "past 30 days" in captured["system"]
    assert "past week" not in captured["system"]
