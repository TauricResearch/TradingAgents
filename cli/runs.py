"""Single-flight run orchestration for web/API-driven analyses.

One active run per process: parallel sessions are separate OS processes
(each ``tradingagents web --port N``), which also isolates the CLI's
module-global ``message_buffer``. A second POST while busy gets 409.
"""

from __future__ import annotations

import threading
import time
import uuid


class RunRecord:
    """Mutable state for one web-driven run; doubles as ask_everywhere hub."""

    def __init__(self, selections: dict):
        self.id = uuid.uuid4().hex[:12]
        self.selections = selections
        self.status = "starting"  # starting|running|done|error
        self.error = None
        self.created = time.time()
        self.pending_prompt = {"question": None, "default": None, "answer": None}
        self.stats_handler = None
        self.start_time = None
        self.final_state = None
        self.thread = None

    def summary(self):
        sel = self.selections
        return {
            "id": self.id,
            "ticker": sel.get("ticker"),
            "date": sel.get("analysis_date"),
            "provider": sel.get("llm_provider"),
            "status": self.status,
            "awaiting_input": bool(self.pending_prompt.get("question")),
            "created": self.created,
            "error": self.error,
        }


class RunManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._runs: dict[str, RunRecord] = {}

    def active(self):
        with self._lock:
            return next(
                (r for r in self._runs.values() if r.status in ("starting", "running")),
                None,
            )

    def start(self, raw_selections: dict) -> RunRecord:
        from cli.main import _normalize_selections, run_analysis
        from cli.utils import _llm_provider_table, provider_default_url

        if self.active() is not None:
            raise BusyError(self.active().id)
        selections = _normalize_selections(dict(raw_selections))
        valid_providers = {pk for _, pk, _ in _llm_provider_table()}
        if selections["llm_provider"] not in valid_providers:
            raise ValueError(f"unknown llm_provider: {selections['llm_provider']}")
        selections.setdefault("backend_url", provider_default_url(selections["llm_provider"]))

        record = RunRecord(selections)
        record.status = "running"

        def _target():
            try:
                run_analysis(
                    selections=selections,
                    prompt_hub=record,
                    headless=True,
                    run_record=record,
                )
            except Exception as exc:  # surface crash to the UI, keep server up
                record.error = f"{type(exc).__name__}: {exc}"
                record.status = "error"

        record.thread = threading.Thread(target=_target, daemon=False)
        with self._lock:
            self._runs[record.id] = record
        record.thread.start()
        return record

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def all(self):
        with self._lock:
            return sorted(self._runs.values(), key=lambda r: r.created, reverse=True)


class BusyError(Exception):
    def __init__(self, run_id: str):
        super().__init__(f"a run is already active: {run_id}")
        self.run_id = run_id


MANAGER = RunManager()
