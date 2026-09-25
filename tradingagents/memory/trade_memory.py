"""Three-tier JSONL memory store.

Rules from architecture:
- all modes append raw records;
- lesson memory is draft/hypothesis only;
- trade mode reads only validated global memory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from tradingagents.storage import SQLiteTradingStore


class CryptoMemoryStore:
    """Append-only store for raw, lesson, and global tiers.

    Defaults to the legacy JSONL layout.  Set
    ``TRADINGAGENTS_STORAGE_BACKEND=sqlite`` to persist the same memory records
    into normalized SQLite tables with selectable memory spaces.
    """

    def __init__(
        self,
        base_dir: str | Path = "~/.tradingagents/crypto_memory",
        storage_backend: Optional[str] = None,
        sqlite_path: Optional[str | Path] = None,
        user_id: Optional[str] = None,
        memory_space_id: Optional[str] = None,
    ):
        self.base_dir = Path(base_dir).expanduser()
        self.raw_dir = self.base_dir / "raw"
        self.lesson_dir = self.base_dir / "lessons"
        self.global_dir = self.base_dir / "global"
        for directory in (self.raw_dir, self.lesson_dir, self.global_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.raw_path = self.raw_dir / "raw.jsonl"
        self.lesson_path = self.lesson_dir / "lessons.jsonl"
        self.global_path = self.global_dir / "global.jsonl"
        self.storage_backend = str(storage_backend or os.getenv("TRADINGAGENTS_STORAGE_BACKEND") or "file").lower()
        self.user_id = str(user_id or os.getenv("TRADINGAGENTS_USER_ID") or "admin")
        self.memory_space_id = str(memory_space_id or os.getenv("TRADINGAGENTS_MEMORY_SPACE_ID") or "default")
        self.sqlite: Optional[SQLiteTradingStore] = None
        if self.storage_backend == "sqlite":
            db_path = Path(sqlite_path or os.getenv("TRADINGAGENTS_SQLITE_PATH") or self.base_dir / "tradingagents.db").expanduser()
            self.sqlite = SQLiteTradingStore(db_path, user_id=self.user_id)

    def append_raw(self, record: Dict) -> None:
        record = dict(record)
        record.setdefault("memory_tier", "raw")
        if self.sqlite:
            self.sqlite.append_memory("raw", record, memory_space_id=self.memory_space_id)
            return
        self._append(self.raw_path, record)

    def append_lesson(self, record: Dict) -> None:
        record = dict(record)
        record.setdefault("memory_tier", "lesson")
        record.setdefault("status", "draft")
        if self.sqlite:
            self.sqlite.append_memory("lesson", record, memory_space_id=self.memory_space_id)
            return
        self._append(self.lesson_path, record)

    def append_global(self, record: Dict) -> None:
        record = dict(record)
        record.setdefault("memory_tier", "global")
        record.setdefault("status", "validated")
        if self.sqlite:
            self.sqlite.append_memory("global", record, memory_space_id=self.memory_space_id)
            return
        self._append(self.global_path, record)

    def load_raw(self) -> List[Dict]:
        if self.sqlite:
            return self.sqlite.load_memory("raw", memory_space_id=self.memory_space_id)
        return self._read(self.raw_path)

    def load_lessons(self) -> List[Dict]:
        if self.sqlite:
            return self.sqlite.load_memory("lesson", memory_space_id=self.memory_space_id)
        return self._read(self.lesson_path)

    def load_global(self) -> List[Dict]:
        if self.sqlite:
            return self.sqlite.load_memory("global", memory_space_id=self.memory_space_id)
        return self._read(self.global_path)

    @staticmethod
    def _append(path: Path, record: Dict) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _read(path: Path) -> List[Dict]:
        if not path.exists():
            return []
        items: List[Dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items


class TradeMemory:
    """Read-only global memory view for trade mode."""

    def __init__(self, store: CryptoMemoryStore, max_items: int = 5):
        self.store = store
        self.max_items = max_items

    def get_global_context(self, symbol: Optional[str] = None) -> str:
        lessons = [item for item in self.store.load_global() if item.get("status") == "validated"]
        if symbol:
            exact = [item for item in lessons if symbol in item.get("coins_tested", []) or item.get("coin") == symbol]
            general = [item for item in lessons if item not in exact]
            lessons = exact + general
        lessons = lessons[-self.max_items:]
        if not lessons:
            return "No validated global lessons available. Trade mode should be conservative."
        lines = ["Validated global lessons (trade mode may use these only):"]
        for item in lessons:
            lines.append(
                f"- {item.get('lesson_id', 'global')}: {item.get('lesson')} "
                f"Recommendation: {item.get('recommendation', 'n/a')} "
                f"Confidence={item.get('confidence', 'n/a')} evidence={item.get('evidence_count', 'n/a')}"
            )
        return "\n".join(lines)