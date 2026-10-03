"""Serialized Responses bodies, namespaced tool replay, and structured parse."""

from __future__ import annotations

import json
from collections.abc import Sequence

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.load import dumpd, load
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tradingagents.llm_clients import capabilities
from tradingagents.llm_clients.chatgpt_client import (
    PUBLIC_RESPONSES_BASE_URL,
    RESPONSES_OUTPUT_KEY,
    TOOL_NAMESPACE,
    ChatGPTClient,
    ChatGPTResponses,
    ChatGPTResponsesError,
)

pytestmark = pytest.mark.unit

ACCESS_TOKEN = "test-access-token"


class Quote(BaseModel):
    """A price quote."""

    ticker: str = Field(description="symbol")
    price: float


@tool
def get_price(ticker: str) -> str:
    """Look up a price."""
    return ticker


def _completed(output: list[dict], response_id: str = "resp_test") -> dict:
    return {
        "id": response_id,
        "object": "response",
        "created_at": 0,
        "model": "gpt-test",
        "status": "completed",
        "output": output,
        "store": False,
    }


def _sse(response: dict) -> bytes:
    event = {"type": "response.completed", "response": response}
    return f"event: response.completed\ndata: {json.dumps(event)}\n\n".encode()


class Recorder:
    def __init__(self, responses: Sequence[dict]):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            return httpx.Response(500, json={"error": "no fixture"})
        payload = _sse(self.responses.pop(0))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)


def _model(recorder: Recorder, **kwargs) -> ChatGPTResponses:
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    return ChatGPTResponses(
        model="gpt-test",
        api_key=ACCESS_TOKEN,
        http_client=client,
        **kwargs,
    )


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content.decode())


