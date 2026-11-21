"""SEL-TA-NFR-002 — Structured observability (JSONL events).

Fit: every emitted line parses; required fields non-null; elapsed nonnegative;
exactly one terminal event per run; no portfolio payload or secret appears.

Enforcing design: runapi/events.EventSink (INV-11).
"""

from __future__ import annotations

import json

import pytest

from tradingagents.runapi.events import EventSink
from tradingagents.runapi.redact import Redactor

pytestmark = pytest.mark.unit

REQUIRED = {"run_id", "ticker", "node", "ts", "elapsed_ms", "event", "event_outcome"}


# TC-NFR002-a: a completed run's events parse with required fields; one terminal.
def test_tc_nfr002_a_completed_events(tmp_path):
    sink = EventSink("run-1", "AAPL", Redactor())
    sink.emit("input", "input.mode_resolved", "NO_PORTFOLIO")
    sink.emit("engine", "run.started", "STARTED")
    sink.emit("output", "run.terminal", "COMPLETED")
    assert sink.write_to(tmp_path / "events.jsonl")

    lines = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]

    for entry in lines:
        assert entry.keys() >= REQUIRED
        assert all(entry[key] is not None for key in REQUIRED)
        assert entry["elapsed_ms"] >= 0
    assert sum(entry["event"] == "run.terminal" for entry in lines) == 1


# TC-NFR002-b: a second terminal event is rejected (exactly one logical terminal).
def test_tc_nfr002_b_only_one_terminal():
    sink = EventSink("run-2", "AAPL")
    sink.emit("output", "run.terminal", "COMPLETED")
    with pytest.raises(ValueError):
        sink.emit("output", "run.terminal", "INCOMPLETE")


# TC-NFR002-c: a secret passed into an event is redacted before it is stored.
def test_tc_nfr002_c_secret_redacted(tmp_path):
    sink = EventSink("run-3", "AAPL", Redactor())
    sink.emit("engine", "provider.call", "auth=Bearer sk-abcdefghijklmnop1234")
    sink.write_to(tmp_path / "events.jsonl")
    text = (tmp_path / "events.jsonl").read_text()
    assert "sk-abcdefghijklmnop1234" not in text
    assert "[REDACTED]" in text
