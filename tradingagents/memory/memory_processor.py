"""Raw → lesson processor for crypto training memory."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from .trade_memory import CryptoMemoryStore


class MemoryProcessor:
    """Create draft lessons from raw cases using simple grouped statistics."""

    def __init__(self, store: CryptoMemoryStore, min_cases: int = 5):
        self.store = store
        self.min_cases = min_cases

    def process(self) -> List[Dict]:
        raw = [item for item in self.store.load_raw() if item.get("result") in {"WIN", "LOSS"}]
        groups: Dict[Tuple[str, str, str, str], List[Dict]] = defaultdict(list)
        for item in raw:
            ctx = item.get("market_context") or {}
            key = (
                item.get("strategy", "unknown"),
                item.get("timeframe", "unknown"),
                ctx.get("market_regime", "unknown"),
                item.get("signal", "unknown"),
            )
            groups[key].append(item)

        existing_keys = {
            (lesson.get("strategy"), lesson.get("timeframe"), lesson.get("condition", {}).get("market_regime"), lesson.get("direction"))
            for lesson in self.store.load_lessons()
        }
        created: List[Dict] = []
        for key, cases in groups.items():
            if len(cases) < self.min_cases or key in existing_keys:
                continue
            wins = sum(1 for case in cases if case.get("result") == "WIN")
            win_rate = wins / len(cases)
            if 0.40 <= win_rate <= 0.60:
                continue
            strategy, timeframe, regime, direction = key
            confidence = round(max(win_rate, 1 - win_rate), 4)
            coins_tested = sorted(
                {
                    str(case.get("coin") or case.get("symbol") or case.get("ticker"))
                    for case in cases
                    if case.get("coin") or case.get("symbol") or case.get("ticker")
                }
            )
            lesson = {
                "lesson_id": f"lesson_draft_{len(self.store.load_lessons()) + len(created) + 1:04d}",
                "strategy": strategy,
                "timeframe": timeframe,
                "direction": direction,
                "condition": {"market_regime": regime},
                "lesson": (
                    f"{strategy} {direction} setups on {timeframe} in {regime} regime "
                    f"had win_rate={win_rate:.1%} over {len(cases)} reviewed cases."
                ),
                "recommendation": "Observe more cases before trade mode; this is a draft lesson only.",
                "confidence": confidence,
                "win_rate": round(win_rate, 4),
                "evidence_count": len(cases),
                "source_modes": sorted({case.get("mode_id", "unknown") for case in cases}),
                "coins_tested": coins_tested,
                "status": "draft",
                "memory_tier": "lesson",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.store.append_lesson(lesson)
            created.append(lesson)
        return created