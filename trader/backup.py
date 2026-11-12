"""A copy of the account directory that can be restored.

The ledgers of the daily, intraday, demo and live accounts are in WAL mode (Issue #12):
the latest commits sit in ``ledger.sqlite-wal`` until a checkpoint, so copying the main
file gives an old, possibly torn, snapshot. SQLite's backup API copies one consistent
committed state, without blocking the job that may be writing. Settings and the memory
log are plain files and are copied as such.

Only what LEDGERS, FILES and LOGS name is copied, never the directory as a whole: the
live account's key file, which may be kept there, stays out of every backup (ADR 0010).
"""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

LEDGERS = ("ledger.sqlite", "intraday/ledger.sqlite", "demo/ledger.sqlite", "live/ledger.sqlite")
FILES = ("settings.json", "memory")
LOGS = "logs"  # the research records: large and append-only, copied only when asked


def backup(
    home: Path, dest: Path, with_logs: bool = False, now: datetime | None = None
) -> tuple[Path, list[tuple[str, int]]]:
    """Copy the account directory ``home`` into ``dest/<UTC time>/`` and return that
    directory with (relative path, bytes) of each thing copied. What ``home`` lacks
    (an intraday, demo or live account not opened, no settings.json) is skipped;
    FileNotFoundError when it has nothing of an account, FileExistsError rather than
    touching a backup already at the target."""
    files = FILES + ((LOGS,) if with_logs else ())
    wanted = [rel for rel in LEDGERS + files if (home / rel).exists()]
    if not wanted:
        raise FileNotFoundError(f"{home} 里没有可备份的账户文件")
    target = dest / (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    if target.exists():
        raise FileExistsError(f"{target} 已存在，不覆盖已有的备份")
    target.mkdir(parents=True)
    return target, [
        (rel, (_snapshot if rel in LEDGERS else _copy)(home / rel, target / rel))
        for rel in wanted
    ]


def _snapshot(src: Path, out: Path) -> int:
    """The committed state of the database ``src``, as one self-contained file at
    ``out``: in rollback-journal mode, so that reading the copy needs no -wal/-shm files
    beside it (a writer that opens it switches it back to WAL)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=30)
    with closing(source), closing(sqlite3.connect(out)) as copy:
        source.backup(copy)
        copy.execute("PRAGMA journal_mode=DELETE")
    return out.stat().st_size


def _copy(src: Path, out: Path) -> int:
    if src.is_dir():
        shutil.copytree(src, out)
        return sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, out)
    return out.stat().st_size
