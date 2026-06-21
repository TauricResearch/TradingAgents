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
    final_state, final_signal = graph.propagate(ticker, trade_date)
    # Parse the decision using the same logic as the normal runner
    # (runner._parse_pm_decision) so background runs get the same
    # decision_action / decision_target / decision_rationale /
    # decision_confidence fields as interactive runs.
    from web.server.runner import _parse_pm_decision
    decision = _parse_pm_decision(final_state or {}, final_signal or "")
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "decision": decision,
        "final_state": final_state,
    }


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
    final_state: Optional[dict] = None


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


def _ranges_overlap(a_from: str, a_to: str, b_from: str, b_to: str) -> bool:
    """Return True if the two date ranges [from, to] overlap (inclusive)."""
    return a_from <= b_to and a_to >= b_from


def _has_overlapping_job(ticker: str, date_from: str, date_to: str) -> tuple[bool, str, str]:
    """Check if there is an active (running/paused) background job for the
    given ticker whose date range overlaps with ``[date_from, date_to]``.

    Returns ``(True, job_id, status)`` if found, ``(False, "", "")`` otherwise.

    Checks both in-memory handles and on-disk state files so that stale
    state.json entries left after a crash are also detected.
    """
    ticker_upper = ticker.upper()
    for jid, h in list(_jobs.items()):
        s = h.state
        if (s.ticker.upper() == ticker_upper and s.status in ("running", "paused")
                and _ranges_overlap(date_from, date_to, s.date_from, s.date_to)):
            return True, jid, s.status
    bg_base = DATA_ROOT / "background_runs"
    if bg_base.exists():
        for d in sorted(bg_base.iterdir()):
            if not d.is_dir():
                continue
            sp = d / "state.json"
            if not sp.exists():
                continue
            try:
                state = BackgroundRunState.load(d.name)
            except (OSError, ValueError, KeyError):
                continue
            if (state.ticker.upper() == ticker_upper and state.status in ("running", "paused")
                    and _ranges_overlap(date_from, date_to, state.date_from, state.date_to)):
                return True, d.name, state.status
    return False, "", ""


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
                                    result.duration_s, state.job_id, idx,
                                    final_state=result.final_state)
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
                                result.duration_s, state.job_id, idx,
                                final_state=result.final_state)
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


def _fetch_close_price(ticker: str, date_iso: str) -> tuple[Optional[float], Optional[str]]:
    """Fetch the last closing price for (ticker, date_iso) from market data.

    Background runs have no live price feed, so we fetch the close from
    OHLCV data (typically already cached by the graph run).  Returns
    ``(None, None)`` on any failure so the caller still produces a valid
    run even when price lookup fails.
    """
    from tradingagents.dataflows.stockstats_utils import load_ohlcv
    from tradingagents.dataflows.symbol_utils import NoMarketDataError

    try:
        df = load_ohlcv(ticker, date_iso)
        if df is not None and not df.empty and "Close" in df.columns:
            close = float(df["Close"].iloc[-1])
            ts = f"{date_iso}T20:00:00Z"  # approximate market close
            log.info("_fetch_close_price: %s on %s = %.2f @ %s", ticker, date_iso, close, ts)
            return close, ts
        log.warning("_fetch_close_price: %s on %s — no Close column (df=%s)",
                     ticker, date_iso,
                     "empty" if df is None or df.empty else f"cols={list(df.columns)})")
    except NoMarketDataError:
        log.warning("_fetch_close_price: %s on %s — NoMarketDataError (no data from yahoo)", ticker, date_iso)
    except Exception as exc:
        log.warning("_fetch_close_price: %s on %s — %s: %s", ticker, date_iso, type(exc).__name__, exc)
    return None, None


