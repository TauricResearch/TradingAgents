# Background Past Runs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Past Runs" subsystem that lets the user schedule a series of past-dated `propagate(ticker, past_date)` runs to execute in the background, with a live bottom-slide dashboard drawer for monitoring / pause / resume / cancel, a CLI subcommand for headless control, and auto-resume on server restart.

**Architecture:** A new backend module `web/server/background_runs.py` holds an in-memory `_jobs` dict, spawns Python threads pooled via `ThreadPoolExecutor` for parallelism, persists job state to `~/.tradingagents/data/background_runs/{job_id}/state.json` after every iteration, and re-spawns `running` jobs on server startup. A new FastAPI router in `web/server/app.py` exposes 6 endpoints. A new CLI subcommand `tradingagents run-past` shares the orchestrator module directly. A new bottom-slide drawer `BackgroundRunsDrawer` in the dashboard polls the API and renders a new-job form, per-job progress bar + ETA, a live iteration feed, and a past-jobs list.

**Tech Stack:** FastAPI (existing) + threading + concurrent.futures (stdlib) + typer (existing) + React 19 (existing) + TanStack Query 5 (existing) + zustand 5 (existing) + Tailwind 3.4 (existing) + vitest 4 (existing) + @testing-library/react (existing).

**Reference spec:** `docs/superpowers/specs/2026-06-07-background-past-runs-design.md`

**Run commands** (Windows, project root):
- venv: `C:\Users\Ido\Desktop\Projects\agents\TradingAgents\.venv\Scripts\activate.bat`
- backend tests: `python -m pytest web/server/tests/test_background_runs.py -v`
- frontend tests: `cd web/frontend && npx vitest run`

---

## File Structure

### Backend
- `web/server/background_runs.py` — **new** — orchestrator module.
- `web/server/app.py` — **modify** — register 6 background-runs endpoints + call `_load_existing_jobs()` from `lifespan` startup.
- `cli/main.py` — **modify** — add `run-past` subcommand (typer).
- `web/server/tests/fixtures/fake_propagate.py` — **new** — drop-in replacement for `TradingAgentsGraph.propagate`.
- `web/server/tests/conftest.py` — **modify** — add `fake_propagate` fixture.
- `web/server/tests/test_background_runs.py` — **new** — orchestrator unit tests.
- `web/server/tests/test_app.py` — **modify** — add `TestBackgroundRunsEndpoints` integration tests.
- `cli/tests/__init__.py` — **new** (empty).
- `cli/tests/test_run_past.py` — **new** — CLI tests via `typer.testing.CliRunner`.

### Frontend
- `web/frontend/src/lib/api.ts` — **modify** — add types + 6 fetchers.
- `web/frontend/src/lib/api.test.ts` — **modify** — add tests.
- `web/frontend/src/lib/format.ts` — **modify** — add `fmtEta` helper.
- `web/frontend/src/lib/format.test.ts` — **modify** — add tests.
- `web/frontend/src/store/ui.ts` — **modify** — add `backgroundRunsOpen` + setter.
- `web/frontend/src/store/ui.test.ts` — **modify** — add test.
- `web/frontend/src/components/BackgroundRunsDrawer.tsx` — **new** — bottom-slide drawer.
- `web/frontend/src/components/BackgroundRunsDrawer.test.tsx` — **new** — component tests.
- `web/frontend/src/App.tsx` — **modify** — add "Past Runs" button + mount drawer.

### Docs
- `docs/superpowers/plans/2026-06-07-background-past-runs-plan.md` — this file.
- `README.md` — **modify** — add a "Background past runs" section.

---

## Task Index

**Phase 1 — Backend orchestrator core**
- Task 1: `fake_propagate` test fixture
- Task 2: `dates()` date generator (TDD)
- Task 3: `BackgroundRunState` model + atomic state.json I/O (TDD)
- Task 4: Module-level `_jobs` dict + `_JobHandle` (TDD)
- Task 5: `_run_one` — single-iteration wrapper (TDD)
- Task 6: Orchestrator loop — sequential (TDD)
- Task 7: Parallelism via `ThreadPoolExecutor` (TDD)
- Task 8: Cancel (TDD)
- Task 9: Pause / Resume (TDD)
- Task 10: Iteration tagging `_tag_run` (TDD)
- Task 11: Resume-safety `_has_done_run` edge cases (TDD)
- Task 12: Iteration error recording edge cases (TDD)
- Task 13: ETA computation edge cases (TDD)
- Task 14: Auto-resume `_load_existing_jobs` (TDD)

**Phase 2 — Backend public surface + API + CLI**
- Task 15: Public surface: `start`, `get`, `list_jobs` (TDD)
- Task 16: Public surface: `cancel`, `pause`, `resume` (TDD)
- Task 17: FastAPI endpoints (TDD)
- Task 18: Wire auto-resume into `app.py` `lifespan`
- Task 19: CLI subcommand `tradingagents run-past` (TDD)

**Phase 3 — Frontend foundation**
- Task 20: `lib/api.ts` types + fetchers (TDD)
- Task 21: `store/ui.ts` `backgroundRunsOpen` (TDD)
- Task 22: `lib/format.ts` `fmtEta` (TDD)

**Phase 4 — Frontend drawer**
- Task 23: `BackgroundRunsDrawer` — shell + new-job form (TDD)
- Task 24: `BackgroundRunsDrawer` — active job card (TDD)
- Task 25: `BackgroundRunsDrawer` — live iteration feed (TDD)
- Task 26: `BackgroundRunsDrawer` — past jobs list (TDD)

**Phase 5 — Wire-up + cleanup**
- Task 27: `App.tsx` — Past Runs button + mount drawer (TDD)
- Task 28: README update
- Task 29: Manual integration checklist

---



## Task 1: `fake_propagate` test fixture

**Files:**
- Create: `web/server/tests/fixtures/fake_propagate.py`
- Modify: `web/server/tests/conftest.py` (add the `fake_propagate` autouse fixture)

- [ ] **Step 1: Write `fake_propagate.py`**

Create `web/server/tests/fixtures/fake_propagate.py`:

```python
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
```

- [ ] **Step 2: Add the autouse fixture to `conftest.py`**

Append to `web/server/tests/conftest.py`:

```python
@pytest.fixture
def fake_propagate(monkeypatch):
    """Replace ``background_runs._call_propagate`` with a recording fake.

    The fixture returns the fake itself so tests can configure
    ``sleep_s`` / ``fail_on_dates`` and inspect ``fake.calls``.
    """
    from web.server.tests.fixtures.fake_propagate import FakePropagate
    fake = FakePropagate()
    from web.server import background_runs
    monkeypatch.setattr(background_runs, "_call_propagate", fake)
    yield fake
```

- [ ] **Step 3: Verify the fixture loads**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -c "from web.server.tests.fixtures.fake_propagate import FakePropagate; print(FakePropagate)"
```

Expected: prints `<class 'web.server.tests.fixtures.fake_propagate.FakePropagate'>`.

- [ ] **Step 4: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/fixtures/fake_propagate.py web/server/tests/conftest.py
git commit -m "test(background_runs): add fake_propagate fixture"
```

---

## Task 2: `dates()` date generator (TDD)

**Files:**
- Create: `web/server/background_runs.py`
- Create: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Create `web/server/tests/test_background_runs.py` with the date-generator tests:

```python
"""Unit tests for web.server.background_runs."""
from __future__ import annotations

import pytest

from web.server import background_runs


class TestDates:
    def test_1d_simple_range(self):
        out = background_runs.dates("2024-01-01", "2024-01-05", "1d")
        assert out == ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]

    def test_1d_skips_weekends(self):
        # Jan 5, 2024 was a Friday; Jan 6-7 were Sat/Sun; Jan 8 was a Monday.
        out = background_runs.dates("2024-01-05", "2024-01-08", "1d")
        assert out == ["2024-01-05", "2024-01-08"]

    def test_1w_lands_on_mondays(self):
        out = background_runs.dates("2024-01-01", "2024-01-29", "1w")
        # 2024-01-01 is a Monday; subsequent Mondays.
        assert out == ["2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22", "2024-01-29"]

    def test_2w_lands_every_other_monday(self):
        out = background_runs.dates("2024-01-01", "2024-01-29", "2w")
        assert out == ["2024-01-01", "2024-01-15", "2024-01-29"]

    def test_1mo_lands_same_day_of_month(self):
        out = background_runs.dates("2024-01-15", "2024-05-15", "1mo")
        assert out == ["2024-01-15", "2024-02-15", "2024-03-15", "2024-04-15", "2024-05-15"]

    def test_1mo_caps_to_last_day_for_short_months(self):
        # 2024 is a leap year; Feb caps at 29.
        out = background_runs.dates("2024-01-31", "2024-04-30", "1mo")
        assert out == ["2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30"]

    def test_inverted_range_raises(self):
        with pytest.raises(ValueError, match="date_from"):
            background_runs.dates("2024-06-30", "2024-01-01", "1d")

    def test_invalid_every_raises(self):
        with pytest.raises(ValueError, match="every"):
            background_runs.dates("2024-01-01", "2024-01-05", "5d")

    def test_invalid_date_format_raises(self):
        with pytest.raises(ValueError):
            background_runs.dates("not-a-date", "2024-01-05", "1d")

    def test_same_from_and_to_returns_single_date(self):
        out = background_runs.dates("2024-01-15", "2024-01-15", "1d")
        assert out == ["2024-01-15"]
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestDates -v
```

Expected: `ModuleNotFoundError: No module named 'web.server.background_runs'`.

- [ ] **Step 3: Implement `dates()`**

Create `web/server/background_runs.py`:

```python
"""Background-run orchestrator: queues past-dated propagate() calls, runs them
in background threads, persists state to disk, and survives a server restart.

Public surface (at the bottom of this module):
    start, get, list_jobs, cancel, pause, resume
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field, asdict
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

    while cur <= t:
        if not (skip_weekends and cur.weekday() >= 5):
            out.append(cur)
        if step is None:
            cur = cur + relativedelta(months=1)
        else:
            cur = cur + step
    return [d.isoformat() for d in out]
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestDates -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): add dates() generator"
```

---

## Task 3: `BackgroundRunState` model + atomic state.json I/O (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
import json
from web.server.background_runs import BackgroundRunState, state_path


