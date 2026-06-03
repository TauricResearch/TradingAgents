# File-Based Storage & Per-Day Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SQLite storage layer with a file-based one and enable real per-day resume via the framework's LangGraph checkpointing.

**Architecture:** Per-run directories under `~/.tradingagents/data/{TICKER}/{SLUG}/` with `run.json`, `events.jsonl`, `llm_calls.jsonl`, and `stages/*.json`. Watchlist is a single `~/.tradingagents/data/watchlist.json`. The runner enables `checkpoint_enabled=True` so LangGraph's per-ticker `SqliteSaver` (separate at `~/.tradingagents/cache/checkpoints/`) drives the actual node-level skip on resume.

**Tech Stack:** Python stdlib only (`json`, `shutil`, `os`, `zoneinfo`); FastAPI; React + TanStack Query + Zustand.

---

## File Structure

**New files:**
- `web/server/storage.py` — IO primitives (`write_json_atomic`, `append_jsonl`, `read_json`, `read_jsonl`) + run-dir helpers (`create_run_dir`, `find_resumable_run`, `clear_ticker_data`, `read_run`, `list_ticker_runs`, `read_run_events`, `read_run_llm_calls`) + `slug_for_now`
- `web/server/queries.py` — read-side helpers that shape persisted data for the API (`read_watchlist`, `write_watchlist`, `add_ticker`, `remove_ticker`)
- `web/server/tests/test_storage.py` — unit tests for `storage.py`
- `web/server/tests/test_queries.py` — unit tests for `queries.py`

**Modified files:**
- `web/server/settings.py` — replace `db_path` with `data_dir` and `cache_dir`
- `web/server/events.py` — switch persistence from `db.append_event` to `append_jsonl` per run dir
- `web/server/runner.py` — `enqueue` resolves the run dir (with resume detection); `build_graph` merges `checkpoint_enabled=True`; `_run_one` writes stage files on `analyst_completed`
- `web/server/llm_calls.py` — switch from SQLModel to per-run `llm_calls.jsonl` append + read
- `web/server/app.py` — endpoints read from files; lifespan unlinks old `dashboard.db`; WS replays full `events.jsonl` on connect; `run_id` becomes a string
- `web/server/tests/conftest.py` — replace `temp_db` fixture with `temp_data_dir` using `tmp_path`
- `web/server/tests/test_runner.py`, `test_app.py`, `test_events.py`, `test_ws.py` — adapt to new APIs
- `web/frontend/src/lib/api.ts` — `RunRow.id` and `RunDetail.run.id` become `string`
- `web/frontend/src/store/ui.ts` — `lastRunIdByTicker` etc. values become `string | null`
- `web/frontend/src/hooks/useRunStream.ts` — handle string runId; clear buffer on mount
- `web/frontend/src/hooks/useFocusedRunEvents.ts`, `useRestoredRunEvents.ts` — handle string runId
- `web/frontend/src/components/TickerHeader.tsx` — Resume button enabled iff today's partial exists; "incomplete — N days ago" hint
- `web/frontend/src/__tests__/*.test.{ts,tsx}` — adapt to string runIds

**Deleted files:**
- `web/server/db.py` — replaced by `storage.py` + `queries.py`
- `web/server/tests/test_db.py` — replaced by `test_queries.py` + `test_storage.py`

---

## Task 1: `storage.py` — atomic IO primitives + slug

**Files:**
- Create: `web/server/storage.py`

- [ ] **Step 1: Create `web/server/storage.py` with the primitives**

```python
"""File-based storage primitives for the dashboard.

This module owns all on-disk IO for the dashboard. Higher-level
read-side helpers that shape data for the API live in ``queries.py``.

All timestamps in persisted files are UTC ISO-8601 with ``Z`` suffix.
The only Israel-local representation is the run directory slug,
which is purely for human readability.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from tradingagents.dataflows.utils import safe_ticker_component


# Module-level settings path; populated by ``init_settings()`` at app startup
# so tests can monkeypatch a temp dir before any storage call.
_settings = {"data_dir": "", "cache_dir": ""}


def init_settings(*, data_dir: str, cache_dir: str) -> None:
    """Configure storage paths. Called from app lifespan / conftest."""
    _settings["data_dir"] = data_dir
    _settings["cache_dir"] = cache_dir
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    Path(cache_dir).mkdir(parents=True, exist_ok=True)


def data_dir() -> Path:
    return Path(_settings["data_dir"])


def cache_dir() -> Path:
    return Path(_settings["cache_dir"])


def ticker_dir(ticker: str) -> Path:
    """Return ``data/{ticker}/`` (creating it)."""
    safe = safe_ticker_component(ticker).upper()
    p = data_dir() / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---- atomic JSON ----

def write_json_atomic(path: Path | str, data: Any) -> None:
    """Write ``data`` as JSON to ``path`` atomically via tmp + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path | str) -> Optional[Any]:
    """Return parsed JSON or ``None`` on missing/invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---- append-only JSONL ----

def append_jsonl(path: Path | str, obj: Any) -> None:
    """Append ``obj`` as a single JSON line. Creates parent dir if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def read_jsonl(path: Path | str) -> list[Any]:
    """Read JSONL, skipping any malformed last line (incomplete write)."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[Any] = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                out.append(json.loads(s))
            except json.JSONDecodeError:
                # Truncated last line from a crash — skip it. Earlier
                # lines are valid and preserved.
                continue
    return out


# ---- slug ----

def slug_for_now(now: Optional[datetime] = None) -> str:
    """Return an Israel-local slug like ``2026-06-03_14-30-00_IDT``.

    ``IDT`` = Israel Daylight Time (Apr–Oct), ``IST`` = Israel Standard Time.
    The slug is purely for human display; timestamps inside files are UTC.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    israel = now.astimezone(ZoneInfo("Asia/Jerusalem"))
    suffix = "IDT" if israel.dst().total_seconds() > 0 else "IST"
    return israel.strftime("%Y-%m-%d_%H-%M-%S_") + suffix


def utc_iso(dt: datetime) -> str:
    """Format a datetime as UTC ISO-8601 with ``Z`` suffix."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---- ticker cleanup (used by watchlist removal) ----

def clear_ticker_data(ticker: str) -> None:
    """Remove the ticker's data dir and framework checkpoint DB.

    Idempotent: a no-op if either is already missing.
    """
    safe = safe_ticker_component(ticker).upper()
    td = data_dir() / safe
    if td.exists():
        shutil.rmtree(td)
    cp = cache_dir() / "checkpoints" / f"{safe}.db"
    if cp.exists():
        cp.unlink()
```

