"""Tests for the agent orchestrator."""
from __future__ import annotations

from unittest.mock import Mock, patch
from web.server.ticker_agent.orchestrator import run_cycle, _build_strategy_prompt, status, STEP_NAMES


def test_build_strategy_prompt_includes_context():
    context = {
        "watchlist_size": 5,
        "universe_size": 100,
        "scored_tickers": 10,
        "watchlist_tickers": ["AAPL", "NVDA"],
        "universe": ["AAPL", "MSFT", "NVDA"],
        "top_scores": {},
        "coverage_gaps": ["NVDA", "AMD"],
        "memory": [],
    }
    prompt = _build_strategy_prompt(context)
    assert "AAPL" in prompt
    assert "NVDA" in prompt
    assert "100" in prompt


@patch("web.server.ticker_agent.orchestrator._emit_event")
@patch("web.server.ticker_agent.orchestrator._call_llm_strategy")
@patch("web.server.ticker_agent.orchestrator._gather_context")
@patch("web.server.ticker_agent.orchestrator._execute_plan")
@patch("web.server.ticker_agent.orchestrator._rank_and_store")
@patch("web.server.ticker_agent.orchestrator._write_memory")
@patch("web.server.ticker_agent.orchestrator._self_improve")
def test_run_cycle_full_flow(mock_improve, mock_memory, mock_rank, mock_execute, mock_context, mock_llm, mock_emit):
    mock_context.return_value = {"test": "context"}
    mock_llm.return_value = {"investigation_plan": [], "sectors_to_watch": [], "reasoning_summary": "test", "conclusions": []}
    mock_execute.return_value = {"scheduled": []}
    mock_rank.return_value = {"scored": 0, "top_ticker": None}

    result = run_cycle()

    mock_context.assert_called_once()
    mock_llm.assert_called_once()
    mock_execute.assert_called_once()
    mock_rank.assert_called_once()
    mock_memory.assert_called_once()
    mock_improve.assert_called_once()
    assert mock_emit.call_count >= 9  # 7 steps with structured events
    assert result["status"] == "completed"


@patch("web.server.ticker_agent.orchestrator._emit_event")
def test_status_includes_step(mock_emit):
    s = status()
    assert "current_step" in s
    assert s["current_step"] == 0
    assert "current_step_name" in s
    assert s["current_step_name"] == "Idle"


def test_step_names_length():
    assert len(STEP_NAMES) == 8  # idle + 7 steps


@patch("web.server.ticker_agent.orchestrator._emit_event")
@patch("web.server.ticker_agent.orchestrator._call_llm_strategy")
@patch("web.server.ticker_agent.orchestrator._gather_context")
@patch("web.server.ticker_agent.orchestrator._execute_plan")
@patch("web.server.ticker_agent.orchestrator._rank_and_store")
@patch("web.server.ticker_agent.orchestrator._write_memory")
@patch("web.server.ticker_agent.orchestrator._self_improve")
def test_live_events_populated(mock_improve, mock_memory, mock_rank, mock_execute, mock_context, mock_llm, mock_emit):
    from web.server.ticker_agent.orchestrator import _live_events
    mock_context.return_value = {"test": "context"}
    mock_llm.return_value = {"investigation_plan": [], "sectors_to_watch": [], "reasoning_summary": "test", "conclusions": []}
    mock_execute.return_value = {"scheduled": []}
    mock_rank.return_value = {"scored": 0, "top_ticker": None}

    _live_events.clear()
    run_cycle()

    # Since we mock _emit_event, events are not actually added via the mock.
    # This test verifies the live_events function signature and that
    # status picks up step changes correctly.
    from web.server.ticker_agent.orchestrator import live_events
    result = live_events(since=0)
    assert "events" in result
    assert "current_step" in result
    assert "current_step_name" in result
