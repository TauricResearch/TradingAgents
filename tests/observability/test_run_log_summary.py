"""Tests for RunLogger counters — isolation unit tests and wiring regression (PR-B3)."""

import json
from pathlib import Path

from tradingagents.observability import RunLogger

# ---------------------------------------------------------------------------
# Unit tests: logger works in isolation
# ---------------------------------------------------------------------------


def test_summary_counts_llm_events():
    """RunLogger.summary() aggregates tokens from log_vendor_call equivalents."""
    log = RunLogger()
    # Simulate two LLM events by directly appending (mirrors callback behaviour)
    from tradingagents.observability import _Event

    log._append(
        _Event(
            kind="llm",
            ts=0,
            data={
                "model": "gpt-4",
                "tokens_in": 100,
                "tokens_out": 200,
                "agent": "",
                "duration_ms": 0,
                "prompt": "",
                "response": "",
            },
        )
    )
    log._append(
        _Event(
            kind="llm",
            ts=0,
            data={
                "model": "gpt-4",
                "tokens_in": 50,
                "tokens_out": 75,
                "agent": "",
                "duration_ms": 0,
                "prompt": "",
                "response": "",
            },
        )
    )

    summary = log.summary()
    assert summary["llm_calls"] == 2
    assert summary["tokens_in"] == 150
    assert summary["tokens_out"] == 275
    assert summary["tokens_total"] == 425


def test_summary_counts_vendor_events():
    """RunLogger.log_vendor_call() increments vendor_calls in summary."""
    log = RunLogger()
    log.log_vendor_call("ohlcv", "yfinance", success=True, duration_ms=120.0)
    log.log_vendor_call("news", "finnhub", success=True, duration_ms=80.0)
    log.log_vendor_call("ohlcv", "yfinance", success=False, duration_ms=30.0, error="timeout")

    summary = log.summary()
    assert summary["vendor_calls"] == 3
    assert summary["vendor_success"] == 2
    assert summary["vendor_fail"] == 1


def test_write_log_summary_reflects_recorded_events(tmp_path):
    """write_log() appends a kind=summary line with non-zero counters."""
    log = RunLogger()
    from tradingagents.observability import _Event

    log._append(
        _Event(
            kind="llm",
            ts=0,
            data={
                "model": "gpt-4",
                "tokens_in": 10,
                "tokens_out": 20,
                "agent": "",
                "duration_ms": 0,
                "prompt": "",
                "response": "",
            },
        )
    )
    log.log_vendor_call("ohlcv", "yfinance", success=True, duration_ms=50.0)

    out = tmp_path / "run_log.jsonl"
    log.write_log(out)

    lines = out.read_text().strip().splitlines()
    assert len(lines) >= 2, "Expected at least one event line + summary line"
    summary = json.loads(lines[-1])
    assert summary["kind"] == "summary"
    assert summary["llm_calls"] == 1
    assert summary["vendor_calls"] == 1
    assert summary["tokens_in"] == 10
    assert summary["tokens_out"] == 20


# ---------------------------------------------------------------------------
# Wiring regression: PortfolioGraph must be constructed with rl.callback
# ---------------------------------------------------------------------------


def test_portfolio_graph_accepts_callbacks_kwarg():
    """PortfolioGraph.__init__ accepts a callbacks list without error.

    This verifies the interface expected by the engine wiring fix (B3.1):
    PortfolioGraph(config=..., callbacks=[rl.callback]) must be valid.
    """
    from unittest.mock import MagicMock, patch

    # Patch heavy LLM creation so the test stays unit-level
    with patch("tradingagents.graph.portfolio_graph.create_llm_client", return_value=MagicMock()):
        from tradingagents.graph.portfolio_graph import PortfolioGraph

        fake_callback = MagicMock()
        pg = PortfolioGraph(config={}, callbacks=[fake_callback])
        # The callbacks must be stored on the instance
        assert fake_callback in pg.callbacks


def test_engine_portfolio_passes_callbacks_to_graph():
    """LangGraphEngine.run_portfolio passes rl.callback to PortfolioGraph constructor.

    Verifies the fix for the zero-counter bug: the engine must not create
    PortfolioGraph without the RunLogger callback, otherwise on_llm_end never fires.
    """

    engine_src = (
        Path(__file__).parent.parent.parent / "agent_os/backend/services/langgraph_engine.py"
    )
    source = engine_src.read_text()

    # We expect to find PortfolioGraph( ... callbacks=[rl.callback] ... )
    # A simple source-level check catches the most common regression.
    assert "callbacks=[rl.callback]" in source or "callbacks = [rl.callback]" in source, (
        "LangGraphEngine.run_portfolio does not pass rl.callback to PortfolioGraph. "
        "This causes zero llm_calls in run_log.jsonl. "
        "Fix: PortfolioGraph(config={...}, callbacks=[rl.callback])"
    )