- [ ] **Step 2: Verify the file imports without errors**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server import storage; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add web/server/storage.py
git commit -m "feat(storage): atomic JSON + JSONL primitives and slug helper"
```

---

## Task 2: `tests/test_storage.py` — primitives + slug

**Files:**
- Create: `web/server/tests/test_storage.py`

- [ ] **Step 1: Create the test file**

```python
"""Unit tests for ``web.server.storage`` primitives."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from web.server import storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data, cache


def test_write_json_atomic_survives_concurrent_reader(tmp_path, data_root):
    target = tmp_path / "config.json"
    storage.write_json_atomic(target, {"v": 1})
    with open(target, "r", encoding="utf-8") as reader:
        reader.read()
    storage.write_json_atomic(target, {"v": 2})
    assert storage.read_json(target) == {"v": 2}


def test_write_json_atomic_replaces_partial_files_atomically(tmp_path, data_root):
    target = tmp_path / "x.json"
    storage.write_json_atomic(target, {"a": 1, "b": [1, 2, 3]})
    raw = target.read_text(encoding="utf-8")
    assert "\n" in raw  # indented
    parsed = json.loads(raw)
    assert parsed == {"a": 1, "b": [1, 2, 3]}


def test_write_json_atomic_creates_parent_dirs(tmp_path, data_root):
    target = tmp_path / "nested" / "deeper" / "x.json"
    storage.write_json_atomic(target, {"ok": True})
    assert storage.read_json(target) == {"ok": True}


def test_read_json_returns_none_for_missing(tmp_path, data_root):
    assert storage.read_json(tmp_path / "absent.json") is None


def test_read_json_returns_none_for_malformed(tmp_path, data_root):
    p = tmp_path / "broken.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert storage.read_json(p) is None


def test_append_jsonl_produces_valid_lines(tmp_path, data_root):
    p = tmp_path / "events.jsonl"
    storage.append_jsonl(p, {"a": 1})
    storage.append_jsonl(p, {"a": 2})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"a": 1}
    assert json.loads(lines[1]) == {"a": 2}


def test_read_jsonl_skips_truncated_last_line(tmp_path, data_root):
    """A crash mid-write leaves a partial last line. read_jsonl must
    not raise and must skip the bad line while preserving earlier ones."""
    p = tmp_path / "events.jsonl"
    storage.append_jsonl(p, {"a": 1})
    storage.append_jsonl(p, {"a": 2})
    raw = p.read_text(encoding="utf-8")
    p.write_text(raw + '{"a": 3, "b":', encoding="utf-8")
    out = storage.read_jsonl(p)
    assert out == [{"a": 1}, {"a": 2}]


def test_read_jsonl_empty_when_file_missing(tmp_path, data_root):
    assert storage.read_jsonl(tmp_path / "absent.jsonl") == []


def test_slug_for_now_uses_israel_timezone_in_summer():
    """July is IDT (DST in effect)."""
    dt_utc = datetime(2026, 7, 15, 11, 0, 0, tzinfo=timezone.utc)  # 14:00 Israel
    assert storage.slug_for_now(dt_utc) == "2026-07-15_14-00-00_IDT"


def test_slug_for_now_uses_israel_timezone_in_winter():
    """January is IST (no DST)."""
    dt_utc = datetime(2026, 1, 15, 11, 0, 0, tzinfo=timezone.utc)  # 13:00 Israel
    assert storage.slug_for_now(dt_utc) == "2026-01-15_13-00-00_IST"


def test_utc_iso_uses_z_suffix():
    dt = datetime(2026, 6, 3, 11, 30, 0, 123456, tzinfo=timezone.utc)
    assert storage.utc_iso(dt) == "2026-06-03T11:30:00.123456Z"


def test_utc_iso_handles_naive_datetime():
    """A tz-less datetime is assumed UTC."""
    dt = datetime(2026, 6, 3, 11, 30, 0)
    assert storage.utc_iso(dt).endswith("Z")


def test_clear_ticker_data_removes_both_data_dir_and_checkpoint(tmp_path, data_root):
    data, cache = data_root
    (data / "NVDA" / "2026-06-03_14-30-00_IDT").mkdir(parents=True)
    (data / "NVDA" / "2026-06-03_14-30-00_IDT" / "run.json").write_text("{}")
    (cache / "checkpoints").mkdir(parents=True, exist_ok=True)
    (cache / "checkpoints" / "NVDA.db").write_text("")

    storage.clear_ticker_data("NVDA")

    assert not (data / "NVDA").exists()
    assert not (cache / "checkpoints" / "NVDA.db").exists()


def test_clear_ticker_data_is_noop_when_missing(tmp_path, data_root):
    storage.clear_ticker_data("ZZZZ")  # should not raise
```

- [ ] **Step 2: Run the tests**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_storage.py -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add web/server/tests/test_storage.py
git commit -m "test(storage): cover atomic IO, JSONL, slug, and cleanup"
```

---

## Task 3: `settings.py` — replace `db_path` with `data_dir` + `cache_dir`

**Files:**
- Modify: `web/server/settings.py`

- [ ] **Step 1: Replace the file contents**

```python
"""Environment-driven settings for the dashboard server."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_root() -> Path:
    p = Path.home() / ".tradingagents"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass(frozen=True)
class Settings:
    data_dir: str = os.environ.get(
        "TRADINGAGENTS_DATA_DIR", str(_default_root() / "data")
    )
    cache_dir: str = os.environ.get(
        "TRADINGAGENTS_CACHE_DIR", str(_default_root() / "cache")
    )
    host: str = os.environ.get("TRADINGAGENTS_DASHBOARD_HOST", "127.0.0.1")
    port: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PORT", "8000"))
    max_concurrent: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_MAX_CONCURRENT", "3"))
    price_poll_s: int = int(os.environ.get("TRADINGAGENTS_DASHBOARD_PRICE_POLL_S", "2"))
    log_level: str = os.environ.get("TRADINGAGENTS_DASHBOARD_LOG_LEVEL", "INFO")
    frontend_dist: str = os.environ.get("TRADINGAGENTS_FRONTEND_DIST", "web/frontend/dist")


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Verify the module imports**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server.settings import get_settings; s = get_settings(); print(s.data_dir, s.cache_dir)"`
Expected: prints two absolute paths under `~/.tradingagents/`.

- [ ] **Step 3: Commit**

```bash
git add web/server/settings.py
git commit -m "refactor(settings): introduce data_dir and cache_dir"
```

---

## Task 4: `storage.py` — run directory helpers

**Files:**
- Modify: `web/server/storage.py` (append to the end)

- [ ] **Step 1: Append run-directory helpers**

```python
# ---- run directory helpers (continued) ----

def run_id_for(ticker: str, started_at: datetime) -> str:
    """Stable per-run identifier: ``TICKER:UTC_ISO_TIMESTAMP``."""
    return f"{safe_ticker_component(ticker).upper()}:{utc_iso(started_at)}"


def today_utc_iso() -> str:
    """Today as a UTC ISO date (the framework's ``trade_date`` value)."""
    return datetime.now(timezone.utc).date().isoformat()


def create_run_dir(ticker: str, started_at: Optional[datetime] = None) -> dict:
    """Create a fresh run dir + write initial run.json. Return the dir info.

    The returned dict has keys: ``run_dir`` (Path), ``run_id`` (str),
    ``slug`` (str), ``started_at_iso`` (str).
    """
    if started_at is None:
        started_at = now_utc()
    slug = slug_for_now(started_at)
    td = ticker_dir(ticker)
    run_dir = td / slug
    # Race-avoidance: if a dir with this slug already exists (unlikely at
    # second resolution but possible in tests), append a counter.
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
    }
    write_json_atomic(run_dir / "run.json", run_json)
    return {
        "run_dir": run_dir,
        "run_id": run_id,
        "slug": run_dir.name,
        "started_at_iso": run_json["started_at"],
    }


def read_run(run_id: str) -> Optional[dict]:
    """Find and parse run.json for ``run_id``.

    Walks all ticker dirs to locate the dir whose run.json's id matches.
    Returns ``None`` if not found.
    """
    for td in data_dir().iterdir():
        if not td.is_dir():
            continue
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
            rj = read_json(sd / "run.json")
            if rj and rj.get("id") == run_id:
                return rj
    return None


def read_run_dir(run_id: str) -> Optional[Path]:
    """Return the directory Path for ``run_id`` (cheap; no JSON parse)."""
    for td in data_dir().iterdir():
        if not td.is_dir():
            continue
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
            rj = read_json(sd / "run.json")
            if rj and rj.get("id") == run_id:
                return sd
    return None


def list_ticker_runs(ticker: str, limit: int = 50) -> list[dict]:
    """Return runs for a ticker, newest first (by started_at)."""
    td = data_dir() / safe_ticker_component(ticker).upper()
    if not td.exists():
        return []
    rows: list[dict] = []
    for sd in td.iterdir():
        if not sd.is_dir():
            continue
        rj = read_json(sd / "run.json")
        if rj:
            rows.append(rj)
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows[:limit]


def find_resumable_run(ticker: str, today_iso: str) -> Optional[dict]:
    """Return the partial run dir info for ``ticker`` started today (UTC).

    "Partial" means ``status == "running"`` AND ``started_at``'s date is
    ``today_iso``. Returns ``None`` if no such run exists.
    """
    td = data_dir() / safe_ticker_component(ticker).upper()
    if not td.exists():
        return None
    for sd in td.iterdir():
        if not sd.is_dir():
            continue
        rj = read_json(sd / "run.json")
        if not rj:
            continue
        if rj.get("status") != "running":
            continue
        started_iso = rj.get("started_at") or ""
        if not started_iso.startswith(today_iso):
            continue
        return {
            "run_dir": sd,
            "run_id": rj["id"],
            "slug": sd.name,
            "started_at_iso": started_iso,
            "run_json": rj,
        }
    return None


def mark_run_status(run_id: str, **fields) -> None:
    """Update fields on run.json in place. Raises if the run is missing."""
    rd = read_run_dir(run_id)
    if rd is None:
        raise KeyError(f"run not found: {run_id}")
    rj = read_json(rd / "run.json") or {}
    rj.update(fields)
    write_json_atomic(rd / "run.json", rj)


def mark_run_superseded(run_id: str) -> None:
    """Used by force=true to retire today's partial before starting fresh."""
    mark_run_status(run_id, status="superseded")


def list_run_events(run_id: str) -> list[dict]:
    rd = read_run_dir(run_id)
    if rd is None:
        return []
    return read_jsonl(rd / "events.jsonl")


def list_run_llm_calls(run_id: str) -> list[dict]:
    rd = read_run_dir(run_id)
    if rd is None:
        return []
    return read_jsonl(rd / "llm_calls.jsonl")


def append_run_event(run_id: str, event_obj: dict) -> None:
    rd = read_run_dir(run_id)
    if rd is None:
        raise KeyError(f"run not found: {run_id}")
    append_jsonl(rd / "events.jsonl", event_obj)


def append_run_llm_call(run_id: str, call_obj: dict) -> None:
    rd = read_run_dir(run_id)
    if rd is None:
        raise KeyError(f"run not found: {run_id}")
    append_jsonl(rd / "llm_calls.jsonl", call_obj)


def write_stage(run_id: str, stage: str, stage_payload: dict) -> None:
    """Write a single ``stages/{stage}.json`` atomically.

    Also updates ``run.json.completed_stages`` to keep the denormalized
    cache in sync (so a reader can list progress without walking
    stages/).
    """
    rd = read_run_dir(run_id)
    if rd is None:
        raise KeyError(f"run not found: {run_id}")
    write_json_atomic(rd / "stages" / f"{stage}.json", stage_payload)
    rj = read_json(rd / "run.json") or {}
    completed = list(rj.get("completed_stages") or [])
    if stage not in completed:
        completed.append(stage)
        rj["completed_stages"] = completed
        write_json_atomic(rd / "run.json", rj)


def walk_data_dir() -> Iterable[Path]:
    """Yield every ticker subdir under data/. Used by startup cleanup."""
    dd = data_dir()
    if not dd.exists():
        return
    for td in dd.iterdir():
        if td.is_dir():
            yield td
```

