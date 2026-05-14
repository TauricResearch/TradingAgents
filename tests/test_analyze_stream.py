"""Tests for scripts/py/analyze_stream.py — the Python bridge.

Uses @pytest.mark.smoke so it runs with `just test-smoke`.
All tests mock TradingAgentsGraph to avoid LLM API calls.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Smoke marker (matches just test-smoke)
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# Load analyze_stream as an isolated module (avoids sys.path issues with uv)
# ---------------------------------------------------------------------------

def _load_analyze_stream():
    """Load scripts/py/analyze_stream.py as an isolated module."""
    script_path = Path(__file__).parent.parent / "scripts" / "py" / "analyze_stream.py"
    spec = importlib.util.spec_from_file_location("analyze_stream", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyze_stream"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bridge():
    return _load_analyze_stream()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_graph():
    """Return a mock TradingAgentsGraph that returns canned results."""
    graph = MagicMock()
    graph.state = {}
    graph.memory_log._log_path = None  # no memory log by default
    final_state = {
        "market_report": "Market analysis: bullish on tech.",
        "news_report": "Recent news positive.",
        "fundamentals_report": "Strong fundamentals.",
        "sentiment_report": "Bullish sentiment.",
        "investment_debate_state": {"history": ["Round 1: bull argument"]},
    }
    decision = {"action": "buy", "reasoning": "Strong buy signal", "confidence": 0.8}
    graph.propagate.return_value = (final_state, decision)
    return graph


@pytest.fixture
def temp_memory_log(tmp_path):
    """Create a temp memory log file for position context tests."""
    log_file = tmp_path / "trading_memory.md"
    log_file.write_text("")
    return log_file


# ---------------------------------------------------------------------------
# Test emit_stdout produces valid JSON lines
# ---------------------------------------------------------------------------

class TestEmitStdout:
    def test_emit_produces_valid_json_line(self, bridge):
        """Each emit_stdout call writes exactly one valid JSON line to stdout."""
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            bridge.emit_stdout("start", {"ticker": "TKA.DE", "date": "2026-05-02"})
            line = captured.getvalue().strip()
            assert line, "No output captured"
            parsed = json.loads(line)
            assert parsed["event"] == "start"
            assert parsed["data"]["ticker"] == "TKA.DE"
            assert parsed["data"]["date"] == "2026-05-02"
        finally:
            sys.stdout = old_stdout

    def test_emit_produces_json_line_with_unicode(self, bridge):
        """emit_stdout handles unicode characters correctly."""
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            bridge.emit_stdout("decision", {"signal": "buy", "reasoning": "Bullish on tech 📈"})
            line = captured.getvalue().strip()
            parsed = json.loads(line)
            assert "📈" in parsed["data"]["reasoning"]
        finally:
            sys.stdout = old_stdout

    def test_multiple_emits_produce_newline_separated_lines(self, bridge):
        """Consecutive emits produce separate lines with no trailing garbage."""
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            bridge.emit_stdout("start", {"ticker": "TKA.DE"})
            bridge.emit_stdout("complete", {"ticker": "TKA.DE"})
            lines = captured.getvalue().strip().split("\n")
            assert len(lines) == 2
            assert json.loads(lines[0])["event"] == "start"
            assert json.loads(lines[1])["event"] == "complete"
        finally:
            sys.stdout = old_stdout


# ---------------------------------------------------------------------------
# Test _inject_position_context writes correct format
# ---------------------------------------------------------------------------

class TestInjectPositionContext:
    def test_injects_correct_markdown_format(self, bridge, temp_memory_log):
        """The injected entry uses the correct memory log format."""
        memory_log = MagicMock()
        memory_log._log_path = temp_memory_log
        memory_log._SEPARATOR = "\n---\n"

        bridge._inject_position_context(
            memory_log, ticker="TKA.DE", context="500 shares @ 8.45", date="2026-05-02"
        )

        content = temp_memory_log.read_text()
        assert "[2026-05-02 | TKA.DE | neutral | n/a | n/a | n/a]" in content
        assert "**Position context (current holding):** 500 shares @ 8.45" in content
        assert "DECISION:" in content
        assert "REFLECTION:" in content
        assert memory_log._SEPARATOR in content

    def test_injects_multiple_contexts_without_overwriting(self, bridge, temp_memory_log):
        """Multiple injections append to the log, don't overwrite."""
        memory_log = MagicMock()
        memory_log._log_path = temp_memory_log
        memory_log._SEPARATOR = "\n---\n"

        bridge._inject_position_context(
            memory_log, ticker="TKA.DE", context="100 shares @ 10.00", date="2026-05-02"
        )
        bridge._inject_position_context(
            memory_log, ticker="SPY", context="50 shares @ 450.00", date="2026-05-02"
        )

        content = temp_memory_log.read_text()
        assert content.count(memory_log._SEPARATOR) == 2
        assert "TKA.DE" in content
        assert "SPY" in content

    def test_skips_when_no_log_path(self, bridge):
        """No exception when _log_path is None."""
        memory_log = MagicMock()
        memory_log._log_path = None
        # Should not raise
        bridge._inject_position_context(
            memory_log, ticker="TKA.DE", context="500 shares @ 8.45", date="2026-05-02"
        )


