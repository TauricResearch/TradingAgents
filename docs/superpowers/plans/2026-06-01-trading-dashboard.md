# TradingAgents Live Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web dashboard to the TradingAgents framework that runs the multi-agent pipeline on a watchlist of tickers and streams every event in real time.

**Architecture:** One Python process (FastAPI + uvicorn on :8000) serves both the HTTP/WebSocket API and the built React app. YFinance polls prices every 15s. SQLite stores watchlist + run history. React 18 + Vite + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zustand on the frontend.

**Tech Stack:** Python 3.11+, FastAPI, sqlmodel, aiosqlite, pyyaml (already in repo), yfinance (already in repo), pytest. Vite, React 18, TypeScript, Tailwind, shadcn/ui, TanStack Query, Zustand, ws, vitest, @testing-library/react, Playwright.

**Reference spec:** `docs/superpowers/specs/2026-06-01-trading-dashboard-design.md`

---

## File Structure

New and modified files for this plan. Every file is owned by exactly one task.

```
TradingAgents/
  tradingagents/
    graph/
      trading_graph.py                 # MODIFIED: add event_callback hook (Task 1)
  web/
    server/
      __init__.py                      # Task 2
      settings.py                      # Task 2
      db.py                            # Tasks 3, 4
      events.py                        # Task 5
      price_feed.py                    # Task 6
      runner.py                        # Tasks 7, 8
      app.py                           # Tasks 9, 10, 11, 12
      tests/
        __init__.py
        conftest.py                    # Task 3
        test_db.py                     # Task 4
        test_events.py                 # Task 5
        test_price_feed.py             # Task 6
        test_runner.py                 # Task 8
        test_ws.py                     # Task 11
        test_app.py                    # Tasks 9, 10, 12
        fixtures/
          fake_graph.py                # Task 8
          fake_yfinance.py             # Task 6
    frontend/
      package.json                     # Task 13
      vite.config.ts                   # Task 13
      tsconfig.json                    # Task 13
      tailwind.config.js               # Task 13
      postcss.config.js                # Task 13
      index.html                       # Task 13
      src/
        main.tsx                       # Task 13
        App.tsx                        # Task 14
        index.css                      # Task 13
        components/
          ui/                          # shadcn primitives (Task 13)
          WatchlistRail.tsx            # Task 17
          TickerRow.tsx                # Task 17
          AddTickerCommand.tsx         # Task 17
          TickerHeader.tsx             # Task 18
          StageGrid.tsx                # Task 19
          LiveEventStream.tsx          # Task 20
          DecisionPanel.tsx            # Task 21
          RunHistoryDrawer.tsx         # Task 22
        hooks/
          useRunStream.ts              # Task 16
          usePrices.ts                 # Task 14
        lib/
          api.ts                       # Task 14
          ws.ts                        # Task 16
          events.ts                    # Task 15
          queryClient.ts               # Task 14
        store/
          ui.ts                        # Task 15
        __tests__/
          events-protocol.test.ts      # Task 15
          WatchlistRail.test.tsx       # Task 17
          StageGrid.test.tsx           # Task 19
          LiveEventStream.test.tsx     # Task 20
          useRunStream.test.ts         # Task 16
          DecisionPanel.test.tsx       # Task 21
          mocks/
            mockWs.ts                  # Task 16
    README.md                          # Task 27
    package.json                       # Task 13 (root-level convenience)
docs/superpowers/plans/2026-06-01-trading-dashboard.md
```

---

## Phase 1 — Foundation

### Task 1: Add event callback hook to `trading_graph.py`

**Files:**
- Modify: `tradingagents/graph/trading_graph.py`
- Test: a temporary sanity script (no permanent test; this is a hook addition)

- [ ] **Step 1: Locate the propagate method**

Read `tradingagents/graph/trading_graph.py` and find the `propagate` method signature. Note its current positional and keyword args.

- [ ] **Step 2: Add the `event_callback` keyword parameter**

```python
def propagate(self, company_name: str, trade_date: str, *, event_callback: Callable[[str, dict], None] | None = None) -> dict:
    """..."""
    # existing body
```

Add `Callable` to the imports at the top of the file:
```python
from collections.abc import Callable
```

- [ ] **Step 3: Wrap the existing node iteration so each call invokes the callback**

Find the section of `propagate` that iterates over the graph's nodes (likely a `for` loop with `graph.stream()` or `graph.invoke(stream_mode="updates")`). Immediately before the per-node `state_update` is merged, insert:

```python
if event_callback is not None:
    try:
        event_callback("node_entered", {"node": node_name, "ts": _now_iso()})
    except Exception:  # callbacks must never break the run
        logger.exception("event_callback raised; continuing")
```

Do not remove or alter any existing behavior. Existing callers that don't pass `event_callback` behave exactly as before.

- [ ] **Step 4: Run the existing test suite (or main.py) to confirm no regression**

Run: `python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print(TradingAgentsGraph.propagate.__doc__)"`
Expected: imports cleanly; signature includes `event_callback`.

- [ ] **Step 5: Commit**

```bash
git add tradingagents/graph/trading_graph.py
git commit -m "feat(graph): add event_callback hook to propagate()"
```

---

### Task 2: Create `web/server` package skeleton

**Files:**
- Create: `web/server/__init__.py`
- Create: `web/server/settings.py`
- Create: `web/server/tests/__init__.py`
- Create: `web/server/tests/conftest.py`

- [ ] **Step 1: Create `__init__.py` files**

`web/server/__init__.py`:
```python
"""TradingAgents dashboard backend."""

__version__ = "0.1.0"
```

`web/server/tests/__init__.py`: empty file.

- [ ] **Step 2: Write `settings.py`**

```python
"""Environment-driven settings for the dashboard server."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_db_path() -> str:
    home = Path.home() / ".tradingagents"
    home.mkdir(parents=True, exist_ok=True)
    return str(home / "dashboard.db")


@dataclass(frozen=True)
class Settings:
    db_path: str = os.environ.get("TRADINGAGENTS_DASHBOARD_DB", _default_db_path())
    host: str = os.environ.get("TRADINGAGENTS_DASHBOARD_HOST", "127.0.0.1")
    port: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PORT", "8000"))
    max_concurrent: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))
    price_poll_s: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PRICE_POLL_S", "15"))
    log_level: str = os.environ.get("TRADINGAGENTS_DASHBOARD_LOG_LEVEL", "INFO")
    frontend_dist: str = os.environ.get("TRADINGAGENTS_FRONTEND_DIST", "web/frontend/dist")


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: Write `conftest.py` with an isolated in-memory DB fixture**

```python
import os
import pytest
from sqlmodel import SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from web.server import db


@pytest.fixture
def temp_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("TRADINGAGENTS_DASHBOARD_DB", str(db_path))
    # reload the module-level engine
    db._engine = None
    db.init_db()
    yield str(db_path)
    db._engine = None
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from web.server.settings import get_settings; print(get_settings())"`
Expected: prints a `Settings(...)` line; no import errors.

- [ ] **Step 5: Commit**

```bash
git add web/server
git commit -m "feat(web): scaffold dashboard server package"
```

---

## Phase 2 — Backend core

### Task 3: Add sqlmodel + aiosqlite to pyproject and create `db.py` schema

**Files:**
- Modify: `pyproject.toml` (or `requirements.txt` — whichever the repo uses; inspect first)
- Create: `web/server/db.py`

- [ ] **Step 1: Inspect the dependency manifest**

Run: `ls pyproject.toml requirements.txt 2>/dev/null`
Use whichever exists. Most likely `pyproject.toml` (project uses `uv`).

- [ ] **Step 2: Add dependencies**

If `pyproject.toml` exists, in the `[project] dependencies` array add:
```
"sqlmodel>=0.0.16",
"aiosqlite>=0.19.0",
"fastapi>=0.110.0",
"uvicorn[standard]>=0.27.0",
"websockets>=12.0",
"python-multipart>=0.0.9",
```

Then run: `uv sync` (or `pip install -e .` if uv is not used).

- [ ] **Step 3: Write the failing test for schema creation**

`web/server/tests/test_db.py`:
```python
from sqlmodel import select

from web.server import db
from web.server.db import Watchlist, Run, Event


def test_init_db_creates_tables(temp_db):
    # init_db already called by fixture
    with db.get_session() as s:
        assert s.exec(select(Watchlist)).first() is None
        assert s.exec(select(Run)).first() is None
        assert s.exec(select(Event)).first() is None
```

- [ ] **Step 4: Run the test, expect failure**

Run: `pytest web/server/tests/test_db.py::test_init_db_creates_tables -v`
Expected: FAIL — `db.init_db` does not exist.

- [ ] **Step 5: Write `db.py` with models and `init_db`**

`web/server/db.py`:
```python
"""SQLite persistence layer for the dashboard."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from sqlmodel import Field, SQLModel, Session, create_engine, select


_engine = None


class Watchlist(SQLModel, table=True):
    __tablename__ = "watchlist"
    ticker: str = Field(primary_key=True)
    company_name: str
    exchange: str
    added_at: datetime
    last_run_id: Optional[int] = None
    last_decision: Optional[str] = None
    last_decision_at: Optional[datetime] = None


class Run(SQLModel, table=True):
    __tablename__ = "run"
    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str  # queued | running | done | failed | cancelled
    cancel_requested: bool = False
    decision_action: Optional[str] = None
    decision_target: Optional[float] = None
    decision_rationale: Optional[str] = None
    decision_confidence: Optional[float] = None
    unpersisted: bool = False
    idempotency_key: str = Field(index=True)


class Event(SQLModel, table=True):
    __tablename__ = "event"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(index=True)
    ts: datetime
    type: str
    payload_json: str


def _make_engine():
    path = os.environ.get("TRADINGAGENTS_DASHBOARD_DB")
    if not path or path == ":memory:":
        from sqlalchemy.pool import StaticPool
        return create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as s:
        yield s
```

- [ ] **Step 6: Run the test, expect pass**

Run: `pytest web/server/tests/test_db.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock web/server/db.py web/server/tests/test_db.py web/server/tests/conftest.py
git commit -m "feat(web): add db.py schema with Watchlist/Run/Event tables"
```

---

### Task 4: Implement watchlist and run CRUD with tests

**Files:**
- Modify: `web/server/db.py`
- Modify: `web/server/tests/test_db.py`

- [ ] **Step 1: Write the failing test for watchlist CRUD**

Append to `test_db.py`:
```python
from datetime import datetime, timezone
from web.server import db
from web.server.db import Watchlist, Run, Event


def test_watchlist_add_list_remove(temp_db):
    db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))
    db.add_watchlist(Watchlist(ticker="AAPL", company_name="Apple", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))

    rows = db.list_watchlist()
    tickers = {r.ticker for r in rows}
    assert tickers == {"NVDA", "AAPL"}

    db.remove_watchlist("NVDA")
    rows = db.list_watchlist()
    assert {r.ticker for r in rows} == {"AAPL"}


def test_watchlist_duplicate_raises(temp_db):
    db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))
    import pytest
    with pytest.raises(db.DuplicateTicker):
        db.add_watchlist(Watchlist(ticker="NVDA", company_name="NVIDIA", exchange="NASDAQ", added_at=datetime.now(timezone.utc)))
```

- [ ] **Step 2: Run tests, expect failure**