- [ ] **Step 2: Verify the additions import cleanly**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server import storage; print(storage.find_resumable_run.__doc__[:60])"`
Expected: prints first 60 chars of the docstring.

- [ ] **Step 3: Commit**

```bash
git add web/server/storage.py
git commit -m "feat(storage): run dir helpers (create/find/append/mark)"
```

---

## Task 5: `queries.py` — watchlist + run shapers

**Files:**
- Create: `web/server/queries.py`

- [ ] **Step 1: Create the file**

```python
"""Read-side helpers that shape persisted data for the API layer.

Pure functions on top of ``storage``; no FastAPI types here. This split
keeps the low-level IO testable independently of the API.
"""
from __future__ import annotations

from datetime import datetime

from tradingagents.dataflows.utils import safe_ticker_component

from web.server import storage


class DuplicateTicker(Exception):
    pass


# ---- watchlist ----

def read_watchlist() -> list[dict]:
    """Return the watchlist rows, sorted by added_at ascending."""
    rows = storage.read_json(storage.data_dir() / "watchlist.json")
    if not rows:
        return []
    return rows.get("tickers", [])


def _write_watchlist(rows: list[dict]) -> None:
    storage.write_json_atomic(
        storage.data_dir() / "watchlist.json",
        {"version": 1, "tickers": rows},
    )


def add_ticker(ticker: str, company_name: str, exchange: str) -> dict:
    """Add a ticker to the watchlist. Raises DuplicateTicker if present."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    if any(r["ticker"] == safe for r in rows):
        raise DuplicateTicker(safe)
    row = {
        "ticker": safe,
        "company_name": company_name,
        "exchange": exchange,
        "added_at": storage.utc_iso(storage.now_utc()),
        "last_run_id": None,
        "last_decision": None,
        "last_decision_at": None,
    }
    rows.append(row)
    _write_watchlist(rows)
    # Make sure the ticker data dir exists so the next /api/runs call
    # can drop its run subdir in there.
    storage.ticker_dir(safe)
    return row


def remove_ticker(ticker: str) -> None:
    """Remove the ticker from the watchlist and delete its analysis data."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    next_rows = [r for r in rows if r["ticker"] != safe]
    if next_rows == rows:
        return  # not present; nothing to do
    _write_watchlist(next_rows)
    storage.clear_ticker_data(safe)


def update_last_decision(ticker: str, run_id: str, decision_text: str, at: datetime) -> None:
    """Set the watchlist row's last_decision_* fields. No-op if ticker is gone."""
    safe = safe_ticker_component(ticker).upper()
    rows = read_watchlist()
    changed = False
    for r in rows:
        if r["ticker"] == safe:
            r["last_run_id"] = run_id
            r["last_decision"] = decision_text
            r["last_decision_at"] = storage.utc_iso(at)
            changed = True
    if changed:
        _write_watchlist(rows)


# ---- run queries (shape persisted run.json + events.jsonl for the API) ----

def run_to_dict(r: dict) -> dict:
    """Shape a stored run.json for the API. Keeps the wire format stable."""
    return {
        "id": r.get("id"),
        "ticker": r.get("ticker"),
        "slug": r.get("slug"),
        "started_at": r.get("started_at"),
        "finished_at": r.get("finished_at"),
        "status": r.get("status"),
        "decision_action": r.get("decision_action"),
        "decision_target": r.get("decision_target"),
        "decision_rationale": r.get("decision_rationale"),
        "decision_confidence": r.get("decision_confidence"),
    }


def event_to_dict(e: dict, run_id: str) -> dict:
    """Shape a stored events.jsonl line for the API."""
    return {
        "id": e.get("id"),
        "type": e.get("type"),
        "ts": e.get("ts"),
        "data": e.get("data", {}),
        "run_id": run_id,
    }


def llm_call_to_dict(c: dict) -> dict:
    """Shape a stored llm_calls.jsonl line for the API."""
    return {
        "id": c.get("id"),
        "run_id": c.get("run_id"),
        "ticker": c.get("ticker"),
        "node_name": c.get("node_name", ""),
        "started_at": c.get("started_at"),
        "model": c.get("model", ""),
        "prompt_text": c.get("prompt_text", ""),
        "response_text": c.get("response_text", ""),
        "tool_calls": c.get("tool_calls", []),
        "input_tokens": c.get("input_tokens", 0),
        "output_tokens": c.get("output_tokens", 0),
        "total_tokens": c.get("total_tokens", 0),
        "duration_ms": c.get("duration_ms", 0),
    }
```

- [ ] **Step 2: Verify imports**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server import queries; print(queries.run_to_dict.__doc__[:60])"`
Expected: prints first 60 chars of docstring.

- [ ] **Step 3: Commit**

```bash
git add web/server/queries.py
git commit -m "feat(queries): watchlist + run/event/llm_call shapers"
```

---

## Task 6: `tests/test_queries.py` — watchlist CRUD + shapers

**Files:**
- Create: `web/server/tests/test_queries.py`

- [ ] **Step 1: Create the test file**

