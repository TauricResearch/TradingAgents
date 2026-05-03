from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.openai_client import (
    OpenAIClient,
    reject_retired_deepseek_model,
    strip_deepseek_reasoning_content,
)


def test_deepseek_catalog_defaults_to_v4_models():
    assert get_model_options("deepseek", "quick")[0][1] == "deepseek-v4-flash"
    assert get_model_options("deepseek", "deep")[0][1] == "deepseek-v4-pro"


def test_deepseek_old_model_names_are_rejected():
    for model in ("deepseek-chat", "deepseek-reasoner"):
        try:
            reject_retired_deepseek_model(model)
        except ValueError as exc:
            assert "deepseek-v4-flash" in str(exc)
            assert "deepseek-v4-pro" in str(exc)
        else:
            raise AssertionError(f"{model} should be rejected")


def test_deepseek_client_disables_thinking_by_default():
    llm = OpenAIClient(
        "deepseek-v4-pro",
        provider="deepseek",
        api_key="test-key",
    ).get_llm()

    assert llm.model_name == "deepseek-v4-pro"
    assert llm.extra_body == {"thinking": {"type": "disabled"}}


def test_deepseek_client_rejects_old_model_names():
    try:
        OpenAIClient(
            "deepseek-reasoner",
            provider="deepseek",
            api_key="test-key",
        ).get_llm()
    except ValueError as exc:
        assert "retired" in str(exc)
    else:
        raise AssertionError("deepseek-reasoner should be rejected")


def test_mimo_catalog_defaults_and_uses_anthropic_endpoint(monkeypatch):
    assert get_model_options("mimo", "quick")[0][1] == "mimo-v2.5"
    assert get_model_options("mimo", "deep")[0][1] == "mimo-v2.5-pro"

    monkeypatch.setenv("MIMO_API_KEY", "test-key")
    llm = create_llm_client("mimo", "mimo-v2.5").get_llm()

    assert llm.model == "mimo-v2.5"
    assert str(llm.anthropic_api_url) == "https://token-plan-sgp.xiaomimimo.com/anthropic"
    assert llm.anthropic_api_key.get_secret_value() == "test-key"


def test_strip_deepseek_reasoning_content_from_message_history():
    messages = [
        HumanMessage(content="Analyze AAPL"),
        AIMessage(
            content="",
            additional_kwargs={
                "reasoning_content": "private thinking",
                "tool_calls": [{"id": "call_1", "type": "function"}],
            },
        ),
        {
            "role": "assistant",
            "content": "final answer",
            "reasoning_content": "old thinking",
        },
    ]

    cleaned = strip_deepseek_reasoning_content(messages)

    assert "reasoning_content" not in cleaned[1].additional_kwargs
    assert cleaned[1].additional_kwargs["tool_calls"] == [{"id": "call_1", "type": "function"}]
    assert "reasoning_content" not in cleaned[2]
    assert "reasoning_content" in messages[1].additional_kwargs
    assert "reasoning_content" in messages[2]