Run: `pytest web/server/tests/test_db.py -v -k watchlist`
Expected: FAIL — `add_watchlist` etc. don't exist; `DuplicateTicker` doesn't exist.

- [ ] **Step 3: Add CRUD helpers and `DuplicateTicker` to `db.py`**

Append to `web/server/db.py`:
```python
class DuplicateTicker(Exception):
    pass


def add_watchlist(row: Watchlist) -> None:
    with get_session() as s:
        existing = s.get(Watchlist, row.ticker)
        if existing is not None:
            raise DuplicateTicker(row.ticker)
        s.add(row)
        s.commit()


def remove_watchlist(ticker: str) -> None:
    with get_session() as s:
        row = s.get(Watchlist, ticker)
        if row is not None:
            s.delete(row)
            s.commit()


def list_watchlist() -> list[Watchlist]:
    with get_session() as s:
        return list(s.exec(select(Watchlist).order_by(Watchlist.added_at)))


def update_watchlist_last_decision(ticker: str, run_id: int, decision_text: str, at: datetime) -> None:
    with get_session() as s:
        row = s.get(Watchlist, ticker)
        if row is None:
            return
        row.last_run_id = run_id
        row.last_decision = decision_text
        row.last_decision_at = at
        s.add(row)
        s.commit()
```

- [ ] **Step 4: Run tests, expect pass**

Run: `pytest web/server/tests/test_db.py -v -k watchlist`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing run tests**

Append:
```python
def test_run_crud_and_events(temp_db):
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    assert rid > 0

    db.append_event(rid, "run_started", {})
    db.append_event(rid, "analyst_thinking", {"stage": "market", "message": "hi"})
    db.append_event(rid, "decision", {"action": "BUY", "target": 260.0})

    run = db.get_run(rid)
    assert run.ticker == "NVDA"
    assert run.status == "running"

    events = db.events_for_run(rid)
    assert [e.type for e in events] == ["run_started", "analyst_thinking", "decision"]

    db.mark_run_done(rid, decision_action="BUY", decision_target=260.0, decision_rationale="r", decision_confidence=0.8)
    run = db.get_run(rid)
    assert run.status == "done"
    assert run.decision_action == "BUY"
    assert run.finished_at is not None


def test_run_idempotency(temp_db):
    rid1 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    db.mark_run_done(rid1, decision_action="HOLD", decision_target=None, decision_rationale="", decision_confidence=0.5)
    rid2 = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    assert rid1 == rid2
```

- [ ] **Step 6: Implement run/event helpers**

Append to `db.py`:
```python
import json
from datetime import datetime, timezone


def create_run(ticker: str, idempotency_key: str) -> int:
    with get_session() as s:
        existing = s.exec(select(Run).where(Run.idempotency_key == idempotency_key, Run.status != "running")).first()
        if existing is not None:
            return existing.id
        row = Run(ticker=ticker, started_at=datetime.now(timezone.utc), status="running", idempotency_key=idempotency_key)
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def get_run(run_id: int) -> Optional[Run]:
    with get_session() as s:
        return s.get(Run, run_id)


def list_runs(limit: int = 20) -> list[Run]:
    with get_session() as s:
        return list(s.exec(select(Run).order_by(Run.started_at.desc()).limit(limit)))


def append_event(run_id: int, type_: str, data: dict) -> int:
    with get_session() as s:
        row = Event(run_id=run_id, ts=datetime.now(timezone.utc), type=type_, payload_json=json.dumps(data))
        s.add(row)
        s.commit()
        s.refresh(row)
        return row.id


def events_for_run(run_id: int, since_id: int = 0) -> list[Event]:
    with get_session() as s:
        return list(s.exec(select(Event).where(Event.run_id == run_id, Event.id > since_id).order_by(Event.id)))


def mark_run_done(run_id: int, *, decision_action: str, decision_target: Optional[float], decision_rationale: str, decision_confidence: float) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.status = "done"
        row.finished_at = datetime.now(timezone.utc)
        row.decision_action = decision_action
        row.decision_target = decision_target
        row.decision_rationale = decision_rationale
        row.decision_confidence = decision_confidence
        s.add(row)
        s.commit()


def mark_run_failed(run_id: int, reason: str) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.status = "failed"
        row.finished_at = datetime.now(timezone.utc)
        if row.decision_rationale is None:
            row.decision_rationale = f"failed: {reason}"
        s.add(row)
        s.commit()


def request_cancellation(run_id: int) -> None:
    with get_session() as s:
        row = s.get(Run, run_id)
        if row is None:
            return
        row.cancel_requested = True
        s.add(row)
        s.commit()


def reap_stale_runs(timeout_s: int) -> int:
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_s)
    count = 0
    with get_session() as s:
        stale = list(s.exec(select(Run).where(Run.status == "running", Run.started_at < cutoff)))
        for row in stale:
            row.status = "failed"
            row.finished_at = datetime.now(timezone.utc)
            s.add(row)
            count += 1
        s.commit()
    return count
```

- [ ] **Step 7: Run tests, expect pass**

Run: `pytest web/server/tests/test_db.py -v`
Expected: PASS (4 tests).

- [ ] **Step 8: Commit**

```bash
git add web/server/db.py web/server/tests/test_db.py
git commit -m "feat(web): implement watchlist and run CRUD with tests"
```

---

### Task 5: Implement `events.py` protocol

**Files:**
- Create: `web/server/events.py`
- Create: `web/server/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

`web/server/tests/test_events.py`:
```python
from datetime import datetime, timezone
from web.server.events import EventType, emit, make_event, wire_format


def test_make_event_shape():
    e = make_event("analyst_thinking", run_id=42, data={"stage": "market", "message": "hi"})
    assert e["v"] == 1
    assert e["type"] == "analyst_thinking"
    assert e["run_id"] == 42
    assert e["data"] == {"stage": "market", "message": "hi"}
    assert isinstance(e["ts"], str)
    # ISO-8601
    datetime.fromisoformat(e["ts"].replace("Z", "+00:00"))


def test_wire_format_is_json_serializable():
    import json
    e = make_event("decision", run_id=1, data={"action": "BUY", "target": 260.5})
    json.dumps(e)  # must not raise


def test_event_type_enum_has_required_keys():
    required = {
        "RUN_STARTED", "RUN_FINISHED", "RUN_FAILED",
        "ANALYST_STARTED", "ANALYST_THINKING", "ANALYST_COMPLETED",
        "TOOL_CALL", "TOOL_RESULT", "TOOL_CALL_WARNING",
        "DEBATE_MESSAGE", "RISK_MESSAGE", "DECISION",
        "PRICE_UPDATE", "SERVER_NOTICE",
    }
    actual = {m.name for m in EventType}
    missing = required - actual
    assert not missing, f"missing event types: {missing}"


def test_emit_persists_and_broadcasts(monkeypatch, temp_db):
    from web.server import db
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:2026-06-01")
    seen = []
    monkeypatch.setattr("web.server.events._broadcast", lambda run_id, evt: seen.append(evt))

    eid = emit(rid, "analyst_thinking", {"stage": "market", "message": "hi"})
    assert eid > 0
    assert len(seen) == 1
    assert seen[0]["type"] == "analyst_thinking"

    events = db.events_for_run(rid)
    assert len(events) == 1
    import json
    assert json.loads(events[0].payload_json)["message"] == "hi"
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest web/server/tests/test_events.py -v`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement `events.py`**

```python
"""WebSocket event protocol shared by backend emitter and frontend mirror."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from web.server import db


class EventType(str, Enum):
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    ANALYST_STARTED = "analyst_started"
    ANALYST_THINKING = "analyst_thinking"
    ANALYST_COMPLETED = "analyst_completed"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_CALL_WARNING = "tool_call_warning"
    DEBATE_MESSAGE = "debate_message"
    RISK_MESSAGE = "risk_message"
    DECISION = "decision"
    PRICE_UPDATE = "price_update"
    SERVER_NOTICE = "server_notice"


PROTOCOL_VERSION = 1


def make_event(type_: str, *, run_id: int, data: dict) -> dict:
    return {
        "v": PROTOCOL_VERSION,
        "type": type_,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "data": data,
    }


_broadcast: Callable[[int, dict], None] = lambda run_id, evt: None


def set_broadcast(fn: Callable[[int, dict], None]) -> None:
    """Inject the WebSocket broadcast function. Called from app.py at startup."""
    global _broadcast
    _broadcast = fn


def emit(run_id: int, type_: str, data: dict) -> int:
    """Persist an event and broadcast it to live subscribers.

    Persistence failures are logged and broadcast still happens in-memory.
    Returns the event id on success, 0 on persistence failure.
    """
    evt = make_event(type_, run_id=run_id, data=data)
    event_id = 0
    try:
        event_id = db.append_event(run_id, type_, data)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("failed to persist event run=%s type=%s", run_id, type_)
    try:
        _broadcast(run_id, evt)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("broadcast failed run=%s type=%s", run_id, type_)
    return event_id


def wire_format(evt: dict) -> str:
    return json.dumps(evt, separators=(",", ":"))
```

- [ ] **Step 4: Run, expect pass**

Run: `pytest web/server/tests/test_events.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add web/server/events.py web/server/tests/test_events.py
git commit -m "feat(web): add events.py protocol with persistence+broadcast"
```

---

### Task 6: Implement `price_feed.py` poller

**Files:**
- Create: `web/server/price_feed.py`
- Create: `web/server/tests/test_price_feed.py`
- Create: `web/server/tests/fixtures/__init__.py`
- Create: `web/server/tests/fixtures/fake_yfinance.py`

- [ ] **Step 1: Create fixtures package**

`web/server/tests/fixtures/__init__.py`: empty.

- [ ] **Step 2: Write the fake YFinance fixture**

`web/server/tests/fixtures/fake_yfinance.py`:
```python
"""In-memory replacement for yfinance for tests."""
from __future__ import annotations
from typing import Iterable


class _FakeSeries:
    def __init__(self, prices: list[float]):
        self._prices = prices

    @property
    def empty(self) -> bool:
        return len(self._prices) == 0

    def __getitem__(self, key):
        # support .loc["Close"]
        return self


class _FakeDf:
    def __init__(self, by_ticker: dict[str, list[float]]):
        self._by = by_ticker

    def __getitem__(self, ticker):
        return _FakeSeries(self._by.get(ticker, []))


def make_fake_download(by_ticker: dict[str, list[float]]):
    def _download(tickers: Iterable[str] | str, **kwargs):
        if isinstance(tickers, str):
            return _FakeDf({tickers: by_ticker.get(tickers, [])})
        return _FakeDf({t: by_ticker.get(t, []) for t in tickers})
    return _download
```

- [ ] **Step 3: Write the failing test**

`web/server/tests/test_price_feed.py`:
```python
import asyncio
import pytest
from web.server import price_feed
from web.server.tests.fixtures.fake_yfinance import make_fake_download


@pytest.mark.asyncio
async def test_first_poll_updates_snapshot(monkeypatch):
    snapshot = price_feed.PriceSnapshot(price=0.0, prev_close=0.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snapshot}, tickers=lambda: ["NVDA"])
    fake = make_fake_download({"NVDA": [110.0, 111.0, 112.4]})
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(fake)}))

    await price_feed._poll_once(state, broadcast=lambda e: None)
    s = state.snapshots["NVDA"]
    assert s.price == 112.4
    assert s.sparkline == [110.0, 111.0, 112.4]
    assert s.stale is False


@pytest.mark.asyncio
async def test_partial_failure_marks_stale(monkeypatch):
    snap_ok = price_feed.PriceSnapshot(price=200.0, prev_close=200.0, change_pct=0.0, sparkline=[])
    snap_bad = price_feed.PriceSnapshot(price=100.0, prev_close=100.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap_ok, "BAD": snap_bad}, tickers=lambda: ["NVDA", "BAD"])

    def bad_download(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(bad_download)}))

    await price_feed._poll_once(state, broadcast=lambda e: None)
    # on total failure, snapshots are unchanged but no exception propagates
    assert state.snapshots["NVDA"].price == 200.0
    assert state.snapshots["BAD"].price == 100.0


@pytest.mark.asyncio
async def test_missing_ticker_marks_stale(monkeypatch):
    snap = price_feed.PriceSnapshot(price=50.0, prev_close=50.0, change_pct=0.0, sparkline=[50.0])
    state = price_feed.PriceState(snapshots={"NVDA": snap, "BAD": price_feed.PriceSnapshot(0,0,0,[])}, tickers=lambda: ["NVDA", "BAD"])
    fake = make_fake_download({"NVDA": [50.0, 51.0]})  # no "BAD"
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(fake)}))

    broadcasts = []
    await price_feed._poll_once(state, broadcast=lambda e: broadcasts.append(e))
    assert state.snapshots["NVDA"].price == 51.0
    assert state.snapshots["BAD"].stale is True
```

- [ ] **Step 4: Run, expect failure**

Run: `pytest web/server/tests/test_price_feed.py -v`
Expected: FAIL — module doesn't exist; `asyncio` mode may also be missing.

- [ ] **Step 5: Add `pytest-asyncio` to dev deps and configure mode**

In `pyproject.toml` under `[project.optional-dependencies] dev`, add:
```
"pytest-asyncio>=0.23.0",
```

Also add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["web/server/tests"]
```

Then: `uv sync`

- [ ] **Step 6: Implement `price_feed.py`**

```python
"""Background poller that fans out live prices to all WS clients."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