```python
"""Unit tests for ``web.server.queries``."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from web.server import queries, storage


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


def test_watchlist_starts_empty(data_root):
    assert queries.read_watchlist() == []


def test_add_ticker_creates_row(data_root):
    row = queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    assert row["ticker"] == "NVDA"
    assert row["company_name"] == "NVIDIA"
    assert row["exchange"] == "NASDAQ"
    assert queries.read_watchlist() == [row]


def test_add_ticker_uppercases_ticker(data_root):
    queries.add_ticker("nvda", "NVIDIA", "NASDAQ")
    rows = queries.read_watchlist()
    assert rows[0]["ticker"] == "NVDA"


def test_add_duplicate_ticker_raises(data_root):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    with pytest.raises(queries.DuplicateTicker):
        queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")


def test_add_ticker_creates_data_dir(data_root, tmp_path):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    assert (tmp_path / "data" / "NVDA").is_dir()


def test_remove_ticker_clears_data(data_root, tmp_path):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    rd = tmp_path / "data" / "NVDA" / "2026-06-03_14-30-00_IDT"
    rd.mkdir(parents=True)
    (rd / "run.json").write_text("{}")
    queries.remove_ticker("NVDA")
    assert queries.read_watchlist() == []
    assert not (tmp_path / "data" / "NVDA").exists()


def test_remove_ticker_unknown_is_noop(data_root):
    queries.remove_ticker("ZZZZ")  # must not raise
    assert queries.read_watchlist() == []


def test_update_last_decision_sets_fields(data_root):
    queries.add_ticker("NVDA", "NVIDIA", "NASDAQ")
    queries.update_last_decision(
        "NVDA", "NVDA:2026-06-03T11:30:00.000000Z", "BUY @ 260.0", datetime(2026, 6, 3, 11, 35, tzinfo=timezone.utc)
    )
    rows = queries.read_watchlist()
    assert rows[0]["last_run_id"] == "NVDA:2026-06-03T11:30:00.000000Z"
    assert rows[0]["last_decision"] == "BUY @ 260.0"
    assert rows[0]["last_decision_at"] == "2026-06-03T11:35:00.000000Z"


def test_update_last_decision_for_missing_ticker_is_noop(data_root):
    queries.update_last_decision("ZZZZ", "r", "x", datetime.now(timezone.utc))
    assert queries.read_watchlist() == []


def test_run_to_dict_passes_through_fields():
    raw = {
        "id": "NVDA:2026-06-03T11:30:00.000000Z",
        "ticker": "NVDA",
        "slug": "2026-06-03_14-30-00_IDT",
        "started_at": "2026-06-03T11:30:00.000000Z",
        "finished_at": "2026-06-03T11:35:00.000000Z",
        "status": "done",
        "decision_action": "BUY",
        "decision_target": 260.0,
        "decision_rationale": "ok",
        "decision_confidence": 0.8,
    }
    assert queries.run_to_dict(raw) == raw


def test_event_to_dict_keeps_run_id():
    e = {"id": 1, "type": "analyst_thinking", "ts": "2026-06-03T11:30:00.000000Z", "data": {"x": 1}}
    out = queries.event_to_dict(e, "NVDA:r")
    assert out["run_id"] == "NVDA:r"
    assert out["data"] == {"x": 1}
```

- [ ] **Step 2: Run the tests**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_queries.py -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add web/server/tests/test_queries.py
git commit -m "test(queries): watchlist CRUD + run/event shapers"
```

---

## Task 7: `events.py` — persist via `storage.append_run_event`

**Files:**
- Modify: `web/server/events.py:1-73`

- [ ] **Step 1: Replace the SQLModel persistence call**

Read the current `web/server/events.py` end-to-end first. The `emit()` function currently calls `db.append_event(...)`. Replace the whole `events.py` with:

```python
"""Domain events: persist to disk + broadcast to WS subscribers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Set

from fastapi import WebSocket

from . import storage

log = logging.getLogger(__name__)


class EventType(str, Enum):
    """All 14 event types. String values are part of the WS protocol."""

    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    RUN_DONE = "run_done"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    ANALYST_STARTED = "analyst_started"
    ANALYST_THINKING = "analyst_thinking"
    ANALYST_MESSAGE = "analyst_message"
    ANALYST_TOOL_CALL = "analyst_tool_call"
    ANALYST_TOOL_RESULT = "analyst_tool_result"
    ANALYST_COMPLETED = "analyst_completed"
    STAGE_COMPLETED = "stage_completed"
    LLM_CALL = "llm_call"
    TOKEN_USAGE = "token_usage"


def make_event(run_id: str, type_: EventType, data: Dict[str, Any]) -> Dict[str, Any]:
    """Build the canonical event dict that goes on the wire + to disk."""
    return {
        "id": f"{run_id}:{datetime.now(timezone.utc).timestamp():.6f}",
        "run_id": run_id,
        "type": type_.value if isinstance(type_, EventType) else str(type_),
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data": data,
    }


_subscribers: Dict[str, Set[WebSocket]] = {}


async def _broadcast(event: Dict[str, Any]) -> None:
    """Best-effort fanout to all WS subscribers (run-specific + global)."""
    rid = event.get("run_id")
    targets: List[WebSocket] = []
    if rid and rid in _subscribers:
        targets.extend(_subscribers[rid])
    targets.extend(_subscribers.get("*", []))
    for ws in targets:
        try:
            await ws.send_json(event)
        except Exception as exc:  # noqa: BLE001
            log.warning("WS broadcast failed: %s", exc)


def emit(run_id: str, type_: EventType, data: Dict[str, Any]) -> None:
    """Persist + broadcast a domain event. Safe to call from sync code."""
    event = make_event(run_id, type_, data)
    try:
        storage.append_run_event(run_id, event)
    except KeyError:
        log.warning("emit() called for unknown run_id=%s; dropping", run_id)
        return
    # Schedule broadcast on the running event loop.
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # no loop → caller is a test or shutdown path
    loop.create_task(_broadcast(event))


def subscribe(run_id: str, ws: WebSocket) -> None:
    _subscribers.setdefault(run_id, set()).add(ws)


def unsubscribe(run_id: str, ws: WebSocket) -> None:
    if run_id in _subscribers:
        _subscribers[run_id].discard(ws)
        if not _subscribers[run_id]:
            del _subscribers[run_id]


def subscribe_global(ws: WebSocket) -> None:
    _subscribers.setdefault("*", set()).add(ws)


def unsubscribe_global(ws: WebSocket) -> None:
    if "*" in _subscribers:
        _subscribers["*"].discard(ws)
        if not _subscribers["*"]:
            del _subscribers["*"]
```

- [ ] **Step 2: Verify no SQLModel import remains**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && Select-String -Path web\server\events.py -Pattern "from .db|from .* import .*db" | Measure-Object`
Expected: `Count: 0`.

- [ ] **Step 3: Commit**

```bash
git add web/server/events.py
git commit -m "refactor(events): persist via storage.append_run_event"
```

---

## Task 8: `llm_calls.py` — file-backed LLM call log

**Files:**
- Modify: `web/server/llm_calls.py:1-81`

- [ ] **Step 1: Replace the file**

The current `llm_calls.py` writes to SQLModel. Replace it with a file-backed implementation that mirrors the same signatures so callers (`callbacks.py`) don't change.

```python
"""File-backed LLM call log. One JSONL line per call, per run."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import storage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_llm_call(
    run_id: str,
    *,
    node_name: str,
    ticker: str,
    model: str,
    prompt_text: str,
    response_text: str,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    started_at: Optional[str] = None,
) -> None:
    """Append a single LLM call to ``{run_dir}/llm_calls.jsonl``."""
    call = {
        "id": f"{run_id}:{_now_iso()}:{node_name}",
        "run_id": run_id,
        "node_name": node_name,
        "ticker": ticker,
        "model": model,
        "prompt_text": prompt_text,
        "response_text": response_text,
        "tool_calls_json": tool_calls or [],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
        "started_at": started_at or _now_iso(),
    }
    try:
        storage.append_run_llm_call(run_id, call)
    except KeyError:
        # Run was deleted mid-run; nothing we can do.
        pass


def llm_calls_for_run(run_id: str) -> List[Dict[str, Any]]:
    """Return all LLM calls recorded for a run, in order."""
    return storage.list_run_llm_calls(run_id)


