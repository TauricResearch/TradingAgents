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


def _data_root() -> Path:
    p = Path(os.environ.get("TRADINGAGENTS_DATA_DIR", str(Path.home() / ".tradingagents" / "data")))
    p.mkdir(parents=True, exist_ok=True)
    return p


# Convenience alias used by tests; mirrors _data_root() so monkeypatch works.
DATA_ROOT = Path(os.environ.get("TRADINGAGENTS_DATA_DIR", str(Path.home() / ".tradingagents" / "data")))


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
            os.replace(tmp, d / "state.json")
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
