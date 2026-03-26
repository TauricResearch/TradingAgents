import json
import os
from pathlib import Path
from tradingagents.report_paths import REPORTS_ROOT

class LessonStore:
    """Append-only JSON store for screening lessons.

    Deduplicates on (ticker, scan_date, horizon_days).
    Atomic writes: write to .tmp, then os.replace().
    """
    DEFAULT_PATH = REPORTS_ROOT / "memory" / "selection_lessons.json"

    def __init__(self, path: Path | str | None = None):
        if path is None:
            self.path = self.DEFAULT_PATH
        else:
            self.path = Path(path)

        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load_all(self) -> list[dict]:
        """Returns all lessons, or [] if file is missing."""
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []

    def append(self, lessons: list[dict]) -> int:
        """Appends lessons, skipping duplicates. Returns count added."""
        if not lessons:
            return 0

        existing_lessons = self.load_all()
        existing_keys = {
            (l.get("ticker"), l.get("scan_date"), l.get("horizon_days"))
            for l in existing_lessons
        }

        to_add = []
        for l in lessons:
            key = (l.get("ticker"), l.get("scan_date"), l.get("horizon_days"))
            if key not in existing_keys:
                to_add.append(l)
                existing_keys.add(key)

        if not to_add:
            return 0

        new_lessons = existing_lessons + to_add

        tmp_path = self.path.with_suffix('.tmp')
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(new_lessons, f, indent=2)

        os.replace(tmp_path, self.path)

        return len(to_add)

    def clear(self) -> None:
        """Clears the store (for test isolation)."""
        if self.path.exists():
            self.path.unlink()