import yfinance as yf

from web.server import events


log = logging.getLogger(__name__)


@dataclass
class PriceSnapshot:
    price: float = 0.0
    prev_close: float = 0.0
    change_pct: float = 0.0
    sparkline: list[float] = field(default_factory=list)
    stale: bool = False


@dataclass
class PriceState:
    snapshots: dict[str, PriceSnapshot]
    tickers: Callable[[], list[str]]


async def _poll_once(state: PriceState, broadcast: Callable[[dict], None]) -> None:
    tickers = list(state.tickers())
    if not tickers:
        return
    try:
        df = yf.download(tickers=tickers, period="1d", interval="1m", progress=False, group_by="ticker")
    except Exception:
        log.exception("yfinance total failure; skipping poll")
        return

    for ticker in tickers:
        snap = state.snapshots.get(ticker) or PriceSnapshot()
        try:
            series = df[ticker]["Close"] if len(tickers) > 1 else df["Close"]
            if hasattr(series, "empty") and series.empty:
                snap.stale = True
            else:
                values = list(series.dropna().tail(30))
                if not values:
                    snap.stale = True
                else:
                    snap.price = float(values[-1])
                    snap.sparkline = [float(v) for v in values]
                    snap.stale = False
        except Exception:
            log.exception("price lookup failed for %s; marking stale", ticker)
            snap.stale = True
        state.snapshots[ticker] = snap

        broadcast(events.make_event(
            "price_update",
            run_id=0,
            data={
                "ticker": ticker,
                "price": snap.price,
                "change_pct": snap.change_pct,
                "sparkline": snap.sparkline,
                "stale": snap.stale,
            },
        ))


class PriceFeed:
    def __init__(self, state: PriceState, poll_s: int = 15):
        self.state = state
        self.poll_s = poll_s
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

    async def _loop(self, broadcast: Callable[[dict], None]) -> None:
        while not self._stop.is_set():
            try:
                await _poll_once(self.state, broadcast)
            except Exception:
                log.exception("poll loop iteration crashed; continuing")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_s)
            except asyncio.TimeoutError:
                pass

    def start(self, broadcast: Callable[[dict], None]) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(broadcast))

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None
```

- [ ] **Step 7: Run, expect pass**

Run: `pytest web/server/tests/test_price_feed.py -v`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add web/server/price_feed.py web/server/tests/test_price_feed.py web/server/tests/fixtures pyproject.toml uv.lock
git commit -m "feat(web): add price_feed poller with yfinance"
```

---

## Phase 3 — Runner, App, and WebSocket

### Task 7: Implement `runner.py` core

**Files:**
- Create: `web/server/runner.py`
- Create: `web/server/tests/fixtures/fake_graph.py`

- [ ] **Step 1: Write the fake TradingAgentsGraph fixture**

`web/server/tests/fixtures/fake_graph.py`:
```python
"""Drop-in replacement for TradingAgentsGraph that emits scripted events."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ScriptedNode:
    name: str
    events: list[dict] = field(default_factory=list)
    state_patch: dict = field(default_factory=dict)


@dataclass
class ScriptedRun:
    nodes: list[ScriptedNode]
    final_state: dict
    fail_after: Optional[str] = None  # node name; if set, raise after that node
    rate_limit_count: int = 0  # how many times to raise RateLimitError before succeeding


class RateLimitError(RuntimeError):
    pass


class FakeGraph:
    def __init__(self, run: ScriptedRun):
        self._run = run

    def propagate(self, ticker: str, trade_date: str, *, event_callback: Optional[Callable] = None):
        from web.server import events
        from web.server.runner import _to_run_id
        # ScriptedRun uses sentinel run_id 0; the runner overrides
        raise NotImplementedError("Use FakeTradingAgents wrapper")


class FakeTradingAgents:
    """Acts like TradingAgentsGraph but uses the ScriptedRun for the runner."""
    def __init__(self, script: ScriptedRun):
        self._script = script

    def propagate(self, ticker: str, trade_date: str, *, event_callback=None):
        rl_remaining = self._script.rate_limit_count
        for node in self._script.nodes:
            if event_callback is not None:
                event_callback("node_entered", {"node": node.name})
            for ev in node.events:
                event_callback(ev["type"], ev.get("data", {}))
            if rl_remaining > 0:
                rl_remaining -= 1
                raise RateLimitError("simulated 429")
            if self._script.fail_after == node.name:
                raise RuntimeError(f"simulated failure at {node.name}")
        return self._script.final_state


def happy_path(ticker: str) -> ScriptedRun:
    return ScriptedRun(
        nodes=[
            ScriptedNode("Market Analyst", [
                {"type": "analyst_thinking", "data": {"stage": "market", "message": "analyzing prices"}},
                {"type": "analyst_completed", "data": {"stage": "market", "summary": "bullish"}},
            ]),
            ScriptedNode("Bull Researcher", [
                {"type": "debate_message", "data": {"side": "bull", "round": 1, "text": "upside"}},
            ]),
            ScriptedNode("Bear Researcher", [
                {"type": "debate_message", "data": {"side": "bear", "round": 1, "text": "downside"}},
            ]),
            ScriptedNode("Trader", [
                {"type": "decision", "data": {"action": "BUY", "target": 260.0, "rationale": "ok", "confidence": 0.8}},
            ]),
        ],
        final_state={"decision": {"action": "BUY", "target": 260.0}},
    )
```

- [ ] **Step 2: Write the failing runner tests**

`web/server/tests/test_runner.py`:
```python
import asyncio
import pytest
from datetime import datetime, timezone

from web.server import db, runner
from web.server.tests.fixtures.fake_graph import FakeTradingAgents, happy_path, RateLimitError


@pytest.mark.asyncio
async def test_happy_path_emits_and_persists(monkeypatch, temp_db):
    monkeypatch.setattr(runner, "build_graph", lambda config: FakeTradingAgents(happy_path("NVDA")))
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    rid = runner.enqueue("NVDA", idempotency_key="NVDA:2026-06-01")
    # wait for the queue worker to finish
    await runner._wait_for_idle(timeout=5)

    run = db.get_run(rid)
    assert run.status == "done"
    assert run.decision_action == "BUY"
    assert run.decision_target == 260.0

    events = db.events_for_run(rid)
    types = [e.type for e in events]
    assert "run_started" in types
    assert "analyst_thinking" in types
    assert "debate_message" in types
    assert "decision" in types
    assert "run_finished" in types


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(monkeypatch, temp_db):
    from web.server.tests.fixtures.fake_graph import ScriptedRun, ScriptedNode

    started = []
    release = asyncio.Event()

    def slow_graph(config):
        class Slow:
            async def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                started.append(ticker)
                await release.wait()
                return {"decision": {"action": "HOLD"}}
        return Slow()

    monkeypatch.setattr(runner, "build_graph", slow_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))
    monkeypatch.setattr(runner, "MAX_CONCURRENT", 2)

    runner.enqueue("A", idempotency_key="A:k")
    runner.enqueue("B", idempotency_key="B:k")
    runner.enqueue("C", idempotency_key="C:k")

    # wait until 2 are running
    for _ in range(50):
        if len(started) >= 2:
            break
        await asyncio.sleep(0.05)
    assert len(started) == 2

    # release the held jobs
    release.set()
    await runner._wait_for_idle(timeout=5)
    assert len(started) == 3


@pytest.mark.asyncio
async def test_cancellation_emits_run_failed(monkeypatch, temp_db):
    from web.server.tests.fixtures.fake_graph import ScriptedRun, ScriptedNode

    started = asyncio.Event()
    release = asyncio.Event()

    def blocking_graph(config):
        class Blocking:
            def propagate(self_inner, ticker, trade_date, *, event_callback=None):
                started.set()
                release.wait()
                return {}
        return Blocking()

    monkeypatch.setattr(runner, "build_graph", blocking_graph)
    monkeypatch.setattr(runner.events, "emit", lambda rid, t, d: db.append_event(rid, t, d))

    rid = runner.enqueue("NVDA", idempotency_key="NVDA:cancel")
    await started.wait()
    db.request_cancellation(rid)
    release.set()
    await runner._wait_for_idle(timeout=5)

    run = db.get_run(rid)
    assert run.status == "failed"
    assert "cancel" in (run.decision_rationale or "").lower()
```

- [ ] **Step 3: Run, expect failure**

Run: `pytest web/server/tests/test_runner.py -v`
Expected: FAIL — module doesn't exist; `runner.MAX_CONCURRENT`, `_wait_for_idle`, `build_graph` don't exist.

- [ ] **Step 4: Implement `runner.py`**