def list_runs_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Return all run.json rows for a ticker, newest first."""
    return storage.list_ticker_runs(ticker)
```

- [ ] **Step 2: Verify import works**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server import llm_calls; print(llm_calls.save_llm_call.__doc__.splitlines()[0])"`
Expected: prints `Append a single LLM call to ``{run_dir}/llm_calls.jsonl``.`

- [ ] **Step 3: Commit**

```bash
git add web/server/llm_calls.py
git commit -m "refactor(llm_calls): persist to per-run JSONL"
```

---

## Task 9: `runner.py` — enable framework checkpointing

**Files:**
- Modify: `web/server/runner.py` (top-of-file imports + `build_graph` call)

- [ ] **Step 1: Read the current `runner.py` head + the graph build path**

Read `web/server/runner.py:1-100` and locate the call to `build_graph(...)` (search for `build_graph(`). The current code passes `config` (a dict) and `callbacks` to `build_graph`.

- [ ] **Step 2: Set `checkpoint_enabled=True` in the config**

Find the line that builds the dict passed to `build_graph`. It currently does not include `checkpoint_enabled`. Add the key:

```python
config = {
    **DEFAULT_CONFIG,  # whatever the existing spread is
    "ticker": ticker,
    "trade_date": date_str,
    "checkpoint_enabled": True,  # NEW: enables LangGraph SqliteSaver under
                                 # data_cache_dir/checkpoints/{TICKER}.db
}
```

If the file uses a different config construction pattern (e.g., a `dict(...)` literal), add `"checkpoint_enabled": True` to that literal in the same shape.

- [ ] **Step 3: Add a thin wrapper around the framework's `clear_checkpoint`**

At the top of `web/server/runner.py`, near the other framework imports, add:

```python
from tradingagents.graph.checkpointer import (
    clear_checkpoint,
    thread_id as framework_thread_id,
)
```

And add a module-level helper (place it just above `_STAGE_MAP`):

```python
def checkpoint_thread_id(ticker: str, date_str: str) -> str:
    """Mirror of ``tradingagents.graph.checkpointer.thread_id`` for tests."""
    return framework_thread_id(ticker, date_str)


def clear_today_checkpoint(ticker: str, date_str: str) -> None:
    """Used by force=true to drop the LangGraph thread state for today."""
    from . import storage
    clear_checkpoint(storage.cache_dir(), ticker, date_str)
```

(`storage.cache_dir()` is added in Task 3 — it returns the same path the framework's `default_config.data_cache_dir` resolves to.)

- [ ] **Step 4: Verify the runner module imports**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server import runner; print(runner.checkpoint_thread_id.__doc__.splitlines()[0])"`
Expected: prints the first line of the docstring without error.

- [ ] **Step 5: Commit**

```bash
git add web/server/runner.py
git commit -m "feat(runner): enable LangGraph checkpointing for resume"
```

---

## Task 10: `runner.py` — `enqueue()` with resume + force

**Files:**
- Modify: `web/server/runner.py` (the `enqueue` function and the queue map)

- [ ] **Step 1: Replace the storage-backed `enqueue` implementation**

Find the current `enqueue(ticker, idempotency_key, force)` function. Replace it with:

```python
async def enqueue(ticker: str, date_str: str, force: bool = False) -> str:
    """Resolve today's run for ``ticker`` and either resume or start fresh.

    Returns the ``run_id`` (a string of the form ``TICKER:UTC_ISO``).

    Rules:
    - force=true: clear the LangGraph thread state for today, mark any
      existing partial as ``superseded``, create a new run dir + run.json.
    - force=false:
        - If today's run is already terminal (done/failed/cancelled/
          superseded), return that run_id without starting anything.
        - If today's run is ``running`` (partial), reuse its dir; the
          framework's thread_id will match the existing SqliteSaver
          checkpoint and resume from the last completed node.
        - If no run for today, create a fresh run dir + enqueue.
    """
    from . import storage
    ticker_u = ticker.upper()

    # Look for an existing run for today, any status.
    existing = storage.find_resumable_run(ticker_u, date_str)
    if existing and not force:
        run_json = existing["run_json"]
        status = run_json.get("status")
        if status == "running":
            # Resume: reuse dir, no new checkpoint, no enqueue.
            log.info("resuming run %s for %s", existing["run_id"], ticker_u)
            return existing["run_id"]
        # Terminal today → idempotent no-op.
        log.info("idempotent: returning existing %s run %s", status, existing["run_id"])
        return existing["run_id"]

    if existing and force:
        # Retire the partial before starting fresh.
        storage.mark_run_superseded(existing["run_id"])
        clear_today_checkpoint(ticker_u, date_str)
        log.info("force=true: superseded %s", existing["run_id"])

    info = storage.create_run_dir(ticker_u)
    run_id = info["run_id"]
    # Enqueue a worker that calls _run_one.
    await _WORK_QUEUE.put((run_id, ticker_u, date_str, info["run_dir"]))
    return run_id
```

(The queue map `_WORK_QUEUE` is initialized at module load as `asyncio.Queue()`.)

- [ ] **Step 2: Update the worker loop**

Find the existing top-level worker that pulls from the queue and calls `_run_one(rid, sem)`. Change it to pass the run_dir through:

```python
async def _worker(sem: asyncio.Semaphore) -> None:
    while True:
        run_id, ticker, date_str, run_dir = await _WORK_QUEUE.get()
        try:
            await _run_one(run_id, ticker, date_str, run_dir, sem)
        except Exception as exc:  # noqa: BLE001
            log.exception("worker failed for %s: %s", run_id, exc)
        finally:
            _WORK_QUEUE.task_done()
```

- [ ] **Step 3: Verify by importing**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "import inspect, web.server.runner as r; print(inspect.signature(r.enqueue))"`
Expected: prints something like `(ticker: str, date_str: str, force: bool = False) -> str`.

- [ ] **Step 4: Commit**

```bash
git add web/server/runner.py
git commit -m "feat(runner): resume-or-fresh enqueue with force=true clear"
```

---

## Task 11: `runner.py` — `_run_one()` writes per-stage files

**Files:**
- Modify: `web/server/runner.py` (the `_run_one` function)

- [ ] **Step 1: Update the signature and persist each analyst stage**

Find the existing `_run_one(rid, sem)` function. Replace its signature with `_run_one(run_id, ticker, date_str, run_dir, sem)`. Then locate the inner loop that handles `analyst_completed` events (search for `EventType.ANALYST_COMPLETED` or the `analyst_completed` string). Immediately after the existing broadcast, write the stage file:

```python
# Inside the event-dispatch loop, in the analyst_completed branch:
from . import storage, events
stage = _STAGE_MAP.get(node_name, node_name)  # existing helper
started_ts = state.get("__stage_started__", {}).get(node_name)
duration_ms = 0
if started_ts:
    duration_ms = int((time.time() - started_ts) * 1000)
storage.write_stage(
    run_id,
    stage,
    {
        "stage": stage,
        "node": node_name,
        "state_key": _state_key_for_node(node_name),  # see step 2
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "duration_ms": duration_ms,
        "value": _stage_summary_for_node(node_name, state),  # existing helper
    },
)
```

- [ ] **Step 2: Add the `_state_key_for_node` helper**

The framework's `propagate()` method populates a state dict. Each analyst stage writes its result under a known key. Add a small mapping near `_STAGE_MAP`:

```python
_NODE_STATE_KEY = {
    "market_analyst": "market_report",
    "social_analyst": "sentiment_report",
    "news_analyst": "news_report",
    "fundamentals_analyst": "fundamentals_report",
    "bull_researcher": "investment_debate_state.bull_history",
    "bear_researcher": "investment_debate_state.bear_history",
    "research_manager": "investment_plan",
    "trader": "trader_investment_plan",
    "risky_analyst": "risk_debate_state.risky_history",
    "safe_analyst": "risk_debate_state.safe_history",
    "neutral_analyst": "risk_debate_state.neutral_history",
    "risk_manager": "final_trade_decision",
}


def _state_key_for_node(node_name: str) -> str:
    return _NODE_STATE_KEY.get(node_name, node_name)
```

(Note: the exact state keys are determined by the framework. Adjust this
mapping if the actual keys differ — open `tradingagents/graph/trading_graph.py`
and grep for the keys the nodes write into state. The mapping above is the
best current guess from the spec's exploration.)

- [ ] **Step 3: Update termination paths**

Wherever the existing code calls `db.mark_run_done(rid, ...)` and `db.update_watchlist_last_decision(...)`, replace with:

```python
storage.mark_run_status(
    run_id,
    status="done",
    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    decision_action=decision["action"],
    decision_target=decision.get("target"),
    decision_rationale=decision.get("rationale"),
    decision_confidence=decision.get("confidence"),
)
# Note: the framework's ``trading_graph.propagate()`` already calls
# ``clear_checkpoint(data_cache_dir, ticker, date)`` on successful
# completion (see tradingagents/graph/trading_graph.py:549). We do NOT
# duplicate that call here.
from . import queries
queries.update_last_decision(
    ticker,
    run_id,
    decision_summary,
    datetime.now(timezone.utc),
)
```

Wherever it calls `db.mark_run_failed(rid, error)`, replace with `storage.mark_run_status(run_id, status="failed", finished_at=..., error=str(error))`.

Wherever it calls `db.request_cancellation(rid)`, no change is needed in the runner — the cancellation endpoint handles that.

- [ ] **Step 4: Cancel polling replaces `db.get_run(rid).cancel_requested`**

Find the cancel-check site (likely inside the main loop or after each step). Replace `db.get_run(rid).cancel_requested` with:

```python
run_json = storage.read_run(run_id) or {}
if run_json.get("cancel_requested"):
    storage.mark_run_status(
        run_id,
        status="cancelled",
        finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    events.emit(run_id, events.EventType.RUN_CANCELLED, {})
    return
```

- [ ] **Step 5: Verify no `db.` references remain in runner**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && Select-String -Path web\server\runner.py -Pattern "\bdb\." | Measure-Object`
Expected: `Count: 0`.

- [ ] **Step 6: Commit**

```bash
git add web/server/runner.py
git commit -m "feat(runner): per-stage file persistence + cancel via run.json"
```

---

## Task 12: `app.py` — endpoints, lifespan, WS handlers

**Files:**
- Modify: `web/server/app.py:1-404`

- [ ] **Step 1: Replace imports at the top of the file**

Replace the SQLModel/db import line with:

```python
from . import storage, queries, events, llm_calls, runner, settings as settings_mod
```

(Remove `from . import db`. Keep the rest of the imports as they are.)

- [ ] **Step 2: Update `lifespan` to drop the SQLite DB**

Find the `lifespan` async context manager. The `init_db()` call and `reap_stale_runs()` are gone. Replace with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Drop the legacy SQLite DB if present.
    s = settings_mod.get_settings()
    legacy = Path(s.db_path) if hasattr(s, "db_path") and s.db_path else None
    if legacy and legacy.exists():
        log.warning("removing legacy SQLite DB at %s (file-based storage only)", legacy)
        try:
            legacy.unlink()
        except OSError as exc:
            log.error("failed to remove legacy DB: %s", exc)
    storage.init_settings(data_dir=s.data_dir, cache_dir=s.cache_dir)
    # Mark any previously-running runs as failed (process restart recovery).
    for td in storage.walk_data_dir():
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
            rj = storage.read_json(sd / "run.json")
            if rj and rj.get("status") == "running":
                storage.mark_run_status(
                    rj["id"],
                    status="failed",
                    finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                )
                log.warning("reaped stale running run %s", rj["id"])
    # Start the runner worker.
    await runner.start()
    yield
    await runner.stop()
```

- [ ] **Step 3: Update `GET /api/watchlist`**

Find the handler and replace its body with:

```python
@app.get("/api/watchlist")
def list_watchlist() -> list[dict]:
    return [queries.watchlist_to_dict(r) for r in queries.read_watchlist()]
```

- [ ] **Step 4: Update `POST /api/watchlist`**

```python
@app.post("/api/watchlist", status_code=201)
def add_to_watchlist(body: WatchlistIn) -> dict:
    try:
        row = queries.add_ticker(body.ticker, body.company_name, body.exchange)
    except queries.DuplicateTicker:
        raise HTTPException(status_code=409, detail="ticker already on watchlist")
    return queries.watchlist_to_dict(row)
```

- [ ] **Step 5: Update `DELETE /api/watchlist/{ticker}`**

```python
@app.delete("/api/watchlist/{ticker}", status_code=204)
def remove_from_watchlist(ticker: str) -> Response:
    queries.remove_ticker(ticker)
    return Response(status_code=204)
```

- [ ] **Step 6: Update `POST /api/runs`**

```python
@app.post("/api/runs", status_code=202)
async def start_run(body: RunIn) -> dict:
    ticker = body.ticker.upper()
    if ticker not in {r["ticker"] for r in queries.read_watchlist()}:
        raise HTTPException(status_code=404, detail="ticker not on watchlist")
    date_str = storage.today_utc_iso()
    run_id = await runner.enqueue(ticker, date_str, force=bool(body.force))
    return {"run_id": run_id}
```

- [ ] **Step 7: Update `GET /api/tickers/{ticker}/runs`**

```python
@app.get("/api/tickers/{ticker}/runs")
def list_ticker_runs(ticker: str, limit: int = 50) -> list[dict]:
    rows = storage.list_ticker_runs(ticker.upper(), limit=limit)
    return [queries.run_to_dict(r) for r in rows]
```

- [ ] **Step 8: Update `GET /api/runs/{run_id}` and add the events/llm_calls subroutes**

```python
@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    rj = storage.read_run(run_id)
    if rj is None:
        raise HTTPException(status_code=404, detail="run not found")
    out = queries.run_to_dict(rj)
    out["events"] = [queries.event_to_dict(e, run_id) for e in storage.list_run_events(run_id)]
    out["llm_calls"] = [queries.llm_call_to_dict(c) for c in storage.list_run_llm_calls(run_id)]
    out["stages"] = _load_stages(run_id)
    return out
```

And the helper (placed near the other `_to_dict` helpers at the bottom):

```python
def _load_stages(run_id: str) -> list[dict]:
    rd = storage.read_run_dir(run_id)
    if rd is None:
        return []
    out = []
    for sp in sorted((rd / "stages").glob("*.json")):
        d = storage.read_json(sp) or {}
        out.append(d)
    return out
```

- [ ] **Step 9: Update `POST /api/runs/{run_id}/cancel`**

```python
@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    rj = storage.read_run(run_id)
    if rj is None:
        raise HTTPException(status_code=404, detail="run not found")
    storage.mark_run_status(run_id, cancel_requested=True)
    return queries.run_to_dict(storage.read_run(run_id))
```

- [ ] **Step 10: Update the WS handler for `/ws/runs/{run_id}`**

Drop the `?since=` param. On connect, replay the full `events.jsonl`. The existing code in `app.py` likely uses `_consume_run_stream`. Replace the handler body with:

```python
@app.websocket("/ws/runs/{run_id}")
async def ws_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    rj = storage.read_run(run_id)
    if rj is None:
        await ws.send_json({"type": "error", "detail": "run not found"})
        await ws.close()
        return
    # Replay all events for the run.
    for ev in storage.list_run_events(run_id):
        await ws.send_json(ev)
    events.subscribe(run_id, ws)
    try:
        while True:
            # Drain client messages; we don't act on them.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        events.unsubscribe(run_id, ws)
```

- [ ] **Step 11: Delete the legacy `_to_dict` helpers at the bottom of `app.py`**

`_run_to_dict`, `_event_to_dict`, `_llm_call_to_dict` move into `queries.py` (Tasks 5). Remove them from `app.py` and confirm no other code in `app.py` references them.

- [ ] **Step 12: Verify the app module imports cleanly**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "from web.server.app import app; print(len(app.routes), 'routes')"`
Expected: prints a non-zero route count with no ImportError.

- [ ] **Step 13: Commit**

```bash
git add web/server/app.py
git commit -m "refactor(app): file-backed storage, drop SQLite, full event replay"
```

---

## Task 13: delete `db.py` and `test_db.py`

**Files:**
- Delete: `web/server/db.py`
- Delete: `web/server/tests/test_db.py`

- [ ] **Step 1: Remove the files**

Run:
```bash
git rm web/server/db.py web/server/tests/test_db.py
```

- [ ] **Step 2: Verify no other imports remain**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && rg "from \.db|from web\.server\.db|import .*db" web/server/ web/frontend/src/ 2>&1 || Select-String -Path web\server -Recurse -Pattern "from \.db\b|from web\.server\.db\b" | Measure-Object`
Expected: zero matches.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove legacy SQLModel db.py"
```

---

## Task 14: `conftest.py` — switch from `temp_db` to `data_root`

**Files:**
- Modify: `web/server/tests/conftest.py`

- [ ] **Step 1: Read the current `conftest.py`**

Open `web/server/tests/conftest.py` and identify the `temp_db` fixture and the `client` / `app` fixtures that depend on it.

- [ ] **Step 2: Replace `temp_db` with `data_root`**

Remove the SQLModel setup (any `init_db()` call, `Settings(db_path=...)`, `monkeypatch.setenv("TRADINGAGENTS_DASHBOARD_DB", ...)`, SQLModel.metadata.create_all). Replace with:

```python
import pytest
from pathlib import Path
from web.server import storage, settings as settings_mod


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Per-test data dir under tmp_path. Sets env vars + inits storage."""
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("TRADINGAGENTS_DATA_DIR", str(data))
    monkeypatch.setenv("TRADINGAGENTS_CACHE_DIR", str(cache))
    storage.init_settings(data_dir=str(data), cache_dir=str(cache))
    return data


