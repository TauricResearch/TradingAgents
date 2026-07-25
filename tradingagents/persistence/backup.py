"""Server-controlled SQLite backup and restore workflow."""

from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .database import CURRENT_SCHEMA_VERSION, Database

BACKUP_ID = re.compile(r"^[0-9a-f-]{36}$")
REQUIRED_TABLES = {"analysis_jobs", "job_events", "reports", "advice_versions", "conversations", "usage_records", "source_observations", "trust_assessments", "provider_cache"}


@dataclass(frozen=True)
class RestorePreview:
    backup_id: str
    valid: bool
    compatible: bool
    schema_version: int | None
    created_at: str | None
    size_bytes: int | None
    reason: str | None = None


class BackupService:
    def __init__(self, database: Database, backup_dir: str | Path | None = None):
        self.database = database
        self.backup_dir = Path(backup_dir or database.path.parent / "backups")

    def create(self) -> RestorePreview:
        self.database.migrate()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_id = str(uuid.uuid4())
        target = self._path(backup_id)
        with self.database.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        return self.preview(backup_id)

    def list(self) -> list[RestorePreview]:
        if not self.backup_dir.exists():
            return []
        paths = sorted(
            self.backup_dir.glob("*.sqlite3"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return [self.preview(item.stem) for item in paths]

    def preview(self, backup_id: str) -> RestorePreview:
        path = self._path(backup_id)
        if not path.is_file():
            return RestorePreview(backup_id, False, False, None, None, None, "BACKUP_NOT_FOUND")
        try:
            uri = f"file:{path}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                version = Database.schema_version(conn)
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            valid = integrity == "ok" and tables >= REQUIRED_TABLES
            compatible = valid and version <= CURRENT_SCHEMA_VERSION
            reason = None if valid and compatible else ("SCHEMA_TOO_NEW" if valid else "CORRUPT_OR_INCOMPLETE")
            return RestorePreview(backup_id, valid, compatible, version, datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(), path.stat().st_size, reason)
        except sqlite3.DatabaseError:
            return RestorePreview(backup_id, False, False, None, None, path.stat().st_size, "CORRUPT_OR_INCOMPLETE")

    def restore(self, backup_id: str) -> RestorePreview:
        preview = self.preview(backup_id)
        if not preview.valid or not preview.compatible:
            raise ValueError(preview.reason or "INVALID_BACKUP")
        source_path = self._path(backup_id)
        with sqlite3.connect(f"file:{source_path}?mode=ro", uri=True) as source, self.database.connect() as target:
            source.backup(target)
        self.database.migrate()
        return preview

    def _path(self, backup_id: str) -> Path:
        if not BACKUP_ID.fullmatch(backup_id):
            raise ValueError("INVALID_BACKUP_ID")
        return self.backup_dir / f"{backup_id}.sqlite3"