# ---------------------------------------------------------------------------
# Test heartbeat mechanism
# ---------------------------------------------------------------------------

class TestHeartbeat:
    def test_heartbeat_thread_emits_to_stderr(self, bridge):
        """Heartbeat thread writes JSON events to stderr at configured interval."""
        old_stderr = sys.stderr
        captured = io.StringIO()
        sys.stderr = captured

        stop_event = threading.Event()
        interval = 1  # 1 second for fast test

        t = threading.Thread(target=bridge.heartbeat_loop, args=(interval, stop_event), daemon=True)
        t.start()
        time.sleep(3.5)  # wait for 3 ticks
        stop_event.set()
        t.join(timeout=2)

        sys.stderr = old_stderr

        lines = [l.strip() for l in captured.getvalue().split("\n") if l.strip()]
        heartbeats = [l for l in lines if l.startswith('{"event": "heartbeat"')]
        # Should have ~3 heartbeats in ~3.5 seconds with 1s interval
        assert len(heartbeats) >= 2, f"Expected ≥2 heartbeats, got {len(heartbeats)}: {heartbeats}"
        for hb in heartbeats:
            parsed = json.loads(hb)
            assert parsed["event"] == "heartbeat"
            assert "tick" in parsed["data"]
            assert isinstance(parsed["data"]["tick"], int)


# ---------------------------------------------------------------------------
# Test CLI argument parsing
# ---------------------------------------------------------------------------

class TestArgParsing:
    def test_default_timeout_is_240(self, bridge):
        """Default timeout when not specified should be 240."""
        parser = bridge.argparse.ArgumentParser()
        parser.add_argument("ticker")
        parser.add_argument("--timeout", type=int, default=240)
        args = parser.parse_args(["TKA.DE"])
        assert args.timeout == 240

    def test_timeout_is_configurable(self, bridge):
        """--timeout arg overrides the default."""
        parser = bridge.argparse.ArgumentParser()
        parser.add_argument("ticker")
        parser.add_argument("--timeout", type=int, default=240)
        args = parser.parse_args(["TKA.DE", "--timeout", "60"])
        assert args.timeout == 60

    def test_heartbeat_interval_is_configurable(self, bridge):
        """--heartbeat-interval arg is parsed correctly."""
        parser = bridge.argparse.ArgumentParser()
        parser.add_argument("ticker")
        parser.add_argument("--heartbeat-interval", type=int, default=15)
        args = parser.parse_args(["TKA.DE", "--heartbeat-interval", "30"])
        assert args.heartbeat_interval == 30

    def test_llm_config_args_parsed(self, bridge):
        """--llm-provider, --deep-think-llm, --quick-think-llm are parsed."""
        parser = bridge.argparse.ArgumentParser()
        parser.add_argument("ticker")
        parser.add_argument("--llm-provider", default=None)
        parser.add_argument("--deep-think-llm", default=None)
        parser.add_argument("--quick-think-llm", default=None)
        args = parser.parse_args([
            "TKA.DE",
            "--llm-provider", "openai",
            "--deep-think-llm", "deepseek/deepseek-v4-flash",
            "--quick-think-llm", "deepseek/deepseek-v4-flash",
        ])
        assert args.llm_provider == "openai"
        assert args.deep_think_llm == "deepseek/deepseek-v4-flash"
        assert args.quick_think_llm == "deepseek/deepseek-v4-flash"

    def test_retry_flag_parsed(self, bridge):
        """--retry flag is parsed as boolean."""
        parser = bridge.argparse.ArgumentParser()
        parser.add_argument("ticker")
        parser.add_argument("--retry", action="store_true")
        args = parser.parse_args(["TKA.DE", "--retry"])
        assert args.retry is True

    def test_start_event_includes_retry_flag(self, bridge):
        """The start event data includes the retry field."""
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            bridge.emit_stdout("start", {
                "ticker": "TKA.DE",
                "date": "2026-05-02",
                "position_context": None,
                "retry": True,
            })
            line = captured.getvalue().strip()
            parsed = json.loads(line)
            assert parsed["data"]["retry"] is True
            assert parsed["data"]["retry"] is not None
        finally:
            sys.stdout = old_stdout