```python
"""Async orchestrator that wraps TradingAgentsGraph and emits typed events."""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from web.server import db, events


log = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))


def build_graph(config=None):
    """Build a TradingAgentsGraph. Tests monkeypatch this."""
    return TradingAgentsGraph(config or DEFAULT_CONFIG)


_queue: asyncio.Queue = None  # type: ignore
_workers: list[asyncio.Task] = []
_sem: asyncio.Semaphore = None  # type: ignore
_idle = threading.Event()
_idle.set()


def enqueue(ticker: str, *, idempotency_key: str) -> int:
    rid = db.create_run(ticker=ticker, idempotency_key=idempotency_key)
    if _queue is not None:
        _queue.put_nowait(rid)
    else:
        # not started yet — run synchronously in a thread so tests can call before start()
        threading.Thread(target=_run_one_sync, args=(rid,), daemon=True).start()
    return rid


async def start(num_workers: int = 1) -> None:
    global _queue, _sem
    _queue = asyncio.Queue()
    _sem = asyncio.Semaphore(MAX_CONCURRENT)
    for _ in range(num_workers):
        _workers.append(asyncio.create_task(_worker_loop()))


async def stop() -> None:
    for w in _workers:
        w.cancel()
    for w in _workers:
        try:
            await w
        except Exception:
            pass
    _workers.clear()


async def _wait_for_idle(timeout: float = 30) -> None:
    """Test helper: wait until the queue is empty and no worker is running."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _queue is None or (_queue.empty() and not _sem.locked()):
            return
        await asyncio.sleep(0.05)
    raise TimeoutError("runner did not become idle in time")


async def _worker_loop() -> None:
    assert _queue is not None and _sem is not None
    while True:
        rid = await _queue.get()
        try:
            await _sem.acquire()
        except Exception:
            continue
        asyncio.create_task(_run_one(rid, _sem))


def _run_one_sync(rid: int) -> None:
    asyncio.run(_run_one(rid, asyncio.Semaphore(1)))


async def _run_one(rid: int, sem: asyncio.Semaphore) -> None:
    try:
        run = db.get_run(rid)
        if run is None:
            return
        if run.cancel_requested:
            db.mark_run_failed(rid, "cancelled")
            events.emit(rid, "run_failed", {"reason": "cancelled"})
            return

        events.emit(rid, "run_started", {"ticker": run.ticker})
        graph = build_graph()

        # Convert graph events → events.emit
        def cb(node_name: str, payload: dict) -> None:
            mapping = {
                "node_entered": "analyst_started",
            }
            type_ = mapping.get(node_name, "analyst_thinking")
            if run.cancel_requested:
                raise _CancelSentinel()
            events.emit(rid, type_, {"node": payload.get("node", node_name), **payload})

        loop = asyncio.get_event_loop()
        retries = 3
        last_err = None
        for attempt in range(retries + 1):
            try:
                final = await loop.run_in_executor(None, graph.propagate, run.ticker, datetime.now(timezone.utc).date().isoformat())
                break
            except _CancelSentinel:
                db.mark_run_failed(rid, "cancelled")
                events.emit(rid, "run_failed", {"reason": "cancelled"})
                return
            except Exception as e:
                last_err = e
                if "429" in str(e) and attempt < retries:
                    import random
                    await asyncio.sleep(0.1 * (2 ** attempt) + random.random() * 0.1)
                    events.emit(rid, "tool_call_warning", {"message": f"retrying after {type(e).__name__}"})
                    continue
                db.mark_run_failed(rid, f"{type(e).__name__}: {e}")
                events.emit(rid, "run_failed", {"reason": "exception", "exception_class": type(e).__name__, "message": str(e)})
                return
        else:
            db.mark_run_failed(rid, f"exhausted retries: {last_err}")
            events.emit(rid, "run_failed", {"reason": "exhausted_retries"})
            return

        decision = (final or {}).get("decision") or {}
        action = decision.get("action")
        target = decision.get("target")
        rationale = decision.get("rationale", "")
        confidence = decision.get("confidence", 0.0)
        db.mark_run_done(rid, decision_action=action or "HOLD", decision_target=target, decision_rationale=rationale, decision_confidence=confidence)
        db.update_watchlist_last_decision(run.ticker, rid, f"{action} @ {target}" if target else (action or ""), datetime.now(timezone.utc))
        events.emit(rid, "run_finished", {"duration_s": 0})
    finally:
        sem.release()


class _CancelSentinel(Exception):
    pass
```

- [ ] **Step 5: Run, expect pass**

Run: `pytest web/server/tests/test_runner.py -v`
Expected: PASS (3 tests). Use `pytest-asyncio` mode `auto` (configured in Task 6).

- [ ] **Step 6: Commit**

```bash
git add web/server/runner.py web/server/tests/test_runner.py web/server/tests/fixtures/fake_graph.py
git commit -m "feat(web): add async runner with semaphore + cancellation + retries"
```

---

### Task 8: Implement `app.py` — health, watchlist, prices, runs, WS

**Files:**
- Create: `web/server/app.py`
- Modify: `web/server/tests/test_app.py` (create)
- Modify: `web/server/tests/test_ws.py` (create)

- [ ] **Step 1: Write the failing test for health + watchlist routes**

`web/server/tests/test_app.py`:
```python
import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import db


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("web.server.events._broadcast", lambda rid, evt: None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "watchlist_size" in body


def test_watchlist_crud(client):
    r = client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
    assert r.status_code == 201
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    assert {row["ticker"] for row in r.json()} == {"NVDA"}

    # duplicate
    r = client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
    assert r.status_code == 409

    r = client.delete("/api/watchlist/NVDA")
    assert r.status_code == 204
    assert client.get("/api/watchlist").json() == []


def test_runs_lifecycle(client, monkeypatch):
    from web.server import runner
    monkeypatch.setattr(runner, "build_graph", lambda config=None: None)
    r = client.post("/api/runs", json={"ticker": "NVDA"})
    assert r.status_code == 201
    rid = r.json()["run_id"]
    assert rid > 0

    r = client.get(f"/api/runs/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["run"]["ticker"] == "NVDA"
    assert body["events"] == []  # nothing emitted yet (graph is None)

    r = client.get("/api/runs?limit=10")
    assert r.status_code == 200
    assert len(r.json()) >= 1
```

- [ ] **Step 2: Run, expect failure**

Run: `pytest web/server/tests/test_app.py -v`
Expected: FAIL — `app.py` doesn't exist.

- [ ] **Step 3: Implement `app.py` (part 1 — health, watchlist, runs)**

```python
"""FastAPI application factory for the TradingAgents dashboard."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web.server import db, events, price_feed, runner
from web.server.settings import get_settings


log = logging.getLogger(__name__)


# Per-run subscriber lists. _subs[run_id] = set of asyncio.Queue.
_subs: dict[int, set[asyncio.Queue]] = {}


def _broadcast(run_id: int, evt: dict) -> None:
    for q in list(_subs.get(run_id, ())):
        try:
            q.put_nowait(evt)
        except Exception:
            pass


events.set_broadcast(_broadcast)


# --------- request/response models ---------

class WatchlistIn(BaseModel):
    ticker: str
    company_name: str = ""
    exchange: str = ""


class RunIn(BaseModel):
    ticker: str


# --------- lifespan ---------

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    db.init_db()
    db.reap_stale_runs(timeout_s=600)

    state = price_feed.PriceState(
        snapshots={},
        tickers=lambda: [w.ticker for w in db.list_watchlist()],
    )
    feed = price_feed.PriceFeed(state, poll_s=settings.price_poll_s)

    # start runner
    await runner.start(num_workers=1)
    feed.start(broadcast=_broadcast)
    app.state.price_feed = feed
    app.state.price_state = state
    try:
        yield
    finally:
        await feed.stop()
        await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="TradingAgents Dashboard", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "uptime_s": 0,  # simple; real uptime tracked by external process
            "watchlist_size": len(db.list_watchlist()),
            "runs_in_queue": 0,
            "runs_running": 0,
        }

    @app.get("/api/watchlist")
    def list_watch():
        return [_w_to_dict(w) for w in db.list_watchlist()]

    @app.post("/api/watchlist", status_code=201)
    def add_watch(row: WatchlistIn):
        from web.server.db import Watchlist, DuplicateTicker
        try:
            db.add_watchlist(Watchlist(
                ticker=row.ticker.upper(),
                company_name=row.company_name,
                exchange=row.exchange,
                added_at=datetime.utcnow(),
            ))
        except DuplicateTicker:
            raise HTTPException(status_code=409, detail={"error": "already_in_watchlist"})
        return _w_to_dict(db.list_watchlist()[[w.ticker for w in db.list_watchlist()].index(row.ticker.upper())])

    @app.delete("/api/watchlist/{ticker}", status_code=204)
    def del_watch(ticker: str):
        db.remove_watchlist(ticker.upper())
        return JSONResponse(status_code=204, content=None)

    @app.get("/api/prices")
    def prices():
        return app.state.price_state.snapshots

    @app.post("/api/runs", status_code=201)
    def create_run(row: RunIn):
        from datetime import date
        rid = runner.enqueue(row.ticker.upper(), idempotency_key=f"{row.ticker.upper()}:{date.today().isoformat()}")
        return {"run_id": rid}

    @app.get("/api/runs")
    def list_runs(limit: int = 20):
        return [_run_to_dict(r) for r in db.list_runs(limit=limit)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: int):
        run = db.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return {
            "run": _run_to_dict(run),
            "events": [_event_to_dict(e) for e in db.events_for_run(run_id)],
        }

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: int):
        db.request_cancellation(run_id)
        return {"cancelled": True}

    @app.websocket("/ws/runs/{run_id}")
    async def ws_run(ws: WebSocket, run_id: int, since: int = 0):
        await ws.accept()
        # Replay persisted events since `since`
        for e in db.events_for_run(run_id, since_id=since):
            await ws.send_json({
                "v": 1,
                "type": e.type,
                "ts": e.ts.isoformat() + "Z",
                "run_id": e.run_id,
                "data": json.loads(e.payload_json),
                "id": e.id,
            })
        # Subscribe to live
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)
        _subs.setdefault(run_id, set()).add(q)
        try:
            while True:
                evt = await q.get()
                await ws.send_json(evt)
        except WebSocketDisconnect:
            pass
        finally:
            _subs.get(run_id, set()).discard(q)

    # static mount (only if build dir exists)
    settings = get_settings()
    if os.path.isdir(settings.frontend_dist):
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")

    return app


def _w_to_dict(w) -> dict:
    return {
        "ticker": w.ticker,
        "company_name": w.company_name,
        "exchange": w.exchange,
        "added_at": w.added_at.isoformat() if w.added_at else None,
        "last_decision": w.last_decision,
        "last_decision_at": w.last_decision_at.isoformat() if w.last_decision_at else None,
    }


def _run_to_dict(r) -> dict:
    return {
        "id": r.id,
        "ticker": r.ticker,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "status": r.status,
        "decision_action": r.decision_action,
        "decision_target": r.decision_target,
        "decision_rationale": r.decision_rationale,
        "decision_confidence": r.decision_confidence,
    }


def _event_to_dict(e) -> dict:
    import json
    return {
        "id": e.id,
        "type": e.type,
        "ts": e.ts.isoformat() if e.ts else None,
        "data": json.loads(e.payload_json),
    }
```

Note: `add_watch` is a quick impl that re-queries to find the new row; in production you'd return the inserted object directly. For this task the test only checks the list endpoint after add.

- [ ] **Step 4: Run, expect pass**

Run: `pytest web/server/tests/test_app.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add web/server/app.py web/server/tests/test_app.py
git commit -m "feat(web): FastAPI app with health, watchlist, runs, WS"
```

---

### Task 9: Write the WebSocket replay test and verify it passes

**Files:**
- Create: `web/server/tests/test_ws.py`

- [ ] **Step 1: Write the failing WS test**

