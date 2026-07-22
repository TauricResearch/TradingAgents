"""Full-fidelity per-run backtest artifacts on the persistent data dir.

Zero-loss record of a run: every equity point (per bar), every trade, and
every decision (the funnel row) live as JSON files under
``<data_dir>/backtest_runs/<run_id>/`` — nothing is downsampled or dropped.
The run metadata store (file or Firestore) holds only metrics + summaries;
these files are the bulk truth, streamed to the UI on demand.

Written incrementally during the run (atomic full-file rewrites on an
adaptive cadence — on the GCS-fuse mount appends re-upload the object
anyway, so bounded rewrites of the whole file are the honest cost model),
so a crash/restart preserves everything up to the last checkpoint.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

from tradingagents.pro.dashboard.prefs import default_data_dir

logger = logging.getLogger(__name__)

ARTIFACT_NAMES = ("equity", "trades", "decisions")


def artifacts_root(base_dir: str | Path | None = None) -> Path:
    return Path(base_dir) if base_dir else default_data_dir() / "backtest_runs"


class RunArtifacts:
    """Writer/reader for one run's artifact directory."""

    def __init__(self, run_id: str, base_dir: str | Path | None = None):
        self.run_id = run_id
        self.dir = artifacts_root(base_dir) / run_id

    # --- writing ---------------------------------------------------------------

    def write(self, *, equity: list[dict], trades: list[dict],
              decisions: list[dict]) -> None:
        """Atomic full snapshot of all three artifacts (crash-safe)."""
        from tradingagents.pro.persistence import atomic_write_text

        self.dir.mkdir(parents=True, exist_ok=True)
        for name, rows in (("equity", equity), ("trades", trades),
                           ("decisions", decisions)):
            atomic_write_text(self.dir / f"{name}.json",
                              json.dumps(rows, default=str))

    # --- reading ---------------------------------------------------------------

    def path(self, name: str) -> Path:
        if name not in ARTIFACT_NAMES:
            raise KeyError(name)
        return self.dir / f"{name}.json"

    def read(self, name: str) -> list[dict]:
        try:
            return json.loads(self.path(name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception:
            logger.warning("corrupt artifact %s for run %s", name, self.run_id)
            return []

    def exists(self) -> bool:
        return self.dir.is_dir()

    def delete(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def checkpoint_interval(total_decisions: int, use_llm: bool) -> int:
    """Artifact-write cadence: every 25 decisions for LLM runs (interruption
    is money) and for small runs; for big deterministic runs, bound the total
    number of full-file rewrites to ~200 so write volume stays O(n)."""
    if use_llm:
        return 25
    return max(25, total_decisions // 200)
