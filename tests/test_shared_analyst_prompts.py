from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from tradingagents.agents.analysts.fundamentals_analyst import (
    build_fundamentals_prompt,
    create_fundamentals_analyst,
)
from tradingagents.agents.analysts.market_analyst import build_market_prompt, create_market_analyst
from tradingagents.agents.analysts.news_analyst import build_news_prompt, create_news_analyst

BUILDERS = [build_market_prompt, build_news_prompt, build_fundamentals_prompt]


@pytest.mark.parametrize("builder", BUILDERS)
def test_analyst_context_and_explicit_language(builder, monkeypatch):
    from tradingagents.dataflows import config

    monkeypatch.setattr(config, "get_config", lambda: pytest.fail("global config read"))
    state = {"company_of_interest": "BTC-USD", "trade_date": "2026-09-10", "asset_type": "crypto"}
    prompt = builder(state, output_language="French")
    assert isinstance(prompt, str)
    assert "BTC-USD" in prompt and "2026-09-10" in prompt
    assert "crypto" in prompt and "French" in prompt


@pytest.mark.parametrize("builder", BUILDERS)
def test_direct_builders_keep_resolved_identity_and_do_not_fetch(builder, monkeypatch):
    import requests.sessions

    from tradingagents.agents.utils import agent_utils

    monkeypatch.setattr(requests.sessions.Session, "request", lambda *args, **kwargs: pytest.fail("network"))
    monkeypatch.setattr(
        agent_utils, "resolve_instrument_identity", lambda *args, **kwargs: pytest.fail("identity lookup")
    )
    prompt = builder(
        {
            "company_of_interest": "SHOP.TO",
            "trade_date": "2026-09-10",
            "instrument_context": "The instrument is SHOP.TO; Company: ACME {Holdings}.",
        },
        output_language="English",
    )
    assert "SHOP.TO" in prompt and "ACME {Holdings}" in prompt and "2026-09-10" in prompt
    assert "Write your entire response" not in prompt
    assert "If you are unable to fully answer, that's OK" in prompt


def test_market_builder_keeps_verified_snapshot_guidance():
    prompt = build_market_prompt(
        {"company_of_interest": "7203.T", "trade_date": "2026-09-10"}, output_language="English"
    )
    assert "get_verified_market_snapshot" in prompt
    assert "source of truth" in prompt


def test_fundamentals_builder_preserves_legacy_tuple_body():
    prompt = build_fundamentals_prompt(
        {"company_of_interest": "7203.T", "trade_date": "2026-09-10"}, output_language="English"
    )
    assert '("You are a researcher tasked with analyzing fundamental information' in prompt
    assert 'for specific financial statements.",)' in prompt


@pytest.mark.parametrize(
    ("factory", "builder", "report_key"),
    [
        (create_market_analyst, build_market_prompt, "market_report"),
        (create_news_analyst, build_news_prompt, "news_report"),
        (create_fundamentals_analyst, build_fundamentals_prompt, "fundamentals_report"),
    ],
)
def test_factories_send_their_direct_builder_prompt(factory, builder, report_key, monkeypatch):
    module = __import__(factory.__module__, fromlist=["config"])
    monkeypatch.setattr(module.config, "get_config", lambda: {"output_language": "French"})
    captured = {}
    llm = MagicMock()
    llm.bind_tools.return_value = RunnableLambda(
        lambda messages: captured.setdefault("messages", messages)
        and AIMessage(content="intermediate", tool_calls=[{"name": "get_news", "args": {}, "id": "1"}])
    )
    state = {
        "company_of_interest": "SHOP.TO",
        "trade_date": "2026-09-10",
        "instrument_context": "The instrument is SHOP.TO; Company: ACME {Holdings}.",
        "messages": [],
    }

    result = factory(llm)(state)

    assert captured["messages"].messages[0].content == builder(state, output_language="French")
    assert result[report_key] == ""