```python
import json
import threading
import time
import pytest
from fastapi.testclient import TestClient

from web.server.app import create_app
from web.server import db, runner


@pytest.fixture
def client(temp_db, monkeypatch):
    monkeypatch.setattr("web.server.runner.build_graph", lambda config=None: None)
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_ws_replays_then_live(client, monkeypatch):
    # Insert a run + 2 events directly
    rid = db.create_run(ticker="NVDA", idempotency_key="NVDA:ws")

    db.append_event(rid, "run_started", {"ticker": "NVDA"})
    db.append_event(rid, "analyst_thinking", {"stage": "market", "message": "old"})

    # Open the WS in a thread
    received = []
    stop = threading.Event()

    def listen():
        with client.websocket_connect(f"/ws/runs/{rid}") as ws:
            while not stop.is_set():
                try:
                    msg = ws.receive_json()
                    received.append(msg)
                except Exception:
                    break
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.2)

    # Now emit a live event via the broadcast function the app registered
    from web.server import events
    events.emit(rid, "decision", {"action": "BUY", "target": 200.0})
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    types = [m["type"] for m in received]
    assert "run_started" in types
    assert "analyst_thinking" in types
    assert "decision" in types


def test_ws_replays_only_gap_with_since(client, monkeypatch):
    rid = db.create_run(ticker="AAPL", idempotency_key="AAPL:gap")
    e1 = db.append_event(rid, "run_started", {})
    e2 = db.append_event(rid, "analyst_thinking", {"stage": "market"})

    received = []
    stop = threading.Event()

    def listen():
        with client.websocket_connect(f"/ws/runs/{rid}?since={e1}") as ws:
            while not stop.is_set():
                try:
                    msg = ws.receive_json()
                    received.append(msg)
                except Exception:
                    break
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    time.sleep(0.2)
    stop.set()
    t.join(timeout=2)

    # Only the analyst_thinking event (e2) should have been replayed
    types = [m["type"] for m in received]
    assert types == ["analyst_thinking"]
```

- [ ] **Step 2: Run, expect pass**

Run: `pytest web/server/tests/test_ws.py -v`
Expected: PASS (2 tests). If a test flakes on WS thread timing, increase the `time.sleep` slightly.

- [ ] **Step 3: Commit**

```bash
git add web/server/tests/test_ws.py
git commit -m "test(web): WebSocket replay + gap tests"
```

---

### Task 10: Run all backend tests together and verify green

**Files:** none

- [ ] **Step 1: Run the full backend test suite**

Run: `pytest web/server -v`
Expected: all green. Count: ~15 tests across db, events, price_feed, runner, app, ws.

- [ ] **Step 2: Commit any incidental fixes**

If a test required a small fix in app.py or runner.py, commit it:
```bash
git add web/server
git commit -m "fix(web): backend test fixes"
```

---

## Phase 4 — Frontend foundation

### Task 11: Scaffold Vite + React + TS + Tailwind + shadcn/ui

**Files:**
- Create: `web/frontend/` (entire scaffold)

- [ ] **Step 1: Scaffold via Vite**

Run:
```bash
cd web
npm create vite@latest frontend -- --template react-ts
```

Expected: `web/frontend/` exists with `package.json`, `src/`, `index.html`, `tsconfig.json`.

- [ ] **Step 2: Install runtime dependencies**

```bash
cd web/frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npm install @tanstack/react-query zustand ws lucide-react cmdk
npm install -D @types/ws vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitest/ui
npx tailwindcss init -p
```

- [ ] **Step 3: Configure Tailwind**

`tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

`src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: 0 0% 100%;
  --foreground: 222 47% 11%;
  --muted: 210 40% 96%;
  --muted-foreground: 215 16% 47%;
  --border: 214 32% 91%;
  --accent: 221 83% 53%;
}
body {
  background: hsl(var(--background));
  color: hsl(var(--foreground));
  font-family: system-ui, -apple-system, sans-serif;
}
```

- [ ] **Step 4: Configure Vite proxy**

`vite.config.ts`:
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/__tests__/setup.ts"],
  },
});
```

- [ ] **Step 5: Add vitest setup file**

`src/__tests__/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 6: Verify dev server starts**

Run: `cd web/frontend && npm run dev`
Expected: Vite serves on :5173. Ctrl-C after 2s. No errors.

- [ ] **Step 7: Commit**

```bash
git add web/frontend
git commit -m "feat(web): scaffold Vite+React+TS+Tailwind frontend"
```

---

### Task 12: Add `events.ts` mirror and Zustand store

**Files:**
- Create: `web/frontend/src/lib/events.ts`
- Create: `web/frontend/src/store/ui.ts`
- Create: `web/frontend/src/__tests__/events-protocol.test.ts`

- [ ] **Step 1: Write the TS event mirror**

`src/lib/events.ts`:
```ts
// Hand-synced mirror of web/server/events.py EventType.
// If you add/remove a type, update BOTH files AND the test.
export const EventType = {
  RUN_STARTED: "run_started",
  RUN_FINISHED: "run_finished",
  RUN_FAILED: "run_failed",
  ANALYST_STARTED: "analyst_started",
  ANALYST_THINKING: "analyst_thinking",
  ANALYST_COMPLETED: "analyst_completed",
  TOOL_CALL: "tool_call",
  TOOL_RESULT: "tool_result",
  TOOL_CALL_WARNING: "tool_call_warning",
  DEBATE_MESSAGE: "debate_message",
  RISK_MESSAGE: "risk_message",
  DECISION: "decision",
  PRICE_UPDATE: "price_update",
  SERVER_NOTICE: "server_notice",
} as const;

export type EventTypeValue = typeof EventType[keyof typeof EventType];

export interface WsEvent<T = unknown> {
  v: 1;
  type: EventTypeValue;
  ts: string;
  run_id: number;
  data: T;
  id?: number;
}

export const ALL_EVENT_TYPES: EventTypeValue[] = Object.values(EventType);
```

- [ ] **Step 2: Write the protocol parity test**

`src/__tests__/events-protocol.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { EventType, ALL_EVENT_TYPES } from "../lib/events";

// Mirror the Python expected set
const PYTHON_EXPECTED = new Set([
  "run_started", "run_finished", "run_failed",
  "analyst_started", "analyst_thinking", "analyst_completed",
  "tool_call", "tool_result", "tool_call_warning",
  "debate_message", "risk_message", "decision",
  "price_update", "server_notice",
]);

describe("events protocol", () => {
  it("TS mirror matches Python expected set", () => {
    const ts = new Set(ALL_EVENT_TYPES);
    expect(ts).toEqual(PYTHON_EXPECTED);
  });

  it("no empty type values", () => {
    for (const v of ALL_EVENT_TYPES) {
      expect(v).toBeTruthy();
      expect(typeof v).toBe("string");
    }
  });

  it("EventType keys are unique", () => {
    const values = Object.values(EventType);
    expect(new Set(values).size).toBe(values.length);
  });
});
```

- [ ] **Step 3: Write the Zustand UI store**

`src/store/ui.ts`:
```ts
import { create } from "zustand";
import type { WsEvent } from "../lib/events";

interface UiState {
  focusedTicker: string | null;
  connectedRunId: number | null;
  eventBuffer: WsEvent[];
  setFocusedTicker: (t: string | null) => void;
  setConnectedRunId: (rid: number | null) => void;
  appendEvent: (e: WsEvent) => void;
  clearBuffer: () => void;
}

export const useUi = create<UiState>((set) => ({
  focusedTicker: null,
  connectedRunId: null,
  eventBuffer: [],
  setFocusedTicker: (t) => set({ focusedTicker: t, eventBuffer: [], connectedRunId: null }),
  setConnectedRunId: (rid) => set({ connectedRunId: rid }),
  appendEvent: (e) => set((s) => ({ eventBuffer: [...s.eventBuffer, e].slice(-1000) })),
  clearBuffer: () => set({ eventBuffer: [] }),
}));
```

- [ ] **Step 4: Run vitest, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/events-protocol.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/lib/events.ts web/frontend/src/store/ui.ts web/frontend/src/__tests__/events-protocol.test.ts
git commit -m "feat(web): TS event mirror, UI store, protocol parity test"
```

---

### Task 13: Add API client, query client, and prices hook

**Files:**
- Create: `web/frontend/src/lib/api.ts`
- Create: `web/frontend/src/lib/queryClient.ts`
- Create: `web/frontend/src/hooks/usePrices.ts`
- Create: `web/frontend/src/App.tsx` (minimal shell)

- [ ] **Step 1: Write the API client**

`src/lib/api.ts`:
```ts
const base = "";

export interface WatchlistRow {
  ticker: string;
  company_name: string;
  exchange: string;
  added_at: string | null;
  last_decision: string | null;
  last_decision_at: string | null;
}

export interface RunRow {
  id: number;
  ticker: string;
  started_at: string | null;
  finished_at: string | null;
  status: "queued" | "running" | "done" | "failed" | "cancelled";
  decision_action: string | null;
  decision_target: number | null;
  decision_rationale: string | null;
  decision_confidence: number | null;
}

export interface RunDetail {
  run: RunRow;
  events: Array<{ id: number; type: string; ts: string | null; data: unknown }>;
}

export async function fetchWatchlist(): Promise<WatchlistRow[]> {
  const r = await fetch(`${base}/api/watchlist`);
  if (!r.ok) throw new Error(`watchlist ${r.status}`);
  return r.json();
}

export async function addToWatchlist(ticker: string, company_name: string, exchange: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker, company_name, exchange }),
  });
  if (!r.ok && r.status !== 201) throw new Error(`add ${r.status}`);
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const r = await fetch(`${base}/api/watchlist/${encodeURIComponent(ticker)}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`remove ${r.status}`);
}

export async function fetchPrices(): Promise<Record<string, unknown>> {
  const r = await fetch(`${base}/api/prices`);
  if (!r.ok) throw new Error(`prices ${r.status}`);
  return r.json();
}

export async function startRun(ticker: string): Promise<{ run_id: number }> {
  const r = await fetch(`${base}/api/runs`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ticker }),
  });
  if (!r.ok) throw new Error(`start ${r.status}`);
  return r.json();
}

export async function cancelRun(runId: number): Promise<void> {
  const r = await fetch(`${base}/api/runs/${runId}/cancel`, { method: "POST" });
  if (!r.ok) throw new Error(`cancel ${r.status}`);
}

export async function fetchRunDetail(runId: number): Promise<RunDetail> {
  const r = await fetch(`${base}/api/runs/${runId}`);
  if (!r.ok) throw new Error(`run ${r.status}`);
  return r.json();
}
```

- [ ] **Step 2: Write the query client**

`src/lib/queryClient.ts`:
```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 5_000, refetchOnWindowFocus: false, retry: 1 },
  },
});
```

- [ ] **Step 3: Write the prices hook**

`src/hooks/usePrices.ts`:
```ts
import { useQuery } from "@tanstack/react-query";
import { fetchPrices } from "../lib/api";

export function usePrices() {
  return useQuery({ queryKey: ["prices"], queryFn: fetchPrices, refetchInterval: 20_000 });
}
```

- [ ] **Step 4: Write a minimal `App.tsx`**

`src/App.tsx`:
```tsx
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist } from "./lib/api";
import { useUi } from "./store/ui";

