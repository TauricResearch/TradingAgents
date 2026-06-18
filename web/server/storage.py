"""File-based storage primitives for the dashboard.

This module owns all on-disk IO for the dashboard. Higher-level
read-side helpers that shape data for the API live in ``queries.py``.

All timestamps in persisted files are UTC ISO-8601 with ``Z`` suffix.
The only Israel-local representation is the run directory slug,
which is purely for human readability.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

from tradingagents.dataflows.utils import safe_ticker_component


# Module-level settings path; populated by ``init_settings()`` at app startup
# so tests can monkeypatch a temp dir before any storage call.
_settings = {"data_dir": "", "cache_dir": ""}

# Cache mapping run_id → run directory path, avoiding O(n) directory walks.
# Populated lazily by ``_find_run_dir``.
_run_dir_cache: dict[str, Path] = {}


def clear_run_dir_cache() -> None:
    """Drop the run directory cache.  Tests use this between scenarios."""
    _run_dir_cache.clear()


def init_settings(*, data_dir: str, cache_dir: str) -> None:
    """Configure storage paths. Called from app lifespan / conftest."""
    _settings["data_dir"] = data_dir
    _settings["cache_dir"] = cache_dir
    _run_dir_cache.clear()
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


def ticker_runs_dir(ticker: str, date_iso: str) -> Path:
    """Return ``data/{ticker}/{date_iso}/`` (creating it).

    Each call for this (ticker, date) will create a sub-run dir under this
    path, so a date can have multiple run attempts (resume-safety).
    """
    safe = safe_ticker_component(ticker).upper()
    p = data_dir() / safe / date_iso
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---- atomic JSON ----

# On Windows, antivirus / search indexer / the OS file-locking policy
# can briefly hold a read handle on the dest file even after the
# previous writer closed. os.replace then fails with errno 5 (Access
# denied) or errno 32 (sharing violation). A short retry resolves the
# vast majority of these races; the unlink+rename fallback handles
# the rare case where the lock is held longer.
_ATOMIC_REPLACE_DELAYS: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1)


def _replace_with_retry(tmp: str, path: Path) -> None:
    """``os.replace`` that survives transient Windows file locks.

    Retries with exponential backoff on ``PermissionError`` (errno 5) or
    ``OSError`` with ``winerror`` 5/32 (sharing violation). If all
    retries fail, falls back to ``os.unlink(path)`` + ``os.rename(tmp, path)``
    so the write eventually lands. If the fallback also fails, re-raises
    the original lock error so the caller knows the write was lost.
    """
    last_exc: OSError | None = None
    for delay in _ATOMIC_REPLACE_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            last_exc = exc
            continue
    # All retries exhausted: try the unlink+rename fallback.
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        if last_exc is not None:
            raise last_exc from None
        raise
    os.rename(tmp, path)


def write_json_atomic(path: Path | str, data: Any) -> None:
    """Write ``data`` as JSON to ``path`` atomically via tmp + os.replace.

    The replace step is retried to survive transient Windows file locks
    (see :func:`_replace_with_retry`); only an unrecoverable lock surfaces
    to the caller as ``PermissionError``.
    """
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
        _replace_with_retry(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path | str) -> Optional[Any]:
    """Return parsed JSON or ``None`` on missing/invalid.

    A corrupted file logs a WARNING before returning ``None`` so the
    caller doesn't silently overwrite a recoverable source of truth
    (e.g. the watchlist).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        import logging
        logging.getLogger(__name__).warning(
            "read_json: %s is malformed (%s); returning None", path, exc
        )
        return None


# ---- append-only JSONL ----

def append_jsonl(path: Path | str, obj: Any) -> None:
    """Append ``obj`` as a single JSON line. Creates parent dir if needed.

    Flushed but not ``fsync``'d: durable across process crashes, not
    guaranteed across power loss. A truncated last line (from a crash
    mid-write) is handled by ``read_jsonl``.
    """
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
    """Format a datetime as UTC ISO-8601 with ``Z`` suffix, always including microseconds."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


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


# ---- run directory helpers ----


def run_id_for(ticker: str, started_at: datetime) -> str:
    """Stable per-run identifier: ``TICKER:UTC_ISO_TIMESTAMP``."""
    return f"{safe_ticker_component(ticker).upper()}:{utc_iso(started_at)}"


def today_utc_iso() -> str:
    """Today as a UTC ISO date (the framework's ``trade_date`` value)."""
    return datetime.now(timezone.utc).date().isoformat()


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

    All fields are written on creation; older ``run.json`` files that
    pre-date this change will simply not have these keys, so consumers
    must use ``.get()``.

    Fields:
      llm_provider:     str, LLM provider used (e.g. "openai")
      deep_think_model: str, model for deep reasoning calls
      quick_think_model: str, model for quick reasoning calls
      start_price:      float, ticker price at run start (None until populated)
      start_price_at:   ISO-8601 UTC string, timestamp of start_price
      total_duration_s: float|None, set when run finishes; None while running
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
    _run_dir_cache[run_id] = run_dir
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


def read_run(run_id: str) -> Optional[dict]:
    """Find and parse run.json for ``run_id``.

    Walks all ticker dirs to locate the dir whose run.json's id matches.
    Returns ``None`` if not found.  Results are cached so subsequent
    lookups avoid the directory walk.
    """
    rd = _find_run_dir(run_id)
    if rd is None:
        return None
    return read_json(rd / "run.json")


def _find_run_dir(run_id: str) -> Optional[Path]:
    """Locate the run directory for ``run_id``, using and populating the cache."""
    cached = _run_dir_cache.get(run_id)
    if cached is not None and cached.exists():
        return cached
    for td in data_dir().iterdir():
        if not td.is_dir():
            continue
        for sd in td.iterdir():
            if not sd.is_dir():
                continue
            rj = read_json(sd / "run.json")
            if rj and rj.get("id") == run_id:
                _run_dir_cache[run_id] = sd
                return sd
    return None


def read_run_dir(run_id: str) -> Optional[Path]:
    """Return the directory Path for ``run_id`` (results cached after first lookup)."""
    rd = _find_run_dir(run_id)
    if rd is not None:
        return rd
    dd = data_dir()
    log.warning(
        "read_run_dir: run %s not found under %s; ticker dirs: %s",
        run_id, dd,
        [str(td.name) for td in dd.iterdir() if td.is_dir()],
    )
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


def delete_run(run_id: str) -> bool:
    """Remove the on-disk directory for ``run_id``.

    Returns ``True`` if the directory was found and removed, ``False`` if
    the run did not exist (so callers can treat missing runs as success
    without raising).
    """
    rd = _find_run_dir(run_id)
    if rd is None or not rd.exists():
        return False
    shutil.rmtree(rd)
    _run_dir_cache.pop(run_id, None)
    log.info("deleted run dir for %s: %s", run_id, rd)
    return True


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


TICKER_AGENT_DIR = "ticker_agent"


def ticker_agent_dir() -> Path:
    p = data_dir() / TICKER_AGENT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def ticker_agent_path(name: str) -> Path:
    return ticker_agent_dir() / name
