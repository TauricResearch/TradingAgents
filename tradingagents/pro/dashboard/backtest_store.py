"""Persisted history of completed interactive backtest runs.

One JSON file, one lock, one atomic write — the same crash-consistent shape
as ``PrefsStore``. A bounded ring (newest last) auto-archives the previous run
whenever a new one completes, so "save the last run before starting a new one"
needs no explicit step and nothing is lost. A corrupt file logs a warning and
starts empty — a bad history file must never take the dashboard down.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from tradingagents.pro.dashboard.prefs import default_data_dir

logger = logging.getLogger(__name__)

MAX_RUNS = 25


class BacktestRunStore:
    def __init__(self, path: str | Path | None = None, max_runs: int = MAX_RUNS):
        self.path = Path(path) if path else default_data_dir() / "backtest_runs.json"
        self.max_runs = max_runs
        self._lock = threading.Lock()
        self._runs: list[dict] = self._load()

    def _load(self) -> list[dict]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return []
        try:
            data = json.loads(raw)
            runs = data.get("runs", []) if isinstance(data, dict) else []
            return runs if isinstance(runs, list) else []
        except Exception:
            logger.warning("corrupt backtest history %s; starting empty", self.path)
            return []

    def _write(self) -> None:
        from tradingagents.pro.persistence import atomic_write_text

        atomic_write_text(self.path, json.dumps({"runs": self._runs}, default=str))

    def save(self, record: dict) -> dict:
        """Append a completed run; drop the oldest beyond ``max_runs``."""
        with self._lock:
            self._runs.append(record)
            del self._runs[: -self.max_runs]  # keep newest max_runs
            self._write()
            return record

    def list(self) -> list[dict]:
        """Lightweight metadata for the run picker (newest first)."""
        with self._lock:
            out = []
            for r in reversed(self._runs):
                if r.get("summary"):  # written by current runs
                    out.append(dict(r["summary"]))
                    continue
                # legacy records predate the summary field
                view = r.get("view", {})
                report = view.get("report", {})
                out.append({
                    "id": r.get("id"),
                    "created_at": r.get("created_at"),
                    "symbol": view.get("symbol"),
                    "timeframe": view.get("timeframe"),
                    "duration": view.get("duration"),
                    "provider": view.get("provider"),
                    "status": view.get("status", "done"),
                    "n_trades": view.get("n_trades"),
                    "final_equity": view.get("final_equity"),
                    "total_return": report.get("total_return"),
                    "win_rate": report.get("win_rate"),
                    "window": view.get("window"),
                })
            return out

    def get(self, run_id: str) -> dict | None:
        with self._lock:
            for r in reversed(self._runs):
                if r.get("id") == run_id:
                    return r
            return None

    def delete(self, run_id: str) -> bool:
        with self._lock:
            before = len(self._runs)
            self._runs = [r for r in self._runs if r.get("id") != run_id]
            changed = len(self._runs) != before
            if changed:
                self._write()
            return changed

    # --- live-job checkpoint (survives instance restarts) ------------------------

    def _checkpoint_path(self) -> Path:
        return self.path.with_name("backtest_checkpoint.json")

    def write_checkpoint(self, data: dict) -> None:
        from tradingagents.pro.persistence import atomic_write_text

        atomic_write_text(self._checkpoint_path(), json.dumps(data, default=str))

    def read_checkpoint(self) -> dict | None:
        try:
            return json.loads(self._checkpoint_path().read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception:
            logger.warning("corrupt backtest checkpoint; ignoring")
            return None

    def clear_checkpoint(self) -> None:
        self._checkpoint_path().unlink(missing_ok=True)


__all__ = ["BacktestRunStore", "MAX_RUNS"]