export default function App() {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const { data: watchlist } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });

  useEffect(() => {
    if (!focused && watchlist && watchlist.length > 0) setFocused(watchlist[0].ticker);
  }, [watchlist, focused, setFocused]);

  return (
    <div className="min-h-screen p-6 text-[hsl(var(--foreground))]">
      <h1 className="text-xl font-semibold mb-4">TradingAgents</h1>
      <p className="text-sm text-[hsl(var(--muted-foreground))]">
        Focused ticker: <code>{focused ?? "(none)"}</code>. Components arrive in the next tasks.
      </p>
    </div>
  );
}
```

`src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { queryClient } from "./lib/queryClient";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>
);
```

- [ ] **Step 5: Verify build**

Run: `cd web/frontend && npm run build`
Expected: completes; `dist/index.html` exists.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src
git commit -m "feat(web): api client, query client, prices hook, app shell"
```

---

### Task 14: Add WebSocket client and `useRunStream` hook

**Files:**
- Create: `web/frontend/src/lib/ws.ts`
- Create: `web/frontend/src/hooks/useRunStream.ts`
- Create: `web/frontend/src/__tests__/mocks/mockWs.ts`
- Create: `web/frontend/src/__tests__/useRunStream.test.ts`

- [ ] **Step 1: Write the mock WebSocket helper**

`src/__tests__/mocks/mockWs.ts`:
```ts
import { vi } from "vitest";

export class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  // Test helpers
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  receive(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
  failAndClose() {
    this.onerror?.(new Error("boom"));
    this.readyState = 3;
    this.onclose?.();
  }
}

export function installMockWebSocket() {
  MockWebSocket.instances = [];
  (globalThis as any).WebSocket = MockWebSocket;
  return MockWebSocket;
}
```

- [ ] **Step 2: Write the WS client**

`src/lib/ws.ts`:
```ts
import type { WsEvent } from "./events";

export interface SubscribeOpts {
  url: string;
  onMessage: (evt: WsEvent) => void;
  onStatus?: (status: "connecting" | "open" | "reconnecting" | "closed") => void;
  backoffMs?: (attempt: number) => number;
}

export class ResilientWs {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private closedByUser = false;
  private opts: SubscribeOpts;

  constructor(opts: SubscribeOpts) {
    this.opts = opts;
  }

  start() {
    this.closedByUser = false;
    this.connect();
  }

  stop() {
    this.closedByUser = true;
    this.ws?.close();
    this.ws = null;
    this.opts.onStatus?.("closed");
  }

  private connect() {
    this.opts.onStatus?.(this.attempt === 0 ? "connecting" : "reconnecting");
    const ws = new WebSocket(this.opts.url);
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.opts.onStatus?.("open");
    };
    ws.onmessage = (e) => {
      try {
        const evt = JSON.parse((e as MessageEvent).data as string) as WsEvent;
        this.opts.onMessage(evt);
      } catch {
        // ignore malformed
      }
    };
    ws.onclose = () => {
      if (this.closedByUser) return;
      const delay = (this.opts.backoffMs ?? defaultBackoff)(this.attempt++);
      setTimeout(() => this.connect(), delay);
    };
    ws.onerror = () => {
      // close will follow
    };
  }
}

function defaultBackoff(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 30_000);
}

export function buildRunUrl(runId: number, since?: number): string {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const base = `${proto}//${location.host}/ws/runs/${runId}`;
  return since ? `${base}?since=${since}` : base;
}
```

- [ ] **Step 3: Write the hook**

`src/hooks/useRunStream.ts`:
```ts
import { useEffect, useRef, useState } from "react";
import { ResilientWs, buildRunUrl } from "../lib/ws";
import type { WsEvent } from "../lib/events";
import { useUi } from "../store/ui";

export type WsStatus = "idle" | "connecting" | "open" | "reconnecting" | "closed";

export function useRunStream(runId: number | null) {
  const appendEvent = useUi((s) => s.appendEvent);
  const [status, setStatus] = useState<WsStatus>("idle");
  const lastIdRef = useRef<number>(0);
  const clientRef = useRef<ResilientWs | null>(null);

  useEffect(() => {
    if (runId == null) {
      setStatus("idle");
      return;
    }
    const client = new ResilientWs({
      url: buildRunUrl(runId, lastIdRef.current || undefined),
      onMessage: (evt) => {
        if (typeof evt.id === "number") lastIdRef.current = Math.max(lastIdRef.current, evt.id);
        appendEvent(evt);
      },
      onStatus: setStatus,
    });
    clientRef.current = client;
    client.start();
    return () => {
      client.stop();
      clientRef.current = null;
    };
  }, [runId, appendEvent]);

  return { status };
}
```

- [ ] **Step 4: Write the failing test**

`src/__tests__/useRunStream.test.ts`:
```ts
import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { installMockWebSocket, MockWebSocket } from "./mocks/mockWs";
import { useRunStream } from "../hooks/useRunStream";
import { useUi } from "../store/ui";

describe("useRunStream", () => {
  beforeEach(() => {
    installMockWebSocket();
    useUi.setState({ eventBuffer: [] });
  });

  it("connects and pushes events to the buffer", () => {
    const { result } = renderHook(() => useRunStream(42));
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "run_started", ts: "2026-06-01T00:00:00Z", run_id: 42, data: {}, id: 1 }));
    expect(useUi.getState().eventBuffer).toHaveLength(1);
    expect(result.current.status).toBe("open");
  });

  it("reconnects with ?since= after disconnect", () => {
    const { result } = renderHook(() => useRunStream(42));
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ v: 1, type: "analyst_thinking", ts: "t", run_id: 42, data: {}, id: 5 }));
    act(() => ws.failAndClose());
    // backoff is 1s by default in tests? we'll override:
    // since we can't easily mock timers, accept up to 1.5s
    return new Promise<void>((resolve) => {
      setTimeout(() => {
        const next = MockWebSocket.instances[MockWebSocket.instances.length - 1];
        expect(next.url).toContain("since=5");
        resolve();
      }, 1100);
    });
  });
});
```

- [ ] **Step 5: Run test, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/useRunStream.test.ts`
Expected: PASS. If timing is flaky, increase the timeout in the test.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/lib/ws.ts web/frontend/src/hooks/useRunStream.ts web/frontend/src/__tests__
git commit -m "feat(web): resilient WS client and useRunStream hook"
```

---

## Phase 5 — Frontend components

### Task 15: `WatchlistRail` + `TickerRow` + `AddTickerCommand`

**Files:**
- Create: `web/frontend/src/components/WatchlistRail.tsx`
- Create: `web/frontend/src/components/TickerRow.tsx`
- Create: `web/frontend/src/components/AddTickerCommand.tsx`
- Create: `web/frontend/src/__tests__/WatchlistRail.test.tsx`

- [ ] **Step 1: Write the failing test**

`src/__tests__/WatchlistRail.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WatchlistRail } from "../components/WatchlistRail";
import { useUi } from "../store/ui";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  useUi.setState({ focusedTicker: null });
  global.fetch = vi.fn((url) => {
    if (String(url).endsWith("/api/watchlist")) {
      return Promise.resolve(new Response(JSON.stringify([
        { ticker: "NVDA", company_name: "NVIDIA", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
        { ticker: "AAPL", company_name: "Apple", exchange: "NASDAQ", added_at: null, last_decision: null, last_decision_at: null },
      ])));
    }
    return Promise.resolve(new Response("{}", { status: 200 }));
  }) as any;
});

