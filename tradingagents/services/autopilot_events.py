from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _utcnow() -> str:
    return datetime.utcnow().strftime(ISO_FORMAT)


@dataclass
class HypothesisEvent:
    id: str
    hypothesis_id: str
    event_type: str
    payload: Dict[str, Any]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "hypothesis_id": self.hypothesis_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HypothesisEvent":
        return cls(
            id=str(payload.get("id") or uuid.uuid4().hex),
            hypothesis_id=str(payload.get("hypothesis_id") or ""),
            event_type=str(payload.get("event_type") or "unknown"),
            payload=dict(payload.get("payload") or {}),
            created_at=str(payload.get("created_at") or _utcnow()),
        )


class AutopilotEventQueue:
    def __init__(self, root_dir: Path) -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "events.json"

    def enqueue(self, event: HypothesisEvent) -> None:
        events = self._load()
        events.append(event)
        self._save(events)

    def dequeue_all(self) -> List[HypothesisEvent]:
        events = self._load()
        self._save([])
        return events

    def list(self) -> List[HypothesisEvent]:
        return self._load()

    def _load(self) -> List[HypothesisEvent]:
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError:
                payload = []
        return [HypothesisEvent.from_dict(item) for item in payload or []]

    def _save(self, events: List[HypothesisEvent]) -> None:
        serializable = [event.to_dict() for event in events]
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(serializable, handle, indent=2)
        tmp.replace(self.path)
