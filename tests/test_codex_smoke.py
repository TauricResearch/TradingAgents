"""Live check against the ChatGPT-subscription Codex endpoint.

Skipped unless the smoke marker is selected explicitly *and* a real Codex login
exists, so CI, contributors without a ChatGPT subscription, and ordinary
`pytest -q` runs are all unaffected — each call here spends the user's
subscription quota. Run with: pytest -m smoke
"""
from __future__ import annotations

import pytest
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.llm_clients import codex_auth
from tradingagents.llm_clients.factory import create_llm_client


@pytest.fixture()
def codex_llm(request):
    """A live Codex client, or a skip when this run should not make live calls.

    The credential check is deliberately lazy: resolving at import time would
    read (and possibly rewrite) the real ~/.codex/auth.json during every plain
    `pytest -q` collection.
    """
    if "smoke" not in (request.config.getoption("-m") or ""):
        pytest.skip("live Codex call; select it explicitly with -m smoke")
    try:
        codex_auth.resolve()
    except codex_auth.CodexAuthError:
        pytest.skip("no Codex credentials; skipping live call")
    return create_llm_client("openai_codex", "gpt-5.4-mini").get_llm()


@pytest.mark.smoke
def test_codex_round_trip(codex_llm):
    response = codex_llm.invoke("Reply with exactly: ok")
    assert "ok" in response.content.lower()


@pytest.mark.smoke
def test_codex_system_prompt(codex_llm):
    # Every agent node drives the model through a ChatPromptTemplate whose first
    # message is a system message, so a bare-string round trip is not evidence
    # that this provider works — the raw `system` role 400s on this endpoint.
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You answer with exactly one word, always lowercase."),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    response = (prompt | codex_llm).invoke(
        {"messages": [("user", "What colour is a clear midday sky?")]}
    )

    assert "blue" in response.content.lower()


@pytest.mark.smoke
def test_codex_tool_call(codex_llm):
    # The analyst loop depends on function calling, so a chat-only round trip is
    # not sufficient evidence that this provider is usable.
    schema = {
        "title": "Decision",
        "type": "object",
        "properties": {"action": {"type": "string", "enum": ["BUY", "HOLD", "SELL"]}},
        "required": ["action"],
    }
    result = codex_llm.with_structured_output(schema, method="function_calling").invoke(
        "Rate AAPL."
    )
    assert result["action"] in {"BUY", "HOLD", "SELL"}
