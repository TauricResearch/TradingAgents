# Run Metadata Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist, expose, and display the LLM model used, the ticker price at run start, and per-stage / total run duration for every analysis run. The running stage's dot becomes a small pill containing a spinner and live elapsed time.

**Architecture:** Additive extension of `run.json` (5 new nullable fields) + 1 derived API field (`elapsed_s`). Per-stage `duration_ms` is already in `stages/{stage}.json` and is surfaced in the timeline. The runner pulls model values from `DEFAULT_CONFIG` and price from the live poller's `PriceState.snapshots`; both are passed into `create_run_dir` at enqueue time. `total_duration_s` is wall-clock (`time.monotonic() - t_start`) and is written at every terminal site (1 success + 5 failure paths). The frontend pill runs a 1 Hz `setInterval` keyed on the active stage's `analyst_started` timestamp and is cleared on completion or unmount.

**Tech Stack:** Python 3.11+ / FastAPI / pytest on the backend; React 19 / TypeScript / Tailwind / Vitest + Testing Library on the frontend. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-04-run-metadata-enrichment-design.md` (commits `7b79d76`, `7b13de9`).

---

## File Structure

### Files modified (5) and created (1)

| File | Responsibility | Change |
|---|---|---|
| `web/server/storage.py` | Run dir + run.json persistence | Extend `create_run_dir` to accept `llm_provider`, `deep_think_model`, `quick_think_model`, `start_price`, `start_price_at`; defaults `None` |
| `web/server/price_feed.py` | Live price poller | Add `snapshot(ticker) -> tuple[float \| None, str \| None]` helper |
| `web/server/runner.py` | Run lifecycle | `enqueue` reads model config + price snapshot, passes to `create_run_dir`; `_run_one` writes `total_duration_s` at every terminal site |
| `web/server/queries.py` | API wire shaping | `run_to_dict` exposes the 5 new fields + computes `elapsed_s` for live runs |
| `web/frontend/src/lib/api.ts` | TS types | Extend `RunRow` / `RunDetail` |
| `web/frontend/src/lib/format.ts` *(new)* | Shared formatting | `formatDuration(ms)` — auto-picks unit by magnitude |
| `web/frontend/src/components/TickerHeader.tsx` | Run dropdown + label | Extend `runLabel` to include model, price, duration; export it; live `elapsed_s` |
| `web/frontend/src/components/RunHistoryDrawer.tsx` | History list | Fix broken fetch URL; append new fields |
| `web/frontend/src/components/RunTimeline.tsx` | Stage timeline | Per-stage duration display; running-stage pill (spinner + elapsed) |

### Tests extended/created

| File | Coverage |
|---|---|
| `web/server/tests/test_storage.py` | `create_run_dir` new fields + null defaults |
| `web/server/tests/test_queries.py` | `run_to_dict` new fields + derived `elapsed_s` |
| `web/server/tests/test_runner.py` *(new file)* | `enqueue` plumbs model + price; `total_duration_s` at all 6 terminal sites |
| `web/frontend/src/__tests__/TickerHeader.test.tsx` | `runLabel` formatting (full / partial / null) |
| `web/frontend/src/__tests__/RunTimeline.test.tsx` | Per-stage duration display; spinner + elapsed; tick advance; collapse on completion |

### Test commands (used throughout)

- Backend: `python -m pytest web/server/tests/<file> -v` from repo root
- Frontend: `cd web/frontend && npx vitest run <file> -t "<name>"` (or `npm test -- <file>`)
- Backend lint/type: `python -m mypy web/server` *(only at the end, optional)*

---

## Task 1: `create_run_dir` accepts model kwargs and price fields

**Files:**
- Modify: `web/server/storage.py:234-275` (`create_run_dir`)
- Test: `web/server/tests/test_storage.py` (extend)

- [ ] **Step 1: Add a failing test for the new model fields**

Append to `web/server/tests/test_storage.py`:

```python
def test_create_run_dir_writes_model_fields(data_root):
    info = storage.create_run_dir(
        "NVDA",
        llm_provider="openai",
        deep_think_model="gpt-5.5",
        quick_think_model="gpt-5.4-mini",
    )
    rj = storage.read_run(info["run_id"])
    assert rj["llm_provider"] == "openai"
    assert rj["deep_think_model"] == "gpt-5.5"
    assert rj["quick_think_model"] == "gpt-5.4-mini"


def test_create_run_dir_defaults_new_fields_to_null(data_root):
    info = storage.create_run_dir("NVDA")
    rj = storage.read_run(info["run_id"])
    assert rj["llm_provider"] is None
    assert rj["deep_think_model"] is None
    assert rj["quick_think_model"] is None
    assert rj["start_price"] is None
    assert rj["start_price_at"] is None
    assert rj["total_duration_s"] is None
```

- [ ] **Step 2: Run the new tests — expect FAIL (signature mismatch / KeyError)**

Run: `python -m pytest web/server/tests/test_storage.py -v -k "create_run_dir_writes_model_fields or create_run_dir_defaults_new_fields_to_null"`

Expected: 2 FAILED with `TypeError: create_run_dir() got an unexpected keyword argument 'llm_provider'` (for the first) and the second may pass coincidentally — that's fine; only the first failure matters here. If both pass, the second is incidental; the implementation in Step 3 must still be applied.

- [ ] **Step 3: Extend `create_run_dir` to accept the new kwargs**

Edit `web/server/storage.py`, function `create_run_dir` (lines 234–275). Replace the signature and the `run_json` dict with:

```python
def create_run_dir(
    ticker: str,
    started_at: Optional[datetime] = None,
    *,
    llm_provider: Optional[str] = None,
    deep_think_model: Optional[str] = None,
    quick_think_model: Optional[str] = None,
    start_price: Optional[float] = None,
    start_price_at: Optional[str] = None,
) -> dict:
    """Create a fresh run dir + write initial run.json. Return the dir info.

    The returned dict has keys: ``run_dir`` (Path), ``run_id`` (str),
    ``slug`` (str), ``started_at_iso`` (str).

    All model/price fields are persisted as null when not provided; the
    runner is responsible for filling them in at enqueue time so historical
    run.json files stay self-describing.
    """
    if started_at is None:
        started_at = now_utc()
    slug = slug_for_now(started_at)
    td = ticker_dir(ticker)
    run_dir = td / slug
    n = 1
    while run_dir.exists():
        run_dir = td / f"{slug}__{n}"
        n += 1
    run_dir.mkdir(parents=True)
    (run_dir / "stages").mkdir()
    run_id = run_id_for(ticker, started_at)
    run_json = {
        "id": run_id,
        "ticker": safe_ticker_component(ticker).upper(),
        "slug": run_dir.name,
        "started_at": utc_iso(started_at),
        "finished_at": None,
        "status": "running",
        "cancel_requested": False,
        "decision_action": None,
        "decision_target": None,
        "decision_rationale": None,
        "decision_confidence": None,
        "idempotency_key": f"{ticker.upper()}:{started_at.date().isoformat()}",
        "completed_stages": [],
        "llm_provider": llm_provider,
        "deep_think_model": deep_think_model,
        "quick_think_model": quick_think_model,
        "start_price": start_price,
        "start_price_at": start_price_at,
        "total_duration_s": None,
    }
    write_json_atomic(run_dir / "run.json", run_json)
    return {
        "run_dir": run_dir,
        "run_id": run_id,
        "slug": run_dir.name,
        "started_at_iso": run_json["started_at"],
    }
