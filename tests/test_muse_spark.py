"""Muse must not use forced schema-tool calls (its API accepts only auto).

The transport regressions use real LangChain/OpenAI clients with a fake HTTP
transport: no provider credentials, model calls or market data are needed.
"""

import asyncio
import json

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients.capabilities import get_capabilities


@pytest.mark.parametrize("model", [
    "muse-spark-1.1", "muse-spark-1.2", "muse-spark-1.3",
    "muse-spark-1.2-contributor", "muse-spark-1.3-contributor",
])
def test_muse_prefers_native_schema_instead_of_forced_tool(model):
    caps = get_capabilities(model)
    assert caps.supports_tool_choice is False
    assert caps.supports_json_schema is True
    assert caps.preferred_structured_method == "json_schema"
    assert caps.requires_reasoning_content_roundtrip is False
    assert caps.requires_reasoning_split is False


@pytest.mark.parametrize("model,tool_choice", [
    ("gpt-6-luna", True),
    ("grok-4.7", True),
    ("glm-5.3-flash", True),
    ("deepseek-v4-pro", False),
    ("MiniMax-M3", False),
    ("other-publisher/muse-spark-1.3-contributor", True),
])
def test_other_models_keep_their_existing_structured_strategy(model, tool_choice):
    caps = get_capabilities(model)
    assert caps.preferred_structured_method == "function_calling"
    assert caps.supports_tool_choice is tool_choice


class _Report(BaseModel):
    """A schema-only report; it must not be represented as a forced tool."""

    summary: str
    score: int


def _response(model, protocol):
    text = json.dumps({"summary": "测试通过", "score": 1}, ensure_ascii=False)
    if protocol == "responses":
        return {
            "id": "resp_test", "object": "response", "created_at": 1,
            "model": model, "status": "completed", "error": None,
            "incomplete_details": None,
            "output": [{
                "id": "msg_test", "type": "message", "role": "assistant",
                "status": "completed", "content": [{
                    "type": "output_text", "text": text, "annotations": [],
                }],
            }],
            "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
        }
    return {
        "id": "chatcmpl_test", "object": "chat.completion", "created": 1,
        "model": model, "choices": [{
            "index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": text},
        }],
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }


@pytest.mark.parametrize("model", ["muse-spark-1.2-contributor", "muse-spark-1.3-contributor"])
@pytest.mark.parametrize("protocol", ["responses", "chat_completions"])
@pytest.mark.parametrize("asynchronous", [False, True])
def test_native_schema_reaches_http_without_forced_tool_choice(model, protocol, asynchronous):
    pytest.importorskip("langchain_openai")
    try:
        from langchain_openai._compat import httpx
    except ImportError:
        import httpx

    from tradingagents.llm_clients.factory import create_llm_client

    requests = []

    def handle(request):
        requests.append(request)
        payload = json.loads(request.content)
        # Model the rejection from the bug report rather than mocking the
        # binding method. Before the fix LangChain chooses a named function.
        if payload.get("tool_choice", "auto") != "auto":
            return httpx.Response(400, json={"error": {
                "message": 'only "auto" is supported for tool_choice',
                "type": "invalid_request_error", "param": "tool_choice",
                "code": None,
            }})
        return httpx.Response(200, json=_response(model, protocol))

    async def run():
        with httpx.Client(transport=httpx.MockTransport(handle)) as sync_client:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as async_client:
                common = {
                    "api_key": "test-only-key", "max_retries": 0,
                    "http_client": sync_client, "http_async_client": async_client,
                }
                if protocol == "responses":
                    # Go auto-routing, not a fabricated Chat Completions route
                    # for a Go model whose official endpoint is Responses.
                    client = create_llm_client("opencode-go", model, **common)
                else:
                    client = create_llm_client(
                        "openai_compatible", model, base_url="https://example.test/v1", **common
                    )
                structured = client.get_llm().with_structured_output(_Report)
                result = (await structured.ainvoke("Return a report in Chinese") if asynchronous
                          else structured.invoke("Return a report in Chinese"))
                assert isinstance(result, _Report)
                assert result.summary == "测试通过"
                assert result.score == 1

    asyncio.run(run())
    assert len(requests) == 1  # Valid structured response, no free-text retry.
    payload = json.loads(requests[0].content)
    assert "tool_choice" not in payload
    assert not payload.get("tools")
    if protocol == "responses":
        assert requests[0].url.path == "/zen/go/v1/responses"
        assert payload["text"]["format"]["type"] == "json_schema"
        assert "response_format" not in payload
        assert requests[0].headers["user-agent"].startswith("TradingAgents/")
        assert requests[0].headers["x-opencode-session"]
    else:
        assert requests[0].url.path == "/v1/chat/completions"
        assert payload["response_format"]["type"] == "json_schema"
