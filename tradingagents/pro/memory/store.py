"""Append-only JSONL persistence for memory records.

One JSON object per line; writes are append+flush so a crash loses at most
the record being written. Mirrors the base framework's philosophy of a
human-inspectable memory file, in a machine-friendly shape.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from tradingagents.pro.memory.records import MemoryRecord

logger = logging.getLogger(__name__)


class JsonlStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: MemoryRecord) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
            handle.flush()

    def load(self) -> list[MemoryRecord]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(MemoryRecord.model_validate(json.loads(line)))
                except Exception:
                    logger.warning("skipping corrupt memory line %d in %s",
                                   line_no, self.path)
        return records