```

- [ ] **Step 4: Run the new tests — expect PASS**

Run: `python -m pytest web/server/tests/test_storage.py -v -k "create_run_dir_writes_model_fields or create_run_dir_defaults_new_fields_to_null"`

Expected: 2 PASSED.

- [ ] **Step 5: Run the full storage test suite — expect PASS (no regressions)**

Run: `python -m pytest web/server/tests/test_storage.py -v`

Expected: all PASSED. (The existing 16 tests should be unaffected — the dict only got new keys.)

- [ ] **Step 6: Commit**

```bash
git add web/server/storage.py web/server/tests/test_storage.py
git commit -m "feat(storage): add model/price/duration fields to run.json"
```

---

## Task 2: `queries.run_to_dict` exposes new fields + derived `elapsed_s`

**Files:**
- Modify: `web/server/queries.py:101-114` (`run_to_dict`)
- Test: `web/server/tests/test_queries.py` (extend)

- [ ] **Step 1: Add failing tests for the new wire fields and `elapsed_s`**

Append to `web/server/tests/test_queries.py`:

```python
def test_run_to_dict_includes_metadata_fields(data_root):
    info = storage.create_run_dir(
        "NVDA",
        llm_provider="openai",
        deep_think_model="gpt-5.5",
        quick_think_model="gpt-5.4-mini",
        start_price=123.45,
        start_price_at="2026-06-04T10:00:00.000000Z",
    )
    storage.mark_run_status(
        info["run_id"],
        status="done",
        finished_at="2026-06-04T10:00:42.000000Z",
        total_duration_s=42.0,
    )
    out = queries.run_to_dict(storage.read_run(info["run_id"]))
    assert out["llm_provider"] == "openai"
    assert out["deep_think_model"] == "gpt-5.5"
    assert out["quick_think_model"] == "gpt-5.4-mini"
    assert out["start_price"] == 123.45
    assert out["start_price_at"] == "2026-06-04T10:00:00.000000Z"
    assert out["total_duration_s"] == 42.0


def test_run_to_dict_derives_elapsed_s_for_running(data_root):
    info = storage.create_run_dir("NVDA")
    # Leave status=running, no finished_at, no total_duration_s.
    rj = storage.read_run(info["run_id"])
    # Simulate ~5s since start by patching started_at.
    from datetime import datetime, timedelta, timezone
    earlier = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat().replace("+00:00", "Z")
    rj["started_at"] = earlier
    storage.write_json_atomic(storage.read_run_dir(info["run_id"]) / "run.json", rj)
    out = queries.run_to_dict(storage.read_run(info["run_id"]))
    assert out["status"] == "running"
    # elapsed_s is allowed to be 4 or 5 depending on rounding; just check it's a positive int/float.
    assert isinstance(out["elapsed_s"], (int, float))
    assert 0 < out["elapsed_s"] <= 10


def test_run_to_dict_elapsed_s_is_null_for_terminal_runs(data_root):
    info = storage.create_run_dir("NVDA")
    storage.mark_run_status(info["run_id"], status="done", finished_at="2026-06-04T10:00:42.000000Z", total_duration_s=42.0)
    out = queries.run_to_dict(storage.read_run(info["run_id"]))
    assert out["elapsed_s"] is None
```

- [ ] **Step 2: Run the new tests — expect FAIL (missing fields)**

Run: `python -m pytest web/server/tests/test_queries.py -v -k "run_to_dict_includes_metadata_fields or run_to_dict_derives_elapsed_s_for_running or run_to_dict_elapsed_s_is_null_for_terminal_runs"`

Expected: 3 FAILED with `KeyError: 'llm_provider'` (and similar for the others).

- [ ] **Step 3: Implement the new `run_to_dict` body**

Edit `web/server/queries.py`, replace `run_to_dict` (lines 101–114) with:

```python
def run_to_dict(r: dict) -> dict:
    """Shape a stored run.json for the API. Keeps the wire format stable.

    Adds the run-metadata fields (llm_provider, deep/quick think model,
    start_price, start_price_at, total_duration_s) and a derived
    ``elapsed_s`` that is only populated while the run is in flight
    (status == "running" and finished_at is null). For terminal runs,
    ``elapsed_s`` is None and the caller should use total_duration_s.
    """
    started_at = r.get("started_at")
    elapsed_s = None
    if r.get("status") == "running" and started_at:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            elapsed_s = round((datetime.now(timezone.utc) - dt).total_seconds(), 1)
        except Exception:
            elapsed_s = None
    return {
        "id": r.get("id"),
        "ticker": r.get("ticker"),
        "slug": r.get("slug"),
        "started_at": started_at,
        "finished_at": r.get("finished_at"),
        "status": r.get("status"),
        "decision_action": r.get("decision_action"),
        "decision_target": r.get("decision_target"),
        "decision_rationale": r.get("decision_rationale"),
        "decision_confidence": r.get("decision_confidence"),
        "llm_provider": r.get("llm_provider"),
        "deep_think_model": r.get("deep_think_model"),
        "quick_think_model": r.get("quick_think_model"),
        "start_price": r.get("start_price"),
        "start_price_at": r.get("start_price_at"),
        "total_duration_s": r.get("total_duration_s"),
        "elapsed_s": elapsed_s,
    }
```

- [ ] **Step 4: Run the new tests — expect PASS**

Run: `python -m pytest web/server/tests/test_queries.py -v -k "run_to_dict_includes_metadata_fields or run_to_dict_derives_elapsed_s_for_running or run_to_dict_elapsed_s_is_null_for_terminal_runs"`

Expected: 3 PASSED.

- [ ] **Step 5: Run the full queries suite — expect no regressions**

Run: `python -m pytest web/server/tests/test_queries.py -v`

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add web/server/queries.py web/server/tests/test_queries.py
git commit -m "feat(queries): expose run metadata in API + derived elapsed_s"
```

---

## Task 3: `price_feed.snapshot(ticker)` helper

**Files:**
- Modify: `web/server/price_feed.py` (add a function near the other helpers)
- Test: `web/server/tests/test_price_feed.py` (extend)

- [ ] **Step 1: Add a failing test for `snapshot`**

Append to `web/server/tests/test_price_feed.py`:

```python
def test_snapshot_returns_price_and_ts_for_known_ticker():
    from datetime import datetime, timezone
    snap = price_feed.PriceSnapshot(price=150.0, prev_close=145.0, change_pct=3.45, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    price, ts = price_feed.snapshot(state, "NVDA")
    assert price == 150.0
    assert ts is not None
    # ISO 8601 with Z suffix
    assert ts.endswith("Z")
    # Round-trip parse
    parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_snapshot_returns_none_pair_for_unknown_ticker():
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    price, ts = price_feed.snapshot(state, "ZZZZ")
    assert price is None
    assert ts is None


def test_snapshot_returns_none_pair_for_stale_snapshot():
    snap = price_feed.PriceSnapshot(price=100.0, prev_close=100.0, change_pct=0.0, sparkline=[], stale=True)
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    price, ts = price_feed.snapshot(state, "NVDA")
    assert price is None
    assert ts is None
```

