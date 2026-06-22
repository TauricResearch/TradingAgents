"""NDJSON event protocol + fd-1 discipline.

The adapter speaks to the native app over the child process's stdout, one
compact JSON object per line. fd 1 is reserved exclusively for this channel:
stray ``print()`` calls in the dependency tree and library warnings are pushed
to stderr so they can never corrupt a line.

Dependency-free on purpose (no ``tradingagents`` import) so it is importable and
testable on any interpreter.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from typing import Any, TextIO

# Bump when the event shape changes in a way the Swift decoder must know about.
SCHEMA_VERSION = 1


def reserve_stdout() -> TextIO:
    """Reserve fd 1 for the protocol and return a text stream bound to it.

    Duplicates the original stdout, then redirects fd 1 (and ``sys.stdout``) to
    stderr so anything that writes to "stdout" downstream lands on stderr. The
    returned stream is the ONLY writer that should ever touch the real fd 1.
    Call this once, first thing, before importing ``tradingagents``.
    """
    sys.stdout.flush()
    saved_fd = os.dup(1)
    real_out = os.fdopen(saved_fd, "w", buffering=1, encoding="utf-8", newline="\n")
    # Point fd 1 at stderr's destination and route python-level prints there too.
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return real_out


class Emitter:
    """Serializes events to a single NDJSON stream with a monotonic ``seq``."""

    def __init__(self, stream: TextIO, run_id: str, clock: Callable[[], float] = time.time):
        self._stream = stream
        self._run_id = run_id
        self._seq = 0
        self._clock = clock

    @property
    def seq(self) -> int:
        return self._seq

    def emit(self, event_type: str, **fields: Any) -> dict:
        """Write one event line. Returns the emitted object (handy for tests)."""
        self._seq += 1
        obj = {
            "v": SCHEMA_VERSION,
            "run_id": self._run_id,
            "seq": self._seq,
            "ts": round(self._clock(), 3),
            "type": event_type,
        }
        obj.update(fields)
        self._stream.write(json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str) + "\n")
        self._stream.flush()
        return obj

    def emit_event(self, event: dict) -> dict:
        """Emit an event dict that carries its own ``type`` key (from ``diff``)."""
        fields = {k: v for k, v in event.items() if k != "type"}
        return self.emit(event["type"], **fields)

    def write_object(self, obj: dict) -> None:
        """Write a single bare JSON object + newline (no envelope).

        Used by the read-only ``capabilities`` subcommand, which returns one
        document rather than a run's event stream.
        """
        self._stream.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        self._stream.flush()