# ---------------------------------------------------------------------------
# Test error event emission
# ---------------------------------------------------------------------------

class TestErrorEvents:
    def test_error_event_contains_message_and_traceback(self, bridge):
        """Error events include message and traceback fields."""
        old_stdout = sys.stdout
        captured = io.StringIO()
        sys.stdout = captured

        try:
            bridge.emit_stdout("error", {
                "message": "Analysis timed out after 240s",
                "traceback": "TimeoutError: Python signal.SIGALRM triggered",
            })
            line = captured.getvalue().strip()
            parsed = json.loads(line)
            assert parsed["event"] == "error"
            assert "timed out" in parsed["data"]["message"]
            assert parsed["data"]["traceback"]
        finally:
            sys.stdout = old_stdout

    def test_timeout_error_class_exists(self, bridge):
        """TimeoutError is defined and is an Exception subclass."""
        assert issubclass(bridge.TimeoutError, Exception)


# ---------------------------------------------------------------------------
# Test run_propagate threading and queue communication
# ---------------------------------------------------------------------------

class TestThreadedPropagate:
    def test_propagate_thread_fills_result_holder(self, bridge, mock_graph):
        """The propagate thread populates result_holder with (state, decision)."""
        with patch.object(bridge, "TradingAgentsGraph", return_value=mock_graph):
            result_holder = []
            t = threading.Thread(
                target=bridge.run_propagate,
                args=(["market", "news"], {}, "TKA.DE", "2026-05-02", result_holder),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)
            assert len(result_holder) == 1
            state, decision = result_holder[0]
            assert "market_report" in state
            assert decision["action"] == "buy"

    def test_propagate_thread_catches_exceptions(self, bridge, mock_graph):
        """Graph errors are stored in GRAPH_ERROR, not raised to caller thread."""
        mock_graph.propagate.side_effect = RuntimeError("Graph failed")
        bridge.GRAPH_ERROR.clear()

        with patch.object(bridge, "TradingAgentsGraph", return_value=mock_graph):
            result_holder = []
            t = threading.Thread(
                target=bridge.run_propagate,
                args=(["market"], {}, "TKA.DE", "2026-05-02", result_holder),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)
            assert len(result_holder) == 0
            assert len(bridge.GRAPH_ERROR) == 1
            assert isinstance(bridge.GRAPH_ERROR[0], RuntimeError)
            assert "Graph failed" in str(bridge.GRAPH_ERROR[0])

    def test_graph_error_accumulates(self, bridge, mock_graph):
        """GRAPH_ERROR accumulates across runs (not cleared, only appended)."""
        # Pre-populate with stale error
        bridge.GRAPH_ERROR.append(RuntimeError("stale"))
        mock_graph.propagate.side_effect = RuntimeError("new error")

        with patch.object(bridge, "TradingAgentsGraph", return_value=mock_graph):
            result_holder = []
            t = threading.Thread(
                target=bridge.run_propagate,
                args=(["market"], {}, "TKA.DE", "2026-05-02", result_holder),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)
            # GRAPH_ERROR should contain both stale and new errors
            error_messages = [str(e) for e in bridge.GRAPH_ERROR]
            assert any("stale" in m for m in error_messages)
            assert any("new error" in m for m in error_messages)

    def test_result_holder_empty_on_error(self, bridge, mock_graph):
        """result_holder stays empty when graph raises, not partially filled."""
        mock_graph.propagate.side_effect = ValueError("bad input")
        bridge.GRAPH_ERROR.clear()

        with patch.object(bridge, "TradingAgentsGraph", return_value=mock_graph):
            result_holder = []
            t = threading.Thread(
                target=bridge.run_propagate,
                args=(["market"], {}, "BAD_TICKER", "2026-05-02", result_holder),
                daemon=True,
            )
            t.start()
            t.join(timeout=5)
            assert len(result_holder) == 0