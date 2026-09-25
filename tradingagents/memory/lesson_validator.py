"""Lesson → global validator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from .trade_memory import CryptoMemoryStore


class LessonValidator:
    """Promote draft lessons to global only when architecture thresholds pass."""

    def __init__(
        self,
        store: CryptoMemoryStore,
        min_cases: int = 30,
        min_confidence: float = 0.8,
        min_source_modes: int = 2,
    ):
        self.store = store
        self.min_cases = min_cases
        self.min_confidence = min_confidence
        self.min_source_modes = min_source_modes

    def promote(self, reviewed_by: str = "human") -> List[Dict]:
        promoted: List[Dict] = []
        existing_ids = {item.get("source_lesson_id") for item in self.store.load_global()}
        for lesson in self.store.load_lessons():
            if lesson.get("lesson_id") in existing_ids:
                continue
            source_modes = lesson.get("source_modes") or []
            if int(lesson.get("evidence_count", 0)) < self.min_cases:
                continue
            if float(lesson.get("confidence", 0.0)) < self.min_confidence:
                continue
            if len(set(source_modes)) < self.min_source_modes:
                continue
            global_lesson = {
                "lesson_id": f"global_rule_{len(self.store.load_global()) + len(promoted) + 1:04d}",
                "source_lesson_id": lesson.get("lesson_id"),
                "strategy": lesson.get("strategy"),
                "timeframe": lesson.get("timeframe"),
                "condition": lesson.get("condition", {}),
                "lesson": lesson.get("lesson"),
                "recommendation": lesson.get("recommendation"),
                "confidence": lesson.get("confidence"),
                "evidence_count": lesson.get("evidence_count"),
                "source_modes": source_modes,
                "coins_tested": lesson.get("coins_tested", []),
                "memory_tier": "global",
                "status": "validated",
                "reviewed_by": reviewed_by,
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_global(global_lesson)
            promoted.append(global_lesson)
        return promoted