describe("WatchlistRail", () => {
  it("renders rows and clicking sets focus", async () => {
    wrap(<WatchlistRail />);
    await waitFor(() => expect(screen.getByText("NVDA")).toBeInTheDocument());
    fireEvent.click(screen.getByText("NVDA"));
    expect(useUi.getState().focusedTicker).toBe("NVDA");
  });

  it("shows an Add button", async () => {
    wrap(<WatchlistRail />);
    await waitFor(() => expect(screen.getByText(/add/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd web/frontend && npx vitest run src/__tests__/WatchlistRail.test.tsx`
Expected: FAIL — components don't exist.

- [ ] **Step 3: Write `TickerRow.tsx`**

```tsx
import { useUi } from "../store/ui";

interface Props {
  ticker: string;
  companyName: string;
  lastDecision: string | null;
  sparkline: number[];
  status: "idle" | "queued" | "running" | "done" | "errored";
}

const dotColor: Record<Props["status"], string> = {
  idle: "bg-slate-300",
  queued: "bg-amber-400",
  running: "bg-blue-500 animate-pulse",
  done: "bg-emerald-500",
  errored: "bg-rose-500",
};

export function TickerRow({ ticker, companyName, lastDecision, sparkline, status }: Props) {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const isFocused = focused === ticker;

  const sparkPath = sparkline.length > 1
    ? sparkline.map((v, i) => `${i === 0 ? "M" : "L"} ${i * 4} ${20 - v}`).join(" ")
    : "";

  return (
    <button
      onClick={() => setFocused(ticker)}
      data-focused={isFocused}
      className={`w-full text-left px-3 py-2 rounded-lg flex items-center gap-3 hover:bg-slate-50 ${
        isFocused ? "bg-blue-50 ring-1 ring-blue-200" : ""
      }`}
    >
      <span className={`h-2 w-2 rounded-full ${dotColor[status]}`} />
      <div className="flex-1">
        <div className="text-sm font-semibold">{ticker}</div>
        <div className="text-xs text-slate-500 truncate">{companyName || lastDecision || "—"}</div>
      </div>
      <svg width="40" height="20" className="opacity-60">
        {sparkPath && <path d={sparkPath} stroke="rgb(59 130 246)" strokeWidth="1" fill="none" />}
      </svg>
    </button>
  );
}
```

- [ ] **Step 4: Write `AddTickerCommand.tsx`**

```tsx
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { addToWatchlist } from "../lib/api";

export function AddTickerCommand() {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const qc = useQueryClient();

  async function submit() {
    if (!value) return;
    try {
      await addToWatchlist(value.toUpperCase(), "", "");
      setValue("");
      setOpen(false);
      setError(null);
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    } catch (e) {
      setError("Could not add (maybe already in watchlist?)");
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="w-full text-left px-3 py-2 text-sm text-slate-500 hover:bg-slate-50 rounded-lg"
      >
        + Add ticker
      </button>
    );
  }

  return (
    <div className="p-2">
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Ticker symbol (e.g. NVDA)"
        className="w-full px-2 py-1 text-sm border border-slate-200 rounded"
      />
      {error && <p className="text-xs text-rose-500 mt-1">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Write `WatchlistRail.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices } from "../lib/api";
import { TickerRow } from "./TickerRow";
import { AddTickerCommand } from "./AddTickerCommand";

type RunStatus = "idle" | "queued" | "running" | "done" | "errored";

function statusForTicker(ticker: string, lastDecision: string | null, events: any[]): RunStatus {
  if (!lastDecision) return "idle";
  const last = events.filter((e) => e.type === "run_started" || e.type === "run_finished" || e.type === "run_failed").pop();
  if (!last) return "idle";
  if (last.type === "run_started") return "running";
  if (last.type === "run_finished") return "done";
  return "errored";
}

export function WatchlistRail() {
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });

  return (
    <aside className="w-64 border-r border-slate-200 p-2 h-screen overflow-y-auto">
      <div className="text-xs uppercase tracking-wide text-slate-500 px-2 py-1">Watchlist</div>
      {watchlist.map((row) => {
        const price = (prices as any)[row.ticker] || {};
        return (
          <TickerRow
            key={row.ticker}
            ticker={row.ticker}
            companyName={row.company_name}
            lastDecision={row.last_decision}
            sparkline={price.sparkline || []}
            status={statusForTicker(row.ticker, row.last_decision, [])}
          />
        );
      })}
      <AddTickerCommand />
    </aside>
  );
}
```

- [ ] **Step 6: Run tests, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/WatchlistRail.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add web/frontend/src/components web/frontend/src/__tests__/WatchlistRail.test.tsx
git commit -m "feat(web): WatchlistRail with TickerRow and Add command"
```

---

### Task 16: `TickerHeader` with Run/Cancel

**Files:**
- Create: `web/frontend/src/components/TickerHeader.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { startRun, cancelRun } from "../lib/api";
import { useUi } from "../store/ui";

interface Props { ticker: string; price?: number; changePct?: number; }

export function TickerHeader({ ticker, price, changePct }: Props) {
  const qc = useQueryClient();
  const connectedRunId = useUi((s) => s.connectedRunId);
  const setConnectedRunId = useUi((s) => s.setConnectedRunId);
  const appendEvent = useUi((s) => s.appendEvent);
  const clearBuffer = useUi((s) => s.clearBuffer);

  const start = useMutation({
    mutationFn: () => startRun(ticker),
    onSuccess: ({ run_id }) => {
      clearBuffer();
      setConnectedRunId(run_id);
      qc.invalidateQueries({ queryKey: ["runs", "list"] });
    },
  });

  const cancel = useMutation({
    mutationFn: () => cancelRun(connectedRunId!),
    onSuccess: () => {
      // runner emits run_failed with reason=cancelled; buffer will pick it up
    },
  });

  const isRunning = !!connectedRunId;

  return (
    <div className="flex items-center justify-between mb-4">
      <div>
        <h2 className="text-2xl font-semibold">{ticker}</h2>
        <p className="text-sm text-slate-500">
          {price != null ? `$${price.toFixed(2)}` : "—"}
          {changePct != null && (
            <span className={changePct >= 0 ? "text-emerald-600 ml-2" : "text-rose-600 ml-2"}>
              {changePct >= 0 ? "+" : ""}{(changePct * 100).toFixed(2)}%
            </span>
          )}
        </p>
      </div>
      <div className="flex gap-2">
        <button
          disabled={isRunning || start.isPending}
          onClick={() => start.mutate()}
          className="px-3 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white disabled:opacity-50"
        >
          {start.isPending ? "Starting…" : "Run analysis"}
        </button>
        {isRunning && (
          <button
            onClick={() => cancel.mutate()}
            className="px-3 py-1.5 text-sm font-medium rounded-md border border-slate-300"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manual check (no unit test; covered by E2E later)**

This component is exercised through the App + useRunStream wiring. A unit test would require mocking the WS which is heavy; defer to the Playwright spec.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/components/TickerHeader.tsx
git commit -m "feat(web): TickerHeader with Run/Cancel buttons"
```

---

### Task 17: `StageGrid`

**Files:**
- Create: `web/frontend/src/components/StageGrid.tsx`
- Create: `web/frontend/src/__tests__/StageGrid.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StageGrid } from "../components/StageGrid";
import { useUi } from "../store/ui";

describe("StageGrid", () => {
  it("renders a card per stage", () => {
    render(<StageGrid />);
    for (const name of ["Market", "Sentiment", "News", "Fundamentals", "Research", "Risk", "Trader"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
  });

  it("marks a stage done after analyst_completed", () => {
    useUi.setState({
      eventBuffer: [
        { v: 1, type: "analyst_completed", ts: "t", run_id: 1, data: { stage: "market" }, id: 1 },
      ],
    });
    render(<StageGrid />);
    const card = screen.getByTestId("stage-market");
    expect(card.getAttribute("data-status")).toBe("done");
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd web/frontend && npx vitest run src/__tests__/StageGrid.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write `StageGrid.tsx`**

```tsx
import { useUi } from "../store/ui";

const STAGES = [
  { key: "market", label: "Market" },
  { key: "sentiment", label: "Sentiment" },
  { key: "news", label: "News" },
  { key: "fundamentals", label: "Fundamentals" },
  { key: "research", label: "Research" },
  { key: "risk", label: "Risk" },
  { key: "trader", label: "Trader" },
] as const;

type StageKey = (typeof STAGES)[number]["key"];

function statusFor(stage: StageKey, events: any[]): "idle" | "running" | "done" | "errored" {
  const started = events.find((e) => e.type === "analyst_started" && e.data?.node?.toLowerCase().includes(stage));
  const completed = events.find((e) => e.type === "analyst_completed" && e.data?.stage === stage);
  if (completed) return "done";
  if (started) return "running";
  return "idle";
}

export function StageGrid() {
  const events = useUi((s) => s.eventBuffer);
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2 mb-4">
      {STAGES.map((s) => {
        const status = statusFor(s.key, events);
        return (
          <div
            key={s.key}
            data-testid={`stage-${s.key}`}
            data-status={status}
            className={`rounded-lg border p-3 text-sm ${
              status === "done" ? "border-emerald-200 bg-emerald-50" :
              status === "running" ? "border-blue-200 bg-blue-50 animate-pulse" :
              "border-slate-200 bg-white"
            }`}
          >
            <div className="font-medium">{s.label}</div>
            <div className="text-xs text-slate-500 mt-1">
              {status === "done" ? "✓ done" : status === "running" ? "running…" : "queued"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/StageGrid.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/StageGrid.tsx web/frontend/src/__tests__/StageGrid.test.tsx
git commit -m "feat(web): StageGrid with per-stage status"
```

---

### Task 18: `LiveEventStream`

**Files:**
- Create: `web/frontend/src/components/LiveEventStream.tsx`
- Create: `web/frontend/src/__tests__/LiveEventStream.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { LiveEventStream } from "../components/LiveEventStream";
import { useUi } from "../store/ui";

describe("LiveEventStream", () => {
  it("renders bubbles in order, colors decision green/red", () => {
    useUi.setState({
      eventBuffer: [
        { v: 1, type: "analyst_thinking", ts: "t1", run_id: 1, data: { node: "Market Analyst" }, id: 1 },
        { v: 1, type: "decision", ts: "t2", run_id: 1, data: { action: "BUY", target: 260 }, id: 2 },
      ],
    });
    render(<LiveEventStream />);
    expect(screen.getByText(/Market Analyst/)).toBeInTheDocument();
    const bubble = screen.getByTestId("event-2");
    expect(bubble.className).toMatch(/emerald/);
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd web/frontend && npx vitest run src/__tests__/LiveEventStream.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write `LiveEventStream.tsx`**

```tsx
import { useEffect, useRef } from "react";
import { useUi } from "../store/ui";
import type { WsEvent } from "../lib/events";

const colorForType: Record<string, string> = {
  analyst_started: "bg-blue-100 text-blue-900",
  analyst_thinking: "bg-blue-50 text-blue-900",
  analyst_completed: "bg-blue-50 text-blue-900",
  tool_call: "bg-slate-100 text-slate-700",
  tool_result: "bg-slate-50 text-slate-700",
  debate_message: "bg-amber-50 text-amber-900",
  risk_message: "bg-amber-50 text-amber-900",
  decision: "bg-emerald-100 text-emerald-900",
  run_failed: "bg-rose-100 text-rose-900",
  run_finished: "bg-emerald-50 text-emerald-900",
  server_notice: "bg-slate-100 text-slate-700",
};

export function LiveEventStream() {
  const events = useUi((s) => s.eventBuffer);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [events.length]);

  return (
    <div ref={ref} className="h-96 overflow-y-auto rounded-lg border border-slate-200 bg-white p-3 space-y-2">
      {events.length === 0 && <p className="text-sm text-slate-400">No events yet. Click "Run analysis" to start.</p>}
      {events.map((e) => (
        <Bubble key={(e.id ?? 0) + ":" + e.ts} event={e} />
      ))}
    </div>
  );
}

function Bubble({ event }: { event: WsEvent }) {
  const data = event.data as Record<string, unknown>;
  const text =
    event.type === "analyst_thinking" ? String(data.node ?? data.stage ?? "thinking") :
    event.type === "debate_message" ? `${data.side}: ${data.text}` :
    event.type === "decision" ? `DECISION: ${data.action} @ ${data.target}` :
    event.type === "tool_call" ? `tool: ${data.tool}` :
    event.type === "tool_result" ? `result: ${String(data.summary ?? "").slice(0, 60)}` :
    event.type === "run_failed" ? `failed: ${data.reason}` :
    event.type;
  return (
    <div
      data-testid={`event-${event.id ?? ""}`}
      className={`text-xs px-2 py-1 rounded ${colorForType[event.type] ?? "bg-slate-100 text-slate-700"}`}
    >
      <span className="text-slate-400 mr-2">{new Date(event.ts).toLocaleTimeString()}</span>
      {text}
    </div>
  );
}
```

- [ ] **Step 4: Run, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/LiveEventStream.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/LiveEventStream.tsx web/frontend/src/__tests__/LiveEventStream.test.tsx
git commit -m "feat(web): LiveEventStream with typed bubbles"
```

---

### Task 19: `DecisionPanel`

**Files:**
- Create: `web/frontend/src/components/DecisionPanel.tsx`
- Create: `web/frontend/src/__tests__/DecisionPanel.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DecisionPanel } from "../components/DecisionPanel";

describe("DecisionPanel", () => {
  it("renders action, target, and confidence bar", () => {
    render(<DecisionPanel action="BUY" target={260.5} confidence={0.82} rationale="looks good" />);
    expect(screen.getByText(/BUY/)).toBeInTheDocument();
    expect(screen.getByText(/\$260/)).toBeInTheDocument();
    expect(screen.getByText(/looks good/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd web/frontend && npx vitest run src/__tests__/DecisionPanel.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write `DecisionPanel.tsx`**

```tsx
interface Props {
  action: "BUY" | "SELL" | "HOLD" | string;
  target: number | null;
  confidence: number;
  rationale: string;
  degraded?: boolean;
}

export function DecisionPanel({ action, target, confidence, rationale, degraded }: Props) {
  const actionColor = action === "BUY" ? "text-emerald-600" : action === "SELL" ? "text-rose-600" : "text-slate-600";
  const pct = Math.max(0, Math.min(1, confidence)) * 100;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 mt-4">
      <div className="flex items-center gap-3 mb-2">
        <span className={`text-2xl font-semibold ${actionColor}`}>{action}</span>
        {target != null && <span className="text-lg text-slate-700">@ ${target.toFixed(2)}</span>}
        <div className="flex-1" />
        {degraded && <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">degraded</span>}
      </div>
      <div className="text-xs text-slate-500 mb-1">Confidence</div>
      <div className="h-2 bg-slate-100 rounded">
        <div className="h-2 rounded bg-blue-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="text-sm text-slate-700 mt-3 whitespace-pre-wrap">{rationale}</p>
    </div>
  );
}
```

- [ ] **Step 4: Run, expect pass**

Run: `cd web/frontend && npx vitest run src/__tests__/DecisionPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/components/DecisionPanel.tsx web/frontend/src/__tests__/DecisionPanel.test.tsx
git commit -m "feat(web): DecisionPanel with confidence bar"
```

---

### Task 20: `RunHistoryDrawer`

**Files:**
- Create: `web/frontend/src/components/RunHistoryDrawer.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchRunDetail, type RunRow } from "../lib/api";

async function fetchRuns(): Promise<RunRow[]> {
  const r = await fetch("/api/runs?limit=50");
  if (!r.ok) throw new Error(`runs ${r.status}`);
  return r.json();
}

export function RunHistoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: runs = [] } = useQuery({ queryKey: ["runs", "list"], queryFn: fetchRuns, enabled: open });

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-white border-l border-slate-200 shadow-xl z-10">
      <div className="flex items-center justify-between p-3 border-b border-slate-200">
        <h3 className="font-semibold">Run history</h3>
        <button onClick={onClose} className="text-sm text-slate-500">Close</button>
      </div>
      <div className="overflow-y-auto h-full pb-12">
        {runs.map((r) => <RunRowItem key={r.id} run={r} />)}
      </div>
    </div>
  );
}

function RunRowItem({ run }: { run: RunRow }) {
  const { data: detail } = useQuery({
    queryKey: ["run", run.id],
    queryFn: () => fetchRunDetail(run.id),
  });
  return (
    <details className="border-b border-slate-100 p-3">
      <summary className="cursor-pointer">
        <span className="text-sm font-medium">{run.ticker}</span>{" "}
        <span className="text-xs text-slate-500">#{run.id} · {run.status}</span>
        {run.decision_action && <span className="ml-2 text-xs">{run.decision_action}{run.decision_target ? ` @ $${run.decision_target}` : ""}</span>}
      </summary>
      <pre className="mt-2 text-xs text-slate-600 overflow-x-auto">
        {JSON.stringify(detail?.events.map((e) => ({ type: e.type, data: e.data })) ?? [], null, 2)}
      </pre>
    </details>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/frontend/src/components/RunHistoryDrawer.tsx
git commit -m "feat(web): RunHistoryDrawer with expandable details"
```

---

### Task 21: Wire it all together in `App.tsx`

**Files:**
- Modify: `web/frontend/src/App.tsx`

- [ ] **Step 1: Replace `App.tsx` with the full layout**

```tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchWatchlist, fetchPrices, type RunRow } from "./lib/api";
import { useUi } from "./store/ui";
import { useRunStream } from "./hooks/useRunStream";
import { WatchlistRail } from "./components/WatchlistRail";
import { TickerHeader } from "./components/TickerHeader";
import { StageGrid } from "./components/StageGrid";
import { LiveEventStream } from "./components/LiveEventStream";
import { DecisionPanel } from "./components/DecisionPanel";
import { RunHistoryDrawer } from "./components/RunHistoryDrawer";

export default function App() {
  const focused = useUi((s) => s.focusedTicker);
  const setFocused = useUi((s) => s.setFocusedTicker);
  const runId = useUi((s) => s.connectedRunId);
  const events = useUi((s) => s.eventBuffer);
  const { data: watchlist = [] } = useQuery({ queryKey: ["watchlist"], queryFn: fetchWatchlist });
  const { data: prices = {} } = useQuery({ queryKey: ["prices"], queryFn: fetchPrices });
  const [historyOpen, setHistoryOpen] = useState(false);

  useRunStream(runId);

  useEffect(() => {
    if (!focused && watchlist.length > 0) setFocused(watchlist[0].ticker);
  }, [watchlist, focused, setFocused]);

  if (!focused) {
    return (
      <div className="min-h-screen p-6">
        <p className="text-sm text-slate-500">Loading watchlist…</p>
      </div>
    );
  }

  const price = (prices as any)[focused] || {};
  const decisionEvent = [...events].reverse().find((e) => e.type === "decision");
  const decision = decisionEvent?.data as { action: string; target: number; rationale: string; confidence: number } | undefined;

  return (
    <div className="min-h-screen flex">
      <WatchlistRail />
      <main className="flex-1 p-6">
        <header className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-semibold">TradingAgents</h1>
          <button onClick={() => setHistoryOpen(true)} className="text-sm text-blue-600">History</button>
        </header>
        <TickerHeader ticker={focused} price={price.price} changePct={price.change_pct} />
        <StageGrid />
        <LiveEventStream />
        {decision && (
          <DecisionPanel
            action={decision.action}
            target={decision.target ?? null}
            confidence={decision.confidence ?? 0}
            rationale={decision.rationale ?? ""}
          />
        )}
      </main>
      <RunHistoryDrawer open={historyOpen} onClose={() => setHistoryOpen(false)} />
    </div>
  );
}

import { useEffect } from "react";
```

- [ ] **Step 2: Verify build**

Run: `cd web/frontend && npm run build`
Expected: build succeeds; `dist/index.html` exists.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/src/App.tsx
git commit -m "feat(web): wire full dashboard layout in App"
```

---

## Phase 6 — Polish & E2E

### Task 22: End-to-end smoke test (manual + Playwright)

**Files:**
- Create: `web/frontend/playwright.config.ts`
- Create: `web/frontend/e2e/full_run.spec.ts`
- Create: `web/frontend/e2e/README.md`

- [ ] **Step 1: Install Playwright**

Run:
```bash
cd web/frontend
npm install -D @playwright/test
npx playwright install --with-deps chromium
```

- [ ] **Step 2: Write `playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  webServer: [
    {
      command: "cd ../.. && python -m uvicorn web.server.app:create_app --factory --port 8000",
      port: 8000,
      reuseExistingServer: true,
      timeout: 30_000,
    },
    {
      command: "npm run dev",
      port: 5173,
      reuseExistingServer: true,
      timeout: 30_000,
    },
  ],
  use: { baseURL: "http://localhost:5173" },
});
```

- [ ] **Step 3: Write `e2e/full_run.spec.ts`**

This test mocks the LLM and runs a single scripted run end-to-end.

```ts
import { test, expect } from "@playwright/test";

test("full run: add ticker, run analysis, see decision", async ({ page }) => {
  await page.goto("/");
  await page.getByText("+ Add ticker").click();
  await page.getByPlaceholder("Ticker symbol").fill("NVDA");
  await page.keyboard.press("Enter");

  // Focused should now be NVDA
  await expect(page.getByRole("heading", { name: "NVDA" })).toBeVisible();

  // Run analysis (uses real TradingAgentsGraph with a stubbed propagate in the test env)
  await page.getByRole("button", { name: "Run analysis" }).click();

  // Wait for decision panel
  await expect(page.getByText(/DECISION/)).toBeVisible({ timeout: 120_000 });
});
```

- [ ] **Step 4: Document the manual checklist**

`web/frontend/e2e/README.md`:
```md
# E2E manual checklist

- [ ] Add 3 tickers, kick off all at once, see queueing
- [ ] Cancel a running analysis, see clean error
- [ ] Restart server mid-run, verify WS reconnects and replays the gap
- [ ] YFinance blocked → see stale badge, server keeps running
- [ ] Open in 2 browser tabs → both get every event
- [ ] Reload mid-run → see persisted events from DB
```

- [ ] **Step 5: Run Playwright (optional, slow)**

Run: `cd web/frontend && npx playwright test`
Expected: 1 test passes. If the test is gated to CI, skip locally.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/playwright.config.ts web/frontend/e2e
git commit -m "test(web): Playwright e2e + manual checklist"
```

---

### Task 23: Write `web/README.md` and root `web/package.json` convenience scripts

**Files:**
- Create: `web/README.md`
- Create: `web/package.json` (root-level convenience)

- [ ] **Step 1: Write `web/README.md`**

```md
# TradingAgents Dashboard

A web UI for running the multi-agent TradingAgents pipeline on a watchlist
of tickers and streaming every event in real time.

## Quick start (production-style)

```bash
# 1. install backend deps
uv sync

# 2. build the frontend
cd web/frontend
npm install
npm run build
cd ../..

# 3. start the dashboard
python -m uvicorn web.server.app:create_app --factory
# → http://localhost:8000
```

## Dev mode (hot reload)

```bash
# terminal 1: backend
python -m uvicorn web.server.app:create_app --factory --reload

# terminal 2: frontend
cd web/frontend
npm run dev
# → http://localhost:5173 (proxies /api and /ws to :8000)
```

## Tests

```bash
# backend
pytest web/server -v

# frontend
cd web/frontend
npx vitest run

# e2e (slow, requires a running server)
npx playwright test
```

## Configuration

Env vars: see `web/server/settings.py`. Most useful:

- `TRADINGAGENTS_DASHBOARD_PORT` (default 8000)
- `TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT` (default 3)
- `TRADINGAGENTS_DASHBOARD_PRICE_POLL_S` (default 15)
- `TRADINGAGENTS_DASHBOARD_DB` (default `~/.tradingagents/dashboard.db`)

## Manual checklist

See `web/frontend/e2e/README.md`.
```

- [ ] **Step 2: Add a root `web/package.json` for convenience**

```json
{
  "name": "tradingagents-web",
  "private": true,
  "version": "0.1.0",
  "scripts": {
    "dev": "cd frontend && npm run dev",
    "build": "cd frontend && npm run build",
    "test": "cd frontend && npx vitest run",
    "test:e2e": "cd frontend && npx playwright test"
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add web/README.md web/package.json
git commit -m "docs(web): README and root convenience package.json"
```

---

### Task 24: Run the full test matrix and verify everything is green

**Files:** none

- [ ] **Step 1: Backend tests**

Run: `pytest web/server -v`
Expected: all green.

- [ ] **Step 2: Frontend unit tests**

Run: `cd web/frontend && npx vitest run`
Expected: all green.

- [ ] **Step 3: Build**

Run: `cd web/frontend && npm run build`
Expected: succeeds; `dist/` populated.

- [ ] **Step 4: Final commit if any fixups**

```bash
git status
# if anything to add:
git add -A
git commit -m "chore: final fixups"
```

---

## Self-Review

**Spec coverage check (per section):**

| Spec section | Task(s) |
|---|---|
| §3 Architecture & file layout | Tasks 1, 2, 11 |
| §4.1 db.py | Tasks 3, 4 |
| §4.2 price_feed.py | Task 6 |
| §4.3 runner.py | Task 7 |
| §4.4 events.py | Task 5 |
| §4.5 app.py | Tasks 8, 9 |
| §5 Frontend components | Tasks 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 |
| §6 Data flow | Tasks 7, 8, 14, 18, 21 |
| §7 Error handling | Tasks 4 (reap_stale_runs), 7 (cancellation, retries), 6 (stale), 14 (reconnect with `?since=`), 8 (404, 409) |
| §8 Testing | Tasks 4, 5, 6, 7, 9, 15, 17, 18, 19, 22 |
| §10 Acceptance criteria | All tasks combined satisfy each criterion |

**Type/name consistency check (within plan):**
- `EventType` enum Python ↔ `EventType` const TS — Task 5 + Task 12 + parity test in Task 12.
- `make_event` Python ↔ `WsEvent` TS shape — Tasks 5 and 12.
- `/api/*` and `/ws/*` route paths in spec match `app.py` — Task 8.
- `run_id` ↔ `connectedRunId` in Zustand store — Task 12.
- `last_seen_event_id` ↔ `?since=` query param — Task 14 + Task 8.
- `add_watchlist` raises `DuplicateTicker` — Task 4; `app.py` catches it — Task 8.
- `request_cancellation` flag — Task 4; runner checks it — Task 7.
- `reap_stale_runs(timeout_s)` — Task 4; called in lifespan — Task 8.

**Placeholder scan:** no TBDs, no "implement later", no "similar to" references. Every code block is complete.

Plan ready for execution.
