"""Unit tests for the SSE event envelope/framing (desk_server.events).

Dependency-free; runnable directly: ``PYTHONPATH=. python3 tests/test_desk_server_events.py``.
"""

from __future__ import annotations

import json

from desk_adapter.protocol import SCHEMA_VERSION
from desk_server.events import build_event, sse_format


def test_build_event_envelope():
    ev = build_event("run-1", 3, "node_status", {"node": "Market Analyst", "state": "running"}, clock=lambda: 9.9)
    assert ev == {
        "v": SCHEMA_VERSION,
        "run_id": "run-1",
        "seq": 3,
        "ts": 9.9,
        "type": "node_status",
        "node": "Market Analyst",
        "state": "running",
    }


def test_sse_format_has_id_and_data():
    ev = build_event("r", 7, "agent_step", {"text": "hi\nthere"}, clock=lambda: 0.0)
    frame = sse_format(ev)
    lines = frame.split("\n")
    assert lines[0] == "id: 7"
    assert lines[1].startswith("data: ")
    assert frame.endswith("\n\n")
    # The data line is single-line valid JSON (embedded newline is escaped).
    payload = json.loads(lines[1][len("data: "):])
    assert payload["type"] == "agent_step" and payload["text"] == "hi\nthere"


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