@pytest.fixture
def client(data_root):
    """FastAPI TestClient with the file-backed storage configured."""
    from fastapi.testclient import TestClient
    from web.server.app import app
    with TestClient(app) as c:
        yield c
```

- [ ] **Step 3: Remove any other SQLite-specific fixtures**

If the file has additional fixtures (e.g. `app_with_db`, `seeded_db`), delete them. Search the test suite for `temp_db` usage and remove those references (we'll touch each test file in Task 15).

- [ ] **Step 4: Verify the conftest imports**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -c "import web.server.tests.conftest as c; print(c.data_root.__doc__[:60])"`
Expected: prints first line of the docstring.

- [ ] **Step 5: Commit**

```bash
git add web/server/tests/conftest.py
git commit -m "test(conftest): data_root fixture replaces temp_db"
```

---

## Task 15: backend test adaptations

This task covers five test files. Run them after each step.

### 15a. `tests/test_events.py`

**Files:**
- Modify: `web/server/tests/test_events.py`

- [ ] **Step 1: Replace the SQLModel-backed assertions**

Find the test that calls `events.emit(...)` and asserts on the persisted event. Change to read the JSONL file. The full set of tests in this file is small; replace the whole file with:

```python
"""Unit tests for events.py + storage.append_run_event."""
from __future__ import annotations

import pytest

from web.server import events, storage


def test_emit_writes_event_jsonl(data_root, tmp_path):
    info = storage.create_run_dir("NVDA")
    events.emit(info["run_id"], events.EventType.RUN_QUEUED, {"x": 1})
    lines = (tmp_path / "data" / "NVDA" / info["slug"] / "events.jsonl").read_text().splitlines()
    assert len(lines) == 1
    import json
    ev = json.loads(lines[0])
    assert ev["type"] == "run_queued"
    assert ev["run_id"] == info["run_id"]
    assert ev["data"] == {"x": 1}


def test_emit_for_unknown_run_does_not_raise(data_root, caplog):
    events.emit("NVDA:nonexistent", events.EventType.RUN_QUEUED, {})
    # No exception, no file created.
    assert not (data_root / "NVDA").exists()


def test_make_event_has_utc_timestamp():
    ev = events.make_event("NVDA:r", events.EventType.ANALYST_THINKING, {"k": 1})
    assert ev["ts"].endswith("Z")
    assert ev["type"] == "analyst_thinking"
    assert ev["data"] == {"k": 1}


def test_event_type_values_are_strings():
    assert events.EventType.RUN_DONE.value == "run_done"
    assert events.EventType.ANALYST_COMPLETED.value == "analyst_completed"
```