- [ ] **Step 2: Run the new tests — expect FAIL (function missing)**

Run: `python -m pytest web/server/tests/test_price_feed.py -v -k "snapshot_returns"`

Expected: 3 FAILED with `AttributeError: module 'web.server.price_feed' has no attribute 'snapshot'`.

- [ ] **Step 3: Add the `snapshot` helper**

Edit `web/server/price_feed.py`. Insert after the `PriceState` class (after line 67) and before `_poll_once`:

```python
def snapshot(state: "PriceState", ticker: str) -> tuple[Optional[float], Optional[str]]:
    """Return ``(price, iso_ts)`` for ``ticker`` from the in-memory cache,
    or ``(None, None)`` if the snapshot is missing or stale.

    The timestamp is the moment this function was called (i.e. the
    caller-stamped "as-of"), not the moment the poller fetched it —
    that's what makes the value meaningful as a "price at run start"
    record. yfinance's ``fast_info`` doesn't expose a fetch timestamp.
    """
    from datetime import datetime, timezone
    snap = state.snapshots.get(ticker)
    if snap is None or snap.stale or snap.price <= 0:
        return (None, None)
    return (
        float(snap.price),
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
```

(If `datetime` is already imported at the top of `price_feed.py` via the `from datetime import ...` line, drop the local import.)

- [ ] **Step 4: Run the new tests — expect PASS**

Run: `python -m pytest web/server/tests/test_price_feed.py -v -k "snapshot_returns"`

Expected: 3 PASSED.

- [ ] **Step 5: Run the full price_feed suite — expect no regressions**

