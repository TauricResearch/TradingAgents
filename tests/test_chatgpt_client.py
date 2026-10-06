"""Serialized Responses bodies, namespaced tool replay, and structured parse."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence

import anyio
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
    ChatGPTSubscriptionError,
)

pytestmark = pytest.mark.unit

ACCESS_TOKEN = "test-access-token"


class FixtureSession:
    def __init__(self, token: str = ACCESS_TOKEN):
        self.token = token

    def access_token(self):
        return self.token


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


def _sse_events(events: Sequence[dict]) -> bytes:
    return b"".join(
        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode() for event in events
    )


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


class EventRecorder:
    def __init__(self, streams: Sequence[Sequence[dict]]):
        self.streams = [list(stream) for stream in streams]
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.streams:
            return httpx.Response(500, json={"error": {"message": "no fixture"}})
        payload = _sse_events(self.streams.pop(0))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=payload)


class AsyncEventStream(httpx.AsyncByteStream):
    def __init__(self, events: Sequence[dict]):
        self.events = list(events)
        self.closed = False

    async def __aiter__(self):
        yield _sse_events(self.events)

    async def aclose(self):
        self.closed = True


class AsyncEventRecorder:
    def __init__(self, streams: Sequence[Sequence[dict]]):
        self.streams = [list(stream) for stream in streams]
        self.requests: list[httpx.Request] = []
        self.responses: list[httpx.Response] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.streams:
            return httpx.Response(500, json={"error": {"message": "no fixture"}})
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=AsyncEventStream(self.streams.pop(0)),
        )
        self.responses.append(response)
        return response


def _model(recorder: Recorder, **kwargs) -> ChatGPTResponses:
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    kwargs.setdefault("auth_session", FixtureSession())
    return ChatGPTResponses(
        model="gpt-test",
        api_key=ACCESS_TOKEN,
        http_client=client,
        **kwargs,
    )


def _async_model(recorder: AsyncEventRecorder, **kwargs):
    client = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
    kwargs.setdefault("auth_session", FixtureSession())
    return (
        ChatGPTResponses(
            model="gpt-test",
            api_key=ACCESS_TOKEN,
            http_async_client=client,
            **kwargs,
        ),
        client,
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


def _function_call_item(
    arguments: str,
    item_id: str = "fc_done",
    call_id: str = "call_done",
) -> dict:
    return {
        "id": item_id,
        "type": "function_call",
        "call_id": call_id,
        "name": "get_price",
        "namespace": TOOL_NAMESPACE,
        "arguments": arguments,
        "status": "completed",
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
            base_url="https://evil.example/v1",
            http_client=model.http_client,
        )
    with pytest.raises(ValueError, match="custom endpoint"):
        ChatGPTClient("gpt-test", base_url="https://evil.example/v1")
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
        auth_session=FixtureSession(),
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
        ChatGPTResponses(model="gpt-test", use_previous_response_id=True)
    recorder = Recorder([_completed([_text_message("nope")])])
    with pytest.raises(ChatGPTResponsesError, match="use_previous_response_id"):
        _model(recorder).invoke("hi", use_previous_response_id=True)
    assert recorder.requests == []


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_interleaved_function_argument_deltas_are_confirmed_by_completed_output(
    async_invoke,
):
    output = [
        {
            "id": "fc_a",
            "type": "function_call",
            "call_id": "call_a",
            "name": "get_price",
            "namespace": TOOL_NAMESPACE,
            "arguments": '{"ticker":"AAPL"}',
            "status": "completed",
        },
        {
            "id": "fc_b",
            "type": "function_call",
            "call_id": "call_b",
            "name": "get_price",
            "namespace": TOOL_NAMESPACE,
            "arguments": '{"ticker":"MSFT"}',
            "status": "completed",
        },
    ]
    events = [
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_a",
            "output_index": 0,
            "delta": '{"ticker":"AA',
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_b",
            "output_index": 1,
            "delta": '{"ticker":"MSFT"}',
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_a",
            "output_index": 0,
            "delta": 'PL"}',
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_b",
            "output_index": 1,
            "arguments": '{"ticker":"MSFT"}',
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": "fc_a",
            "output_index": 0,
            "arguments": '{"ticker":"AAPL"}',
        },
        {"type": "response.completed", "response": _completed(output)},
    ]
    if async_invoke:
        recorder = AsyncEventRecorder([events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                return await model.bind_tools([get_price]).ainvoke("prices")

        message = anyio.run(call)
    else:
        recorder = EventRecorder([events])
        message = _model(recorder).bind_tools([get_price]).invoke("prices")
    assert [(call["id"], call["args"]) for call in message.tool_calls] == [
        ("call_a", {"ticker": "AAPL"}),
        ("call_b", {"ticker": "MSFT"}),
    ]
    assert len(recorder.requests) == 1


@pytest.mark.parametrize(
    "api",
    ["invoke", "stream", "ainvoke", "astream"],
)
def test_completed_tool_item_is_preserved_when_terminal_snapshot_omits_it(api):
    item = _function_call_item('{"ticker":"AAPL"}')
    reasoning = {
        "id": "rs_done",
        "type": "reasoning",
        "summary": [],
        "encrypted_content": "enc-done",
    }
    terminal_response = _completed([])
    terminal_response["usage"] = {
        "input_tokens": 8,
        "output_tokens": 3,
        "total_tokens": 11,
    }
    events = [
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": reasoning,
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": item,
        },
        {"type": "response.completed", "response": terminal_response},
    ]
    followup_events = [
        {"type": "response.completed", "response": _completed([_text_message("Done")])}
    ]

    if api in {"ainvoke", "astream"}:
        recorder = AsyncEventRecorder([events, followup_events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                if api == "ainvoke":
                    message = await model.bind_tools([get_price]).ainvoke("price")
                else:
                    chunks = [
                        chunk async for chunk in model.bind_tools([get_price]).astream("price")
                    ]
                    message = chunks[0]
                    for chunk in chunks[1:]:
                        message = message + chunk
                followup = await model.ainvoke(
                    [
                        HumanMessage("price"),
                        message,
                        ToolMessage(content="188.5", tool_call_id="call_done", name="get_price"),
                        HumanMessage("thanks"),
                    ]
                )
                return message, followup

        message, followup = anyio.run(call)
    else:
        recorder = EventRecorder([events, followup_events])
        model = _model(recorder).bind_tools([get_price])
        if api == "invoke":
            message = model.invoke("price")
        else:
            chunks = list(model.stream("price"))
            message = chunks[0]
            for chunk in chunks[1:]:
                message = message + chunk
        followup = model.invoke(
            [
                HumanMessage("price"),
                message,
                ToolMessage(content="188.5", tool_call_id="call_done", name="get_price"),
                HumanMessage("thanks"),
            ]
        )

    assert message.tool_calls == [
        {"name": "get_price", "args": {"ticker": "AAPL"}, "id": "call_done", "type": "tool_call"}
    ]
    output = message.additional_kwargs[RESPONSES_OUTPUT_KEY]
    assert [item["type"] for item in output] == ["reasoning", "function_call"]
    assert output[0]["encrypted_content"] == "enc-done"
    assert message.usage_metadata["total_tokens"] == 11
    assert followup.content == "Done"
    replay = _body(recorder.requests[1])["input"]
    assert replay[1]["type"] == "reasoning"
    assert replay[1]["encrypted_content"] == "enc-done"
    assert replay[2]["type"] == "function_call"
    assert replay[2]["call_id"] == "call_done"
    assert replay[3]["type"] == "function_call_output"
    assert replay[3]["call_id"] == "call_done"
    assert len(recorder.requests) == 2


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_added_tool_item_is_not_executable(async_invoke):
    events = [
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": _function_call_item('{"ticker":"AAPL"}'),
        },
        {"type": "response.completed", "response": _completed([])},
    ]
    if async_invoke:
        recorder = AsyncEventRecorder([events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                return await model.bind_tools([get_price]).ainvoke("price")

        message = anyio.run(call)
    else:
        recorder = EventRecorder([events])
        message = _model(recorder).bind_tools([get_price]).invoke("price")

    assert message.tool_calls == []
    assert message.additional_kwargs[RESPONSES_OUTPUT_KEY] == []
    assert len(recorder.requests) == 1


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
@pytest.mark.parametrize("terminal", ["failed", "incomplete", "quota", "missing"])
def test_done_tool_item_requires_successful_terminal_response(async_invoke, terminal):
    events = [
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": _function_call_item('{"ticker":"AAPL"}'),
        }
    ]
    if terminal == "failed":
        events.append(
            {
                "type": "response.failed",
                "response": {
                    "status": "failed",
                    "error": {"code": "server_error", "message": "fixture failure"},
                },
            }
        )
    elif terminal == "incomplete":
        events.append(
            {
                "type": "response.incomplete",
                "response": {"status": "incomplete"},
            }
        )
    elif terminal == "quota":
        events.append(
            {
                "type": "response.failed",
                "response": {
                    "status": "failed",
                    "error": {
                        "code": "subscription_sharing_usage_limit_exceeded",
                        "message": "fixture quota",
                    },
                },
            }
        )

    if async_invoke:
        recorder = AsyncEventRecorder([events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                with pytest.raises(ChatGPTSubscriptionError):
                    await model.bind_tools([get_price]).ainvoke("price")

        anyio.run(call)
    else:
        recorder = EventRecorder([events])
        with pytest.raises(ChatGPTSubscriptionError):
            _model(recorder).bind_tools([get_price]).invoke("price")

    assert len(recorder.requests) == 1


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_interrupted_stream_after_done_tool_item_is_terminal(async_invoke):
    item_event = {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": _function_call_item('{"ticker":"AAPL"}'),
    }
    requests: list[httpx.Request] = []

    class InterruptedSyncStream(httpx.SyncByteStream):
        def __iter__(self):
            yield _sse_events([item_event])
            raise httpx.ReadError("fixture stream interrupted")

    class InterruptedAsyncStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield _sse_events([item_event])
            raise httpx.ReadError("fixture stream interrupted")

        async def aclose(self):
            pass

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=InterruptedAsyncStream() if async_invoke else InterruptedSyncStream(),
        )

    if async_invoke:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        model = ChatGPTResponses(
            model="gpt-test",
            auth_session=FixtureSession(),
            http_async_client=client,
        )

        async def call():
            async with client:
                with pytest.raises(
                    ChatGPTSubscriptionError,
                    match="interrupted by a transport failure",
                ):
                    await model.bind_tools([get_price]).ainvoke("price")

        anyio.run(call)
    else:
        client = httpx.Client(transport=httpx.MockTransport(handle))
        model = ChatGPTResponses(
            model="gpt-test",
            auth_session=FixtureSession(),
            http_client=client,
        )
        try:
            with pytest.raises(
                ChatGPTSubscriptionError,
                match="interrupted by a transport failure",
            ):
                model.bind_tools([get_price]).invoke("price")
        finally:
            client.close()

    assert len(requests) == 1


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
@pytest.mark.parametrize("case", ["conflict", "malformed", "delta-mismatch"])
def test_completed_tool_item_conflicts_and_bad_arguments_fail_closed(async_invoke, case):
    item = _function_call_item('{"ticker":"AAPL"}')
    if case == "conflict":
        events = [
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": item,
            },
            {
                "type": "response.completed",
                "response": _completed([_function_call_item('{"ticker":"MSFT"}')]),
            },
        ]
    elif case == "malformed":
        events = [
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": _function_call_item("{malformed"),
            },
            {"type": "response.completed", "response": _completed([])},
        ]
    else:
        events = [
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 1,
                "delta": '{"ticker":"MSFT"}',
            },
            {
                "type": "response.output_item.done",
                "output_index": 1,
                "item": item,
            },
            {"type": "response.completed", "response": _completed([])},
        ]

    if async_invoke:
        recorder = AsyncEventRecorder([events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                with pytest.raises(ChatGPTSubscriptionError):
                    await model.bind_tools([get_price]).ainvoke("price")

        anyio.run(call)
    else:
        recorder = EventRecorder([events])
        with pytest.raises(ChatGPTSubscriptionError):
            _model(recorder).bind_tools([get_price]).invoke("price")

    assert len(recorder.requests) == 1


def test_completed_output_merges_in_output_index_order_without_duplicate_calls():
    first = _function_call_item('{"ticker":"AAPL"}', "fc_first", "call_first")
    second = _function_call_item('{"ticker":"MSFT"}', "fc_second", "call_second")
    recorder = EventRecorder(
        [
            [
                {"type": "response.output_item.done", "output_index": 1, "item": second},
                {"type": "response.output_item.done", "output_index": 0, "item": first},
                {"type": "response.completed", "response": _completed([first])},
            ]
        ]
    )

    message = _model(recorder).bind_tools([get_price]).invoke("price")

    assert [call["id"] for call in message.tool_calls] == ["call_first", "call_second"]
    assert [
        item["call_id"]
        for item in message.additional_kwargs[RESPONSES_OUTPUT_KEY]
        if item["type"] == "function_call"
    ] == ["call_first", "call_second"]


def test_stream_yields_text_and_completed_usage_for_sync_and_async_calls():
    response = _completed([_text_message("Hello")])
    response["usage"] = {"input_tokens": 4, "output_tokens": 2, "total_tokens": 6}
    events = [
        {"type": "response.output_text.delta", "delta": "Hel"},
        {"type": "response.output_text.delta", "delta": "lo"},
        {"type": "response.completed", "response": response},
    ]
    sync_recorder = EventRecorder([events])
    chunks = list(_model(sync_recorder).stream("hello"))
    assert "".join(chunk.content for chunk in chunks) == "Hello"
    assert chunks[-1].usage_metadata == {
        "input_tokens": 4,
        "output_tokens": 2,
        "total_tokens": 6,
    }

    async_recorder = AsyncEventRecorder([events])
    async_model, async_client = _async_model(async_recorder)

    async def invoke_async():
        async with async_client:
            return await async_model.ainvoke("hello")

    async_message = anyio.run(invoke_async)
    assert async_message.content == "Hello"
    assert async_message.usage_metadata["total_tokens"] == 6
    assert len(async_recorder.requests) == 1

    async_stream_recorder = AsyncEventRecorder([events])
    async_stream_model, async_stream_client = _async_model(async_stream_recorder)

    async def collect_async_stream():
        async with async_stream_client:
            return [chunk async for chunk in async_stream_model.astream("hello")]

    async_chunks = anyio.run(collect_async_stream)
    assert "".join(chunk.content for chunk in async_chunks) == "Hello"
    assert async_chunks[-1].usage_metadata["total_tokens"] == 6
    assert len(async_stream_recorder.requests) == 1


@pytest.mark.parametrize("api", ["astream", "ainvoke"])
def test_astream_cancel_closes_response_while_next_read_is_blocked(api):
    read_started = threading.Event()
    sync_release = threading.Event()
    sync_reader_done = threading.Event()
    responses: dict[str, httpx.Response] = {}

    class BlockingSyncStream(httpx.SyncByteStream):
        def __iter__(self):
            try:
                yield _sse_events([{"type": "response.output_text.delta", "delta": "provisional"}])
                read_started.set()
                sync_release.wait()
            finally:
                sync_reader_done.set()

    async def exercise():
        async_release = anyio.Event()
        async_stream_closed = anyio.Event()

        class BlockingAsyncStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield _sse_events([{"type": "response.output_text.delta", "delta": "provisional"}])
                read_started.set()
                await async_release.wait()

            async def aclose(self):
                async_stream_closed.set()
                async_release.set()

        def sync_handler(_: httpx.Request) -> httpx.Response:
            response = httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=BlockingSyncStream(),
            )
            responses["sync"] = response
            return response

        def async_handler(_: httpx.Request) -> httpx.Response:
            response = httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=BlockingAsyncStream(),
            )
            responses["async"] = response
            return response

        sync_client = httpx.Client(transport=httpx.MockTransport(sync_handler))
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(async_handler))
        model = ChatGPTResponses(
            model="gpt-test",
            auth_session=FixtureSession(),
            http_client=sync_client,
            http_async_client=async_client,
        )
        first_chunk = anyio.Event()
        yielded: list[str] = []

        async def consume():
            if api == "astream":
                async for chunk in model.astream("cancel during blocked read"):
                    yielded.append(chunk.content)
                    if chunk.content:
                        first_chunk.set()
            else:
                result = await model.ainvoke("cancel during blocked read")
                yielded.append(str(result.content))

        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(consume)
                with anyio.fail_after(2):
                    if api == "astream":
                        await first_chunk.wait()
                    assert await anyio.to_thread.run_sync(lambda: read_started.wait(2))
                task_group.cancel_scope.cancel()

            response = responses.get("async") or responses.get("sync")
            return bool(response and response.is_closed), yielded, async_stream_closed.is_set()
        finally:
            sync_release.set()
            async_release.set()
            await async_client.aclose()
            sync_client.close()

    closed_during_cancel, yielded, async_stream_closed = anyio.run(exercise)
    assert yielded == (["provisional"] if api == "astream" else [])
    assert closed_during_cancel
    assert async_stream_closed or "async" not in responses
    if "sync" in responses:
        assert sync_reader_done.wait(2)


def test_sync_stream_close_closes_response_after_first_delta():
    responses: list[httpx.Response] = []

    def handle(_: httpx.Request) -> httpx.Response:
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_events([{"type": "response.output_text.delta", "delta": "provisional"}]),
        )
        responses.append(response)
        return response

    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    stream = model.stream("close after a provisional delta")
    assert next(stream).content == "provisional"
    stream.close()
    assert responses[0].is_closed


@pytest.mark.parametrize(
    "events,match",
    [
        (
            [{"type": "response.incomplete", "response": {"status": "incomplete"}}],
            "response.incomplete",
        ),
        (
            [{"type": "response.output_text.delta", "delta": "partial"}],
            "without response.completed",
        ),
        (
            [
                {
                    "type": "error",
                    "error": {
                        "code": "permission_denied",
                        "param": "resource",
                        "message": "Plan access is not enabled.",
                    },
                }
            ],
            "Plan access is not enabled",
        ),
    ],
)
@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_non_completed_streams_are_terminal(events, match, async_invoke):
    if async_invoke:
        recorder = AsyncEventRecorder([events])
        model, client = _async_model(recorder)

        async def call():
            async with client:
                with pytest.raises(ChatGPTSubscriptionError, match=match):
                    await model.ainvoke("do not publish partial output")

        anyio.run(call)
    else:
        recorder = EventRecorder([events])
        with pytest.raises(ChatGPTSubscriptionError, match=match):
            _model(recorder).invoke("do not publish partial output")
    assert len(recorder.requests) == 1


def test_quota_failure_after_text_pauses_later_requests():
    recorder = EventRecorder(
        [
            [
                {"type": "response.output_text.delta", "delta": "partial"},
                {
                    "type": "response.failed",
                    "response": {
                        "status": "failed",
                        "error": {"code": "usage_limit_reached", "message": "quota"},
                    },
                },
            ],
            [{"type": "response.completed", "response": _completed([_text_message("no")])}],
        ]
    )

    class Session:
        def access_token(self):
            return ACCESS_TOKEN

    session = Session()
    client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    model = ChatGPTResponses(model="gpt-test", auth_session=session, http_client=client)
    another_model = ChatGPTResponses(model="gpt-test", auth_session=session, http_client=client)
    with pytest.raises(ChatGPTSubscriptionError, match="ChatGPT plan usage limit"):
        model.invoke("first")
    with pytest.raises(ChatGPTSubscriptionError, match="ChatGPT plan usage limit"):
        another_model.invoke("second")
    assert len(recorder.requests) == 1


def test_async_quota_failure_after_text_pauses_later_requests_for_shared_session():
    recorder = AsyncEventRecorder(
        [
            [
                {"type": "response.output_text.delta", "delta": "partial"},
                {
                    "type": "response.failed",
                    "response": {
                        "status": "failed",
                        "error": {"code": "usage_limit_reached", "message": "quota"},
                    },
                },
            ],
            [{"type": "response.completed", "response": _completed([_text_message("no")])}],
        ]
    )

    class Session:
        def access_token(self):
            return ACCESS_TOKEN

    session = Session()
    model, model_client = _async_model(recorder, auth_session=session)
    another_model, another_client = _async_model(recorder, auth_session=session)

    async def call():
        async with model_client:
            with pytest.raises(ChatGPTSubscriptionError, match="ChatGPT plan usage limit"):
                await model.ainvoke("first")
        async with another_client:
            with pytest.raises(ChatGPTSubscriptionError, match="ChatGPT plan usage limit"):
                await another_model.ainvoke("second")

    anyio.run(call)
    assert len(recorder.requests) == 1
    assert len(recorder.streams) == 1


def test_503_retries_before_deltas_and_refreshes_token_each_request():
    class TokenSource:
        calls = 0

        def access_token(self):
            self.calls += 1
            return f"fixture-access-{self.calls}"

    source = TokenSource()
    requests: list[httpx.Request] = []
    outcomes = iter(
        [
            httpx.Response(
                503,
                headers={"x-request-id": "req-transient"},
                json={"error": {"message": "temporary", "code": "server_error"}},
            ),
            httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse(_completed([_text_message("recovered")])),
            ),
        ]
    )

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return next(outcomes)

    client = ChatGPTResponses(
        model="gpt-test",
        api_key=ACCESS_TOKEN,
        auth_session=source,
        max_retries=1,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    assert client.invoke("retry").content == "recovered"
    assert len(requests) == source.calls == 2
    assert [request.headers["authorization"] for request in requests] == [
        "Bearer fixture-access-1",
        "Bearer fixture-access-2",
    ]


def test_async_503_retries_before_deltas_and_refreshes_token_each_request():
    class TokenSource:
        calls = 0

        def access_token(self):
            self.calls += 1
            return f"fixture-access-{self.calls}"

    source = TokenSource()
    requests: list[httpx.Request] = []
    outcomes = [
        httpx.Response(
            503,
            headers={"x-request-id": "req-async-transient"},
            json={"error": {"message": "temporary", "code": "server_error"}},
        ),
        httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=AsyncEventStream(
                [
                    {
                        "type": "response.completed",
                        "response": _completed([_text_message("recovered")]),
                    }
                ]
            ),
        ),
    ]

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return outcomes.pop(0)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=source,
        max_retries=1,
        http_async_client=client,
    )

    async def call():
        async with client:
            return await model.ainvoke("retry")

    assert anyio.run(call).content == "recovered"
    assert len(requests) == source.calls == 2
    assert [request.headers["authorization"] for request in requests] == [
        "Bearer fixture-access-1",
        "Bearer fixture-access-2",
    ]


def test_503_after_text_is_not_replayed():
    request_count = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_events(
                [
                    {"type": "response.output_text.delta", "delta": "partial"},
                    {
                        "type": "response.failed",
                        "response": {
                            "status": "failed",
                            "error": {"code": "server_error", "message": "overloaded"},
                        },
                    },
                ]
            ),
        )

    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        max_retries=2,
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(ChatGPTSubscriptionError, match="overloaded"):
        model.invoke("do not replay")
    assert request_count == 1


@pytest.mark.parametrize(
    "event,max_retries",
    [
        (
            {
                "type": "response.created",
                "sequence_number": 0,
                "response": {
                    "id": "resp_created",
                    "object": "response",
                    "created_at": 0,
                    "model": "gpt-test",
                    "status": "in_progress",
                    "output": [],
                },
            },
            1,
        ),
        (
            {
                "type": "response.function_call_arguments.delta",
                "sequence_number": 1,
                "item_id": "fc_interrupted",
                "output_index": 0,
                "delta": '{"ticker":"A',
            },
            2,
        ),
    ],
)
@pytest.mark.parametrize("async_invoke", [False, True])
def test_interrupted_stream_after_any_event_is_not_retried(event, max_retries, async_invoke):
    class InterruptedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield (f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode())
            raise httpx.ReadError("fixture stream interrupted")

    class AsyncInterruptedStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
            raise httpx.ReadError("fixture stream interrupted")

        async def aclose(self):
            pass

    request_count = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=AsyncInterruptedStream() if async_invoke else InterruptedStream(),
        )

    if async_invoke:
        async_client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        model = ChatGPTResponses(
            model="gpt-test",
            auth_session=FixtureSession(),
            max_retries=max_retries,
            http_async_client=async_client,
        )

        async def call():
            async with async_client:
                with pytest.raises(
                    ChatGPTSubscriptionError,
                    match="interrupted by a transport failure",
                ):
                    await model.ainvoke("do not retry a consumed stream")

        anyio.run(call)
    else:
        model = ChatGPTResponses(
            model="gpt-test",
            auth_session=FixtureSession(),
            max_retries=max_retries,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        )
        with pytest.raises(
            ChatGPTSubscriptionError,
            match="interrupted by a transport failure",
        ):
            model.invoke("do not retry a consumed stream")
    assert request_count == 1


def test_detail_only_http_admission_error_preserves_request_metadata():
    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            headers={"x-request-id": "req-admission"},
            json={"error": {"message": "Subscription access is pending."}},
        )

    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        http_client=httpx.Client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(ChatGPTSubscriptionError, match="Subscription access is pending") as error:
        model.invoke("access check")
    assert error.value.status_code == 403
    assert error.value.request_id == "req-admission"


def test_async_detail_only_http_admission_error_preserves_request_metadata():
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            403,
            headers={"x-request-id": "req-async-admission"},
            json={"error": {"message": "Subscription access is pending."}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        http_async_client=client,
    )

    async def call():
        async with client:
            with pytest.raises(
                ChatGPTSubscriptionError,
                match="Subscription access is pending",
            ) as error:
                await model.ainvoke("access check")
            assert error.value.status_code == 403
            assert error.value.request_id == "req-async-admission"

    anyio.run(call)
    assert len(requests) == 1


def test_revoked_auth_is_terminal_before_responses_request():
    from tradingagents.llm_clients.chatgpt_auth import ReauthorizationRequired

    class RevokedSession:
        def access_token(self):
            raise ReauthorizationRequired("Sign in again to continue.")

    recorder = Recorder([])
    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=RevokedSession(),
        http_client=httpx.Client(transport=httpx.MockTransport(recorder.handler)),
    )
    with pytest.raises(ChatGPTSubscriptionError, match="Sign in again"):
        model.invoke("auth is revoked")
    assert recorder.requests == []


def test_async_revoked_auth_is_terminal_before_responses_request():
    from tradingagents.llm_clients.chatgpt_auth import ReauthorizationRequired

    class RevokedSession:
        def access_token(self):
            raise ReauthorizationRequired("Sign in again to continue.")

    recorder = AsyncEventRecorder([])
    model, client = _async_model(recorder, auth_session=RevokedSession())

    async def call():
        async with client:
            with pytest.raises(ChatGPTSubscriptionError, match="Sign in again"):
                await model.ainvoke("auth is revoked")

    anyio.run(call)
    assert recorder.requests == []


@pytest.mark.parametrize("failure_surface", ["http", "sse"])
@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_subscription_usage_limit_stops_later_shared_session_requests(
    failure_surface, async_invoke
):
    code = "subscription_sharing_usage_limit_exceeded"
    requests: list[httpx.Request] = []

    class Session:
        def access_token(self):
            return ACCESS_TOKEN

    session = Session()

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1 and failure_surface == "http":
            return httpx.Response(
                429,
                headers={"x-request-id": "req-quota-limit"},
                json={
                    "error": {
                        "code": code,
                        "message": "Usage limit exceeded.",
                        "param": "model",
                    }
                },
            )
        if len(requests) == 1:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse_events(
                    [
                        {"type": "response.output_text.delta", "delta": "partial"},
                        {
                            "type": "response.failed",
                            "response": {
                                "status": "failed",
                                "error": {
                                    "code": code,
                                    "message": "Usage limit exceeded.",
                                    "param": "model",
                                },
                            },
                        },
                    ]
                ),
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_completed([_text_message("must not be requested")])),
        )

    clients = [
        httpx.AsyncClient(transport=httpx.MockTransport(handle))
        if async_invoke
        else httpx.Client(transport=httpx.MockTransport(handle))
        for _ in range(2)
    ]
    first = ChatGPTResponses(
        model="gpt-test",
        auth_session=session,
        **({"http_async_client": clients[0]} if async_invoke else {"http_client": clients[0]}),
    )
    second = ChatGPTResponses(
        model="gpt-test",
        auth_session=session,
        **({"http_async_client": clients[1]} if async_invoke else {"http_client": clients[1]}),
    )

    if async_invoke:

        async def call():
            async with clients[0], clients[1]:
                with pytest.raises(ChatGPTSubscriptionError) as first_error:
                    await first.ainvoke("first")
                second_error = None
                try:
                    await second.ainvoke("second")
                except ChatGPTSubscriptionError as error:
                    second_error = error
                assert len(requests) == 1
                assert second_error is not None
                assert second_error.code == "usage_limit_reached"
                assert first_error.value.code == code
                assert first_error.value.status_code == 429
                assert first_error.value.param == "model"
                if failure_surface == "http":
                    assert first_error.value.request_id == "req-quota-limit"

        anyio.run(call)
    else:
        try:
            with pytest.raises(ChatGPTSubscriptionError) as first_error:
                first.invoke("first")
            second_error = None
            try:
                second.invoke("second")
            except ChatGPTSubscriptionError as error:
                second_error = error
            assert len(requests) == 1
            assert second_error is not None
            assert second_error.code == "usage_limit_reached"
            assert first_error.value.code == code
            assert first_error.value.status_code == 429
            assert first_error.value.param == "model"
            if failure_surface == "http":
                assert first_error.value.request_id == "req-quota-limit"
        finally:
            for client in clients:
                client.close()

    assert len(requests) == 1


@pytest.mark.parametrize("failure_surface", ["http", "sse"])
@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_subscription_usage_unavailable_remains_transient(failure_surface, async_invoke):
    code = "subscription_sharing_usage_unavailable"
    requests: list[httpx.Request] = []

    class Session:
        def access_token(self):
            return ACCESS_TOKEN

    session = Session()

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1 and failure_surface == "http":
            return httpx.Response(
                503,
                headers={"x-request-id": "req-usage-unavailable"},
                json={
                    "error": {
                        "code": code,
                        "message": "Usage availability could not be checked.",
                        "param": "model",
                    }
                },
            )
        if len(requests) == 1:
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse_events(
                    [
                        {
                            "type": "response.failed",
                            "response": {
                                "status": "failed",
                                "error": {
                                    "code": code,
                                    "message": "Usage availability could not be checked.",
                                    "param": "model",
                                },
                            },
                        }
                    ]
                ),
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_completed([_text_message("available again")])),
        )

    clients = [
        httpx.AsyncClient(transport=httpx.MockTransport(handle))
        if async_invoke
        else httpx.Client(transport=httpx.MockTransport(handle))
        for _ in range(2)
    ]
    first = ChatGPTResponses(
        model="gpt-test",
        auth_session=session,
        max_retries=1,
        **({"http_async_client": clients[0]} if async_invoke else {"http_client": clients[0]}),
    )
    second = ChatGPTResponses(
        model="gpt-test",
        auth_session=session,
        **({"http_async_client": clients[1]} if async_invoke else {"http_client": clients[1]}),
    )

    if async_invoke:

        async def call():
            async with clients[0], clients[1]:
                if failure_surface == "sse":
                    with pytest.raises(ChatGPTSubscriptionError) as error:
                        await first.ainvoke("temporary unavailable")
                    assert error.value.code == code
                    assert error.value.param == "model"
                else:
                    assert (
                        await first.ainvoke("temporary unavailable")
                    ).content == "available again"
                assert (await second.ainvoke("try later")).content == "available again"

        anyio.run(call)
    else:
        try:
            if failure_surface == "sse":
                with pytest.raises(ChatGPTSubscriptionError) as error:
                    first.invoke("temporary unavailable")
                assert error.value.code == code
                assert error.value.param == "model"
            else:
                assert first.invoke("temporary unavailable").content == "available again"
            assert second.invoke("try later").content == "available again"
        finally:
            for client in clients:
                client.close()

    assert len(requests) == (3 if failure_surface == "http" else 2)


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_subscription_usage_unavailable_http_error_preserves_metadata(async_invoke):
    requests: list[httpx.Request] = []

    class Session:
        def access_token(self):
            return ACCESS_TOKEN

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                503,
                headers={"x-request-id": "req-usage-unavailable"},
                json={
                    "error": {
                        "code": "subscription_sharing_usage_unavailable",
                        "message": "Usage availability could not be checked.",
                        "param": "model",
                    }
                },
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_completed([_text_message("available again")])),
        )

    clients = [
        httpx.AsyncClient(transport=httpx.MockTransport(handle))
        if async_invoke
        else httpx.Client(transport=httpx.MockTransport(handle))
        for _ in range(2)
    ]
    first = ChatGPTResponses(
        model="gpt-test",
        auth_session=Session(),
        **({"http_async_client": clients[0]} if async_invoke else {"http_client": clients[0]}),
    )
    second = ChatGPTResponses(
        model="gpt-test",
        auth_session=first.auth_session,
        **({"http_async_client": clients[1]} if async_invoke else {"http_client": clients[1]}),
    )

    if async_invoke:

        async def call():
            async with clients[0], clients[1]:
                with pytest.raises(ChatGPTSubscriptionError) as error:
                    await first.ainvoke("temporary unavailable")
                assert error.value.status_code == 503
                assert error.value.code == "subscription_sharing_usage_unavailable"
                assert error.value.param == "model"
                assert error.value.request_id == "req-usage-unavailable"
                assert (await second.ainvoke("try later")).content == "available again"

        anyio.run(call)
    else:
        try:
            with pytest.raises(ChatGPTSubscriptionError) as error:
                first.invoke("temporary unavailable")
            assert error.value.status_code == 503
            assert error.value.code == "subscription_sharing_usage_unavailable"
            assert error.value.param == "model"
            assert error.value.request_id == "req-usage-unavailable"
            assert second.invoke("try later").content == "available again"
        finally:
            for client in clients:
                client.close()

    assert len(requests) == 2


def test_wrapper_serializes_configured_reasoning_effort():
    recorder = Recorder([_completed([_text_message("reasoned")])])
    http_client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    client = ChatGPTClient(
        "gpt-5.6-luna",
        api_key=ACCESS_TOKEN,
        auth_session=FixtureSession(),
        reasoning_effort="high",
        http_client=http_client,
    )

    try:
        message = client.get_llm().invoke("use the configured reasoning effort")
    finally:
        http_client.close()

    assert message.content == "reasoned"
    assert _body(recorder.requests[0])["reasoning"] == {"effort": "high"}


@pytest.mark.parametrize("async_invoke", [False, True], ids=["invoke", "ainvoke"])
def test_only_pinned_session_supplies_the_bearer_token(monkeypatch, async_invoke):
    api_key_sentinel = "api-key-sentinel"
    ambient_sentinel = "ambient-token-sentinel"
    session_token = "pinned-session-token"
    monkeypatch.setenv("ACCESS_TOKEN", ambient_sentinel)

    if async_invoke:
        recorder = AsyncEventRecorder(
            [[{"type": "response.completed", "response": _completed([_text_message("ok")])}]]
        )
        transport = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        model = ChatGPTResponses(
            model="gpt-test",
            api_key=api_key_sentinel,
            http_async_client=transport,
        )

        async def call_without_session():
            async with transport:
                with pytest.raises(
                    ChatGPTResponsesError,
                    match="pinned app-owned session",
                ):
                    await model.ainvoke("no credentials may be used")

        anyio.run(call_without_session)
        assert recorder.requests == []

        recorder = AsyncEventRecorder(
            [[{"type": "response.completed", "response": _completed([_text_message("ok")])}]]
        )
        transport = httpx.AsyncClient(transport=httpx.MockTransport(recorder.handler))
        model = ChatGPTResponses(
            model="gpt-test",
            api_key=api_key_sentinel,
            auth_session=FixtureSession(session_token),
            http_async_client=transport,
        )

        async def call_with_session():
            async with transport:
                await model.ainvoke("use the pinned session")

        anyio.run(call_with_session)
    else:
        recorder = Recorder([_completed([_text_message("ok")])])
        transport = httpx.Client(transport=httpx.MockTransport(recorder.handler))
        model = ChatGPTResponses(
            model="gpt-test",
            api_key=api_key_sentinel,
            http_client=transport,
        )
        with pytest.raises(
            ChatGPTResponsesError,
            match="pinned app-owned session",
        ):
            model.invoke("no credentials may be used")
        assert recorder.requests == []

        recorder = Recorder([_completed([_text_message("ok")])])
        transport = httpx.Client(transport=httpx.MockTransport(recorder.handler))
        model = ChatGPTResponses(
            model="gpt-test",
            api_key=api_key_sentinel,
            auth_session=FixtureSession(session_token),
            http_client=transport,
        )
        model.invoke("use the pinned session")

    assert len(recorder.requests) == 1
    assert recorder.requests[0].headers["authorization"] == f"Bearer {session_token}"


@pytest.mark.parametrize(
    "outcome",
    ["success", "provider-error", "retry-exhaustion", "generator-close"],
)
def test_owned_sync_sdk_client_closes_on_every_stream_exit(monkeypatch, outcome):
    from tradingagents.llm_clients import chatgpt_client

    class TrackedClient(httpx.Client):
        pass

    request_count = 0

    def handle(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if outcome == "provider-error":
            return httpx.Response(403, json={"error": {"message": "denied"}})
        if outcome == "retry-exhaustion":
            return httpx.Response(503, json={"error": {"code": "server_error"}})
        if outcome == "generator-close":
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_sse_events([{"type": "response.output_text.delta", "delta": "partial"}]),
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(_completed([_text_message("complete")])),
        )

    original_openai = chatgpt_client.OpenAI
    sdk_clients = []

    def make_openai(**kwargs):
        transport = TrackedClient(transport=httpx.MockTransport(handle))
        kwargs["http_client"] = transport
        client = original_openai(**kwargs)
        sdk_clients.append(client)
        return client

    monkeypatch.setattr(chatgpt_client, "OpenAI", make_openai)
    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        max_retries=1,
    )

    if outcome == "provider-error":
        with pytest.raises(ChatGPTSubscriptionError):
            model.invoke("provider error")
    elif outcome == "retry-exhaustion":
        with pytest.raises(ChatGPTSubscriptionError):
            model.invoke("retry exhaustion")
        assert request_count == 2
    elif outcome == "generator-close":
        stream = model.stream("cancel after first delta")
        assert next(stream).content == "partial"
        stream.close()
    else:
        assert model.invoke("success").content == "complete"

    assert sdk_clients
    assert all(client.is_closed() for client in sdk_clients)


def test_injected_sync_http_client_remains_caller_owned():
    recorder = Recorder([_completed([_text_message("ok")])])
    http_client = httpx.Client(transport=httpx.MockTransport(recorder.handler))
    model = ChatGPTResponses(
        model="gpt-test",
        auth_session=FixtureSession(),
        http_client=http_client,
    )

    try:
        assert model.invoke("shared transport").content == "ok"
        assert not http_client.is_closed
    finally:
        http_client.close()