def _text_message(text: str, message_id: str = "msg_1") -> dict:
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def test_serialized_body_uses_public_responses_contract():
    recorder = Recorder([_completed([_text_message("Hello")])])
    message = _model(recorder).invoke(
        [SystemMessage("Be brief"), HumanMessage("Say hello")],
        temperature=0.2,
        max_output_tokens=16,
        previous_response_id="resp_stale",
    )
    request = recorder.requests[0]
    body = _body(request)
    assert request.url.host == "api.openai.com"
    assert request.url.scheme == "https"
    assert request.url.path == "/v1/responses"
    assert request.headers["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert body["model"] == "gpt-test"
    assert body["store"] is False
    assert body["stream"] is True
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["input"][0]["role"] == "developer"
    assert body["input"][0]["content"][0]["text"] == "Be brief"
    assert body["input"][1]["role"] == "user"
    assert "system" not in {item.get("role") for item in body["input"]}
    for key in ("temperature", "max_output_tokens", "max_tokens", "previous_response_id"):
        assert key not in body
    assert isinstance(message.content, str)
    assert message.content == "Hello"
    assert message.additional_kwargs[RESPONSES_OUTPUT_KEY][0]["type"] == "message"
    assert PUBLIC_RESPONSES_BASE_URL == "https://api.openai.com/v1"


def test_full_history_and_namespaced_tool_replay_survives_checkpoint():
    tool_output = [
        {
            "id": "rs_1",
            "type": "reasoning",
            "summary": [],
            "encrypted_content": "enc-abc",
        },
        _text_message("Looking up AAPL", "msg_lookup"),
        {
            "id": "fc_item_1",
            "type": "function_call",
            "call_id": "call_1",
            "name": "get_price",
            "namespace": TOOL_NAMESPACE,
            "arguments": '{"ticker": "AAPL"}',
            "status": "completed",
        },
    ]
    recorder = Recorder(
        [
            _completed(tool_output, "resp_tool"),
            _completed([_text_message("Done", "msg_done")], "resp_done"),
        ]
    )
    model = _model(recorder)
    first = model.bind_tools([get_price]).invoke(
        [SystemMessage("Stay factual"), HumanMessage("Price AAPL")]
    )
    first_body = _body(recorder.requests[0])
    namespace = first_body["tools"][0]
    assert namespace["type"] == "namespace"
    assert namespace["name"] == TOOL_NAMESPACE
    assert namespace["tools"][0]["name"] == "get_price"
    assert namespace["tools"][0]["type"] == "function"
    assert first_body["input"][0]["role"] == "developer"
    assert first_body["input"][1]["role"] == "user"
    assert "previous_response_id" not in first_body

    assert isinstance(first.content, str)
    assert first.content == "Looking up AAPL"
    assert [item["type"] for item in first.additional_kwargs[RESPONSES_OUTPUT_KEY]] == [
        "reasoning",
        "message",
        "function_call",
    ]
    assert first.additional_kwargs[RESPONSES_OUTPUT_KEY][0]["encrypted_content"] == "enc-abc"
    assert first.tool_calls[0]["id"] == "call_1"
    assert first.tool_calls[0]["id"] != "fc_item_1"
    assert first.tool_calls[0]["name"] == "get_price"
    assert first.tool_calls[0]["args"] == {"ticker": "AAPL"}

    restored = load(dumpd(first), allowed_objects="messages")
    assert isinstance(restored, AIMessage)
    assert restored.tool_calls[0]["id"] == "call_1"
    assert restored.additional_kwargs[RESPONSES_OUTPUT_KEY][0]["encrypted_content"] == "enc-abc"

    second = model.invoke(
        [
            SystemMessage("Stay factual"),
            HumanMessage("Price AAPL"),
            restored,
            ToolMessage(content="188.5", tool_call_id="call_1", name="get_price"),
            HumanMessage("Thanks"),
        ]
    )
    replay = _body(recorder.requests[1])["input"]
    assert [item.get("role") or item.get("type") for item in replay] == [
        "developer",
        "user",
        "reasoning",
        "assistant",
        "function_call",
        "function_call_output",
        "user",
    ]
    function_call = replay[4]
    assert function_call["name"] == "get_price"
    assert function_call["namespace"] == TOOL_NAMESPACE
    assert function_call["call_id"] == "call_1"
    assert function_call["arguments"] == '{"ticker": "AAPL"}'
    assert function_call["id"] == "fc_item_1"
    assert replay[2]["encrypted_content"] == "enc-abc"
    assert replay[5] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "188.5",
        "namespace": TOOL_NAMESPACE,
        "name": "get_price",
    }
    assert replay[3]["content"][0]["text"] == "Looking up AAPL"
    assert second.content == "Done"
    assert "previous_response_id" not in _body(recorder.requests[1])


def test_custom_tool_keeps_name_and_replays_namespace():
    recorder = Recorder(
        [
            _completed(
                [
                    {
                        "id": "ctc_1",
                        "type": "custom_tool_call",
                        "call_id": "call_c",
                        "name": "calc",
                        "namespace": TOOL_NAMESPACE,
                        "input": "1+1",
                    }
                ]
            )
        ]
    )
    custom = {"type": "custom", "name": "calc", "description": "Calculate"}
    message = _model(recorder).bind_tools([custom]).invoke("calc")
    tool_def = _body(recorder.requests[0])["tools"][0]["tools"][0]
    assert tool_def == {"type": "custom", "name": "calc", "description": "Calculate"}
    assert message.tool_calls[0]["id"] == "call_c"
    assert message.tool_calls[0]["name"] == "calc"
    assert message.content == ""

    recorder.responses.append(_completed([_text_message("2")]))
    _model(recorder).bind_tools([custom]).invoke(
        [
            message,
            ToolMessage(content="2", tool_call_id="call_c", name="calc"),
        ]
    )
    replay = _body(recorder.requests[1])["input"]
    assert replay[0]["type"] == "custom_tool_call"
    assert replay[0]["namespace"] == TOOL_NAMESPACE
    assert replay[0]["name"] == "calc"
    assert replay[0]["call_id"] == "call_c"
    assert replay[1]["type"] == "custom_tool_call_output"
    assert replay[1]["call_id"] == "call_c"