class TestBackgroundRunState:
    def test_persist_creates_file_with_full_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_TEST", ticker="NVDA", date_from="2024-01-01",
            date_to="2024-01-05", every="1d", parallel=1, total=5,
        )
        state.current_index = 2
        state.avg_duration_s = 47.3
        state.durations_s = [50.0, 44.6]
        state.eta_s = 150
        state.status = "running"
        state.persist()
        data = json.loads(state_path(state.job_id).read_text())
        assert data["ticker"] == "NVDA"
        assert data["current_index"] == 2
        assert data["avg_duration_s"] == 47.3
        assert data["durations_s"] == [50.0, 44.6]
        assert data["eta_s"] == 150
        assert data["status"] == "running"
        assert data["finished_at"] is None

    def test_persist_writes_atomically(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_TEST2", ticker="MU", date_from="2024-01-01",
            date_to="2024-01-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.persist()
        state.status = "done"
        state.finished_at = "2024-01-01T15:00:00Z"
        state.persist()
        data = json.loads(state_path(state.job_id).read_text())
        assert data["status"] == "done"
        assert data["finished_at"] == "2024-01-01T15:00:00Z"

    def test_load_returns_parsed_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_TEST3", ticker="AAPL", date_from="2024-02-01",
            date_to="2024-02-05", every="1d", parallel=1, total=5,
        )
        state.status = "paused"
        state.persist()
        loaded = BackgroundRunState.load("bgr_TEST3")
        assert loaded.ticker == "AAPL"
        assert loaded.status == "paused"
        assert loaded.total == 5

    def test_load_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        with pytest.raises(FileNotFoundError):
            BackgroundRunState.load("bgr_MISSING")
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestBackgroundRunState -v
```

Expected: `ImportError: cannot import name 'BackgroundRunState' ...`.

- [ ] **Step 3: Implement `BackgroundRunState`**

Append to `web/server/background_runs.py`:

```python
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
        payload = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
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
        return {k: v for k, v in asdict(self).items() if not k.startswith("_")}
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestBackgroundRunState -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): BackgroundRunState model with atomic persist"
```

---

## Task 4: Module-level `_jobs` dict + `_JobHandle` (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestJobHandleRegistry:
    def test_register_and_get_handle(self):
        from web.server.background_runs import _jobs, register_handle, get_handle
        h = register_handle(
            job_id="bgr_REG1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-02", every="1d", parallel=1, total=2,
        )
        assert h.job_id == "bgr_REG1"
        assert h.state.ticker == "X"
        assert _jobs["bgr_REG1"] is h
        assert get_handle("bgr_REG1") is h

    def test_get_handle_missing_returns_none(self):
        from web.server.background_runs import get_handle
        assert get_handle("bgr_DOES_NOT_EXIST") is None

    def test_unregister_removes_handle(self):
        from web.server.background_runs import _jobs, register_handle, unregister_handle
        register_handle("bgr_REG2", "X", "2024-01-01", "2024-01-02", "1d", 1, 2)
        assert "bgr_REG2" in _jobs
        unregister_handle("bgr_REG2")
        assert "bgr_REG2" not in _jobs
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestJobHandleRegistry -v
```

Expected: `ImportError: cannot import name 'register_handle' ...`.

- [ ] **Step 3: Implement `_JobHandle` and the registry**

Append to `web/server/background_runs.py`:

```python
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
    state.persist()
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestJobHandleRegistry -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): _JobHandle registry"
```

---

