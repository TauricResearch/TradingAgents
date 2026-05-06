"""Integration test for end-to-end RunLogger telemetry.

Validates: Requirements 5.4

Verifies that a mocked graph execution producing LLM calls results in
non-zero `llm_calls` in the `run_log.jsonl` summary block.
"""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, LLMResult

from tradingagents.observability import RunLogger


def _make_llm_result(tokens_in: int, tokens_out: int) -> LLMResult:
    """Build a realistic LLMResult with usage metadata, as LangChain would emit."""
    usage = UsageMetadata(
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        total_tokens=tokens_in + tokens_out,
    )
    message = AIMessage(content="mocked response", usage_metadata=usage)
    generation = ChatGeneration(message=message)
    return LLMResult(generations=[[generation]])


def test_e2e_telemetry_nonzero_llm_calls(tmp_path):
    """End-to-end: mocked graph execution produces non-zero llm_calls in run_log.jsonl.

    Simulates the full callback path that occurs during a real graph execution:
    1. Engine creates a RunLogger and passes rl.callback to graph config
    2. LangGraph fires on_chat_model_start for each LLM invocation
    3. LangGraph fires on_llm_end with token usage in response metadata
    4. Engine calls rl.write_log() at run end
    5. run_log.jsonl summary block reflects accurate counters

    This mirrors the wiring in LangGraphEngine.run_scan / run_pipeline / run_portfolio
    where config={"callbacks": [rl.callback]} is passed to astream_events.
    """
    run_id = str(uuid.uuid4())
    rl = RunLogger(run_id=run_id)

    # Simulate 3 LLM calls as they would fire through the LangChain callback system
    # during a graph execution (e.g., analyst nodes calling ChatOpenAI).
    simulated_calls = [
        {"model": "gpt-4o", "agent": "Market Analyst", "tokens_in": 1500, "tokens_out": 800},
        {"model": "gpt-4o", "agent": "News Analyst", "tokens_in": 2000, "tokens_out": 1200},
        {"model": "gpt-4o", "agent": "Fundamentals Analyst", "tokens_in": 1800, "tokens_out": 950},
    ]

    for call in simulated_calls:
        # Each LLM invocation triggers on_chat_model_start then on_llm_end
        call_run_id = uuid.uuid4()
        rl.callback.on_chat_model_start(
            serialized={"kwargs": {"model_name": call["model"]}},
            messages=[[AIMessage(content="system prompt")]],
            run_id=call_run_id,
            name=call["agent"],
        )
        rl.callback.on_llm_end(
            response=_make_llm_result(call["tokens_in"], call["tokens_out"]),
            run_id=call_run_id,
        )

    # Write the log as the engine would at run completion
    log_path = tmp_path / "run_log.jsonl"
    rl.write_log(log_path)

    # Parse the JSONL file and find the summary block
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) >= 4, f"Expected at least 3 event lines + 1 summary, got {len(lines)}"

    summary_line = json.loads(lines[-1])
    assert summary_line["kind"] == "summary"

    # Core assertion: non-zero llm_calls in the summary
    assert summary_line["llm_calls"] > 0, (
        f"Expected non-zero llm_calls in run_log.jsonl summary, got {summary_line['llm_calls']}"
    )
    # Verify exact counts match our simulated calls
    assert summary_line["llm_calls"] == 3
    assert summary_line["tokens_in"] == 1500 + 2000 + 1800
    assert summary_line["tokens_out"] == 800 + 1200 + 950
    assert summary_line["tokens_total"] == summary_line["tokens_in"] + summary_line["tokens_out"]


def test_e2e_telemetry_callback_captures_model_name(tmp_path):
    """Integration: callback correctly captures model name from serialized metadata."""
    rl = RunLogger(run_id="test-model-capture")

    call_run_id = uuid.uuid4()
    rl.callback.on_chat_model_start(
        serialized={"kwargs": {"model_name": "claude-sonnet-4-20250514"}},
        messages=[[AIMessage(content="hello")]],
        run_id=call_run_id,
    )
    rl.callback.on_llm_end(
        response=_make_llm_result(tokens_in=500, tokens_out=300),
        run_id=call_run_id,
    )

    log_path = tmp_path / "run_log.jsonl"
    rl.write_log(log_path)

    lines = log_path.read_text().strip().splitlines()
    # First line should be the LLM event
    llm_event = json.loads(lines[0])
    assert llm_event["kind"] == "llm"
    assert llm_event["tokens_in"] == 500
    assert llm_event["tokens_out"] == 300

    # Summary should show the model in models_used
    summary = json.loads(lines[-1])
    assert "claude-sonnet-4-20250514" in summary["models_used"]


def test_e2e_telemetry_zero_calls_when_no_llm_invoked(tmp_path):
    """Integration: run_log.jsonl shows zero llm_calls when no LLM was invoked.

    This is the negative case — a graph execution that only uses tools/vendors
    without any LLM calls should still produce a valid summary with llm_calls=0.
    """
    rl = RunLogger(run_id="no-llm-run")

    # Only vendor calls, no LLM calls
    rl.log_vendor_call("ohlcv", "yfinance", success=True, duration_ms=100.0)
    rl.log_tool_call("get_price", "AAPL", success=True, duration_ms=50.0)

    log_path = tmp_path / "run_log.jsonl"
    rl.write_log(log_path)

    lines = log_path.read_text().strip().splitlines()
    summary = json.loads(lines[-1])
    assert summary["kind"] == "summary"
    assert summary["llm_calls"] == 0
    assert summary["tokens_in"] == 0
    assert summary["tokens_out"] == 0
    # But vendor/tool calls should be recorded
    assert summary["vendor_calls"] == 1
    assert summary["tool_calls"] == 1