def test_structured_output_uses_namespaced_schema_and_include_raw():
    arguments = '{"ticker": "AAPL", "price": 1.5}'
    recorder = Recorder(
        [
            _completed(
                [
                    {
                        "id": "fc_schema",
                        "type": "function_call",
                        "call_id": "call_schema",
                        "name": "Quote",
                        "namespace": TOOL_NAMESPACE,
                        "arguments": arguments,
                        "status": "completed",
                    }
                ]
            ),
            _completed(
                [
                    {
                        "id": "fc_schema",
                        "type": "function_call",
                        "call_id": "call_schema",
                        "name": "Quote",
                        "namespace": TOOL_NAMESPACE,
                        "arguments": arguments,
                        "status": "completed",
                    }
                ]
            ),
            _completed(
                [
                    {
                        "id": "fc_bad",
                        "type": "function_call",
                        "call_id": "call_bad",
                        "name": "Quote",
                        "namespace": TOOL_NAMESPACE,
                        "arguments": '{"ticker": "AAPL"}',
                        "status": "completed",
                    }
                ]
            ),
        ]
    )
    model = _model(recorder)
    parsed = model.with_structured_output(Quote).invoke("quote")
    assert parsed == Quote(ticker="AAPL", price=1.5)
    body = _body(recorder.requests[0])
    assert body["tool_choice"] == "required"
    assert body["parallel_tool_calls"] is False
    assert "text" not in body
    namespace_tools = body["tools"][0]["tools"]
    assert [tool["name"] for tool in namespace_tools] == ["Quote"]
    assert namespace_tools[0]["parameters"]["type"] == "object"

    raw = model.with_structured_output(Quote, include_raw=True).invoke("quote")
    assert raw["parsing_error"] is None
    assert raw["parsed"] == Quote(ticker="AAPL", price=1.5)
    assert raw["raw"].tool_calls[0]["id"] == "call_schema"
    assert raw["raw"].tool_calls[0]["id"] != "fc_schema"
    assert raw["raw"].additional_kwargs[RESPONSES_OUTPUT_KEY][0]["namespace"] == TOOL_NAMESPACE

    failed = model.with_structured_output(Quote, include_raw=True).invoke("quote")
    assert failed["parsed"] is None
    assert isinstance(failed["parsing_error"], Exception)
    assert failed["raw"].tool_calls[0]["id"] == "call_bad"


def test_unknown_and_malformed_calls_are_rejected():
    unknown = _completed(
        [
            {
                "id": "fc_unknown",
                "type": "function_call",
                "call_id": "call_unknown",
                "name": "web_search",
                "namespace": TOOL_NAMESPACE,
                "arguments": "{}",
            }
        ]
    )
    wrong_namespace = _completed(
        [
            {
                "id": "fc_ns",
                "type": "function_call",
                "call_id": "call_ns",
                "name": "get_price",
                "namespace": "other",
                "arguments": '{"ticker": "AAPL"}',
            }
        ]
    )
    malformed = _completed(
        [
            {
                "id": "fc_bad",
                "type": "function_call",
                "call_id": "call_bad",
                "name": "get_price",
                "namespace": TOOL_NAMESPACE,
                "arguments": "[1, 2]",
            }
        ]
    )
    recorder = Recorder([unknown, wrong_namespace, malformed])
    model = _model(recorder).bind_tools([get_price])
    with pytest.raises(ChatGPTResponsesError, match="unknown function call"):
        model.invoke("search")
    with pytest.raises(ChatGPTResponsesError, match="namespace"):
        model.invoke("price")
    with pytest.raises(ChatGPTResponsesError, match="must be an object"):
        model.invoke("price")
    assert len(recorder.requests) == 3