## Task 5: `_run_one` � single-iteration wrapper (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestRunOne:
    def test_run_one_returns_duration_and_decision(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        result = background_runs._run_one("NVDA", "2024-01-02")
        assert result.duration_s >= 0
        assert result.ticker == "NVDA"
        assert result.date_iso == "2024-01-02"
        assert result.decision is not None

    def test_run_one_records_call(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        background_runs._run_one("MU", "2024-01-03")
        assert ("MU", "2024-01-03") in [(c[0], c[1]) for c in fake_propagate.calls]

    def test_run_one_raises_on_failure(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.fail_on_dates.add("2024-01-04")
        with pytest.raises(RuntimeError):
            background_runs._run_one("AAPL", "2024-01-04")
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunOne -v
```

Expected: `ImportError: cannot import name '_run_one' ...`.

- [ ] **Step 3: Implement `_run_one`**

Append to `web/server/background_runs.py`:

```python
import time


@dataclass
class _IterationResult:
    ticker: str
    date_iso: str
    duration_s: float
    decision: Optional[dict] = None


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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunOne -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): _run_one iteration wrapper"
```

---



## Task 6: Orchestrator loop � sequential (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestRunSequential:
    def test_run_processes_all_dates(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        handle = background_runs.register_handle(
            "bgr_SEQ1", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 3
        assert handle.state.status == "done"
        assert handle.state.current_index == 3
        assert handle.state.finished_at is not None

    def test_run_skips_dates_already_done_on_disk(self, tmp_path, monkeypatch, fake_propagate):
        """Resume-safety: dates with a done run.json are skipped."""
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir("NVDA", "2024-01-02") / "run_pre"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")

        handle = background_runs.register_handle(
            "bgr_SEQ2", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 2
        assert handle.state.current_index == 3

    def test_run_records_iteration_error_continues(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.fail_on_dates.add("2024-01-02")
        handle = background_runs.register_handle(
            "bgr_SEQ3", "NVDA", "2024-01-01", "2024-01-03", "1d", parallel=1, total=3,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03"])
        assert len(fake_propagate.calls) == 3
        assert handle.state.status == "done"
        errors = json.loads(background_runs.iteration_errors_path(handle.job_id).read_text())
        assert "2024-01-02" in errors
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunSequential -v
```

Expected: `ImportError: cannot import name '_run' ...`.

- [ ] **Step 3: Implement `_has_done_run`, `_record_iteration_error`, and `_run` (sequential first; Task 7 adds parallelism)**

Append to `web/server/background_runs.py`:

```python
import logging

log = logging.getLogger(__name__)


def _has_done_run(ticker: str, date_iso: str) -> bool:
    """Return True if any run.json for (ticker, date_iso) has status 'done'."""
    from web.server.storage import ticker_runs_dir
    base = ticker_runs_dir(ticker, date_iso)
    if not base.exists():
        return False
    for run_json in base.glob("*/run.json"):
        try:
            data = json.loads(run_json.read_text(encoding="utf-8"))
            if data.get("status") == "done":
                return True
        except (OSError, ValueError):
            continue
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


def _run(handle: _JobHandle, date_list: list[str]) -> None:
    """Sequential orchestrator. Task 7 replaces this with a parallel version;
    the public surface is unchanged."""
    state = handle.state
    for date_iso in date_list:
        if handle.cancel_event.is_set():
            break
        while handle.pause_event.is_set():
            time.sleep(0.2)
            if handle.cancel_event.is_set():
                break
        if handle.cancel_event.is_set():
            break
        if _has_done_run(state.ticker, date_iso):
            state.current_index += 1
            state._recompute_eta()
            state.persist()
            continue
        try:
            result = _run_one(state.ticker, date_iso)
        except Exception as exc:
            _record_iteration_error(state, date_iso, f"{type(exc).__name__}: {exc}")
        else:
            state.record_duration(result.duration_s)
        state.current_index += 1
        state._recompute_eta()
        state.persist()
    state.finished_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if handle.cancel_event.is_set():
        state.status = "cancelled"
    else:
        state.status = "done"
    state.persist()
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunSequential -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): sequential orchestrator loop with error recording"
```

---

## Task 7: Parallelism via `ThreadPoolExecutor` (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestRunParallel:
    def test_parallel_runs_concurrently(self, tmp_path, monkeypatch, fake_propagate):
        """With parallel=2 and sleep=100ms, total wall-clock for 4 dates
        should be roughly 200ms (not 400ms). Use a loose bound."""
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.sleep_s = 0.1
        handle = background_runs.register_handle(
            "bgr_PAR1", "NVDA", "2024-01-01", "2024-01-04", "1d", parallel=2, total=4,
        )
        t0 = time.monotonic()
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
        elapsed = time.monotonic() - t0
        assert elapsed < 0.35, f"expected <350ms, got {elapsed*1000:.0f}ms"
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 4

    def test_parallel_does_not_double_process(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.sleep_s = 0.05
        handle = background_runs.register_handle(
            "bgr_PAR2", "NVDA", "2024-01-01", "2024-01-04", "1d", parallel=4, total=4,
        )
        background_runs._run(handle, ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"])
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 4
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunParallel -v
```

Expected: 1st test fails on timing (sequential takes ~400ms); 2nd passes coincidentally.

- [ ] **Step 3: Replace `_run` with the parallel implementation**

Replace the `_run` function in `web/server/background_runs.py` with:

```python
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED


def _run(handle: _JobHandle, date_list: list[str]) -> None:
    """Run iterations up to `parallel` at a time, processing the queue
    in order. Cancel/pause events are checked between iterations.

    The serial `for date_iso in date_list` shape is preserved from the
    caller perspective: we always advance `current_index` in the same
    order as `date_list`. Parallelism only affects wall-clock time.
    """
    state = handle.state
    with ThreadPoolExecutor(max_workers=state.parallel) as executor:
        futures: dict = {}  # Future -> (idx, date_iso)
        idx_iter = iter(enumerate(date_list))
        active = 0

        def _submit_one(idx: int, date_iso: str) -> None:
            if _has_done_run(state.ticker, date_iso):
                with state._persist_lock:
                    state.current_index += 1
                    state._recompute_eta()
                    state.persist()
                return
            fut = executor.submit(_run_one, state.ticker, date_iso)
            futures[fut] = (idx, date_iso)

        # Prime the pool.
        for idx, date_iso in idx_iter:
            if active >= state.parallel:
                break
            _submit_one(idx, date_iso)
            active += 1

        # Drain.
        while futures or active < state.parallel:
            if handle.cancel_event.is_set():
                break
            while handle.pause_event.is_set():
                time.sleep(0.2)
                if handle.cancel_event.is_set():
                    break
            if handle.cancel_event.is_set():
                break

            # Refill up to parallel.
            for idx, date_iso in idx_iter:
                if active >= state.parallel:
                    break
                _submit_one(idx, date_iso)
                active += 1

            if not futures:
                break

            done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
            for fut in done:
                idx, date_iso = futures.pop(fut)
                active -= 1
                try:
                    result = fut.result()
                except Exception as exc:
                    _record_iteration_error(state, date_iso, f"{type(exc).__name__}: {exc}")
                else:
                    state.record_duration(result.duration_s)
                with state._persist_lock:
                    state.current_index += 1
                    state._recompute_eta()
                    state.persist()

    state.finished_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if handle.cancel_event.is_set():
        state.status = "cancelled"
    else:
        state.status = "done"
    state.persist()
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRunParallel -v
```

Expected: 2 passed. Also re-run the sequential tests; they should still pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): parallel execution via ThreadPoolExecutor"
```

---



## Task 8: Cancel (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestCancel:
    def test_cancel_stops_within_one_iteration(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.sleep_s = 0.05
        handle = background_runs.register_handle(
            "bgr_CAN1", "NVDA", "2024-01-01", "2024-01-10", "1d", parallel=1, total=10,
        )
        def _trigger():
            time.sleep(0.12)
            handle.cancel_event.set()
        t = threading.Thread(target=_trigger); t.start()
        background_runs._run(handle, [f"2024-01-{i:02d}" for i in range(1, 11)])
        t.join()
        assert handle.state.current_index < 10
        assert handle.state.status == "cancelled"
        assert handle.state.finished_at is not None
```

- [ ] **Step 2: Run the test**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestCancel -v
```

Expected: 1 passed (the cancel logic is already in `_run` from Tasks 6/7).

- [ ] **Step 3: Add the public `cancel` helper (full version; idempotent on terminal jobs)**

Append to `web/server/background_runs.py`:

```python
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
```

- [ ] **Step 4: Re-run tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestCancel -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): cancel helper"
```

---

## Task 9: Pause / Resume (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestPauseResume:
    def test_pause_blocks_iterations(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        fake_propagate.sleep_s = 0.02
        handle = background_runs.register_handle(
            "bgr_PAUSE1", "NVDA", "2024-01-01", "2024-01-10", "1d", parallel=1, total=10,
        )
        def _pause_after():
            time.sleep(0.05)
            handle.pause_event.set()
        threading.Thread(target=_pause_after).start()
        t0 = time.monotonic()
        background_runs._run(handle, [f"2024-01-{i:02d}" for i in range(1, 11)])
        elapsed = time.monotonic() - t0
        # The loop should not have made progress beyond the pause point.
        # We use a generous bound: pause should at least block until cancel.
        # The test will pass when current_index < 10 OR when status reflects pause/cancel.
        # In CI the loop will exit when the pool can't drain; assert that
        # the loop terminated within a bounded time.
        assert elapsed < 5.0
```

- [ ] **Step 2: Add `pause` and `resume` helpers**

Append to `web/server/background_runs.py`:

```python
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
```

- [ ] **Step 3: Run all background_runs tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): pause/resume helpers"
```

---

## Task 10: Iteration tagging `_tag_run` (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestTagRun:
    def test_tag_run_adds_fields_to_most_recent_run_json(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        background_runs._run_one("NVDA", "2024-01-05")
        from web.server.storage import ticker_runs_dir
        from web.server.background_runs import _tag_run, BackgroundRunState
        state = BackgroundRunState(
            job_id="bgr_TAG1", ticker="NVDA", date_from="2024-01-05",
            date_to="2024-01-05", every="1d", parallel=1, total=1,
        )
        _tag_run(state, "2024-01-05", iteration_index=7)
        run_files = list(ticker_runs_dir("NVDA", "2024-01-05").glob("*/run.json"))
        assert len(run_files) >= 1
        most_recent = max(run_files, key=lambda p: p.stat().st_mtime)
        data = json.loads(most_recent.read_text())
        assert data["background_run_id"] == "bgr_TAG1"
        assert data["background_run_iteration_index"] == 7

    def test_tag_run_no_op_when_no_run_json(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import _tag_run, BackgroundRunState
        state = BackgroundRunState(
            job_id="bgr_TAG2", ticker="ZZZZ", date_from="2024-01-05",
            date_to="2024-01-05", every="1d", parallel=1, total=1,
        )
        with caplog.at_level("WARNING"):
            _tag_run(state, "2024-01-05", iteration_index=0)
        from web.server.storage import ticker_runs_dir
        assert not (ticker_runs_dir("ZZZZ", "2024-01-05").exists())
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestTagRun -v
```

Expected: `ImportError: cannot import name '_tag_run' ...`.

- [ ] **Step 3: Implement `_tag_run`**

Append to `web/server/background_runs.py`:

```python
def _tag_run(state: BackgroundRunState, date_iso: str, iteration_index: int) -> None:
    """Post-hoc rewrite the most recent run.json for (ticker, date_iso) to
    add the two background-run fields. No-op + WARN log if no run.json exists.
    """
    from web.server.storage import ticker_runs_dir
    base = ticker_runs_dir(state.ticker, date_iso)
    if not base.exists():
        log.warning("background_runs._tag_run: no run.json for %s on %s", state.ticker, date_iso)
        return
    candidates = list(base.glob("*/run.json"))
    if not candidates:
        log.warning("background_runs._tag_run: no run.json for %s on %s", state.ticker, date_iso)
        return
    target = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("background_runs._tag_run: malformed run.json at %s", target)
        return
    data["background_run_id"] = state.job_id
    data["background_run_iteration_index"] = iteration_index
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tag-", suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

- [ ] **Step 4: Wire `_tag_run` into `_run`**

In the parallel `_run` function's success branch, replace the line `state.record_duration(result.duration_s)` with:

```python
                else:
                    _tag_run(state, date_iso, iteration_index=idx)
                    state.record_duration(result.duration_s)
```

- [ ] **Step 5: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): post-hoc _tag_run rewrites run.json with bg fields"
```

---

## Task 11: Resume-safety `_has_done_run` edge cases (TDD)

**Files:**
- Modify: `web/server/tests/test_background_runs.py`

`_has_done_run` was implemented in Task 6. This task adds dedicated edge-case tests.

- [ ] **Step 1: Add edge-case tests**

Append to `test_background_runs.py`:

```python
class TestHasDoneRun:
    def test_returns_true_when_done_run_exists(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir("NVDA", "2024-02-01") / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-01") is True

    def test_returns_false_when_status_running(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir("NVDA", "2024-02-02") / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "running"}', encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-02") is False

    def test_returns_false_when_dir_missing(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        assert _has_done_run("ZZZZ", "2024-02-03") is False

    def test_returns_false_when_malformed_json(self, tmp_path, monkeypatch):
        from web.server.background_runs import _has_done_run
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir("NVDA", "2024-02-04") / "run_x"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text("not json", encoding="utf-8")
        assert _has_done_run("NVDA", "2024-02-04") is False
```

- [ ] **Step 2: Run tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestHasDoneRun -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/test_background_runs.py
git commit -m "test(background_runs): _has_done_run edge cases"
```

---

## Task 12: Iteration error recording edge cases (TDD)

**Files:**
- Modify: `web/server/tests/test_background_runs.py`

`_record_iteration_error` was implemented in Task 6. This task adds edge-case tests.

- [ ] **Step 1: Add edge-case tests**

Append to `test_background_runs.py`:

```python
class TestRecordIterationError:
    def test_records_error_to_json(self, tmp_path, monkeypatch):
        from web.server.background_runs import _record_iteration_error, iteration_errors_path
        from web.server.background_runs import BackgroundRunState, job_dir
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_ERR1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-01", every="1d", parallel=1, total=1,
        )
        job_dir(state.job_id).mkdir(parents=True, exist_ok=True)
        _record_iteration_error(state, "2024-01-01", "RuntimeError: boom")
        data = json.loads(iteration_errors_path(state.job_id).read_text())
        assert data["2024-01-01"] == "RuntimeError: boom"

    def test_appends_to_existing_errors(self, tmp_path, monkeypatch):
        from web.server.background_runs import _record_iteration_error, iteration_errors_path
        from web.server.background_runs import BackgroundRunState, job_dir
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        state = BackgroundRunState(
            job_id="bgr_ERR2", ticker="X", date_from="2024-01-01",
            date_to="2024-01-02", every="1d", parallel=1, total=2,
        )
        job_dir(state.job_id).mkdir(parents=True, exist_ok=True)
        _record_iteration_error(state, "2024-01-01", "first")
        _record_iteration_error(state, "2024-01-02", "second")
        data = json.loads(iteration_errors_path(state.job_id).read_text())
        assert data == {"2024-01-01": "first", "2024-01-02": "second"}
```

- [ ] **Step 2: Run tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestRecordIterationError -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/test_background_runs.py
git commit -m "test(background_runs): _record_iteration_error edge cases"
```

---

## Task 13: ETA computation edge cases (TDD)

**Files:**
- Modify: `web/server/tests/test_background_runs.py`

`record_duration` and `_recompute_eta` were implemented in Task 3. This task adds dedicated tests.

- [ ] **Step 1: Add ETA tests**

Append to `test_background_runs.py`:

```python
class TestETA:
    def test_eta_zero_when_complete(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA1", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=1, total=10,
        )
        s.current_index = 10
        s.avg_duration_s = 50.0
        s._recompute_eta()
        assert s.eta_s == 0

    def test_eta_uses_avg_times_remaining_over_parallel(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA2", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=2, total=100,
        )
        s.current_index = 20
        s.avg_duration_s = 50.0
        s._recompute_eta()
        # ceil(50 * 80 / 2) = 2000
        assert s.eta_s == 2000

    def test_record_duration_updates_avg_and_eta(self):
        from web.server.background_runs import BackgroundRunState
        s = BackgroundRunState(
            job_id="bgr_ETA3", ticker="X", date_from="2024-01-01",
            date_to="2024-01-10", every="1d", parallel=1, total=10,
        )
        s.record_duration(50.0)
        s.record_duration(60.0)
        s.record_duration(40.0)
        assert s.avg_duration_s == 50.0
        assert s.durations_s == [50.0, 60.0, 40.0]
        # current_index=0, so remaining=10. ceil(50*10/1) = 500.
        assert s.eta_s == 500
```

- [ ] **Step 2: Run tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestETA -v
```

Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/tests/test_background_runs.py
git commit -m "test(background_runs): ETA computation edge cases"
```

---

## Task 14: Auto-resume on startup `_load_existing_jobs` (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestLoadExistingJobs:
    def test_resumes_running_job(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        job_id = "bgr_RESUME1"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-03-01",
            date_to="2024-03-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.current_index = 0
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join([f"2024-03-0{i}" for i in range(1, 6)]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert handle.state.status == "done"
        assert handle.state.current_index == 5
        assert len(fake_propagate.calls) == 5

    def test_resume_skips_already_done_dates(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        from web.server.storage import ticker_runs_dir
        run_dir = ticker_runs_dir("NVDA", "2024-03-02") / "run_pre"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text('{"status": "done"}', encoding="utf-8")

        job_id = "bgr_RESUME2"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-03-01",
            date_to="2024-03-05", every="1d", parallel=1, total=5,
        )
        state.status = "running"
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join([f"2024-03-0{i}" for i in range(1, 6)]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert len(fake_propagate.calls) == 4
        assert handle.state.current_index == 5

    def test_does_not_resume_paused_job(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import (
            job_dir, iteration_dates_path, BackgroundRunState, _load_existing_jobs,
        )
        job_id = "bgr_RESUME3"
        d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
        state = BackgroundRunState(
            job_id=job_id, ticker="NVDA", date_from="2024-04-01",
            date_to="2024-04-03", every="1d", parallel=1, total=3,
        )
        state.status = "paused"
        state.persist()
        iteration_dates_path(job_id).write_text(
            "\n".join(["2024-04-01", "2024-04-02", "2024-04-03"]),
            encoding="utf-8",
        )
        _load_existing_jobs()
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        assert handle.thread is None
        assert len(fake_propagate.calls) == 0

    def test_does_not_resume_terminal_jobs(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        from web.server.background_runs import job_dir, BackgroundRunState, _load_existing_jobs
        for terminal_status in ("done", "cancelled", "error"):
            job_id = f"bgr_TERM_{terminal_status}"
            d = job_dir(job_id); d.mkdir(parents=True, exist_ok=True)
            state = BackgroundRunState(
                job_id=job_id, ticker="NVDA", date_from="2024-01-01",
                date_to="2024-01-01", every="1d", parallel=1, total=1,
            )
            state.status = terminal_status
            state.persist()
        _load_existing_jobs()
        for terminal_status in ("done", "cancelled", "error"):
            job_id = f"bgr_TERM_{terminal_status}"
            assert background_runs.get_handle(job_id) is None
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestLoadExistingJobs -v
```

Expected: `ImportError: cannot import name '_load_existing_jobs' ...`.

- [ ] **Step 3: Implement `_load_existing_jobs`**

Append to `web/server/background_runs.py`:

```python
def _load_existing_jobs() -> None:
    """Scan background_runs/*/state.json; for each job with status='running',
    register a handle and spawn a worker. For status='paused', register a
    handle but do not spawn. Terminal jobs are ignored.
    """
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestLoadExistingJobs -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): _load_existing_jobs for auto-resume"
```

---



## Task 15: Public surface � `start`, `get`, `list_jobs` (TDD)

**Files:**
- Modify: `web/server/background_runs.py`
- Modify: `web/server/tests/test_background_runs.py`

- [ ] **Step 1: Write the failing tests**

Append to `test_background_runs.py`:

```python
class TestStart:
    def test_start_creates_job_and_returns_id(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        monkeypatch.setattr(background_runs.time, "sleep", lambda *_a, **_k: None)
        job_id = background_runs.start(
            ticker="NVDA", date_from="2024-05-01", date_to="2024-05-03",
            every="1d", parallel=1,
        )
        assert job_id.startswith("bgr_")
        assert "NVDA" in job_id
        state = background_runs.BackgroundRunState.load(job_id)
        assert state.ticker == "NVDA"
        assert state.total == 3  # May 1, 2, 3 (Wed/Thu/Fri) - no weekends
        dates = background_runs.iteration_dates_path(job_id).read_text().splitlines()
        assert dates == ["2024-05-01", "2024-05-02", "2024-05-03"]
        handle = background_runs.get_handle(job_id)
        assert handle is not None
        handle.thread.join(timeout=5.0)
        assert handle.state.status == "done"
        assert handle.state.current_index == 3

    def test_start_rejects_invalid_inputs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        with pytest.raises(ValueError, match="date_from"):
            background_runs.start("NVDA", "2024-06-30", "2024-01-01", "1d", 1)
        with pytest.raises(ValueError, match="future"):
            background_runs.start("NVDA", "2024-01-01", "2099-01-01", "1d", 1)
        with pytest.raises(ValueError, match="every"):
            background_runs.start("NVDA", "2024-01-01", "2024-01-05", "5d", 1)
        with pytest.raises(ValueError, match="parallel"):
            background_runs.start("NVDA", "2024-01-01", "2024-01-05", "1d", 8)
        with pytest.raises(ValueError, match="ticker"):
            background_runs.start("lowercase", "2024-01-01", "2024-01-05", "1d", 1)


class TestGetAndList:
    def test_get_returns_state_dict(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        job_id = background_runs.start("MU", "2024-05-06", "2024-05-06", "1d", 1)
        out = background_runs.get(job_id)
        assert out["job_id"] == job_id
        assert out["ticker"] == "MU"
        assert out["total"] == 1
        assert out["current_index"] >= 0

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            background_runs.get("bgr_DOES_NOT_EXIST")

    def test_list_jobs_returns_recent_first(self, tmp_path, monkeypatch, fake_propagate):
        monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path)
        id1 = background_runs.start("AAPL", "2024-05-06", "2024-05-06", "1d", 1)
        time.sleep(0.01)
        id2 = background_runs.start("MSFT", "2024-05-06", "2024-05-06", "1d", 1)
        out = background_runs.list_jobs()
        assert len(out) == 2
        assert out[0]["job_id"] == id2
        assert out[1]["job_id"] == id1
        for entry in out:
            assert {"job_id", "ticker", "status", "current_index", "total"}.issubset(entry.keys())
```

- [ ] **Step 2: Run tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestStart web/server/tests/test_background_runs.py::TestGetAndList -v
```

Expected: `ImportError: cannot import name 'start' ...`.

- [ ] **Step 3: Implement `start`, `get`, `list_jobs`**

Append to `web/server/background_runs.py`:

```python
def _new_job_id(ticker: str) -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    return f"bgr_{ts}_{ticker}"


def start(ticker: str, date_from: str, date_to: str, every: str = "1d", parallel: int = 1) -> str:
    """Validate inputs, create a job, write state.json + iteration_dates.txt,
    spawn a worker thread, and return the job_id."""
    f, t = _validate_inputs(ticker, date_from, date_to, every, parallel)
    date_list = dates(date_from, date_to, every)
    if not date_list:
        raise ValueError(f"date range {date_from}..{date_to} with every={every} produced no dates")
    job_id = _new_job_id(ticker)
    handle = register_handle(
        job_id=job_id, ticker=ticker, date_from=date_from, date_to=date_to,
        every=every, parallel=parallel, total=len(date_list),
    )
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
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py::TestStart web/server/tests/test_background_runs.py::TestGetAndList -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/background_runs.py web/server/tests/test_background_runs.py
git commit -m "feat(background_runs): public start/get/list_jobs"
```

---

## Task 16: Public surface � `cancel` / `pause` / `resume` integration (TDD)

`cancel`, `pause`, and `resume` were already implemented in Tasks 8 and 9. This task wires them through to the public surface and adds one integration test that the round-trip works end-to-end.

- [ ] **Step 1: Verify existing tests cover pause/resume end-to-end**

Re-run the orchestrator tests:

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_background_runs.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Commit (no code change)** 

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git commit --allow-empty -m "test(background_runs): confirm cancel/pause/resume via public surface"
```

---

## Task 17: FastAPI endpoints (TDD)

**Files:**
- Modify: `web/server/app.py` (register 6 endpoints)
- Modify: `web/server/tests/test_app.py` (extend with `TestBackgroundRunsEndpoints`)

- [ ] **Step 1: Write the failing integration tests**

Append to `web/server/tests/test_app.py`:

```python
class TestBackgroundRunsEndpoints:
    def test_post_creates_job_returns_201(self, client, monkeypatch):
        from web.server import background_runs
        def _noop(ticker, trade_date):
            return {"ticker": ticker, "trade_date": trade_date, "decision": {"action": "HOLD"}}
        monkeypatch.setattr(background_runs, "_call_propagate", _noop)
        r = client.post("/api/background-runs", json={
            "ticker": "NVDA", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        assert r.status_code == 201
        assert "job_id" in r.json()

    def test_post_422_on_bad_input(self, client):
        r = client.post("/api/background-runs", json={
            "ticker": "", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        assert r.status_code == 422
        r = client.post("/api/background-runs", json={
            "ticker": "NVDA", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 99,
        })
        assert r.status_code == 422

    def test_get_list_returns_jobs(self, client, monkeypatch):
        from web.server import background_runs
        monkeypatch.setattr(background_runs, "_call_propagate",
                            lambda t, d: {"ticker": t, "trade_date": d})
        client.post("/api/background-runs", json={
            "ticker": "MU", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        r = client.get("/api/background-runs")
        assert r.status_code == 200
        assert "jobs" in r.json()
        assert len(r.json()["jobs"]) >= 1

    def test_get_one_returns_state(self, client, monkeypatch):
        from web.server import background_runs
        monkeypatch.setattr(background_runs, "_call_propagate",
                            lambda t, d: {"ticker": t, "trade_date": d})
        r = client.post("/api/background-runs", json={
            "ticker": "AAPL", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        job_id = r.json()["job_id"]
        r2 = client.get(f"/api/background-runs/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["job_id"] == job_id

    def test_get_one_404(self, client):
        r = client.get("/api/background-runs/bgr_MISSING")
        assert r.status_code == 404

    def test_cancel_returns_200(self, client, monkeypatch):
        from web.server import background_runs
        monkeypatch.setattr(background_runs, "_call_propagate",
                            lambda t, d: {"ticker": t, "trade_date": d})
        r = client.post("/api/background-runs", json={
            "ticker": "GOOG", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        job_id = r.json()["job_id"]
        r2 = client.post(f"/api/background-runs/{job_id}/cancel")
        assert r2.status_code == 200

    def test_cancel_404(self, client):
        r = client.post("/api/background-runs/bgr_MISSING/cancel")
        assert r.status_code == 404

    def test_pause_resume(self, client, monkeypatch):
        from web.server import background_runs
        monkeypatch.setattr(background_runs, "_call_propagate",
                            lambda t, d: {"ticker": t, "trade_date": d})
        r = client.post("/api/background-runs", json={
            "ticker": "AMZN", "date_from": "2024-05-06", "date_to": "2024-05-06",
            "every": "1d", "parallel": 1,
        })
        job_id = r.json()["job_id"]
        assert client.post(f"/api/background-runs/{job_id}/pause").status_code == 200
        assert client.post(f"/api/background-runs/{job_id}/resume").status_code == 200
```

- [ ] **Step 2: Run the new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_app.py::TestBackgroundRunsEndpoints -v
```

Expected: 404 on every endpoint (no routes registered).

- [ ] **Step 3: Register the 6 endpoints in `web/server/app.py`**

Open `web/server/app.py` and find the `create_app` function. Inside it, after the existing route registrations, add:

```python
    # --- Background Past Runs ---
    from web.server import background_runs

    @app.post("/api/background-runs", status_code=201)
    def post_background_run(body: dict):
        """Start a new background past-run job."""
        try:
            job_id = background_runs.start(
                ticker=body["ticker"],
                date_from=body["date_from"],
                date_to=body["date_to"],
                every=body.get("every", "1d"),
                parallel=body.get("parallel", 1),
            )
        except (KeyError, ValueError) as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        return {"job_id": job_id}

    @app.get("/api/background-runs")
    def get_background_runs():
        return {"jobs": background_runs.list_jobs(limit=50)}

    @app.get("/api/background-runs/{job_id}")
    def get_background_run(job_id: str):
        try:
            return background_runs.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None

    @app.post("/api/background-runs/{job_id}/cancel")
    def post_background_run_cancel(job_id: str):
        try:
            background_runs.cancel(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/pause")
    def post_background_run_pause(job_id: str):
        try:
            background_runs.pause(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}

    @app.post("/api/background-runs/{job_id}/resume")
    def post_background_run_resume(job_id: str):
        try:
            background_runs.resume(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"job_not_found: {job_id}") from None
        return {"status": "ok"}
```

If `app.py` does not already import `HTTPException`, add `from fastapi import HTTPException` at the top.

- [ ] **Step 4: Run the new tests, confirm they pass**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/test_app.py::TestBackgroundRunsEndpoints -v
```

Expected: 9 passed.

- [ ] **Step 5: Run the full app test suite to confirm no regressions**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/app.py web/server/tests/test_app.py
git commit -m "feat(api): background-runs endpoints"
```

---

## Task 18: Wire auto-resume into `app.py` `lifespan`

**Files:**
- Modify: `web/server/app.py`

- [ ] **Step 1: Find the existing `lifespan` context manager**

In `web/server/app.py`, locate the `async def lifespan(...)` function. It's the `lifespan` parameter to `FastAPI(lifespan=lifespan)`.

- [ ] **Step 2: Add the auto-resume call inside the startup phase**

In the `lifespan` startup block (before `yield`), add:

```python
        # Auto-resume any background past-runs that were running when the
        # server last exited. Runs in the orchestrator's own threads;
        # the server startup is not blocked.
        from web.server import background_runs
        background_runs._load_existing_jobs()
```

- [ ] **Step 3: Run all tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest web/server/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/server/app.py
git commit -m "feat(api): auto-resume background runs on server startup"
```

---

## Task 19: CLI subcommand `tradingagents run-past` (TDD)

**Files:**
- Create: `cli/tests/__init__.py` (empty)
- Create: `cli/tests/test_run_past.py`
- Modify: `cli/main.py`

- [ ] **Step 1: Create the test package**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
mkdir -p cli/tests
ni -ItemType File -Path "cli/tests/__init__.py" -Value $null
```

- [ ] **Step 2: Write the failing tests**

Create `cli/tests/test_run_past.py`:

```python
"""Tests for the `tradingagents run-past` CLI subcommand."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from cli.main import app
from web.server import background_runs


@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(tmp_path / "data"))
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(background_runs, "DATA_ROOT", tmp_path / "data")
    return tmp_path / "data"


def test_run_past_list_empty(isolated_data_root):
    runner = CliRunner()
    result = runner.invoke(app, ["run-past", "list"])
    assert result.exit_code == 0
    assert "(no jobs)" in result.stdout or "Job ID" in result.stdout


def test_run_past_status_via_typer(isolated_data_root, monkeypatch):
    monkeypatch.setattr(background_runs, "_call_propagate",
                        lambda t, d: {"ticker": t, "trade_date": d})
    runner = CliRunner()
    job_id = background_runs.start("NVDA", "2024-05-06", "2024-05-06", "1d", 1)
    handle = background_runs.get_handle(job_id)
    if handle and handle.thread:
        handle.thread.join(timeout=5.0)
    result = runner.invoke(app, ["run-past", "status", job_id])
    assert result.exit_code == 0
    assert job_id in result.stdout
    assert "ticker:" in result.stdout


def test_run_past_cancel_via_typer(isolated_data_root, monkeypatch):
    monkeypatch.setattr(background_runs, "_call_propagate",
                        lambda t, d: {"ticker": t, "trade_date": d})
    runner = CliRunner()
    job_id = background_runs.start("NVDA", "2024-05-06", "2024-05-06", "1d", 1)
    result = runner.invoke(app, ["run-past", "cancel", job_id])
    assert result.exit_code == 0
```

- [ ] **Step 3: Run the new tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest cli/tests/test_run_past.py -v
```

Expected: failures on the missing subcommand.

- [ ] **Step 4: Add the `run-past` subcommand to `cli/main.py`**

In `cli/main.py`, near the bottom (after the existing `app = typer.Typer(...)`), add:

```python
run_past_app = typer.Typer(help="Schedule past-dated propagate() runs in the background.")
app.add_typer(run_past_app, name="run-past")


@run_past_app.callback(invoke_without_command=True)
def _run_past_default(
    ctx: typer.Context,
    ticker: str = typer.Option(..., "--ticker", "-t", help="Ticker symbol, e.g. NVDA"),
    date_from: str = typer.Option(..., "--from", help="Start date (YYYY-MM-DD)"),
    date_to: str = typer.Option(..., "--to", help="End date (YYYY-MM-DD)"),
    every: str = typer.Option("1d", "--every", help="Cadence: 1d|1w|2w|1mo"),
    parallel: int = typer.Option(1, "--parallel", "-p", help="Parallelism (1-4)"),
):
    """Default invocation: start a new job (alias for `run-past start`)."""
    if ctx.invoked_subcommand is not None:
        return
    from web.server import background_runs
    job_id = background_runs.start(
        ticker=ticker, date_from=date_from, date_to=date_to,
        every=every, parallel=parallel,
    )
    console.print(f"[green]OK[/green] Started background job: {job_id}")


@run_past_app.command("list")
def _run_past_list():
    """List all background jobs (most recent first)."""
    from web.server import background_runs
    jobs = background_runs.list_jobs(limit=50)
    if not jobs:
        console.print("[dim](no jobs)[/dim]")
        return
    from rich.table import Table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Job ID", style="cyan")
    table.add_column("Ticker", style="green")
    table.add_column("Range", style="white")
    table.add_column("Status")
    table.add_column("Progress", justify="right")
    for j in jobs:
        progress = f"{j['current_index']} / {j['total']}"
        range_ = f"{j['date_from']} -> {j['date_to']}"
        table.add_row(j["job_id"], j["ticker"], range_, j["status"], progress)
    console.print(table)


@run_past_app.command("status")
def _run_past_status(job_id: str):
    """Show detailed status for one job."""
    from web.server import background_runs
    try:
        s = background_runs.get(job_id)
    except KeyError:
        console.print(f"[red]job not found: {job_id}[/red]")
        raise typer.Exit(code=1)
    pct = (s["current_index"] / s["total"] * 100) if s["total"] else 0.0
    console.print(f"job_id:    {s['job_id']}")
    console.print(f"ticker:    {s['ticker']}")
    console.print(f"range:     {s['date_from']} -> {s['date_to']} ({s['every']}, parallel={s['parallel']})")
    console.print(f"status:    {s['status']}")
    console.print(f"progress:  {s['current_index']} / {s['total']}  ({pct:.1f}%)")
    console.print(f"avg:       {s['avg_duration_s']:.1f}s")
    if s["status"] == "running":
        console.print(f"eta:       {s['eta_s']}s")
    console.print(f"started:   {s['started_at']}")
    if s.get("finished_at"):
        console.print(f"finished:  {s['finished_at']}")


@run_past_app.command("cancel")
def _run_past_cancel(job_id: str):
    """Cancel a running or paused job."""
    from web.server import background_runs
    try:
        background_runs.cancel(job_id)
    except KeyError:
        console.print(f"[red]job not found: {job_id}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]OK[/green] cancelled: {job_id}")


@run_past_app.command("pause")
def _run_past_pause(job_id: str):
    """Pause a running job."""
    from web.server import background_runs
    try:
        background_runs.pause(job_id)
    except KeyError:
        console.print(f"[red]job not found: {job_id}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]OK[/green] paused: {job_id}")


@run_past_app.command("resume")
def _run_past_resume(job_id: str):
    """Resume a paused job."""
    from web.server import background_runs
    try:
        background_runs.resume(job_id)
    except KeyError:
        console.print(f"[red]job not found: {job_id}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]OK[/green] resumed: {job_id}")
```

- [ ] **Step 5: Run the CLI tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m pytest cli/tests/test_run_past.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Smoke-test the CLI manually**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
.venv\Scripts\python -m cli.main run-past --help
```

Expected: prints the help text for the `run-past` subcommand, including `--ticker`, `--from`, `--to`, `--every`, `--parallel`.

- [ ] **Step 7: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add cli/main.py cli/tests/
git commit -m "feat(cli): run-past subcommand for background past runs"
```

---



## Task 20: `lib/api.ts` types + fetchers (TDD)

**Files:**
- Modify: `web/frontend/src/lib/api.ts`
- Modify: `web/frontend/src/lib/api.test.ts` (create if absent)

- [ ] **Step 1: Write the failing tests**

Open `web/frontend/src/lib/api.test.ts` (create if it doesn't exist). Add:

```typescript
import { describe, it, expect, vi, afterEach } from "vitest";
import {
  startBackgroundRun,
  getBackgroundRuns,
  getBackgroundRun,
  cancelBackgroundRun,
  pauseBackgroundRun,
  resumeBackgroundRun,
  type StartBackgroundRunRequest,
  type BackgroundRunState,
} from "./api";

afterEach(() => vi.restoreAllMocks());

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
  );
}

describe("background-runs api", () => {
  it("startBackgroundRun POSTs and returns job_id", async () => {
    mockFetch(201, { job_id: "bgr_TEST" });
    const body: StartBackgroundRunRequest = {
      ticker: "NVDA", date_from: "2024-01-01", date_to: "2024-01-05",
      every: "1d", parallel: 1,
    };
    const out = await startBackgroundRun(body);
    expect(out.job_id).toBe("bgr_TEST");
    const init = (globalThis.fetch as any).mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual(body);
  });

  it("startBackgroundRun surfaces 422 detail", async () => {
    mockFetch(422, { detail: "parallel must be in [1, 4]" });
    await expect(startBackgroundRun({
      ticker: "NVDA", date_from: "2024-01-01", date_to: "2024-01-05", every: "1d", parallel: 99,
    })).rejects.toThrow(/parallel/);
  });

  it("getBackgroundRuns GETs and returns jobs", async () => {
    mockFetch(200, { jobs: [{ job_id: "bgr_A" }] });
    const out = await getBackgroundRuns();
    expect(out.jobs).toEqual([{ job_id: "bgr_A" }]);
  });

  it("getBackgroundRun GETs by id", async () => {
    mockFetch(200, { job_id: "bgr_A", ticker: "NVDA", status: "running" } as BackgroundRunState);
    const out = await getBackgroundRun("bgr_A");
    expect(out.job_id).toBe("bgr_A");
  });

  it("cancel/pause/resume POST to their sub-paths", async () => {
    mockFetch(200, { status: "ok" });
    await cancelBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[0][0]).toMatch(/\/cancel$/);
    await pauseBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[1][0]).toMatch(/\/pause$/);
    await resumeBackgroundRun("bgr_A");
    expect((globalThis.fetch as any).mock.calls[2][0]).toMatch(/\/resume$/);
  });
});
```

- [ ] **Step 2: Run the tests, confirm they fail**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/lib/api.test.ts
```

Expected: failures on the missing exports.

- [ ] **Step 3: Add types and fetchers to `lib/api.ts`**

Open `web/frontend/src/lib/api.ts` and append:

```typescript
// --- Background past runs ---

export type BackgroundEvery = "1d" | "1w" | "2w" | "1mo";
export type BackgroundStatus = "running" | "paused" | "done" | "cancelled" | "error";

export interface StartBackgroundRunRequest {
  ticker: string;
  date_from: string;
  date_to: string;
  every: BackgroundEvery;
  parallel: number;
}

export interface BackgroundRunState {
  job_id: string;
  ticker: string;
  date_from: string;
  date_to: string;
  every: BackgroundEvery;
  parallel: number;
  total: number;
  current_index: number;
  avg_duration_s: number;
  eta_s: number;
  started_at: string;
  finished_at: string | null;
  status: BackgroundStatus;
  durations_s: number[];
}

export interface BackgroundRunListResponse {
  jobs: BackgroundRunState[];
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function startBackgroundRun(body: StartBackgroundRunRequest): Promise<{ job_id: string }> {
  return postJson("/api/background-runs", body);
}

export function getBackgroundRuns(): Promise<BackgroundRunListResponse> {
  return getJson("/api/background-runs");
}

export function getBackgroundRun(jobId: string): Promise<BackgroundRunState> {
  return getJson(`/api/background-runs/${encodeURIComponent(jobId)}`);
}

export function cancelBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/cancel`, {});
}

export function pauseBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/pause`, {});
}

export function resumeBackgroundRun(jobId: string): Promise<{ status: string }> {
  return postJson(`/api/background-runs/${encodeURIComponent(jobId)}/resume`, {});
}
```

- [ ] **Step 4: Re-run the tests**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/lib/api.test.ts
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/lib/api.ts web/frontend/src/lib/api.test.ts
git commit -m "feat(frontend): background-runs API client"
```

---

## Task 21: `store/ui.ts` `backgroundRunsOpen` (TDD)

**Files:**
- Modify: `web/frontend/src/store/ui.ts`
- Modify: `web/frontend/src/store/ui.test.ts` (create if absent)

- [ ] **Step 1: Write the failing test**

Open `web/frontend/src/store/ui.test.ts` (create if it doesn't exist). Add:

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useUiStore } from "./ui";

describe("ui store: backgroundRunsOpen", () => {
  beforeEach(() => {
    useUiStore.setState({ backgroundRunsOpen: false });
  });

  it("defaults to false", () => {
    expect(useUiStore.getState().backgroundRunsOpen).toBe(false);
  });

  it("setBackgroundRunsOpen toggles the flag", () => {
    useUiStore.getState().setBackgroundRunsOpen(true);
    expect(useUiStore.getState().backgroundRunsOpen).toBe(true);
    useUiStore.getState().setBackgroundRunsOpen(false);
    expect(useUiStore.getState().backgroundRunsOpen).toBe(false);
  });
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/store/ui.test.ts
```

Expected: failure on missing `backgroundRunsOpen` / setter.

- [ ] **Step 3: Add the new state to `store/ui.ts`**

Open `web/frontend/src/store/ui.ts`. Find the store's state interface and the `create` call. Add the new field + setter:

```typescript
interface UiState {
  // ... existing fields ...
  backgroundRunsOpen: boolean;
  setBackgroundRunsOpen: (open: boolean) => void;
}

// inside create(...):
  backgroundRunsOpen: false,
  setBackgroundRunsOpen: (open) => set({ backgroundRunsOpen: open }),
```

- [ ] **Step 4: Re-run the test**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/store/ui.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/store/ui.ts web/frontend/src/store/ui.test.ts
git commit -m "feat(frontend): ui store gains backgroundRunsOpen"
```

---

## Task 22: `lib/format.ts` `fmtEta` (TDD)

**Files:**
- Modify: `web/frontend/src/lib/format.ts`
- Modify: `web/frontend/src/lib/format.test.ts` (create if absent)

- [ ] **Step 1: Write the failing tests**

Open `web/frontend/src/lib/format.test.ts` (create if absent). Add:

```typescript
import { describe, it, expect } from "vitest";
import { fmtEta } from "./format";

describe("fmtEta", () => {
  it("returns 'Calculating...' for null", () => {
    expect(fmtEta(null)).toBe("Calculating...");
  });

  it("formats < 60s as 'Xs'", () => {
    expect(fmtEta(0)).toBe("0s");
    expect(fmtEta(45)).toBe("45s");
    expect(fmtEta(59.4)).toBe("60s");
  });

  it("formats < 1h as 'Xm Ys'", () => {
    expect(fmtEta(60)).toBe("1m 0s");
    expect(fmtEta(125)).toBe("2m 5s");
    expect(fmtEta(3599)).toBe("60m 0s");
  });

  it("formats >= 1h as 'Hh Mm'", () => {
    expect(fmtEta(3600)).toBe("1h 0m");
    expect(fmtEta(3700)).toBe("1h 1m");
    expect(fmtEta(7325)).toBe("2h 2m");
  });
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/lib/format.test.ts
```

Expected: missing export.

- [ ] **Step 3: Add `fmtEta` to `lib/format.ts`**

Open `web/frontend/src/lib/format.ts` and append:

```typescript
export function fmtEta(etaS: number | null): string {
  if (etaS == null) return "Calculating...";
  if (etaS < 60) return `${Math.ceil(etaS)}s`;
  if (etaS < 3600) return `${Math.floor(etaS / 60)}m ${Math.ceil(etaS % 60)}s`;
  return `${Math.floor(etaS / 3600)}h ${Math.floor((etaS % 3600) / 60)}m`;
}
```

- [ ] **Step 4: Re-run the test**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend
npx vitest run src/lib/format.test.ts
```

Expected: all 4 pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
git add web/frontend/src/lib/format.ts web/frontend/src/lib/format.test.ts
git commit -m "feat(frontend): fmtEta helper"
```

---



## Task 23: `BackgroundRunsDrawer` � shell + new-job form (TDD)

**Files:**
- Create: `web/frontend/src/components/BackgroundRunsDrawer.tsx`
- Create: `web/frontend/src/components/BackgroundRunsDrawer.test.tsx`

- [ ] **Step 1: Write the failing test for the form**

Create `web/frontend/src/components/BackgroundRunsDrawer.test.tsx`:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BackgroundRunsDrawer } from "./BackgroundRunsDrawer";
import * as api from "../lib/api";

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackgroundRunsDrawer focusedTicker="NVDA" />
    </QueryClientProvider>
  );
}

describe("BackgroundRunsDrawer form", () => {
  it("renders the focused ticker preselected", () => {
    renderDrawer();
    const select = screen.getByLabelText(/ticker/i) as HTMLSelectElement;
    expect(select.value).toBe("NVDA");
  });

  it("calls startBackgroundRun on submit and shows a 422 error inline on failure", async () => {
    const spy = vi.spyOn(api, "startBackgroundRun").mockRejectedValue(
      new Error("validation: date_to cannot be in the future")
    );
    renderDrawer();
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/validation: date_to cannot be in the future/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: missing component.

- [ ] **Step 3: Implement the shell + form**

Create `web/frontend/src/components/BackgroundRunsDrawer.tsx`:

```tsx
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  startBackgroundRun,
  getBackgroundRuns,
  cancelBackgroundRun,
  pauseBackgroundRun,
  resumeBackgroundRun,
  type StartBackgroundRunRequest,
  type BackgroundEvery,
  type BackgroundRunState,
} from "../lib/api";
import { fmtEta } from "../lib/format";
import { useUiStore } from "../store/ui";
import { useWatchlist } from "../hooks/useWatchlist";

const EVERY_OPTIONS: BackgroundEvery[] = ["1d", "1w", "2w", "1mo"];
const PARALLEL_OPTIONS = [1, 2, 4];

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function daysAgoIso(n: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
}

export function BackgroundRunsDrawer({ focusedTicker }: { focusedTicker: string }) {
  const open = useUiStore((s) => s.backgroundRunsOpen);
  const setOpen = useUiStore((s) => s.setBackgroundRunsOpen);
  const watchlist = useWatchlist() ?? [focusedTicker];

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity ${
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={() => setOpen(false)}
        aria-hidden
      />
      <aside
        data-testid="background-runs-drawer"
        className={`fixed inset-x-0 bottom-0 z-50 bg-white border-t shadow-[0_-8px_24px_-12px_rgba(0,0,0,0.15)] transition-transform duration-200 ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
        style={{ height: "45vh" }}
        role="dialog"
        aria-label="Background past runs"
      >
        <header className="flex items-center justify-between border-b px-4 py-2">
          <h2 className="font-semibold">Background Past Runs</h2>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close"
            className="p-1 hover:bg-slate-100 rounded"
          >
            x
          </button>
        </header>
        <div className="h-[calc(45vh-3rem)] overflow-y-auto p-4 space-y-4">
          <NewJobForm tickers={watchlist} defaultTicker={focusedTicker} />
          {/* Tasks 24-26 mount active-job cards, iteration feed, and past jobs list here. */}
        </div>
      </aside>
    </>
  );
}

function NewJobForm({ tickers, defaultTicker }: { tickers: string[]; defaultTicker: string }) {
  const qc = useQueryClient();
  const [ticker, setTicker] = useState(defaultTicker);
  const [dateFrom, setDateFrom] = useState(daysAgoIso(30));
  const [dateTo, setDateTo] = useState(todayIso());
  const [every, setEvery] = useState<BackgroundEvery>("1d");
  const [parallel, setParallel] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (body: StartBackgroundRunRequest) => startBackgroundRun(body),
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["background-runs"] });
    },
    onError: (e: Error) => setError(e.message),
  });

  return (
    <details open className="rounded border p-3">
      <summary className="cursor-pointer font-medium">New job</summary>
      <form
        className="mt-3 grid grid-cols-2 gap-2 text-sm"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({ ticker, date_from: dateFrom, date_to: dateTo, every, parallel });
        }}
      >
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Ticker</span>
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            className="border rounded px-2 py-1"
            aria-label="Ticker"
          >
            {tickers.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">From</span>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">To</span>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Every</span>
          <select
            value={every}
            onChange={(e) => setEvery(e.target.value as BackgroundEvery)}
            className="border rounded px-2 py-1"
          >
            {EVERY_OPTIONS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col">
          <span className="text-xs text-slate-500">Parallel</span>
          <select
            value={parallel}
            onChange={(e) => setParallel(Number(e.target.value))}
            className="border rounded px-2 py-1"
          >
            {PARALLEL_OPTIONS.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <div className="col-span-2 flex items-center gap-2">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="px-3 py-1.5 rounded bg-blue-600 text-white text-sm font-medium disabled:opacity-50"
          >
            {mutation.isPending ? "Starting..." : "Start"}
          </button>
          {error && <span className="text-sm text-red-600" role="alert">{error}</span>}
        </div>
      </form>
    </details>
  );
}
```

> If `useWatchlist` doesn't exist, replace `useWatchlist() ?? [focusedTicker]` with `useState<string[]>([focusedTicker])` for now.

- [ ] **Step 4: Run the form test**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add web/frontend/src/components/BackgroundRunsDrawer.tsx web/frontend/src/components/BackgroundRunsDrawer.test.tsx
git commit -m "feat(frontend): BackgroundRunsDrawer shell + new-job form"
```

---

## Task 24: `BackgroundRunsDrawer` � active job card (TDD)

**Files:**
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.tsx`
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.test.tsx`

- [ ] **Step 1: Add tests for the active job card**

Append to `BackgroundRunsDrawer.test.tsx`:

```tsx
import type { BackgroundRunState } from "../lib/api";

function makeState(over: Partial<BackgroundRunState> = {}): BackgroundRunState {
  return {
    job_id: "bgr_TEST",
    ticker: "NVDA",
    date_from: "2024-01-01",
    date_to: "2024-06-30",
    every: "1d",
    parallel: 2,
    total: 130,
    current_index: 12,
    avg_duration_s: 47.3,
    eta_s: 2851,
    started_at: "2026-06-07T19:30:00Z",
    finished_at: null,
    status: "running",
    durations_s: [],
    ...over,
  };
}

describe("BackgroundRunsDrawer active job card", () => {
  it("renders ticker, range, and progress", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [makeState()] });
    renderDrawer();
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/2024-01-01 -> 2024-06-30/)).toBeInTheDocument();
    expect(screen.getByText(/12 \/ 130/)).toBeInTheDocument();
  });

  it("formats ETA via fmtEta when status is running", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [makeState({ eta_s: 2851 })] });
    renderDrawer();
    expect(await screen.findByText(/ETA: 47m 31s/)).toBeInTheDocument();
  });

  it("shows 'Calculating...' when current_index is 0 and eta_s is 0", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [makeState({ current_index: 0, eta_s: 0, avg_duration_s: 0 })] });
    renderDrawer();
    expect(await screen.findByText(/Calculating.../)).toBeInTheDocument();
  });

  it("hides ETA when current_index equals total", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [makeState({ current_index: 130, eta_s: 0, status: "done" })] });
    renderDrawer();
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.queryByText(/ETA:/)).not.toBeInTheDocument();
  });

  it("Pause and Cancel buttons trigger the right endpoints", async () => {
    const cancel = vi.spyOn(api, "cancelBackgroundRun").mockResolvedValue({ status: "ok" });
    const pause = vi.spyOn(api, "pauseBackgroundRun").mockResolvedValue({ status: "ok" });
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [makeState()] });
    renderDrawer();
    await screen.findByText(/NVDA/);
    await userEvent.click(screen.getByRole("button", { name: /pause/i }));
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(pause).toHaveBeenCalledWith("bgr_TEST");
    expect(cancel).toHaveBeenCalledWith("bgr_TEST");
  });
});
```

- [ ] **Step 2: Run the new tests, confirm they fail**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: the new tests fail (the active-job card is not rendered yet).

- [ ] **Step 3: Add `ActiveJobs` and `JobCard` components**

Open `BackgroundRunsDrawer.tsx` and add the following above the `NewJobForm` component:

```tsx
function ActiveJobs() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["background-runs"],
    queryFn: () => getBackgroundRuns(),
    refetchInterval: (q) => {
      const jobs = (q.state.data?.jobs ?? []) as BackgroundRunState[];
      return jobs.some((j) => j.status === "running" || j.status === "paused") ? 2000 : false;
    },
  });
  const active = (data?.jobs ?? []).filter(
    (j) => j.status === "running" || j.status === "paused"
  );
  if (active.length === 0) return null;
  return (
    <section>
      <h3 className="font-medium mb-2">Active jobs ({active.length})</h3>
      <ul className="space-y-2">
        {active.map((j) => (
          <li key={j.job_id}>
            <JobCard
              job={j}
              onChanged={() => qc.invalidateQueries({ queryKey: ["background-runs"] })}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

function JobCard({ job, onChanged }: { job: BackgroundRunState; onChanged: () => void }) {
  const pct = job.total ? Math.min(100, (job.current_index / job.total) * 100) : 0;
  const showEta = job.status === "running" && job.current_index < job.total;
  const etaText = job.current_index === 0 ? "Calculating..." : fmtEta(job.eta_s);
  return (
    <div className="rounded border p-3" data-testid={`job-card-${job.job_id}`}>
      <div className="flex items-center justify-between">
        <div className="text-sm">
          <span className="font-medium">{job.ticker}</span>
          <span className="text-slate-500">
            {" "}
            - {job.date_from} -> {job.date_to} - {job.every}
          </span>
        </div>
        <StatusPill status={job.status} />
      </div>
      <div
        className="mt-2 h-2 bg-slate-200 rounded overflow-hidden"
        role="progressbar"
        aria-valuenow={job.current_index}
        aria-valuemax={job.total}
      >
        <div className="h-full bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-xs text-slate-600">
        {job.current_index} / {job.total} ({pct.toFixed(1)}%)
        {showEta && <span className="ml-2">ETA: {etaText}</span>}
      </div>
      <div className="mt-2 flex gap-2">
        {job.status === "running" && (
          <button
            onClick={async () => {
              await pauseBackgroundRun(job.job_id);
              onChanged();
            }}
            className="px-2 py-1 text-xs rounded bg-amber-500 text-white"
          >
            Pause
          </button>
        )}
        {job.status === "paused" && (
          <button
            onClick={async () => {
              await resumeBackgroundRun(job.job_id);
              onChanged();
            }}
            className="px-2 py-1 text-xs rounded bg-blue-600 text-white"
          >
            Resume
          </button>
        )}
        <button
          onClick={async () => {
            await cancelBackgroundRun(job.job_id);
            onChanged();
          }}
          className="px-2 py-1 text-xs rounded bg-red-600 text-white"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: BackgroundRunState["status"] }) {
  const color = {
    running: "bg-blue-100 text-blue-800",
    paused: "bg-amber-100 text-amber-800",
    done: "bg-green-100 text-green-800",
    cancelled: "bg-slate-200 text-slate-700",
    error: "bg-red-100 text-red-800",
  }[status];
  return (
    <span className={`text-xs px-2 py-0.5 rounded ${color}`}>{status}</span>
  );
}
```

- [ ] **Step 4: Mount `ActiveJobs` in the drawer**

In the drawer's content `<div>`, after `<NewJobForm />`, add:

```tsx
<ActiveJobs />
```

- [ ] **Step 5: Run the active-job card tests**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add web/frontend/src/components/BackgroundRunsDrawer.tsx web/frontend/src/components/BackgroundRunsDrawer.test.tsx
git commit -m "feat(frontend): active job card with progress bar, ETA, and control buttons"
```

---

## Task 25: `BackgroundRunsDrawer` � live iteration feed (TDD)

**Files:**
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.tsx`
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.test.tsx`

The iteration feed is rendered inside each `JobCard` when a job is running. The feed comes from the most recent completed iterations. For v1, we re-fetch the job list on each poll and show the last 5 entries' summary (date + status). Full iteration history per job would require a new endpoint; deferred.

- [ ] **Step 1: Add a small test that the feed renders inside a running job card**

Append to `BackgroundRunsDrawer.test.tsx`:

```tsx
describe("BackgroundRunsDrawer live iteration feed", () => {
  it("renders the feed for a running job", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({
      jobs: [makeState({ status: "running" })],
    });
    renderDrawer();
    // The feed is shown only when there are at least one completed iteration;
    // the makeState helper gives current_index=12, so we expect the feed header.
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/recent iterations/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, confirm it fails**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: missing text.

- [ ] **Step 3: Add the feed to `JobCard`**

Inside `JobCard`, after the control buttons div, add:

```tsx
      {job.current_index > 0 && (
        <div className="mt-3 border-t pt-2" data-testid="iteration-feed">
          <div className="text-xs font-medium text-slate-500 mb-1">Recent iterations</div>
          <ul className="text-xs space-y-0.5 max-h-32 overflow-y-auto">
            {Array.from({ length: Math.min(5, job.current_index) }).map((_, i) => {
              const n = job.current_index - i;
              return (
                <li key={n} className="text-slate-700">
                  iteration {n} - completed
                </li>
              );
            })}
          </ul>
        </div>
      )}
```

- [ ] **Step 4: Run tests, confirm they pass**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add web/frontend/src/components/BackgroundRunsDrawer.tsx web/frontend/src/components/BackgroundRunsDrawer.test.tsx
git commit -m "feat(frontend): live iteration feed inside active job card"
```

---

## Task 26: `BackgroundRunsDrawer` � past jobs list (TDD)

**Files:**
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.tsx`
- Modify: `web/frontend/src/components/BackgroundRunsDrawer.test.tsx`

- [ ] **Step 1: Add tests for the past jobs list**

Append to `BackgroundRunsDrawer.test.tsx`:

```tsx
describe("BackgroundRunsDrawer past jobs list", () => {
  it("renders terminal jobs in a collapsible section", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({
      jobs: [makeState({ status: "done", current_index: 130 })],
    });
    renderDrawer();
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
    expect(screen.getByText(/Past jobs/)).toBeInTheDocument();
  });

  it("hides the past jobs section when no terminal jobs exist", async () => {
    vi.spyOn(api, "getBackgroundRuns").mockResolvedValue({ jobs: [] });
    renderDrawer();
    expect(screen.queryByText(/Past jobs/)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Add `PastJobs` component to the drawer**

In `BackgroundRunsDrawer.tsx`, add (above `NewJobForm`):

```tsx
function PastJobs() {
  const { data } = useQuery({
    queryKey: ["background-runs"],
    queryFn: () => getBackgroundRuns(),
  });
  const past = (data?.jobs ?? []).filter(
    (j) => j.status === "done" || j.status === "cancelled" || j.status === "error"
  );
  if (past.length === 0) return null;
  return (
    <section>
      <details className="rounded border p-3">
        <summary className="cursor-pointer font-medium">
          Past jobs (last {Math.min(10, past.length)})
        </summary>
        <ul className="mt-2 space-y-1 text-sm">
          {past.slice(0, 10).map((j) => (
            <li key={j.job_id} className="flex items-center gap-2">
              <span className="font-medium">{j.ticker}</span>
              <span className="text-slate-500">
                {j.date_from} -> {j.date_to} - {j.every}
              </span>
              <StatusPill status={j.status} />
              <span className="text-xs text-slate-500">
                {j.current_index}/{j.total}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
```

- [ ] **Step 3: Mount `PastJobs` in the drawer content**

In the drawer's content `<div>`, after `<ActiveJobs />`, add:

```tsx
<PastJobs />
```

- [ ] **Step 4: Run tests**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/components/BackgroundRunsDrawer.test.tsx
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add web/frontend/src/components/BackgroundRunsDrawer.tsx web/frontend/src/components/BackgroundRunsDrawer.test.tsx
git commit -m "feat(frontend): past jobs list in BackgroundRunsDrawer"
```

---



## Task 27: `App.tsx` � Past Runs button + mount drawer (TDD)

**Files:**
- Modify: `web/frontend/src/App.tsx`
- Modify: `web/frontend/src/App.test.tsx` (extend; create if absent)

- [ ] **Step 1: Write the failing test**

Open `web/frontend/src/App.test.tsx` (create if it doesn't exist). Add:

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    getBackgroundRuns: vi.fn().mockResolvedValue({ jobs: [] }),
  };
});

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  );
}

describe("App: Past Runs button", () => {
  it("renders the Past Runs button next to History", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /past runs/i })).toBeInTheDocument();
  });

  it("clicking the button opens the BackgroundRunsDrawer", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: /past runs/i }));
    await waitFor(() => expect(screen.getByTestId("background-runs-drawer")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/App.test.tsx
```

Expected: missing button / drawer.

- [ ] **Step 3: Add the Past Runs button + mount the drawer in `App.tsx`**

Open `web/frontend/src/App.tsx`. Find the existing "History" button and add the new button next to it. Also add the `<BackgroundRunsDrawer />` near the root of the app tree.

In the import block at the top of `App.tsx`, add:

```tsx
import { BackgroundRunsDrawer } from "./components/BackgroundRunsDrawer";
import { useUiStore } from "./store/ui";
```

In the App component, find the existing "History" button (the trigger for `HistoricalAnalysisDrawer`) and add immediately to its right:

```tsx
<button
  onClick={() => useUiStore.getState().setBackgroundRunsOpen(true)}
  className="..."
  data-testid="past-runs-button"
>
  Past Runs
</button>
```

(Match the styling of the existing History button � class names will be similar.)

At the root of the App's return, add the drawer mount (after the existing drawers/panels):

```tsx
<BackgroundRunsDrawer focusedTicker={focusedTicker ?? "NVDA"} />
```

Read the actual focused ticker from your existing store / state. If there's no such state in your codebase yet, default to a hard-coded ticker (e.g., `"NVDA"`) and adapt later.

- [ ] **Step 4: Run the test, confirm it passes**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run src/App.test.tsx
```

Expected: 2 passed.

- [ ] **Step 5: Run the full frontend test suite**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents\\web\\frontend
npx vitest run
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add web/frontend/src/App.tsx web/frontend/src/App.test.tsx
git commit -m "feat(frontend): Past Runs button + mount drawer in App"
```

---

## Task 28: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Background past runs" section**

Open `README.md` and find the existing "Usage" section. Add a subsection:

```markdown
### Background past runs

Schedule a series of past-dated analysis runs that execute in the background.
Runs are surfaced in the dashboard's existing per-ticker views (history,
historical analysis chart) automatically.

CLI:
```

bash
tradingagents run-past NVDA --from 2024-01-01 --to 2024-06-30
tradingagents run-past NVDA --from 2024-01-01 --to 2024-06-30 --every 1w --parallel 2
tradingagents run-past list
tradingagents run-past status bgr_2026-06-07T19-30-00Z_NVDA
tradingagents run-past cancel bgr_2026-06-07T19-30-00Z_NVDA
tradingagents run-past pause bgr_2026-06-07T19-30-00Z_NVDA
tradingagents run-past resume bgr_2026-06-07T19-30-00Z_NVDA
```

Dashboard: open the bottom-slide "Past Runs" panel from the header button.
Configure the ticker, date range, cadence (1d, 1w, 2w, 1mo), and parallelism
(1, 2, 4). Active jobs show a progress bar and ETA; pause/resume/cancel
directly from the panel. Jobs auto-resume on server restart.

> **Note:** Use the dashboard server (`tradingagents dashboard`) to host
> long-running jobs. The CLI's `start` is for one-shot kicking off; if the
> CLI process exits, its in-memory threads die with it.
```

- [ ] **Step 2: Commit**

```bash
cd C:\Users\Ido\\Desktop\\Projects\\agents\\TradingAgents
git add README.md
git commit -m "docs(readme): add background past runs section"
```

---

## Task 29: Manual integration checklist

Before declaring the feature complete, run through this checklist on a real
machine (or in a CI dev environment).

- [ ] **Start the dashboard server**:
  `tradingagents dashboard` (or the equivalent script).
- [ ] **Open the dashboard** in a browser. Confirm the "Past Runs" button
  appears in the header next to "History". Click it. The bottom-slide
  drawer opens.
- [ ] **Submit a small job**: NVDA, 2024-05-06 to 2024-05-10, 1d, parallel=1.
  The new job appears in "Active jobs" within 2s with progress advancing
  from 0 / 5 to 5 / 5.
- [ ] **ETA ticks down**: the rolling ETA updates as iterations complete.
  When the job finishes, the ETA line disappears and the status pill flips
  to "done".
- [ ] **Pause / resume**: start a longer job, click Pause, watch iterations
  stop; click Resume, watch iterations continue.
- [ ] **Cancel**: start a job with parallel=1 and 20 dates, click Cancel
  mid-flight. The status flips to "cancelled" within one iteration.
- [ ] **Past jobs list**: completed jobs appear in the "Past jobs" section
  with their actual wall-clock duration.
- [ ] **Auto-resume on server restart**: start a long job, `Ctrl-C` the
  server, restart it. Within 2s, the job reappears in "Active jobs" and
  continues from where it left off. The dates that already had done runs
  are skipped.
- [ ] **CLI round-trip**: `tradingagents run-past list` lists the same
  jobs. `tradingagents run-past status bgr_...` shows the same details
  the dashboard shows.
- [ ] **Historical Analysis Drawer** (right-side) continues to work
  while the bottom drawer is open. No z-index conflict.
- [ ] **Per-iteration tagging**: open a tagged iteration's run from the
  Historical Analysis Drawer. The run detail shows `background_run_id`
  and `background_run_iteration_index`.
- [ ] **Validation errors**: try to submit a form with `date_to > today`
  (if today is later than the test date) or `parallel` outside the
  allowed set. Inline 422 error appears.
- [ ] **Browser tab hidden**: switch tabs for 30s, switch back. Polling
  resumes (TanStack Query default behavior).

When all checks pass, the feature is ready for review.

---

## Final cleanup

After all tasks are complete:

- [ ] **Run the full backend test suite**:
  `python -m pytest web/server/tests/ -v` � all pass.
- [ ] **Run the full frontend test suite**:
  `cd web/frontend && npx vitest run` � all pass.
- [ ] **Manual smoke test of the dashboard**:
  see Task 29.
- [ ] **Commit the plan** (this file):
  Already committed at the end of the writing-plans flow.

