import threading
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage
from langchain_core.outputs import LLMResult, ChatGeneration
from api.callbacks.token_handler import TokenCallbackHandler


def _make_response(input_tokens: int, output_tokens: int) -> LLMResult:
    """Build a minimal LLMResult that on_llm_end will parse."""
    msg = AIMessage(content="ok")
    msg.usage_metadata = {"input_tokens": input_tokens, "output_tokens": output_tokens}
    gen = ChatGeneration(message=msg)
    return LLMResult(generations=[[gen]])


def test_snapshot_and_reset_returns_delta():
    handler = TokenCallbackHandler()
    handler.on_llm_end(_make_response(100, 40))
    result = handler.snapshot_and_reset()
    assert result == {"in": 100, "out": 40}


def test_snapshot_and_reset_zeroes_counters():
    handler = TokenCallbackHandler()
    handler.on_llm_end(_make_response(100, 40))
    handler.snapshot_and_reset()
    second = handler.snapshot_and_reset()
    assert second == {"in": 0, "out": 0}


def test_multiple_llm_calls_accumulate():
    handler = TokenCallbackHandler()
    handler.on_llm_end(_make_response(100, 40))
    handler.on_llm_end(_make_response(200, 60))
    result = handler.snapshot_and_reset()
    assert result == {"in": 300, "out": 100}


def test_concurrent_on_llm_end_does_not_corrupt():
    handler = TokenCallbackHandler()
    threads = [
        threading.Thread(target=handler.on_llm_end, args=(_make_response(10, 5),))
        for _ in range(20)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    result = handler.snapshot_and_reset()
    assert result == {"in": 200, "out": 100}


def test_missing_usage_metadata_does_not_crash():
    handler = TokenCallbackHandler()
    msg = AIMessage(content="no metadata")
    # No usage_metadata attribute
    gen = ChatGeneration(message=msg)
    response = LLMResult(generations=[[gen]])
    handler.on_llm_end(response)  # should not raise
    assert handler.snapshot_and_reset() == {"in": 0, "out": 0}


def test_empty_outer_generations_does_not_crash():
    handler = TokenCallbackHandler()
    response = LLMResult(generations=[])
    handler.on_llm_end(response)  # IndexError guard
    assert handler.snapshot_and_reset() == {"in": 0, "out": 0}


def test_empty_inner_generations_does_not_crash():
    handler = TokenCallbackHandler()
    response = LLMResult(generations=[[]])
    handler.on_llm_end(response)  # IndexError guard
    assert handler.snapshot_and_reset() == {"in": 0, "out": 0}