def test_endpoint_token_and_malformed_extra_body_send_no_bearer():
    recorder = Recorder([_completed([_text_message("nope")])])
    model = _model(recorder)
    with pytest.raises(ValueError, match="custom endpoint"):
        ChatGPTResponses(
            model="gpt-test",
            api_key=ACCESS_TOKEN,
            base_url="https://evil.example/v1",
            http_client=model.http_client,
        )
    with pytest.raises(ValueError, match="custom endpoint"):
        ChatGPTClient("gpt-test", base_url="https://evil.example/v1", api_key=ACCESS_TOKEN)
    with pytest.raises(ChatGPTResponsesError, match="custom endpoint"):
        model.invoke("hi", base_url="https://evil.example/v1")
    with pytest.raises(ChatGPTResponsesError, match="token"):
        model.invoke("hi", api_key="other-token")
    with pytest.raises(ChatGPTResponsesError, match="malformed extra_body"):
        model.invoke("hi", extra_body={"base_url": "https://evil.example/v1"})
    with pytest.raises(ChatGPTResponsesError, match="malformed extra_body"):
        model.invoke("hi", extra_body=["temperature"])
    with pytest.raises(ChatGPTResponsesError, match="unsupported hosted tool"):
        model.bind_tools([{"type": "image_generation"}]).invoke("draw")
    with pytest.raises(ChatGPTResponsesError, match="bad tool schema"):
        model.invoke(
            "hi",
            tools=[{"type": "function", "function": {"name": "x", "parameters": ["bad"]}}],
        )
    assert recorder.requests == []


def test_previous_response_id_override_is_omitted_from_body():
    recorder = Recorder([_completed([_text_message("ok")])])
    _model(recorder).invoke(
        "hi",
        previous_response_id="resp_stale",
        temperature=0.4,
        max_tokens=8,
        extra_body={
            "previous_response_id": "resp_stale_body",
            "temperature": 0.9,
            "max_output_tokens": 5,
        },
    )
    body = _body(recorder.requests[0])
    for key in ("previous_response_id", "temperature", "max_output_tokens", "max_tokens"):
        assert key not in body
    assert body["store"] is False
    assert body["stream"] is True
    assert recorder.requests[0].url.host == "api.openai.com"


def test_prompt_runnable_and_callbacks_use_the_chat_model():
    class Handler(BaseCallbackHandler):
        def __init__(self):
            self.events: list[str] = []

        def on_chat_model_start(self, serialized, messages, **kwargs):
            self.events.append("start")

        def on_llm_end(self, response, **kwargs):
            self.events.append("end")

    recorder = Recorder([_completed([_text_message("Brief")])])
    model = _model(recorder)
    handler = Handler()
    prompt = ChatPromptTemplate.from_messages([("system", "Be brief"), ("human", "{question}")])
    result = (prompt | model).invoke({"question": "Hi"}, config={"callbacks": [handler]})
    body = _body(recorder.requests[0])
    assert body["input"][0]["role"] == "developer"
    assert body["input"][0]["content"][0]["text"] == "Be brief"
    assert body["input"][1]["content"][0]["text"] == "Hi"
    assert result.content == "Brief"
    assert handler.events == ["start", "end"]


def test_wrapper_drops_sampling_caps_and_does_not_change_capabilities():
    before = capabilities.get_capabilities("gpt-4.1")
    recorder = Recorder([_completed([_text_message("ok")])])
    client = ChatGPTClient(
        "gpt-4.1",
        api_key=ACCESS_TOKEN,
        temperature=0.3,
        max_tokens=20,
        http_client=httpx.Client(transport=httpx.MockTransport(recorder.handler)),
    )
    llm = client.get_llm()
    assert isinstance(llm, ChatGPTResponses)
    assert capabilities.get_capabilities("gpt-4.1") == before
    message = llm.invoke("hi")
    body = _body(recorder.requests[0])
    assert body["model"] == "gpt-4.1"
    assert "temperature" not in body
    assert "max_output_tokens" not in body
    assert message.content == "ok"


def test_use_previous_response_id_cannot_be_enabled():
    with pytest.raises(ValueError, match="use_previous_response_id"):
        ChatGPTResponses(model="gpt-test", api_key=ACCESS_TOKEN, use_previous_response_id=True)
    recorder = Recorder([_completed([_text_message("nope")])])
    with pytest.raises(ChatGPTResponsesError, match="use_previous_response_id"):
        _model(recorder).invoke("hi", use_previous_response_id=True)
    assert recorder.requests == []