- [ ] **Step 2: Run the test file**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_events.py -v`
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add web/server/tests/test_events.py
git commit -m "test(events): file-backed event assertions"
```

### 15b. `tests/test_ws.py`

**Files:**
- Modify: `web/server/tests/test_ws.py`

- [ ] **Step 1: Switch to file-backed fixtures**

Replace any SQLite seeding with `storage.create_run_dir(ticker)` and `storage.append_run_event(...)`. For the WS test that asserts "replay since=ID", delete that assertion — v1 always replays from the start of `events.jsonl`.

- [ ] **Step 2: Add a regression test for full replay**

Append a new test at the end of the file:

```python
def test_ws_replay_sends_all_events(data_root, client):
    from web.server import storage, events
    info = storage.create_run_dir("NVDA")
    for i in range(3):
        events.emit(info["run_id"], events.EventType.ANALYST_THINKING, {"i": i})
    with client.websocket_connect(f"/ws/runs/{info['run_id']}") as ws:
        msgs = [ws.receive_json() for _ in range(3)]
    assert [m["data"]["i"] for m in msgs] == [0, 1, 2]
```

- [ ] **Step 3: Run the test file**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_ws.py -v`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add web/server/tests/test_ws.py
git commit -m "test(ws): full event.jsonl replay"
```

### 15c. `tests/test_app.py`

**Files:**
- Modify: `web/server/tests/test_app.py`

- [ ] **Step 1: Find all integer `run_id` literals and `assert run["id"] == 1` patterns**

For each, replace with the new string format. The pattern is: any test that creates a run via `client.post("/api/runs", json={...})` then reads the response should now expect a string like `"NVDA:2026-06-03T11:30:00.000000Z"`. Use a helper:

```python
def _run_id_for(ticker: str, when_iso: str) -> str:
    return f"{ticker.upper()}:{when_iso}"
```

- [ ] **Step 2: Update the `/api/runs` response test**

```python
def test_post_runs_returns_string_run_id(data_root, client):
    client.post("/api/watchlist", json={"ticker": "NVDA", "company_name": "NVIDIA", "exchange": "NASDAQ"})
    r = client.post("/api/runs", json={"ticker": "NVDA"})
    assert r.status_code == 202
    body = r.json()
    assert isinstance(body["run_id"], str)
    assert body["run_id"].startswith("NVDA:")
```

- [ ] **Step 3: Update the cancel endpoint test**

`POST /api/runs/{run_id}/cancel` body is now a dict (was a row from SQLModel). Just check `response.json()["status"] == "cancelled"` after the cancel call.

- [ ] **Step 4: Run the test file**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_app.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add web/server/tests/test_app.py
git commit -m "test(app): string run_id, file-backed responses"
```

### 15d. `tests/test_runner.py`

**Files:**
- Modify: `web/server/tests/test_runner.py`

This is the largest adaptation. The existing tests use `FakeTradingAgents` to drive a scripted graph; they assert on SQLModel rows. Approach: keep the fake graph exactly as it is (it doesn't touch the DB), and only change the assertions that read the DB.

- [ ] **Step 1: Update the run-creation assertion**

Where the test currently calls `db.get_run(rid)` and asserts the status, replace with:

```python
from web.server import storage
rj = storage.read_run(run_id)
assert rj["status"] == "done"
```

- [ ] **Step 2: Update the events assertion**

Where the test asserts `len(events_for_run(rid)) == N`, replace with:

```python
assert len(storage.list_run_events(run_id)) == N
```

- [ ] **Step 3: Add a new test: resume picks up an existing partial**

```python
import pytest
from web.server import runner, storage


@pytest.mark.asyncio
async def test_enqueue_resumes_today_partial(data_root):
    # Seed a partial run dir.
    info = storage.create_run_dir("NVDA")
    # enqueue() with no force should return the same run_id.
    rid = await runner.enqueue("NVDA", storage.today_utc_iso(), force=False)
    assert rid == info["run_id"]
    # No new dir created.
    ticker_dir = data_root / "NVDA"
    assert len([p for p in ticker_dir.iterdir() if p.is_dir()]) == 1


@pytest.mark.asyncio
async def test_enqueue_force_starts_new_run(data_root):
    info = storage.create_run_dir("NVDA")
    new_rid = await runner.enqueue("NVDA", storage.today_utc_iso(), force=True)
    assert new_rid != info["run_id"]
    old = storage.read_run(info["run_id"])
    assert old["status"] == "superseded"
    ticker_dir = data_root / "NVDA"
    assert len([p for p in ticker_dir.iterdir() if p.is_dir()]) == 2


