"""A partial ChatGPT response must be retried as a whole before committing output."""

import asyncio
from unittest import mock

import pytest
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from openai import APIConnectionError, AuthenticationError

from tradingagents.llm_clients.openai_client import ChatGPTPlanChatOpenAI


def _disconnect():
    error = APIConnectionError(request=mock.Mock())
    error.__cause__ = RuntimeError(
        "peer closed connection without sending complete message body (incomplete chunked read)"
    )
    return error


def _llm(retries=2):
    return ChatGPTPlanChatOpenAI(
        model="gpt-5.5", api_key="test-only", use_responses_api=True, max_retries=retries
    )


@pytest.mark.unit
def test_invoke_discards_partial_answer_and_retries_the_whole_request(monkeypatch):
    calls, waits = [], []
    monkeypatch.setattr("time.sleep", waits.append)

    def stream(self, messages, **kwargs):
        calls.append(messages)
        if len(calls) == 1:
            yield ChatGenerationChunk(message=AIMessageChunk(content="discard this partial answer"))
            raise _disconnect()
        yield ChatGenerationChunk(message=AIMessageChunk(content="complete answer"))

    monkeypatch.setattr(ChatGPTPlanChatOpenAI, "_stream", stream)
    result = _llm().invoke("same prompt")
    assert result.content == "complete answer"
    assert len(calls) == 2 and calls[0] == calls[1]
    assert waits == [1]


@pytest.mark.unit
@pytest.mark.parametrize("retries", [0, 2])
def test_persistent_disconnect_respects_retry_budget(monkeypatch, retries):
    calls, waits = [], []
    monkeypatch.setattr("time.sleep", waits.append)
    error = _disconnect()

    def stream(self, *args, **kwargs):
        calls.append(1)
        raise error
        yield  # make this a stream without emitting partial output

    monkeypatch.setattr(ChatGPTPlanChatOpenAI, "_stream", stream)
    with pytest.raises(APIConnectionError) as raised:
        _llm(retries).invoke("test")
    assert raised.value is error
    assert len(calls) == retries + 1
    assert waits == [1, 2][:retries]


@pytest.mark.unit
@pytest.mark.parametrize("kind", ["auth", "connect"])
def test_non_stream_failures_are_not_retried_again(monkeypatch, kind):
    calls = []
    error = (
        AuthenticationError("sign in again", response=mock.Mock(), body=None)
        if kind == "auth" else APIConnectionError(request=mock.Mock())
    )

    def stream(self, *args, **kwargs):
        calls.append(1)
        raise error
        yield

    monkeypatch.setattr(ChatGPTPlanChatOpenAI, "_stream", stream)
    with pytest.raises(type(error)):
        _llm().invoke("test")
    assert len(calls) == 1


@pytest.mark.unit
def test_async_invoke_discards_partial_answer_before_retry(monkeypatch):
    calls, waits = [], []

    async def sleep(delay):
        waits.append(delay)

    async def stream(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            yield ChatGenerationChunk(message=AIMessageChunk(content="partial"))
            raise _disconnect()
        yield ChatGenerationChunk(message=AIMessageChunk(content="complete"))

    monkeypatch.setattr("asyncio.sleep", sleep)
    monkeypatch.setattr(ChatGPTPlanChatOpenAI, "_astream", stream)
    result = asyncio.run(_llm().ainvoke("test"))
    assert result.content == "complete"
    assert len(calls) == 2 and waits == [1]
