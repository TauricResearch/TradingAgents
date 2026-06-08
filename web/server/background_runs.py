"""Background-run orchestrator: queues past-dated propagate() calls, runs them
in background threads, persists state to disk, and survives a server restart.

Public surface (at the bottom of this module):
    start, get, list_jobs, cancel, pause, resume
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field, fields, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dateutil.relativedelta import relativedelta


def _call_propagate(ticker: str, trade_date: str) -> dict:
    """Default propagator. The fake_propagate fixture patches this symbol."""
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    graph = TradingAgentsGraph()
    final_state, _ = graph.propagate(ticker, trade_date)
    return {"ticker": ticker, "trade_date": trade_date, "decision": final_state.get("decision", {})}


_EVERY_OPTIONS = {"1d", "1w", "2w", "1mo"}
_TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,16}$")


def _validate_inputs(ticker: str, date_from: str, date_to: str, every: str, parallel: int) -> tuple[date, date]:
    if not _TICKER_RE.match(ticker):
        raise ValueError(f"invalid ticker: {ticker!r}")
    try:
        f = date.fromisoformat(date_from)
        t = date.fromisoformat(date_to)
    except ValueError as e:
        raise ValueError(f"invalid date format: {e}")
    if f > t:
        raise ValueError(f"date_from ({date_from}) must be <= date_to ({date_to})")
    if t > datetime.now(tz=timezone.utc).date():
        raise ValueError(f"date_to ({date_to}) cannot be in the future")
    if every not in _EVERY_OPTIONS:
        raise ValueError(f"every must be one of {sorted(_EVERY_OPTIONS)}, got {every!r}")
    if not (1 <= parallel <= 4):
        raise ValueError(f"parallel must be in [1, 4], got {parallel}")
    return f, t


def dates(date_from: str, date_to: str, every: str) -> list[str]:
    """Return ISO date strings, inclusive on both ends.

    Cadence rules:
      - 1d  : business days only (Mon-Fri, NYSE holidays NOT skipped in v1)
      - 1w  : weekly, lands on Mondays
      - 2w  : biweekly, lands on Mondays
      - 1mo : monthly, lands on the from-date's day-of-month; caps to last day
              for short months. Weekends are NOT skipped.
    """
    f = date.fromisoformat(date_from)
    t = date.fromisoformat(date_to)
    if f > t:
        raise ValueError(f"date_from ({date_from}) must be <= date_to ({date_to})")
    if every not in _EVERY_OPTIONS:
        raise ValueError(f"every must be one of {sorted(_EVERY_OPTIONS)}, got {every!r}")

    out: list[date] = []
    cur = f
    if every == "1d":
        step = timedelta(days=1)
        skip_weekends = True
    elif every == "1w":
        step = timedelta(weeks=1)
        skip_weekends = True
    elif every == "2w":
        step = timedelta(weeks=2)
        skip_weekends = True
    else:  # "1mo"
        step = None
        skip_weekends = False
        target_day = f.day

    while cur <= t:
        if not (skip_weekends and cur.weekday() >= 5):
            out.append(cur)
        if step is None:
            nxt = cur + relativedelta(months=1)
            if nxt.day != target_day:
                import calendar
                last_day = calendar.monthrange(nxt.year, nxt.month)[1]
                nxt = nxt.replace(day=min(target_day, last_day))
            cur = nxt
        else:
            cur = cur + step
    return [d.isoformat() for d in out]


import json
import os
import tempfile


DATA_ROOT = Path(os.environ.get("TRADINGAGENTS_DATA_DIR", str(Path.home() / ".tradingagents" / "data")))


def _data_root() -> Path:
    """Return DATA_ROOT.  This function exists so that the many path helpers
    below (job_dir, state_path, …) can be kept consistent with the public
    symbol ``DATA_ROOT`` that tests monkeypatch."""
    return DATA_ROOT


def job_dir(job_id: str) -> Path:
    return _data_root() / "background_runs" / job_id


def state_path(job_id: str) -> Path:
    return job_dir(job_id) / "state.json"


def iteration_dates_path(job_id: str) -> Path:
    return job_dir(job_id) / "iteration_dates.txt"


def iteration_errors_path(job_id: str) -> Path:
    return job_dir(job_id) / "iteration_errors.json"


@dataclass
class BackgroundRunState:
    job_id: str
    ticker: str
    date_from: str
    date_to: str
    every: str
    parallel: int
    total: int
    current_index: int = 0
    avg_duration_s: float = 0.0
    eta_s: int = 0
    started_at: str = ""
    finished_at: Optional[str] = None
    status: str = "running"  # running | paused | done | cancelled | error
    durations_s: list[float] = field(default_factory=list)
    _persist_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def record_duration(self, duration_s: float) -> None:
        self.durations_s.append(duration_s)
        self.avg_duration_s = sum(self.durations_s) / len(self.durations_s)
        self._recompute_eta()

    def _recompute_eta(self) -> None:
        remaining = self.total - self.current_index
        if remaining <= 0:
            self.eta_s = 0
        else:
            denom = self.parallel if self.parallel > 0 else 1
            self.eta_s = max(0, int(round(self.avg_duration_s * remaining / denom)))

    def persist(self) -> None:
        """Atomic write of state.json."""
        d = job_dir(self.job_id)
        d.mkdir(parents=True, exist_ok=True)
        payload = {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")}
        text = json.dumps(payload, indent=2, sort_keys=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".state-", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            dst = d / "state.json"
            for _attempt in range(3):
                try:
                    os.replace(tmp, dst)
                    break
                except PermissionError:
                    if _attempt == 2:
                        raise
                    time.sleep(0.02 * (_attempt + 1))
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    @classmethod
    def load(cls, job_id: str) -> "BackgroundRunState":
        p = state_path(job_id)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")}


_jobs: dict[str, "_JobHandle"] = {}


@dataclass
class _JobHandle:
    job_id: str
    cancel_event: threading.Event
    pause_event: threading.Event
    state: BackgroundRunState
    thread: Optional[threading.Thread] = None


def register_handle(
    job_id: str, ticker: str, date_from: str, date_to: str,
    every: str, parallel: int, total: int,
) -> _JobHandle:
    state = BackgroundRunState(
        job_id=job_id, ticker=ticker, date_from=date_from, date_to=date_to,
        every=every, parallel=parallel, total=total,
    )
    handle = _JobHandle(
        job_id=job_id,
        cancel_event=threading.Event(),
        pause_event=threading.Event(),
        state=state,
    )
    _jobs[job_id] = handle
    return handle


def get_handle(job_id: str) -> Optional[_JobHandle]:
    return _jobs.get(job_id)


def unregister_handle(job_id: str) -> None:
    _jobs.pop(job_id, None)


import time


@dataclass
class _IterationResult:
    ticker: str
    date_iso: str
    duration_s: float
    decision: Optional[dict] = None


import logging

log = logging.getLogger(__name__)


def _has_done_run(ticker: str, date_iso: str) -> bool:
    """Return True if any run.json for (ticker, date_iso) has status 'done'.

    Scans all subdirectories under ``DATA_ROOT / TICKER / `` and checks
    each run.json for a matching ``trade_date`` field.  Supports both the
    standard timestamp-slug layout and older layouts.
    """
    base = DATA_ROOT / ticker.upper()
    if not base.exists():
        return False
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        rj = sub / "run.json"
        if not rj.exists():
            continue
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("trade_date") == date_iso and data.get("status") == "done":
            return True
    return False


def _record_iteration_error(state: BackgroundRunState, date_iso: str, error: str) -> None:
    p = iteration_errors_path(state.job_id)
    errors: dict[str, str] = {}
    if p.exists():
        try:
            errors = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            errors = {}
    errors[date_iso] = error
    p.write_text(json.dumps(errors, indent=2, sort_keys=True), encoding="utf-8")


from concurrent.futures import Future, ThreadPoolExecutor, wait, FIRST_COMPLETED


def _run(handle: _JobHandle, date_list: list[str]) -> None:
    """Run iterations up to `parallel` at a time. Cancel/pause events are
    checked while waiting for the next batch of completed futures.

    current_index advances in date_list order. Parallelism only affects
    wall-clock time.
    """
    state = handle.state
    pending: dict[Future, tuple[int, str]] = {}

    def _submit(idx: int, date_iso: str) -> None:
        if _has_done_run(state.ticker, date_iso):
            with state._persist_lock:
                state.current_index += 1
                state._recompute_eta()
                state.persist()
            return
        fut = executor.submit(_run_one, state.ticker, date_iso)
        pending[fut] = (idx, date_iso)

    with ThreadPoolExecutor(max_workers=state.parallel) as executor:
        it = iter(enumerate(date_list))

        def _refill() -> None:
            for idx, iso in it:
                _submit(idx, iso)
                if len(pending) >= state.parallel:
                    return

        _refill()

        while pending:
            if handle.cancel_event.is_set():
                break
            if handle.pause_event.is_set():
                done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
                for fut in done:
                    idx, date_iso = pending.pop(fut)
                    try:
                        result = fut.result()
                    except Exception as exc:
                        _record_iteration_error(state, date_iso, f"{type(exc).__name__}: {exc}")
                    else:
                        _record_run(state.ticker, date_iso, result.decision,
                                    result.duration_s, state.job_id, idx)
                        state.record_duration(result.duration_s)
                    with state._persist_lock:
                        state.current_index += 1
                        state._recompute_eta()
                        state.persist()
                continue

            done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                idx, date_iso = pending.pop(fut)
                try:
                    result = fut.result()
                except Exception as exc:
                    _record_iteration_error(state, date_iso, f"{type(exc).__name__}: {exc}")
                else:
                    _record_run(state.ticker, date_iso, result.decision,
                                result.duration_s, state.job_id, idx)
                    state.record_duration(result.duration_s)
                with state._persist_lock:
                    state.current_index += 1
                    state._recompute_eta()
                    state.persist()
            _refill()

    state.finished_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if handle.cancel_event.is_set():
        state.status = "cancelled"
    elif handle.pause_event.is_set():
        state.status = "paused"
    else:
        state.status = "done"
    state.persist()


def _record_run(ticker: str, date_iso: str, decision: Optional[dict], duration_s: float,
                background_job_id: str, background_iteration_index: int) -> None:
    """Create a standard run directory + run.json for a completed iteration.

    Uses ``storage.create_run_dir`` so that the history endpoint
    (``list_ticker_runs``) finds the run.  The ``trade_date`` field allows
    ``_has_done_run`` to detect duplicates for resume-safety.
    """
    from web.server import storage  # defer to avoid early import side-effects

    run_info = storage.create_run_dir(ticker)
    run_dir = run_info["run_dir"]
    rj_path = run_dir / "run.json"
    data = json.loads(rj_path.read_text(encoding="utf-8"))

    data["status"] = "done"
    # The propagate call finished, so total_duration_s is known.
    data["total_duration_s"] = duration_s
    data["trade_date"] = date_iso
    data["background_run_id"] = background_job_id
    data["background_run_iteration_index"] = background_iteration_index
    dec = decision or {}
    data["decision_action"] = dec.get("action")
    data["decision_target"] = dec.get("target")
    data["decision_rationale"] = dec.get("rationale")
    data["decision_confidence"] = dec.get("confidence")

    fd, tmp = tempfile.mkstemp(dir=run_dir, prefix=".run-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, rj_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _run_one(ticker: str, date_iso: str) -> _IterationResult:
    """Call propagate() for a single (ticker, date). Measure wall-clock time.
    Raises on failure (caller decides how to record the error)."""
    t0 = time.monotonic()
    out = _call_propagate(ticker, date_iso)
    duration_s = time.monotonic() - t0
    decision = None
    if isinstance(out, dict):
        decision = out.get("decision")
    return _IterationResult(
        ticker=ticker, date_iso=date_iso,
        duration_s=duration_s, decision=decision,
    )


def _load_existing_jobs() -> None:
    """Scan background_runs/*/state.json; for each job with status='running',
    register a handle and spawn a worker. For status='paused', register a
    handle but do not spawn. Terminal jobs are ignored."""
    base = _data_root() / "background_runs"
    if not base.exists():
        return
    for d in sorted(base.iterdir()):
        if not d.is_dir():
            continue
        sp = d / "state.json"
        if not sp.exists():
            continue
        try:
            state = BackgroundRunState.load(d.name)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("background_runs._load_existing_jobs: skipping %s: %s", d.name, exc)
            continue
        if state.status not in ("running", "paused"):
            continue
        handle = _JobHandle(
            job_id=state.job_id,
            cancel_event=threading.Event(),
            pause_event=threading.Event(),
            state=state,
        )
        if state.status == "paused":
            handle.pause_event.set()
        _jobs[state.job_id] = handle
        if state.status == "running":
            dp = d / "iteration_dates.txt"
            if not dp.exists():
                log.warning("background_runs._load_existing_jobs: %s has no iteration_dates.txt", state.job_id)
                continue
            date_list = [line.strip() for line in dp.read_text(encoding="utf-8").splitlines() if line.strip()]
            t = threading.Thread(
                target=_run, args=(handle, date_list),
                daemon=True, name=f"bg-run-{state.job_id}",
            )
            handle.thread = t
            t.start()


def cancel(job_id: str) -> None:
    h = get_handle(job_id)
    if h is None:
        try:
            state = BackgroundRunState.load(job_id)
        except FileNotFoundError:
            raise KeyError(job_id) from None
        if state.status in ("done", "cancelled", "error"):
            return
        return
    h.cancel_event.set()


def pause(job_id: str) -> None:
    h = get_handle(job_id)
    if h is None:
        raise KeyError(job_id)
    h.pause_event.set()
    h.state.status = "paused"
    h.state.persist()


def _spawn_worker(job_id: str, date_list: list[str]) -> None:
    h = get_handle(job_id)
    if not h:
        return
    t = threading.Thread(target=_run, args=(h, date_list), daemon=True, name=f"bg-run-{job_id}")
    h.thread = t
    t.start()


def resume(job_id: str) -> None:
    h = get_handle(job_id)
    if h is None:
        raise KeyError(job_id)
    h.pause_event.clear()
    h.state.status = "running"
    dp = iteration_dates_path(job_id)
    if dp.exists():
        date_list = [line.strip() for line in dp.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        date_list = []
    _spawn_worker(job_id, date_list)
    h.state.persist()


def _new_job_id(ticker: str) -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"bgr_{ts}_{ticker}"


def start(ticker: str, date_from: str, date_to: str, every: str = "1d", parallel: int = 1) -> str:
    f, t = _validate_inputs(ticker, date_from, date_to, every, parallel)
    date_list = dates(date_from, date_to, every)
    if not date_list:
        raise ValueError(f"date range {date_from}..{date_to} with every={every} produced no dates")
    job_id = _new_job_id(ticker)
    handle = register_handle(
        job_id=job_id, ticker=ticker, date_from=date_from, date_to=date_to,
        every=every, parallel=parallel, total=len(date_list),
    )
    handle.state.persist()
    iteration_dates_path(job_id).write_text("\n".join(date_list) + "\n", encoding="utf-8")
    t = threading.Thread(
        target=_run, args=(handle, date_list),
        daemon=True, name=f"bg-run-{job_id}",
    )
    handle.thread = t
    t.start()
    return job_id


def get(job_id: str) -> dict:
    h = get_handle(job_id)
    if h is not None:
        return h.state.to_dict()
    try:
        state = BackgroundRunState.load(job_id)
    except FileNotFoundError:
        raise KeyError(job_id) from None
    return state.to_dict()


def list_jobs(limit: int = 50) -> list[dict]:
    base = _data_root() / "background_runs"
    if not base.exists():
        return []
    out: list[dict] = []
    for d in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        sp = d / "state.json"
        if not sp.exists():
            continue
        try:
            state = BackgroundRunState.load(d.name)
        except (OSError, ValueError, KeyError):
            continue
        out.append(state.to_dict())
        if len(out) >= limit:
            break
    return out