@pytest.mark.asyncio
async def test_enqueue_idempotent_for_done_today(data_root):
    info = storage.create_run_dir("NVDA")
    storage.mark_run_status(info["run_id"], status="done")
    rid = await runner.enqueue("NVDA", storage.today_utc_iso(), force=False)
    assert rid == info["run_id"]
    # No new dir.
    ticker_dir = data_root / "NVDA"
    assert len([p for p in ticker_dir.iterdir() if p.is_dir()]) == 1


@pytest.mark.asyncio
async def test_enqueue_starts_fresh_when_no_partial(data_root):
    rid = await runner.enqueue("NVDA", storage.today_utc_iso(), force=False)
    assert rid.startswith("NVDA:")
    assert (data_root / "NVDA").is_dir()
```

- [ ] **Step 4: Run the test file**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_runner.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add web/server/tests/test_runner.py
git commit -m "test(runner): resume/force/idempotent enqueue"
```

### 15e. `tests/test_callbacks.py`

**Files:**
- Modify: `web/server/tests/test_callbacks.py` (only if needed)

- [ ] **Step 1: Inspect for `db.` references**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && Select-String -Path web\server\tests\test_callbacks.py -Pattern "\bdb\." | Measure-Object`

- [ ] **Step 2: If `Count: 0` (likely), no changes needed**

If there are no `db.` calls, the file works as-is — the callbacks module accepts an injected `save_call` and doesn't touch storage directly.

- [ ] **Step 3: If changes are needed, swap to a captured `save_call`**

Replace any `monkeypatch.setattr(llm_calls, "save_llm_call", ...)` lines with a captured list:

```python
calls: list[dict] = []
def fake_save(*args, **kwargs):
    calls.append(kwargs)
# when constructing the callback handler:
handler = CaptureCallbackHandler(save_call=fake_save)
assert len(calls) == 1
```

- [ ] **Step 4: Run the test file**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests/test_callbacks.py -v`
Expected: all green.

- [ ] **Step 5: Commit (only if there are changes)**

```bash
git add web/server/tests/test_callbacks.py
git commit -m "test(callbacks): use captured save_call instead of db"
```

---

## Task 16: frontend `lib/api.ts` + `store/ui.ts` — string run IDs

**Files:**
- Modify: `web/frontend/src/lib/api.ts`
- Modify: `web/frontend/src/store/ui.ts`

- [ ] **Step 1: Change `RunRow.id` from `number` to `string`**

In `web/frontend/src/lib/api.ts`:

```ts
export interface RunRow {
  id: string;             // was: number
  ticker: string;
  slug: string;           // NEW: human-readable dir name (e.g. "2026-06-03_14-30-00_IDT")
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  cancel_requested: boolean;
  decision_action: DecisionAction | null;
  decision_target: number | null;
  decision_rationale: string | null;
  decision_confidence: number | null;
}

export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "superseded";
```

Also: `fetchRunDetail` is unchanged in shape; just the response contains string `id` now.

- [ ] **Step 2: Add a helper to build a `run_id` for the API client**

At the bottom of `lib/api.ts`:

```ts
export function buildRunId(ticker: string, startedAtIso: string): string {
  return `${ticker.toUpperCase()}:${startedAtIso}`;
}
```

(This is used in tests; the server is the source of truth for run_ids.)

- [ ] **Step 3: Update `store/ui.ts`**

Open `web/frontend/src/store/ui.ts`. Change every `Record<string, number | null>` to `Record<string, string | null>`. Specifically:

```ts
lastRunIdByTicker: Record<string, string | null>;
historicalRunIdByTicker: Record<string, string | null>;
activeRunIdByTicker: Record<string, string | null>;
```

(If a `persist` middleware is configured, run `localStorage.clear()` once during dev to drop the old numeric-typed map — or bump the persisted version key.)

- [ ] **Step 4: Update the hook param types**

`useRunStream`, `useFocusedRunEvents`, `useRestoredRunEvents` all take a `runId: string` (already the case in TypeScript). If they currently cast it, drop the cast. No other changes.

- [ ] **Step 5: Run the type check**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend && npm run typecheck`
Expected: no TS errors.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/lib/api.ts web/frontend/src/store/ui.ts
git commit -m "feat(frontend): string run_id throughout"
```

---

## Task 17: frontend — Resume button + incomplete hint

**Files:**
- Modify: `web/frontend/src/components/TickerHeader.tsx`
- Modify: `web/frontend/src/components/DecisionPanel.tsx` (small)
- Modify: `web/frontend/src/hooks/useFocusedRunEvents.ts`

- [ ] **Step 1: Add a "Resume" button in `TickerHeader.tsx`**

When the history dropdown shows a run with `status === "running"` and `started_at` is today, add a `Resume` button next to it. The button calls:

```ts
await startRun({ ticker, force: false });  // server's enqueue does the resume
```

The server's `enqueue()` is already idempotent and resume-aware (Task 10), so the client just calls the same `startRun` with `force=false`.

- [ ] **Step 2: Show an "incomplete" hint in `DecisionPanel.tsx`**

Add a small banner above the decision when `run.status === "running"`:

```tsx
{run.status === "running" && (
  <div className="incomplete-hint">
    This run was interrupted. Click <b>Resume</b> in the header to continue.
  </div>
)}
```

- [ ] **Step 3: Update `useFocusedRunEvents.ts` to clear buffer on WS mount**

To prevent duplicate events when switching from REST-replay to live WS, clear the buffer for the runId before subscribing:

```ts
useEffect(() => {
  if (!runId) return;
  // Clear any stale events for this runId; the WS will replay the full log.
  useUIStore.getState().clearEventBuffer(runId);
}, [runId]);
```

(`clearEventBuffer` is a small new action on the Zustand store; add it if it doesn't exist.)

- [ ] **Step 4: Add a unit test for the resume button visibility**

In `web/frontend/src/components/TickerHeader.test.tsx` (create if missing):

```tsx
import { render, screen } from "@testing-library/react";
import { TickerHeader } from "./TickerHeader";

const baseRun = {
  id: "NVDA:2026-06-03T11:30:00.000000Z",
  ticker: "NVDA",
  slug: "2026-06-03_14-30-00_IDT",
  started_at: "2026-06-03T11:30:00.000000Z",
  finished_at: null,
  status: "running" as const,
  cancel_requested: false,
  decision_action: null,
  decision_target: null,
  decision_rationale: null,
  decision_confidence: null,
};

test("shows Resume button for today's incomplete run", () => {
  render(<TickerHeader ticker="NVDA" focusedRun={baseRun} todayIso="2026-06-03" />);
  expect(screen.getByRole("button", { name: /resume/i })).toBeInTheDocument();
});

test("hides Resume button for completed run", () => {
  render(<TickerHeader ticker="NVDA" focusedRun={{ ...baseRun, status: "done" }} todayIso="2026-06-03" />);
  expect(screen.queryByRole("button", { name: /resume/i })).toBeNull();
});
```

(Adjust the `TickerHeader` props to match its real signature; pass through a stub `onResume` and `onRerun` callback prop.)

- [ ] **Step 5: Run the frontend tests**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend && npm test -- --run`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/components/TickerHeader.tsx web/frontend/src/components/DecisionPanel.tsx web/frontend/src/hooks/useFocusedRunEvents.ts web/frontend/src/components/TickerHeader.test.tsx
git commit -m "feat(frontend): resume button + incomplete hint + buffer clear"
```

---

## Final verification

- [ ] **Step 1: Run the full backend test suite**

Run: `cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents && python -m pytest web/server/tests -v`
Expected: all green.

- [ ] **Step 2: Run the frontend type check + tests**

Run:
```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend && npm run typecheck
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents\web\frontend && npm test -- --run
```
Expected: no errors.

- [ ] **Step 3: Smoke-run the server and hit the endpoints**

```bash
cd C:\Users\Ido\Desktop\Projects\agents\TradingAgents
python -m web.server.app
# in another shell:
curl -s http://localhost:8000/api/watchlist
```
Expected: returns `[]` (and the legacy `~/.tradingagents/dashboard.db` is deleted at startup if it existed).

- [ ] **Step 4: Final commit (if any uncommitted changes)**

```bash
git status
# if anything is dirty:
git add -A
git commit -m "chore: file-based storage migration complete"
```

---

<!-- PLAN_END -->




