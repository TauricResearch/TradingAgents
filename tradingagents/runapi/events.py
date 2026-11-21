"""Bounded JSONL lifecycle events; never accepts model or portfolio payloads."""

from __future__ import annotations

import json
import os
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path


class EventSink:
    def __init__(self, run_id: str, ticker: str, redactor=None):
        self.run_id = run_id
        self.ticker = ticker
        self.redactor = redactor
        self.started = time.monotonic()
        self.events: list[dict] = []
        self._terminal_added = False

    def emit(self, node: str, event: str, event_outcome: str) -> dict:
        if node not in {"input", "engine", "output"}:
            raise ValueError("event node must be input, engine, or output")
        if event == "run.terminal":
            if self._terminal_added:
                raise ValueError("only one terminal event may be recorded")
            self._terminal_added = True
        entry = {
            "run_id": self.run_id, "ticker": self.ticker, "node": node,
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "elapsed_ms": max(0, int((time.monotonic() - self.started) * 1000)),
            "event": event, "event_outcome": event_outcome,
        }
        if self.redactor:
            entry = self.redactor.scrub(entry)
        self.events.append(entry)
        return entry

    def write_to(self, path: Path) -> bool:
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n"
                                               for event in self.events), encoding="utf-8")
            os.replace(temporary, path)
            return True
        except OSError:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            return False
