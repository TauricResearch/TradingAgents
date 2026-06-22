"""Unit tests for the NDJSON emitter (desk_adapter.protocol).

Dependency-free; runnable directly: ``PYTHONPATH=. python3 tests/test_desk_adapter_protocol.py``.
"""

from __future__ import annotations

import io
import json

from desk_adapter.protocol import SCHEMA_VERSION, Emitter


def _lines(buf):
    return [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]


def test_emit_envelope_and_monotonic_seq():
    buf = io.StringIO()
    em = Emitter(buf, run_id="r1", clock=lambda: 123.456)
    em.emit("warming", phase="import")
    em.emit("node_status", node="Market Analyst", state="in_progress")
    rows = _lines(buf)
    assert [r["seq"] for r in rows] == [1, 2]
    assert all(r["v"] == SCHEMA_VERSION and r["run_id"] == "r1" for r in rows)
    assert rows[0]["type"] == "warming" and rows[0]["phase"] == "import"
    assert rows[0]["ts"] == 123.456
    assert rows[1]["node"] == "Market Analyst"


def test_emit_event_dict_roundtrip():
    buf = io.StringIO()
    em = Emitter(buf, run_id="r2", clock=lambda: 0.0)
    em.emit_event({"type": "tool_call", "name": "get_news", "args": {"q": "AAPL"}})
    row = _lines(buf)[0]
    assert row["type"] == "tool_call" and row["name"] == "get_news"
    assert row["args"] == {"q": "AAPL"}
    assert "type" in row and row["seq"] == 1


def test_each_line_is_valid_standalone_json():
    buf = io.StringIO()
    em = Emitter(buf, run_id="r3", clock=lambda: 1.0)
    # Text with embedded newlines must stay on one physical line (JSON-escaped).
    em.emit("agent_step", text="line one\nline two", role="News Analyst")
    raw = buf.getvalue()
    assert raw.count("\n") == 1  # exactly one record terminator
    row = json.loads(raw)
    assert row["text"] == "line one\nline two"


def test_write_object_is_bare_no_envelope():
    buf = io.StringIO()
    em = Emitter(buf, run_id="r4", clock=lambda: 1.0)
    em.write_object({"schema": "capabilities", "providers": []})
    row = _lines(buf)[0]
    assert row == {"schema": "capabilities", "providers": []}
    assert "seq" not in row and "v" not in row


if __name__ == "__main__":
    import sys
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