def _record_run(ticker: str, date_iso: str, decision: Optional[dict], duration_s: float,
                background_job_id: str, background_iteration_index: int,
                final_state: Optional[dict] = None) -> None:
    """Create a standard run directory + run.json for a completed iteration.

    Uses ``storage.create_run_dir`` so that the history endpoint
    (``list_ticker_runs``) finds the run.  The ``trade_date`` field allows
    ``_has_done_run`` to detect duplicates for resume-safety.

    When ``final_state`` is provided, also writes stage files and events
    so background runs have the same persisted data as interactive runs.
    """
    from web.server import events as _events  # defer import
    from web.server import storage  # defer to avoid early import side-effects
    from tradingagents.default_config import DEFAULT_CONFIG  # for model info

    # Use the trade date as the started_at so the slug is meaningful
    # (e.g. "2026-06-01_03-00-00_IDT") and matches historical expectations.
    trade_dt = datetime.fromisoformat(date_iso).replace(tzinfo=timezone.utc)

    # Fetch close price from market data (background runs don't have a
    # live price feed, so we look up the historical close).
    start_price, start_price_at = _fetch_close_price(ticker, date_iso)

    # Fetch end_price: the close price of the next trading day, used to
    # evaluate whether BUY/SELL decisions were correct.
    from dateutil.relativedelta import relativedelta
    next_date_iso = (datetime.fromisoformat(date_iso) + relativedelta(days=1)).date().isoformat()
    end_price, _ = _fetch_close_price(ticker, next_date_iso)

    run_info = storage.create_run_dir(
        ticker,
        started_at=trade_dt,
        llm_provider=DEFAULT_CONFIG.get("llm_provider"),
        deep_think_model=DEFAULT_CONFIG.get("deep_think_llm"),
        quick_think_model=DEFAULT_CONFIG.get("quick_think_llm"),
        start_price=start_price,
        start_price_at=start_price_at,
    )
    run_dir = run_info["run_dir"]
    run_id = run_info["run_id"]
    rj_path = run_dir / "run.json"
    data = json.loads(rj_path.read_text(encoding="utf-8"))

    data["status"] = "done"
    # The propagate call finished, so total_duration_s is known.
    data["total_duration_s"] = duration_s
    data["trade_date"] = date_iso
    data["background_run_id"] = background_job_id
    data["background_run_iteration_index"] = background_iteration_index
    log.info("_record_run: %s/%s start_price=%s start_price_at=%s",
             ticker, date_iso, data.get("start_price"), data.get("start_price_at"))
    dec = decision or {}
    data["decision_action"] = dec.get("action")
    data["decision_target"] = dec.get("target")
    data["decision_rationale"] = dec.get("rationale")
    data["decision_confidence"] = dec.get("confidence")
    data["end_price"] = end_price

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

    # ---- persist stage files + events from final_state ----
    if final_state is None:
        return

    # Map stage names to the report field in final_state.
    _STAGE_REPORT_MAP = {
        "market": "market_report",
        "sentiment": "sentiment_report",
        "news": "news_report",
        "fundamentals": "fundamentals_report",
        "research": "investment_plan",
        "trader": "trader_investment_plan",
        "risk": "final_trade_decision",
    }

    # Write stage files and emit completion events for every stage
    # whose report is present and non-empty in final_state.
    for stage_name, report_field in _STAGE_REPORT_MAP.items():
        report_text = (final_state.get(report_field) or "")
        if not report_text:
            # Try nested path for research/risk debate sub-stages
            if stage_name == "research":
                bs = (final_state.get("investment_debate_state") or {}).get("judge_decision")
                report_text = bs or ""
            elif stage_name == "risk":
                rds = (final_state.get("risk_debate_state") or {}).get("judge_decision")
                report_text = rds or ""
        if not report_text:
            continue

        excerpt = report_text[:200] + "\u2026" if len(report_text) > 200 else report_text
        storage.write_stage(
            run_id,
            stage_name,
            {
                "stage": stage_name,
                "state_key": report_field,
                "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "value": report_text,
            },
        )
        # Emit an analyst_completed event for this stage so the UI's
        # timeline and restore-from-disk paths can pick it up.
        # Note: using string keys matching the WS protocol (same as runner.py).
        _events.emit(run_id, _events.EventType.ANALYST_COMPLETED, {
            "stage": stage_name,
            "summary": "completed",
            "report_excerpt": excerpt,
            "report_text": report_text,
        })

    # Emit the decision event so the dashboard can display it.
    _events.emit(run_id, "decision", {
        "action": dec.get("action"),
        "target": dec.get("target"),
        "rationale": dec.get("rationale"),
        "confidence": dec.get("confidence"),
    })

    # Emit run_finished.
    summary_by_stage = {}
    for s, field in _STAGE_REPORT_MAP.items():
        report = (final_state.get(field) or "")
        if report:
            summary_by_stage[s] = report[:200]
    _events.emit(run_id, "run_finished", {
        "duration_s": duration_s,
        "summary_by_stage": summary_by_stage,
    })


def _run_one(ticker: str, date_iso: str) -> _IterationResult:
    """Call propagate() for a single (ticker, date). Measure wall-clock time.
    Raises on failure (caller decides how to record the error)."""
    t0 = time.monotonic()
    out = _call_propagate(ticker, date_iso)
    duration_s = time.monotonic() - t0
    decision = None
    final_state = None
    if isinstance(out, dict):
        decision = out.get("decision")
        final_state = out.get("final_state")
    return _IterationResult(
        ticker=ticker, date_iso=date_iso,
        duration_s=duration_s, decision=decision,
        final_state=final_state,
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
        state.status = "cancelled"
        state.finished_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        state.persist()
        return
    # Immediately update in-memory state AND persist to disk so list_jobs()
    # (which reads from disk) reflects the change right away.
    h.state.status = "cancelled"
    h.state.finished_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    h.state.persist()
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
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%fZ")
    return f"bgr_{ts}_{ticker}"


def start(ticker: str, date_from: str, date_to: str, every: str = "1d", parallel: int = 1) -> str:
    f, t = _validate_inputs(ticker, date_from, date_to, every, parallel)
    found, existing_id, existing_status = _has_overlapping_job(ticker, date_from, date_to)
    if found:
        existing = get(existing_id)
        raise ValueError(
            f"A background run for {ticker} is already {existing_status} "
            f"(job_id: {existing_id}) with date range "
            f"{existing.get('date_from', '?')}..{existing.get('date_to', '?')}. "
            f"Cancel or wait for it to complete before starting a new one "
            f"with an overlapping range."
        )
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


def delete_job(job_id: str) -> None:
    h = get_handle(job_id)
    if h is not None:
        h.cancel_event.set()
        unregister_handle(job_id)
    d = job_dir(job_id)
    if d.exists():
        import shutil
        shutil.rmtree(d)
