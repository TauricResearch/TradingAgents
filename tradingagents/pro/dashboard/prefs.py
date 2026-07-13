"""User preferences, watchlists, and notification read-state.

One JSON file, one lock, one atomic write: for a single-operator terminal
that is the smallest crash-consistent design. The file lives in the data
dir Docker/k8s already volume-mount (``TRADINGAGENTS_PRO_DATA``, default
``~/.tradingagents/pro``). A corrupt file logs a warning and starts from
defaults — a bad prefs file must never take the dashboard down.

``layouts`` stays a free-form dict: it is client-owned grid state; the
backend validates the envelope, not the widget geometry.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

MAX_NOTIFICATIONS = 500
MAX_DOCUMENT_BYTES = 256 * 1024


def default_data_dir() -> Path:
    return Path(
        os.environ.get("TRADINGAGENTS_PRO_DATA", Path.home() / ".tradingagents" / "pro")
    )


class _Mutable(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Watchlist(_Mutable):
    name: str = Field(min_length=1, max_length=64)
    symbols: list[str] = Field(default_factory=list, max_length=100)


class Notification(_Mutable):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: str = "info"
    event: str = ""
    text: str = ""
    time: str = ""
    read: bool = False


class SavedView(_Mutable):
    name: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=512)


class UserPrefs(_Mutable):
    theme: str = "light"
    default_symbol: str = "BTC-USD"
    layouts: dict[str, Any] = Field(default_factory=dict)
    views: list[SavedView] = Field(default_factory=list, max_length=50)
    muted_events: list[str] = Field(default_factory=list, max_length=100)
    version: int = 1


class PrefsDocument(_Mutable):
    prefs: UserPrefs = Field(default_factory=UserPrefs)
    watchlists: list[Watchlist] = Field(default_factory=list)
    notifications: list[Notification] = Field(default_factory=list)


class PrefsStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_data_dir() / "dashboard_prefs.json"
        self._lock = threading.Lock()
        self._document = self._load()

    # --- persistence -------------------------------------------------------------

    def _load(self) -> PrefsDocument:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return PrefsDocument()
        try:
            return PrefsDocument.model_validate_json(raw)
        except Exception:
            logger.warning("corrupt prefs file %s; starting from defaults", self.path)
            return PrefsDocument()

    def _write(self) -> None:
        from tradingagents.pro.persistence import atomic_write_text

        atomic_write_text(self.path, self._document.model_dump_json(indent=1))

    # --- prefs -------------------------------------------------------------------

    def get_prefs(self) -> dict:
        with self._lock:
            return self._document.prefs.model_dump()

    def put_prefs(self, data: dict) -> dict:
        prefs = UserPrefs.model_validate(data)  # 422s bubble via caller
        with self._lock:
            self._document.prefs = prefs
            self._write()
            return prefs.model_dump()

    # --- watchlists --------------------------------------------------------------

    def watchlists(self) -> list[dict]:
        with self._lock:
            return [w.model_dump() for w in self._document.watchlists]

    def upsert_watchlist(self, data: dict) -> dict:
        watchlist = Watchlist.model_validate(data)
        with self._lock:
            existing = [w for w in self._document.watchlists
                        if w.name != watchlist.name]
            existing.append(watchlist)
            self._document.watchlists = existing
            self._write()
            return watchlist.model_dump()

    def delete_watchlist(self, name: str) -> bool:
        with self._lock:
            before = len(self._document.watchlists)
            self._document.watchlists = [
                w for w in self._document.watchlists if w.name != name
            ]
            changed = len(self._document.watchlists) != before
            if changed:
                self._write()
            return changed

    # --- notifications -----------------------------------------------------------

    def add_notification(self, severity: str, event: str, text: str,
                         time: str = "") -> dict:
        note = Notification(severity=severity, event=event, text=text, time=time)
        with self._lock:
            self._document.notifications.append(note)
            del self._document.notifications[:-MAX_NOTIFICATIONS]
            self._write()
            return note.model_dump()

    def notifications(self, unread_only: bool = False) -> list[dict]:
        with self._lock:
            notes = self._document.notifications
            if unread_only:
                notes = [n for n in notes if not n.read]
            return [n.model_dump() for n in reversed(notes)]  # newest first

    def mark_read(self, ids: list[str] | None = None) -> int:
        """Empty/None ids = mark everything read. Returns count changed."""
        with self._lock:
            targets = set(ids or [])
            changed = 0
            for note in self._document.notifications:
                if note.read or (targets and note.id not in targets):
                    continue
                note.read = True
                changed += 1
            if changed:
                self._write()
            return changed


class NotificationSink:
    """AlertManager sink persisting alerts as dashboard notifications."""

    def __init__(self, store: PrefsStore):
        self.store = store

    def deliver(self, alert) -> None:
        self.store.add_notification(
            severity=alert.severity, event=alert.event,
            text=alert.text, time=alert.time,
        )
