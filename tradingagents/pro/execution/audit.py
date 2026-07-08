"""Immutable audit log: append-only JSONL with hash chaining.

Every entry commits to its predecessor (``hash = sha256(prev_hash +
canonical_entry)``), so any edit, deletion, or reordering of past entries
breaks verification. This is tamper-*evident* storage — pair it with
filesystem permissions/shipping for tamper resistance.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tradingagents.contracts import utc_now

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: str | Path | None = None):
        self._path = Path(path) if path else None
        self._entries: list[dict] = []
        if self._path and self._path.exists():
            with self._path.open(encoding="utf-8") as handle:
                self._entries = [json.loads(line) for line in handle if line.strip()]

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    @staticmethod
    def _digest(prev_hash: str, body: dict) -> str:
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()

    def append(self, event: str, payload: dict) -> dict:
        prev_hash = self._entries[-1]["hash"] if self._entries else GENESIS
        body = {
            "seq": len(self._entries),
            "ts": utc_now().isoformat(),
            "event": event,
            "payload": payload,
            "prev_hash": prev_hash,
        }
        entry = {**body, "hash": self._digest(prev_hash, body)}
        self._entries.append(entry)
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> bool:
        prev_hash = GENESIS
        for i, entry in enumerate(self._entries):
            body = {k: entry[k] for k in ("seq", "ts", "event", "payload", "prev_hash")}
            if entry["seq"] != i or entry["prev_hash"] != prev_hash:
                return False
            if entry["hash"] != self._digest(prev_hash, body):
                return False
            prev_hash = entry["hash"]
        return True
