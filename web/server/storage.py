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