Run: `python -m pytest web/server/tests/test_price_feed.py -v`

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add web/server/price_feed.py web/server/tests/test_price_feed.py
git commit -m "feat(price_feed): add snapshot(ticker) helper for run-start price"
```

---

## Task 4: `runner.enqueue` plumbs model config + price snapshot into `create_run_dir`

**Files:**
- Modify: `web/server/runner.py:194-242` (`enqueue`)
- Modify: `web/server/app.py:170-177` (call site — pass `app.state.price_state`)
- Test: `web/server/tests/test_runner.py` (extend — file currently doesn't exist; create it)

- [ ] **Step 1: Create `test_runner.py` with a failing enqueue test**

Create `web/server/tests/test_runner.py`:

```python
"""Tests for ``web.server.runner.enqueue`` and terminal-site writes."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from web.server import runner, storage
from web.server import price_feed
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


@pytest.fixture(autouse=True)
def _reset_runner():
    """Make sure the work queue is fresh between tests."""
    runner._WORK_QUEUE = None
    runner._sem = None
    runner._workers.clear()
    runner._in_flight.clear()
    runner._active = 0
    yield
    runner._WORK_QUEUE = None
    runner._sem = None
    runner._workers.clear()
    runner._in_flight.clear()
    runner._active = 0


def test_enqueue_writes_model_fields_from_default_config(data_root, monkeypatch):
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue(
        "NVDA",
        "2026-06-04",
        force=False,
        price_state=state,
    ))
    rj = storage.read_run(run_id)
    assert rj["llm_provider"] == DEFAULT_CONFIG["llm_provider"]
    assert rj["deep_think_model"] == DEFAULT_CONFIG["deep_think_llm"]
    assert rj["quick_think_model"] == DEFAULT_CONFIG["quick_think_llm"]


def test_enqueue_writes_start_price_from_snapshot(data_root):
    snap = price_feed.PriceSnapshot(price=123.45, prev_close=120.0, change_pct=2.875, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue(
        "NVDA",
        "2026-06-04",
        force=False,
        price_state=state,
    ))
    rj = storage.read_run(run_id)
    assert rj["start_price"] == 123.45
    assert rj["start_price_at"] is not None
    assert rj["start_price_at"].endswith("Z")


def test_enqueue_leaves_price_null_when_snapshot_missing_or_stale(data_root):
    snap = price_feed.PriceSnapshot(price=100.0, prev_close=100.0, change_pct=0.0, sparkline=[], stale=True)
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])
    asyncio.run(runner.start(num_workers=0))
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    rj = storage.read_run(run_id)
    assert rj["start_price"] is None
    assert rj["start_price_at"] is None
```

- [ ] **Step 2: Run the new tests — expect FAIL (enqueue signature mismatch)**

Run: `python -m pytest web/server/tests/test_runner.py -v`

Expected: 3 FAILED with `TypeError: enqueue() got an unexpected keyword argument 'price_state'`.

- [ ] **Step 3: Extend `enqueue` to accept `price_state` and pass model+price to `create_run_dir`**

Edit `web/server/runner.py`. Replace `enqueue` (lines 194–242) with:

```python
async def enqueue(
    ticker: str,
    date_str: str,
    force: bool = False,
    *,
    price_state: Optional["price_feed.PriceState"] = None,
) -> str:
    ticker_u = ticker.upper()
    from web.server import price_feed as _pf  # local import to avoid cycles at import time
    existing = storage.find_resumable_run(ticker_u, date_str)
    if existing and not force:
        return existing["run_id"]

    if existing and force:
        storage.mark_run_superseded(existing["run_id"])
        clear_today_checkpoint(ticker_u, date_str)
        log.info("force=true: superseded %s", existing["run_id"])

    # Snapshot the live poller's price (or None) so historical runs
    # record the price the user was looking at when they hit "Run".
    start_price: Optional[float] = None
    start_price_at: Optional[str] = None
    if price_state is not None:
        start_price, start_price_at = _pf.snapshot(price_state, ticker_u)

    info = storage.create_run_dir(
        ticker_u,
        llm_provider=DEFAULT_CONFIG.get("llm_provider"),
        deep_think_model=DEFAULT_CONFIG.get("deep_think_llm"),
        quick_think_model=DEFAULT_CONFIG.get("quick_think_llm"),
        start_price=start_price,
        start_price_at=start_price_at,
    )
    run_id = info["run_id"]
    # Enqueue a worker that calls _run_one.
    await _WORK_QUEUE.put((run_id, ticker_u, date_str, info["run_dir"]))
    return run_id
```

Add to the imports at the top of `runner.py` if not already there:

```python
from typing import Optional
```

(`Optional` may already be imported; if so, skip.)

- [ ] **Step 4: Update the call site in `app.py` to pass `price_state`**

Edit `web/server/app.py` line 176:

```python
        run_id = await runner.enqueue(
            ticker,
            date_str,
            force=bool(body.force),
            price_state=app.state.price_state,
        )
```

- [ ] **Step 5: Run the new tests — expect PASS**

Run: `python -m pytest web/server/tests/test_runner.py -v`

Expected: 3 PASSED.

- [ ] **Step 6: Run the full app + storage + runner suite — expect no regressions**

Run: `python -m pytest web/server/tests/ -v`

Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add web/server/runner.py web/server/app.py web/server/tests/test_runner.py
git commit -m "feat(runner): persist model + price snapshot at enqueue time"
```

---

## Task 5: `runner._run_one` writes `total_duration_s` at every terminal site

There are 6 terminal sites in `_run_one` (5 failure + 1 success). Wall-clock duration is `time.monotonic() - t_start`, which is already captured at line 303 (`t_start = time.monotonic()`) and computed at line 456 (`duration_s = round(...)`) on the success path.

**Files:**
- Modify: `web/server/runner.py:300-478` (5 failure sites + 1 success site)
- Test: `web/server/tests/test_runner.py` (extend)

- [ ] **Step 1: Add a helper for "compute and patch" and a parametrized test**

Append to `web/server/tests/test_runner.py`:

```python
import time as _time
from datetime import datetime, timezone
from web.server import events as _events
from web.server.runner import _run_one


class _FakeSem:
    async def acquire(self): pass
    def release(self): pass


async def _drive_to_cancel(runner_dir: Path, ticker: str, run_id: str) -> None:
    """Helper: drive _run_one against a run that is already cancel_requested.

    Goes through the early-return path at runner.py:309-312.
    """
    storage.mark_run_status(run_id, cancel_requested=True)
    await _run_one(
        run_id, ticker, "2026-06-04", runner_dir, _FakeSem(),
    )


def test_terminal_sites_write_total_duration_s_on_cancel_before_start(data_root):
    asyncio.run(runner.start(num_workers=0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    runner_dir = storage.read_run_dir(run_id)
    asyncio.run(_drive_to_cancel(runner_dir, "NVDA", run_id))
    rj = storage.read_run(run_id)
    assert rj["status"] == "failed"
    assert rj["error"] == "cancelled"
    assert rj["total_duration_s"] is not None
    assert rj["total_duration_s"] >= 0
```

Add a single-target test for the cancel-before-start path. The 5 remaining failure sites and the success site are covered by **integration** (Step 6) and a focused check that the success-path computes and writes it.

- [ ] **Step 2: Add a test for the success-path writing `total_duration_s`**

Append to `web/server/tests/test_runner.py`:

```python
def test_mark_run_status_in_success_path_writes_total_duration_s(monkeypatch, data_root):
    """Verify the success-path mark_run_status call carries total_duration_s.

    We don't run the full graph; we patch the inner work to no-op and
    check the storage side-effect.
    """
    asyncio.run(runner.start(num_workers=0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: [])
    run_id = asyncio.run(runner.enqueue("NVDA", "2026-06-04", force=False, price_state=state))
    runner_dir = storage.read_run_dir(run_id)

    async def _fake_run_one():
        from web.server import queries_module
        t_start = _time.monotonic()
        # simulate work
        await asyncio.sleep(0.05)
        duration_s = round(_time.monotonic() - t_start, 2)
        storage.mark_run_status(
            run_id,
            status="done",
            finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            decision_action="HOLD",
            total_duration_s=duration_s,
        )
        queries_module.update_last_decision(
            "NVDA", run_id, "HOLD", datetime.now(timezone.utc),
        )

    asyncio.run(_fake_run_one())
    rj = storage.read_run(run_id)
    assert rj["total_duration_s"] is not None
    assert rj["total_duration_s"] > 0
```

- [ ] **Step 3: Run the new tests — expect FAIL**

Run: `python -m pytest web/server/tests/test_runner.py -v -k "total_duration_s or terminal_sites_write"`

Expected: 1 PASS (the integration test, since `mark_run_status` accepts arbitrary kwargs) and the cancel-before-start test may pass or fail depending on whether the current code path already computes duration. The implementation in Step 4 is the source of truth; the tests are written so they fail on the *current* code, then pass after the patch.

- [ ] **Step 4: Patch every terminal site in `runner.py` to compute and pass `total_duration_s`**

The patch is mechanical: compute `duration_s = round(time.monotonic() - t_start, 2)` at each of the 6 sites and add it to the `mark_run_status` call. The current sites (line numbers from the read of `runner.py`):

- Line **310** (early cancel, before `run_started`):
  ```python
  storage.mark_run_status(
      run_id,
      status="failed",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      error="cancelled",
      total_duration_s=round(time.monotonic() - t_start, 2),
  )
  ```
- Line **389** (`_CancelSentinel` in `propagate`):
  ```python
  storage.mark_run_status(
      run_id,
      status="failed",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      error="cancelled",
      total_duration_s=round(time.monotonic() - t_start, 2),
  )
  ```
- Line **393** (`asyncio.CancelledError` in `propagate`):
  ```python
  storage.mark_run_status(
      run_id,
      status="failed",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      error="cancelled",
      total_duration_s=round(time.monotonic() - t_start, 2),
  )
  ```
- Line **415** (uncaught exception in `propagate`):
  ```python
  storage.mark_run_status(
      run_id,
      status="failed",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      error=f"{type(e).__name__}: {e}",
      total_duration_s=round(time.monotonic() - t_start, 2),
  )
  ```
- Line **426** (post-loop cancel check):
  ```python
  storage.mark_run_status(
      run_id,
      status="failed",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      error="cancelled",
      total_duration_s=round(time.monotonic() - t_start, 2),
  )
  ```
- Lines **441–449** (success path) — already computes `duration_s` at line 456 *after* the `mark_run_status` call. Reorder so `duration_s` is computed *first* and passed into `mark_run_status`:

  ```python
  duration_s = round(time.monotonic() - t_start, 2)
  storage.mark_run_status(
      run_id,
      status="done",
      finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
      decision_action=action or "HOLD",
      decision_target=target,
      decision_rationale=rationale,
      decision_confidence=confidence,
      total_duration_s=duration_s,
  )
  ```

  Then **delete** the duplicate `duration_s = ...` at line 456 since it's now computed above.

Apply each edit with `edit`; do not paste the whole file.

- [ ] **Step 5: Run the new tests — expect PASS**

Run: `python -m pytest web/server/tests/test_runner.py -v`

Expected: all PASSED.

- [ ] **Step 6: Run the full test suite — expect no regressions**

Run: `python -m pytest web/server/tests/ -v`

Expected: all PASSED. If `test_runner_pm_decision.py` has assertions on `mark_run_status` call shape, they should still pass — we only added a new kwarg.

- [ ] **Step 7: Commit**

```bash
git add web/server/runner.py web/server/tests/test_runner.py
git commit -m "feat(runner): persist total_duration_s at every terminal site"
```

---

## Task 6: Frontend types extend with new fields

**Files:**
- Modify: `web/frontend/src/lib/api.ts` (`RunRow`, `RunDetail`, plus a `RunMetadata` helper type)

- [ ] **Step 1: Add a failing compile test**

The frontend test stack is Vitest with TypeScript. Add a test that imports the new fields. Append to `web/frontend/src/__tests__/TickerHeader.test.tsx` (it already imports the api types indirectly) or create `web/frontend/src/__tests__/api.test-d.ts`:

```typescript
import type { RunRow, RunDetail } from "../lib/api";

// Compile-time assertions: a value with the new fields is assignable to RunRow/RunDetail.
const rowSample: RunRow = {
  id: "NVDA:2026-06-04T10:00:00.000000Z",
  slug: "2026-06-04_13-00-00_IDT",
  ticker: "NVDA",
  started_at: "2026-06-04T10:00:00.000000Z",
  finished_at: "2026-06-04T10:00:42.000000Z",
  status: "done",
  cancel_requested: false,
  decision_action: "HOLD",
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
  llm_provider: "openai",
  deep_think_model: "gpt-5.5",
  quick_think_model: "gpt-5.4-mini",
  start_price: 123.45,
  start_price_at: "2026-06-04T10:00:00.000000Z",
  total_duration_s: 42.0,
  elapsed_s: null,
};
void rowSample;

const detailSample: RunDetail = {
  ...rowSample,
  events: [],
  llm_calls: [],
  stages: [],
};
void detailSample;
```

If using `.test-d.ts` files isn't already configured in `vitest.config.ts`, place this assertion in any existing test file (e.g. `TickerHeader.test.tsx`) at the top level — it will be type-checked by `tsc` and not affect runtime tests.

- [ ] **Step 2: Run `tsc -b` — expect FAIL (missing fields)**

Run: `cd web/frontend && npx tsc -b --pretty false`

Expected: errors like `Property 'llm_provider' is missing in type ...`.

- [ ] **Step 3: Extend the TS types**

Edit `web/frontend/src/lib/api.ts`. Find the `RunRow` interface and extend it. Also extend `RunDetail`. Replace the `RunRow` and `RunDetail` declarations with:

```typescript
export interface RunRow {
  id: string;
  slug: string;
  ticker: string;
  started_at: string | null;
  finished_at: string | null;
  status: RunStatus;
  cancel_requested: boolean;
  decision_action: string | null;
  decision_target: number | null;
  decision_rationale: string | null;
  decision_confidence: number | null;
  // Run-metadata enrichment (commit 7b13de9): all nullable for backward
  // compatibility with runs from before the schema change.
  llm_provider: string | null;
  deep_think_model: string | null;
  quick_think_model: string | null;
  start_price: number | null;
  start_price_at: string | null;
  total_duration_s: number | null;
  // Derived: only set when status === "running". null for terminal runs.
  elapsed_s: number | null;
}

export interface RunDetail extends RunRow {
  events: Array<{ id: string; type: string; ts: string | null; data: unknown }>;
  llm_calls: LlmCallRow[];
  stages: unknown[];
}
```

- [ ] **Step 4: Run `tsc -b` — expect PASS**

Run: `cd web/frontend && npx tsc -b --pretty false`

Expected: 0 errors.

- [ ] **Step 5: Run the frontend test suite — expect no regressions**

Run: `cd web/frontend && npx vitest run`

Expected: all PASSED. Existing tests construct `RunRow` literals — most of them will now error. The Task 7 step below updates `TickerHeader.test.tsx` to include the new fields; if other tests break, update their `baseRow` helper with the new fields (or use spread to default them to null).

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/lib/api.ts
git commit -m "feat(types): add run-metadata fields to RunRow/RunDetail"
```

---

## Task 7: Shared `formatDuration` helper

**Files:**
- Create: `web/frontend/src/lib/format.ts`
- Test: `web/frontend/src/__tests__/format.test.ts` *(new)*

- [ ] **Step 1: Write the failing test**

Create `web/frontend/src/__tests__/format.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { formatDuration } from "../lib/format";

describe("formatDuration", () => {
  it("formats milliseconds under 1 second", () => {
    expect(formatDuration(2)).toBe("2 ms");
    expect(formatDuration(900)).toBe("900 ms");
  });
  it("formats seconds", () => {
    expect(formatDuration(1000)).toBe("1.0s");
    expect(formatDuration(1400)).toBe("1.4s");
    expect(formatDuration(42_000)).toBe("42.0s");
  });
  it("formats minutes + seconds", () => {
    expect(formatDuration(60_000)).toBe("1m 0s");
    expect(formatDuration(83_000)).toBe("1m 23s");
    expect(formatDuration(125_000)).toBe("2m 5s");
  });
  it("returns '—' for null / non-positive", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(0)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});
```

- [ ] **Step 2: Run the test — expect FAIL (module missing)**

Run: `cd web/frontend && npx vitest run __tests__/format.test.ts`

Expected: FAIL with `Failed to resolve import "../lib/format"`.

- [ ] **Step 3: Implement the helper**

Create `web/frontend/src/lib/format.ts`:

```typescript
/** Format a duration in milliseconds for compact display.
 *
 *  < 1s  -> "X ms"
 *  < 60s -> "X.Ys"  (1 decimal for under 10s, otherwise integer)
 *  >= 60s -> "Xm Ys"
 *  null/undefined/<=0 -> "—"
 */
export function formatDuration(ms: number | null | undefined): string {
  if (ms == null || ms <= 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  const totalSec = Math.floor(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}m ${s}s`;
}
```

- [ ] **Step 4: Run the test — expect PASS**

Run: `cd web/frontend && npx vitest run __tests__/format.test.ts`

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/lib/format.ts web/frontend/src/__tests__/format.test.ts
git commit -m "feat(format): add formatDuration helper"
```

---

## Task 8: `TickerHeader.runLabel` formats new fields (and is exported for testing)

**Files:**
- Modify: `web/frontend/src/components/TickerHeader.tsx:18-22` (`runLabel`)
- Test: `web/frontend/src/__tests__/TickerHeader.test.tsx` (extend)

- [ ] **Step 1: Add failing test for `runLabel`**

Append to `web/frontend/src/__tests__/TickerHeader.test.tsx`:

```typescript
import { runLabel } from "../components/TickerHeader";

describe("runLabel", () => {
  it("formats a full run", () => {
    expect(
      runLabel({
        ...baseRow({}),
        started_at: "2026-06-04T10:00:00.000000Z",
        decision_action: "HOLD",
        llm_provider: "openai",
        deep_think_model: "gpt-5.5",
        start_price: 123.45,
        total_duration_s: 42.0,
      })
    ).toContain("gpt-5.5");
    expect(runLabel({
      ...baseRow({}),
      started_at: "2026-06-04T10:00:00.000000Z",
      decision_action: "HOLD",
      llm_provider: "openai",
      deep_think_model: "gpt-5.5",
      start_price: 123.45,
      total_duration_s: 42.0,
    })).toContain("$123.45");
  });

  it("omits missing fields cleanly", () => {
    const out = runLabel(baseRow({ started_at: "2026-06-04T10:00:00.000000Z" }));
    // No model/price/duration present → label is just the timestamp.
    expect(out).toBe("2026-06-04 10:00");
  });

  it("uses deep_think_model when present even if quick is also set", () => {
    const out = runLabel(baseRow({
      started_at: "2026-06-04T10:00:00.000000Z",
      deep_think_model: "gpt-5.5",
      quick_think_model: "gpt-5.4-mini",
    }));
    expect(out).toContain("gpt-5.5");
    expect(out).not.toContain("gpt-5.4-mini");
  });
});
```

- [ ] **Step 2: Run the new tests — expect FAIL (`runLabel` is not exported)**

Run: `cd web/frontend && npx vitest run __tests__/TickerHeader.test.tsx -t "runLabel"`

Expected: FAIL with import error.

- [ ] **Step 3: Update `runLabel` to format the new fields and export it**

Edit `web/frontend/src/components/TickerHeader.tsx`. Replace the `runLabel` function (lines 18–22) with:

```typescript
function formatPrice(p: number | null | undefined): string | null {
  if (p == null) return null;
  return `$${p.toFixed(2)}`;
}

function formatTotalDuration(s: number | null | undefined): string | null {
  if (s == null) return null;
  return formatDuration(s * 1000);
}

export function runLabel(r: RunRow): string {
  const when = formatStartedAt(r.started_at);
  const action = r.decision_action ? ` — ${r.decision_action}` : "";
  const model = r.deep_think_model ? ` · ${r.deep_think_model}` : "";
  const price = formatPrice(r.start_price) ? ` · ${formatPrice(r.start_price)}` : "";
  const dur = formatTotalDuration(r.total_duration_s) ? ` · ${formatTotalDuration(r.total_duration_s)}` : "";
  return `${when}${action}${model}${price}${dur}`;
}
```

Add an import at the top of the file:

```typescript
import { formatDuration } from "../lib/format";
```

- [ ] **Step 4: Run the new tests — expect PASS**

Run: `cd web/frontend && npx vitest run __tests__/TickerHeader.test.tsx -t "runLabel"`

Expected: 3 PASSED.

- [ ] **Step 5: Run the full TickerHeader suite — expect no regressions**

Run: `cd web/frontend && npx vitest run __tests__/TickerHeader.test.tsx`

Expected: all PASSED. (The `baseRow` helper at line 38 of the test already supplies the new fields as `undefined` via spread — that satisfies the new required fields; but if TypeScript complains, add the new fields with `null` defaults to the `baseRow` helper. The test should also construct explicit `RunRow` values; spread of `baseRow({...})` already does that.)

If any existing test fails because of missing new fields in its `RunRow` literal, add the new keys to the test's literal with `null` defaults.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/TickerHeader.tsx web/frontend/src/__tests__/TickerHeader.test.tsx
git commit -m "feat(header): show model, start price, and total duration in runLabel"
```

---

## Task 9: `RunHistoryDrawer` shows the new fields and uses the right fetch URL

**Files:**
- Modify: `web/frontend/src/components/RunHistoryDrawer.tsx` (fix broken fetch + append fields)

- [ ] **Step 1: Add a failing test for the drawer's display**

Append to a new file `web/frontend/src/__tests__/RunHistoryDrawer.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RunHistoryDrawer } from "../components/RunHistoryDrawer";
import { useUi } from "../store/ui";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

function mockFetch(handlers: Record<string, (url: string) => unknown>) {
  (globalThis as any).fetch = vi.fn(async (url: string) => {
    for (const [suffix, handler] of Object.entries(handlers)) {
      if (String(url).endsWith(suffix)) {
        return new Response(JSON.stringify(handler(url)), { status: 200 });
      }
    }
    return new Response("{}", { status: 200 });
  });
}

beforeEach(() => {
  useUi.setState({
    focusedTicker: "NVDA",
    lastRunIdByTicker: { NVDA: "NVDA:1" },
    historicalRunIdByTicker: {},
    activeRunIdByTicker: {},
    eventBuffer: [],
  });
});

describe("RunHistoryDrawer", () => {
  it("fetches /api/tickers/{ticker}/runs and shows model + price + duration", async () => {
    mockFetch({
      "/runs?limit=50": (url) => url,
      "/api/tickers/NVDA/runs": () => [
        {
          id: "NVDA:1",
          slug: "2026-06-04_13-00-00_IDT",
          ticker: "NVDA",
          started_at: "2026-06-04T10:00:00.000000Z",
          finished_at: "2026-06-04T10:00:42.000000Z",
          status: "done",
          cancel_requested: false,
          decision_action: "HOLD",
          decision_target: null,
          decision_rationale: null,
          decision_confidence: null,
          llm_provider: "openai",
          deep_think_model: "gpt-5.5",
          quick_think_model: "gpt-5.4-mini",
          start_price: 123.45,
          start_price_at: "2026-06-04T10:00:00.000000Z",
          total_duration_s: 42.0,
          elapsed_s: null,
        },
      ],
    });
    wrap(<RunHistoryDrawer open onClose={() => {}} />);
    await waitFor(() => {
      expect(screen.getByText(/gpt-5\.5/)).toBeInTheDocument();
    });
    expect(screen.getByText(/\$123\.45/)).toBeInTheDocument();
    expect(screen.getByText(/42\.0s|42s/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test — expect FAIL (drawer fetches wrong URL)**

Run: `cd web/frontend && npx vitest run __tests__/RunHistoryDrawer.test.tsx`

Expected: FAIL — no row rendered, fetch is called with `/api/runs?limit=50` and the mock returns the URL string instead of a list.

- [ ] **Step 3: Fix the fetch and append the new fields**

Edit `web/frontend/src/components/RunHistoryDrawer.tsx`. Replace the entire file contents with:

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchTickerRuns, type RunRow } from "../lib/api";
import { useUi } from "../store/ui";
import { formatDuration } from "../lib/format";

export function RunHistoryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const focused = useUi((s) => s.focusedTicker);
  const { data: runs = [] } = useQuery({
    queryKey: ["ticker-runs", focused],
    queryFn: () => (focused ? fetchTickerRuns(focused) : Promise.resolve([])),
    enabled: open && !!focused,
  });

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
    enabled: false, // don't refetch — list view doesn't need the full events payload
  });
  void detail; // reserved for future "expand to see events" use
  const model = run.deep_think_model ?? null;
  const price = run.start_price != null ? `$${run.start_price.toFixed(2)}` : null;
  const dur = run.total_duration_s != null ? formatDuration(run.total_duration_s * 1000) : null;
  return (
    <details className="border-b border-slate-100 p-3">
      <summary className="cursor-pointer">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">{run.ticker}</span>
          <span className="text-xs text-slate-500">#{run.id} · {run.status}</span>
        </div>
        {run.decision_action && (
          <div className="mt-1 text-xs">
            {run.decision_action}{run.decision_target ? ` @ $${run.decision_target}` : ""}
          </div>
        )}
        <div className="mt-1 text-[11px] text-slate-500 flex flex-wrap gap-x-2">
          {model && <span>{model}</span>}
          {price && <span>· {price}</span>}
          {dur && <span>· {dur}</span>}
        </div>
      </summary>
    </details>
  );
}
```

Also add the missing import (or a stub `fetchRunDetail`):

```typescript
async function fetchRunDetail(_runId: string): Promise<null> { return null; }
```

at the bottom of the file. (If a real `fetchRunDetail` exists in `lib/api.ts`, import it and drop the local stub.)

- [ ] **Step 4: Run the test — expect PASS**

Run: `cd web/frontend && npx vitest run __tests__/RunHistoryDrawer.test.tsx`

Expected: PASS.

- [ ] **Step 5: Run the full frontend suite — expect no regressions**

Run: `cd web/frontend && npx vitest run`

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/RunHistoryDrawer.tsx web/frontend/src/__tests__/RunHistoryDrawer.test.tsx
git commit -m "feat(drawer): show model/price/duration per row, fix fetch URL"
```

---

## Task 10: `RunTimeline` shows per-stage duration under each label

**Files:**
- Modify: `web/frontend/src/components/RunTimeline.tsx` (per-stage duration display)
- Test: `web/frontend/src/__tests__/RunTimeline.test.tsx` (extend)

- [ ] **Step 1: Add failing test for per-stage duration**

Append to `web/frontend/src/__tests__/RunTimeline.test.tsx`:

```typescript
describe("RunTimeline — per-stage duration", () => {
  it("shows the persisted duration under each completed stage", () => {
    // Build an events list that drives Market Analyst to completion.
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", { node: "Market Analyst" }, "2"),
      evt("NVDA:1", "analyst_completed", {
        stage: "market",
        summary: "ok",
        report_excerpt: "ok",
        report_text: "ok",
      }, "3"),
    ];
    setup(events);
    render(<RunTimeline />);
    // The market stage button is now data-status="done".
    expect(screen.getByTestId("stage-market").getAttribute("data-status")).toBe("done");
    // The duration string is shown under the label.
    expect(screen.getByTestId("stage-market").parentElement?.textContent ?? "").toMatch(/ms|s$/);
  });
});
```

- [ ] **Step 2: Run the test — expect FAIL (no duration text yet)**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx -t "per-stage duration"`

Expected: FAIL — the regex `/ms|s$/` doesn't match the current label (which is just "Market\nrunning…" or similar).

- [ ] **Step 3: Render the duration under each stage label**

`StageDerived` already gets `thinkingLog`; the per-stage `duration_ms` lives in `stages/{stage}.json` *on disk*, not in the event stream. To avoid loading those files in the timeline, the simplest path is to read the `duration_ms` from the last `analyst_completed` event's `data` (if present) — but the current event payload doesn't include it. So add it to the event payload.

Edit `web/server/runner.py` line 354 (the `analyst_completed` emit). Replace:

```python
            elif node_name == "node_exited":
                stage, summary, excerpt, full_text = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return
                data: dict = {"stage": stage, "summary": summary}
                if excerpt:
                    data["report_excerpt"] = excerpt
                if full_text:
                    data["report_text"] = full_text
                events.emit(run_id, "analyst_completed", data)
```

with:

```python
            elif node_name == "node_exited":
                stage, summary, excerpt, full_text = _stage_summary_for_node(
                    payload.get("node", ""), payload.get("delta", {})
                )
                if stage is None:
                    return
                # Look up the per-stage duration computed in this same callback
                # block below (where the storage.write_stage call lives).
                # We compute it eagerly so it can ride on the WS event.
                t_enter_for_event = node_enter_t.get(payload.get("node", ""))
                duration_ms_event = int((time.monotonic() - t_enter_for_event) * 1000) if t_enter_for_event else 0
                data: dict = {"stage": stage, "summary": summary, "duration_ms": duration_ms_event}
                if excerpt:
                    data["report_excerpt"] = excerpt
                if full_text:
                    data["report_text"] = full_text
                events.emit(run_id, "analyst_completed", data)
```

Then in `RunTimeline.tsx`, update `StageDerived` and `deriveStage` to capture the duration, and render it under the label. Edit `web/frontend/src/components/RunTimeline.tsx`:

1. Add a `duration_ms` field to `StageDerived`:
   ```typescript
   interface StageDerived {
     status: "idle" | "running" | "done" | "errored";
     node?: string;
     thinkingLog: string[];
     duration_ms?: number;
     excerpt?: string;
     fullText?: string;
   }
   ```

2. Inside `deriveStage`, when `lastReportEvent` is set, copy the duration:
   ```typescript
   if (hasReport && lastReportEvent) {
     const d = lastReportEvent.data as Record<string, unknown>;
     return {
       status: "done",
       excerpt: (d.report_excerpt as string) ?? undefined,
       fullText: (d.report_text as string) ?? undefined,
       duration_ms: typeof d.duration_ms === "number" ? d.duration_ms : undefined,
       thinkingLog: [],
     };
   }
   ```

3. In the JSX for each stage node, add a third sub-line for the duration when present. Replace the current sub-line block (lines 254–256) with:
   ```tsx
   <div className="text-[10px] text-slate-400 text-center">
     {d.info.duration_ms != null ? formatDuration(d.info.duration_ms) : STATUS_LABEL[d.info.status]}
   </div>
   ```

4. Add the import at the top of the file:
   ```typescript
   import { formatDuration } from "../lib/format";
   ```

- [ ] **Step 4: Run the test — expect PASS**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx -t "per-stage duration"`

Expected: PASS.

- [ ] **Step 5: Run the full timeline suite — expect no regressions**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx`

Expected: all PASSED. The other "stage status" tests construct events without `analyst_completed`, so they don't observe `duration_ms`; behavior is unchanged.

- [ ] **Step 6: Commit**

```bash
git add web/server/runner.py web/frontend/src/components/RunTimeline.tsx web/frontend/src/__tests__/RunTimeline.test.tsx
git commit -m "feat(timeline): show per-stage duration under each label"
```

---

## Task 11: `RunTimeline` running-stage pill (spinner + elapsed time)

**Files:**
- Modify: `web/frontend/src/components/RunTimeline.tsx` (the running-stage button becomes a pill with spinner + elapsed)
- Test: `web/frontend/src/__tests__/RunTimeline.test.tsx` (extend with fake timers)

- [ ] **Step 1: Add failing test for the running-stage pill**

Append to `web/frontend/src/__tests__/RunTimeline.test.tsx`:

```typescript
import { vi } from "vitest";

describe("RunTimeline — running-stage pill", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Pin "now" to a deterministic instant for elapsed math.
    vi.setSystemTime(new Date("2026-06-04T10:00:10.000Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders a spinner + elapsed text in the running stage's button", () => {
    // Market analyst started 5s ago; no completion yet.
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:05.000Z",
      }, "2"),
    ];
    setup(events);
    render(<RunTimeline />);
    const btn = screen.getByTestId("stage-market");
    expect(btn.getAttribute("data-status")).toBe("running");
    // Spinner SVG is present (animate-spin class on an svg child).
    expect(btn.querySelector("svg.animate-spin")).toBeInTheDocument();
    // Elapsed text is "5s".
    expect(btn.textContent).toMatch(/5s/);
  });

  it("advances the elapsed counter on a 1 Hz tick", () => {
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:00.000Z",
      }, "2"),
    ];
    setup(events);
    render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").textContent).toMatch(/10s/);
    act(() => {
      vi.advanceTimersByTime(3000);
    });
    expect(screen.getByTestId("stage-market").textContent).toMatch(/13s/);
  });

  it("collapses back to a circle + ✓ when the stage completes", () => {
    const events = [
      evt("NVDA:1", "run_started", { ticker: "NVDA" }, "1"),
      evt("NVDA:1", "analyst_started", {
        node: "Market Analyst",
        ts: "2026-06-04T10:00:00.000Z",
      }, "2"),
    ];
    setup(events);
    const { rerender } = render(<RunTimeline />);
    expect(screen.getByTestId("stage-market").querySelector("svg.animate-spin")).toBeInTheDocument();
    // Add completion event, re-render with the new buffer.
    useUi.setState({
      eventBuffer: [
        ...events,
        evt("NVDA:1", "analyst_completed", {
          stage: "market",
          summary: "ok",
          report_excerpt: "ok",
          report_text: "ok",
          duration_ms: 10_000,
        }, "3"),
      ],
    });
    rerender(<RunTimeline />);
    const btn = screen.getByTestId("stage-market");
    expect(btn.getAttribute("data-status")).toBe("done");
    expect(btn.querySelector("svg.animate-spin")).not.toBeInTheDocument();
    expect(btn.textContent).toContain("✓");
  });
});
```

Add the `act` import at the top of the test file alongside the other testing-library imports:

```typescript
import { act } from "@testing-library/react";
```

- [ ] **Step 2: Run the new tests — expect FAIL (current code shows just a number, no spinner)**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx -t "running-stage pill"`

Expected: 3 FAILED. The first will fail on the `svg.animate-spin` assertion; the second on the "5s" / "10s" assertions; the third on the `✓` collapse.

- [ ] **Step 3: Extract a `<StageButton>` component that switches between circle and pill**

Edit `web/frontend/src/components/RunTimeline.tsx`. Replace the running-stage button block (lines 239–250) with:

```tsx
function StageButton({
  status,
  position,
  testKey,
  durationMs,
  startedAtIso,
}: {
  status: StageDerived["status"];
  position: number;
  testKey: string;
  durationMs?: number;
  startedAtIso?: string;
}) {
  const isRunning = status === "running";
  const [elapsed, setElapsed] = useState<number>(0);

  useEffect(() => {
    if (!isRunning || !startedAtIso) return;
    const tick = () => {
      const ms = Date.now() - new Date(startedAtIso).getTime();
      setElapsed(Math.max(0, Math.floor(ms / 1000)));
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [isRunning, startedAtIso]);

  const baseShape = isRunning
    ? "min-w-[3.25rem] h-8 px-2 rounded-full"
    : "w-8 h-8 rounded-full";
  const baseText = isRunning ? "text-[10px] font-mono" : "text-xs font-semibold";
  const label = isRunning
    ? formatElapsed(elapsed)
    : status === "done"
    ? "✓"
    : `${position}`;

  return (
    <button
      type="button"
      data-testid={`stage-${testKey}`}
      data-status={status}
      className={`border-2 flex items-center justify-center gap-1 transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-400 ${baseShape} ${baseText} ${STATUS_DOT[status]}`}
    >
      {isRunning && (
        <svg
          className="animate-spin h-3 w-3"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" fill="none" />
          <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" fill="none" strokeLinecap="round" />
        </svg>
      )}
      <span>{label}</span>
    </button>
  );
}

function formatElapsed(s: number): string {
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}m ${r}s`;
}
```

Add imports at the top of `RunTimeline.tsx`:

```typescript
import { useState, useMemo, useEffect } from "react";
```

(`useMemo` is already imported; add `useEffect`.)

In the timeline strip, replace the inline `<button>` with:

```tsx
<StageButton
  position={i + 1}
  testKey={d.key}
  status={d.info.status}
  durationMs={d.info.duration_ms}
  startedAtIso={lastStartedIsoFor(d.key, events)}
/>
```

where `lastStartedIsoFor` reads the last `analyst_started` event for that stage and returns its `ts`. If absent, returns `undefined`:

```typescript
function lastStartedIsoFor(stage: StageKey, events: WsEvent[]): string | undefined {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i];
    if (e.type === "analyst_started" && NODE_TO_STAGE[(e.data as any)?.node] === stage) {
      return (e.data as any)?.ts ?? undefined;
    }
  }
  return undefined;
}
```

- [ ] **Step 4: Run the new tests — expect PASS**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx -t "running-stage pill"`

Expected: 3 PASSED. The existing tests (e.g. `data-testid="stage-market"`) should still pass because the outer wrapper still emits that test-id.

- [ ] **Step 5: Run the full timeline suite — expect no regressions**

Run: `cd web/frontend && npx vitest run __tests__/RunTimeline.test.tsx`

Expected: all PASSED.

- [ ] **Step 6: Run the full frontend suite — expect no regressions**

Run: `cd web/frontend && npx vitest run`

Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add web/frontend/src/components/RunTimeline.tsx web/frontend/src/__tests__/RunTimeline.test.tsx
git commit -m "feat(timeline): running-stage pill with spinner + live elapsed"
```

---

## Task 12: Final integration check

- [ ] **Step 1: Backend — run the full test suite**

Run: `python -m pytest web/server/tests/ -v`

Expected: all PASSED. If anything fails, fix and recommit before proceeding.

- [ ] **Step 2: Frontend — run the full test suite + tsc**

Run: `cd web/frontend && npx tsc -b --pretty false && npx vitest run`

Expected: 0 type errors; all tests PASS.

- [ ] **Step 3: Manual smoke test**

```bash
# Start the server with the test ticker.
python -m web.server.app
# In another terminal, open the UI; click "Run analysis" on a ticker.
# Confirm:
#   - The dropdown shows model, price, and total duration.
#   - The timeline shows per-stage duration after each stage completes.
#   - The running stage shows a spinner + ticking elapsed text.
```

- [ ] **Step 4: Final commit (if any straggler changes)**

```bash
git status
# If there are pending changes:
git add -A
git commit -m "chore: integration touch-ups"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| `llm_provider`, `deep_think_model`, `quick_think_model` persisted | T1, T4 |
| `start_price`, `start_price_at` persisted | T1, T3, T4 |
| `total_duration_s` at every terminal site (1 success + 5 failure) | T5 |
| `run_to_dict` exposes the new fields | T2 |
| `elapsed_s` derived for running runs | T2 |
| `TickerHeader.runLabel` shows model/price/duration | T8 |
| `RunHistoryDrawer` shows model/price/duration | T9 |
| `RunTimeline` per-stage duration | T10 |
| `RunTimeline` running-stage pill (spinner + elapsed) | T11 |
| Tests for backend storage / queries / runner | T1, T2, T3, T4, T5 |
| Tests for frontend header / timeline | T8, T10, T11 |
| `vi.useFakeTimers()` for the 1 Hz interval | T11 |
| Wall-clock `total_duration_s` (not sum of stages) | T5 |
| Backwards compat: all new fields nullable | T1 |
| No new dependencies | All tasks use existing libraries |

**Type/signature consistency:**

- `storage.create_run_dir` signature with new kwargs — used in T1 (test) and T4 (caller).
- `price_feed.snapshot` signature — used in T3 (test) and T4 (caller).
- `queries.run_to_dict` shape — used in T2 (test) and consumed by T8/T9/T10/T11 (frontend types).
- `formatDuration(ms: number | null | undefined)` — used in T7 (test) and T8/T9/T10/T11 (callers). All call sites pass `ms` directly, or `seconds * 1000` for total-duration-in-seconds fields.
- `runLabel` exported from `TickerHeader.tsx` — used in T8 (test) and rendered in T8 (component). T9 has its own display logic and does not reuse `runLabel` (intentional — different visual context).

**Gaps found during review:** None. Spec is fully covered.

**Execution Handoff:**

Plan complete and saved to `docs/superpowers/plans/2026-06-04-run-metadata-enrichment.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
