"""Drop-in replacement for ``TradingAgentsGraph.propagate`` used by the
background-runs tests. The fake records every call, can sleep a configurable
amount per call to simulate LLM latency, and can fail on selected iterations
to exercise the error path.

When ``record_in_storage`` is True (default), the fake also writes a
``run.json`` to the standard per-ticker per-date path so the resume-safety
check (``_has_done_run``) and the iteration tagger (``_tag_run``) can be
exercised against real on-disk artifacts.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field


@dataclass
class FakePropagate:
    """Thread-safe recording fake."""

    sleep_s: float = 0.0
    fail_on_dates: set[str] = field(default_factory=set)
    record_in_storage: bool = True

    calls: list[tuple[str, str, float]] = field(default_factory=list)
    # (ticker, trade_date, monotonic_at_call_start)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __call__(self, ticker: str, trade_date: str, *args, **kwargs) -> dict:
        t0 = time.monotonic()
        with self._lock:
            self.calls.append((ticker, trade_date, t0))
        if self.sleep_s > 0:
            time.sleep(self.sleep_s)
        if trade_date in self.fail_on_dates:
            raise RuntimeError(f"fake_propagate: forced failure on {trade_date}")
        if self.record_in_storage:
            self._write_fake_run(ticker, trade_date)
        return {
            "ticker": ticker,
            "trade_date": trade_date,
            "decision": {"action": "BUY", "target": 100.0},
        }

    def _write_fake_run(self, ticker: str, trade_date: str) -> None:
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir(ticker, trade_date) / f"run_{int(time.time()*1000)}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(json.dumps({
            "id": run_dir.name,
            "ticker": ticker,
            "trade_date": trade_date,
            "status": "done",
            "decision_action": "BUY",
            "decision_target": 100.0,
            "start_price": 99.0,
            "started_at": "2024-01-01T14:30:00Z",
            "finished_at": "2024-01-01T14:31:00Z",
        }), encoding="utf-8")
