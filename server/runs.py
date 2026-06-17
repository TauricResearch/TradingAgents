"""RunRegistry: spawn worker.py subprocesses, drain their NDJSON, expose
snapshots and an async event feed for SSE.

Design notes:
  * Each analysis runs in its own worker.py subprocess (engine config isolation),
    exactly as the Streamlit app did.
  * A daemon reader thread ALWAYS drains the worker's stdout, even with no SSE
    subscriber attached — otherwise the worker fills the 64 KB pipe buffer and
    deadlocks in pipe_write (the orphan-defense lesson from the Streamlit app).
  * SSE consumers read the run record's append-only `events` list by offset;
    server-side polling of an in-memory list is cheap and avoids fragile
    thread→asyncio queue bridging. The browser is still *pushed* over the open
    SSE connection — no per-update client round-trip.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from typing import Any, Optional

import user_prefs
from tradingagents.default_config import DEFAULT_CONFIG
from .config import settings
from .schemas import AnalysisStartReq

_HARD_TIMEOUT_SEC = 1800  # 30 min — > 4× a normal run; matches webui GC timeout


class Run:
    def __init__(self, run_id: str, email: str, req: AnalysisStartReq):
        self.run_id = run_id
        self.email = email
        self.ticker = req.ticker
        self.trade_date = req.trade_date
        self.status = "pending"  # pending | running | done | error
        self.events: list[dict[str, Any]] = []  # append-only NDJSON events
        self.chunks: list[dict[str, Any]] = []
        self.stats: Optional[dict] = None
        self.decision: Optional[str] = None
        self.error: Optional[dict] = None
        self.started_at = time.time()
        self.proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def append(self, ev: dict) -> None:
        with self._lock:
            self.events.append(ev)
            kind = ev.get("kind")
            if kind == "started":
                self.status = "running"
            elif kind == "chunk":
                self.chunks.append(ev.get("data", {}))
            elif kind == "stats":
                self.stats = ev.get("data")
            elif kind == "done":
                self.decision = ev.get("decision")
                self.status = "done"
            elif kind == "error":
                self.error = ev
                self.status = "error"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "run_id": self.run_id,
                "status": self.status,
                "chunks": list(self.chunks),
                "stats": self.stats,
                "decision": self.decision,
                "error": self.error,
                "started_at": self.started_at,
                "elapsed": time.time() - self.started_at,
            }

    def events_from(self, offset: int) -> list[dict]:
        with self._lock:
            return self.events[offset:]

    @property
    def finished(self) -> bool:
        return self.status in ("done", "error")


class RunRegistry:
    def __init__(self):
        self._runs: dict[str, Run] = {}
        self._sem = threading.Semaphore(settings.max_concurrent_runs)
        self._lock = threading.Lock()

    def _active_for(self, email: str, ticker: str, date: str) -> Optional[Run]:
        with self._lock:
            for run in self._runs.values():
                if (run.email, run.ticker, run.trade_date) == (email, ticker, date) \
                        and not run.finished:
                    return run
        return None

    def _build_config(self, email: str, req: AnalysisStartReq) -> dict:
        home = user_prefs.user_home(email)
        cfg = DEFAULT_CONFIG.copy()
        # Doubao only. We intentionally ignore req.provider/deep_model/quick_model
        # (the UI no longer offers a choice; old prefs may still say "qwen").
        # Deep model is the non-reasoning Doubao 1.5 Pro for speed.
        cfg["llm_provider"] = "doubao"
        cfg["deep_think_llm"] = "doubao-1-5-pro-32k-250115"
        cfg["quick_think_llm"] = "doubao-seed-1-6-flash-250828"
        cfg["max_debate_rounds"] = req.max_debate_rounds
        cfg["max_risk_discuss_rounds"] = req.max_risk_discuss_rounds
        cfg["output_language"] = req.output_language
        cfg["backend_url"] = None
        cfg["checkpoint_enabled"] = req.checkpoint_enabled
        cfg["data_cache_dir"] = str(home / "cache")
        cfg["results_dir"] = str(home / "logs")
        cfg["memory_log_path"] = str(home / "memory" / "trading_memory.md")
        return cfg

    def start(self, email: str, req: AnalysisStartReq) -> tuple[str, bool]:
        existing = self._active_for(email, req.ticker, req.trade_date)
        if existing is not None:
            return existing.run_id, True

        if not self._sem.acquire(blocking=False):
            raise RuntimeError("at_capacity")

        run_id = f"{email}|{req.ticker}|{req.trade_date}|{int(time.time() * 1000)}"
        run = Run(run_id, email, req)
        with self._lock:
            self._runs[run_id] = run

        try:
            proc = subprocess.Popen(
                [settings.python_bin, "-u", settings.worker_path],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1, encoding="utf-8",
            )
        except Exception:
            self._sem.release()
            raise
        run.proc = proc

        request = {
            "config": self._build_config(email, req),
            "ticker": req.ticker,
            "trade_date": req.trade_date,
            "selected_analysts": req.selected_analysts,
            "user_research": req.user_research or "",
        }
        proc.stdin.write(json.dumps(request, ensure_ascii=False))
        proc.stdin.close()

        t = threading.Thread(target=self._drain, args=(run,), daemon=True)
        t.start()
        return run_id, False

    def _drain(self, run: Run) -> None:
        """Read NDJSON from the worker until EOF. Always runs (deadlock defense)."""
        proc = run.proc
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if time.time() - run.started_at > _HARD_TIMEOUT_SEC:
                    proc.kill()
                    run.append({"kind": "error", "type": "Timeout",
                                "msg": "run exceeded hard timeout"})
                    break
                try:
                    run.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # stray non-NDJSON line
            proc.wait(timeout=30)
            if not run.finished:
                code = proc.returncode
                run.append({"kind": "error", "type": "WorkerExited",
                            "msg": f"worker exited with code {code}"})
        except Exception as e:  # noqa: BLE001 — never let the reader thread die silently
            if not run.finished:
                run.append({"kind": "error", "type": type(e).__name__, "msg": str(e)})
        finally:
            self._sem.release()

    def get(self, run_id: str) -> Optional[Run]:
        with self._lock:
            return self._runs.get(run_id)

    def cancel(self, run_id: str) -> bool:
        run = self.get(run_id)
        if run is None or run.proc is None:
            return False
        if not run.finished:
            run.proc.kill()
            run.append({"kind": "error", "type": "Cancelled", "msg": "cancelled by user"})
        return True


registry = RunRegistry()
