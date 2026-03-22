import threading
import pytest
from cli.stats_handler import StatsCallbackHandler
from langchain_core.outputs import LLMResult, Generation, ChatGeneration
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata

def test_stats_handler_initial_state():
    handler = StatsCallbackHandler()
    stats = handler.get_stats()
    assert stats == {
        "llm_calls": 0,
        "tool_calls": 0,
        "tokens_in": 0,
        "tokens_out": 0,
    }

def test_stats_handler_on_llm_start():
    handler = StatsCallbackHandler()
    handler.on_llm_start(serialized={}, prompts=["test"])
    assert handler.llm_calls == 1
    assert handler.get_stats()["llm_calls"] == 1

def test_stats_handler_on_chat_model_start():
    handler = StatsCallbackHandler()
    handler.on_chat_model_start(serialized={}, messages=[[]])
    assert handler.llm_calls == 1
    assert handler.get_stats()["llm_calls"] == 1

def test_stats_handler_on_tool_start():
    handler = StatsCallbackHandler()
    handler.on_tool_start(serialized={}, input_str="test tool")
    assert handler.tool_calls == 1
    assert handler.get_stats()["tool_calls"] == 1

def test_stats_handler_on_llm_end_with_usage():
    handler = StatsCallbackHandler()

    # ChatGeneration wraps chat messages; Generation (plain text) has no .message attr.
    usage_metadata = UsageMetadata(input_tokens=10, output_tokens=20, total_tokens=30)
    message = AIMessage(content="test response", usage_metadata=usage_metadata)
    generation = ChatGeneration(message=message)
    response = LLMResult(generations=[[generation]])

    handler.on_llm_end(response)

    stats = handler.get_stats()
    assert stats["tokens_in"] == 10
    assert stats["tokens_out"] == 20

def test_stats_handler_on_llm_end_no_usage():
    handler = StatsCallbackHandler()

    # Generation without message/usage_metadata
    generation = Generation(text="test response")
    response = LLMResult(generations=[[generation]])

    handler.on_llm_end(response)

    stats = handler.get_stats()
    assert stats["tokens_in"] == 0
    assert stats["tokens_out"] == 0

def test_stats_handler_on_llm_end_empty_generations():
    handler = StatsCallbackHandler()
    response = LLMResult(generations=[[]])
    handler.on_llm_end(response)

    response_none = LLMResult(generations=[])
    # on_llm_end does try response.generations[0][0], so generations=[] will trigger IndexError which is handled.
    handler.on_llm_end(response_none)

    assert handler.tokens_in == 0
    assert handler.tokens_out == 0

def test_stats_handler_thread_safety():
    handler = StatsCallbackHandler()
    num_threads = 10
    increments_per_thread = 100

    def worker():
        for _ in range(increments_per_thread):
            handler.on_llm_start({}, [])
            handler.on_tool_start({}, "")

            # ChatGeneration wraps chat messages with usage_metadata
            usage_metadata = UsageMetadata(input_tokens=1, output_tokens=1, total_tokens=2)
            message = AIMessage(content="x", usage_metadata=usage_metadata)
            generation = ChatGeneration(message=message)
            response = LLMResult(generations=[[generation]])
            handler.on_llm_end(response)

    threads = []
    for _ in range(num_threads):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    stats = handler.get_stats()
    expected_calls = num_threads * increments_per_thread
    assert stats["llm_calls"] == expected_calls
    assert stats["tool_calls"] == expected_calls
    assert stats["tokens_in"] == expected_calls
    assert stats["tokens_out"] == expected_calls
