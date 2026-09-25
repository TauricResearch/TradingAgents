"""Round-robin Gemini API key selection for training workloads."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Iterable, List, Optional


_LOCK = threading.Lock()


def parse_google_api_keys(value: Optional[object]) -> List[str]:
    """Normalize Gemini API key configuration into a clean list."""
    if value is None:
        value = os.getenv("GOOGLE_API_KEYS") or os.getenv("GOOGLE_API_KEY")

    if isinstance(value, str):
        keys = [part.strip() for part in value.replace("\n", ",").split(",")]
    elif isinstance(value, Iterable):
        keys = [str(part).strip() for part in value]
    else:
        keys = []

    return [key for key in keys if key]


def _key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]


class GoogleApiKeyRotator:
    """Persisted round-robin selector for multiple Gemini API keys.

    The state file stores only a short hash of each key, never the raw secret.
    """

    def __init__(self, api_keys: Iterable[str], state_path: str):
        self.api_keys = list(api_keys)
        if not self.api_keys:
            raise ValueError("At least one Gemini API key is required")
        self.state_path = Path(state_path).expanduser()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    def next_key(self, role: str = "default") -> str:
        """Return the next API key and advance persisted usage state."""
        with _LOCK:
            state = self._load_state()
            key_ids = [_key_id(key) for key in self.api_keys]
            cursor = int(state.get("cursor", -1))
            next_index = (cursor + 1) % len(self.api_keys)
            selected_key = self.api_keys[next_index]
            selected_id = key_ids[next_index]

            usage = state.setdefault("usage", {})
            usage.setdefault(selected_id, {"requests": 0, "roles": {}})
            usage[selected_id]["requests"] += 1
            usage[selected_id].setdefault("roles", {})[role] = (
                usage[selected_id].setdefault("roles", {}).get(role, 0) + 1
            )

            state["cursor"] = next_index
            state["key_ids"] = key_ids
            self._save_state(state)
            return selected_key

    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {"cursor": -1, "usage": {}}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"cursor": -1, "usage": {}}

    def _save_state(self, state: dict) -> None:
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self.state_path)
