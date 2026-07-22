"""Firestore-backed backtest run store (production).

Same interface as the file-backed ``BacktestRunStore`` — save/list/get/
delete + the live-job checkpoint — but each run is its own document in the
``backtest_runs`` collection, so saves never rewrite unrelated runs, list()
is a summaries-only query, and deletes are per-document. Bulk artifacts
(full equity curve / trades / decisions) stay on the /data mount
(``backtest_artifacts``); documents comfortably fit Firestore's 1MB cap.

Selected in main.py via ``PRO_BACKTEST_STORE=firestore``; any init failure
falls back to the file store with a logged warning — storage backend
problems must never take the dashboard down.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

RUNS_COLLECTION = "backtest_runs"
STATE_COLLECTION = "backtest_state"
CHECKPOINT_DOC = "current"
MAX_RUNS = 25


class FirestoreRunStore:
    def __init__(self, client=None, project: str | None = None,
                 max_runs: int = MAX_RUNS):
        if client is None:  # pragma: no cover — exercised in prod only
            from google.cloud import firestore

            client = firestore.Client(project=project)
        self._db = client
        self.max_runs = max_runs

    # --- runs -------------------------------------------------------------------

    def save(self, record: dict) -> dict:
        run_id = record["id"]
        self._db.collection(RUNS_COLLECTION).document(run_id).set(record)
        self._prune()
        return record

    def list(self) -> list[dict]:
        query = (self._db.collection(RUNS_COLLECTION)
                 .order_by("created_at", direction="DESCENDING")
                 .limit(self.max_runs))
        out = []
        for doc in query.stream():
            data = doc.to_dict() or {}
            if data.get("summary"):
                out.append(dict(data["summary"]))
            else:  # imported legacy record
                view = data.get("view", {})
                report = view.get("report", {})
                out.append({
                    "id": data.get("id") or doc.id,
                    "created_at": data.get("created_at"),
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
        doc = self._db.collection(RUNS_COLLECTION).document(run_id).get()
        return (doc.to_dict() or None) if getattr(doc, "exists", False) else None

    def delete(self, run_id: str) -> bool:
        ref = self._db.collection(RUNS_COLLECTION).document(run_id)
        if not getattr(ref.get(), "exists", False):
            return False
        ref.delete()
        return True

    def _prune(self) -> None:
        """Evict the oldest runs (and their artifacts) beyond ``max_runs``."""
        try:
            docs = list(self._db.collection(RUNS_COLLECTION)
                        .order_by("created_at", direction="DESCENDING")
                        .stream())
            for doc in docs[self.max_runs:]:
                from tradingagents.pro.dashboard.backtest_artifacts import (
                    RunArtifacts,
                )
                RunArtifacts(doc.id).delete()
                doc.reference.delete()
        except Exception:
            logger.warning("backtest run prune failed", exc_info=True)

    # --- live-job checkpoint ------------------------------------------------------

    def write_checkpoint(self, data: dict) -> None:
        self._db.collection(STATE_COLLECTION).document(CHECKPOINT_DOC).set(data)

    def read_checkpoint(self) -> dict | None:
        doc = self._db.collection(STATE_COLLECTION).document(CHECKPOINT_DOC).get()
        return (doc.to_dict() or None) if getattr(doc, "exists", False) else None

    def clear_checkpoint(self) -> None:
        self._db.collection(STATE_COLLECTION).document(CHECKPOINT_DOC).delete()

    # --- migration ------------------------------------------------------------------

    def import_legacy_file(self, path: str | Path) -> int:
        """One-time import of runs from the legacy single-JSON file store.
        Only runs when the collection is empty; the file is left untouched."""
        path = Path(path)
        if not path.is_file():
            return 0
        try:
            if next(iter(self._db.collection(RUNS_COLLECTION)
                         .limit(1).stream()), None) is not None:
                return 0  # collection already has data — never overwrite
            runs = json.loads(path.read_text(encoding="utf-8")).get("runs", [])
        except Exception:
            logger.warning("legacy backtest store unreadable; skipping import")
            return 0
        imported = 0
        for record in runs:
            run_id = record.get("id")
            if not run_id:
                continue
            view = record.get("view", {}) or {}
            # legacy records embedded bulk arrays — strip them (artifacts
            # did not exist yet; metrics/summaries are preserved)
            view.pop("equity_curve", None)
            record["view"] = view
            self._db.collection(RUNS_COLLECTION).document(run_id).set(record)
            imported += 1
        if imported:
            logger.info("imported %d legacy backtest runs into Firestore",
                        imported)
        return imported


def build_run_store(data_path: Path):
    """Storage selection for main.py: Firestore when PRO_BACKTEST_STORE=
    firestore (with legacy import), else — or on any Firestore failure —
    the file store."""
    import os

    from tradingagents.pro.dashboard.backtest_store import BacktestRunStore

    legacy_path = data_path / "backtest_runs.json"
    if os.environ.get("PRO_BACKTEST_STORE", "").lower() == "firestore":
        try:
            store = FirestoreRunStore(
                project=os.environ.get("PRO_FIREBASE_PROJECT_ID") or None)
            store.import_legacy_file(legacy_path)
            logger.info("backtest runs: Firestore store active")
            return store
        except Exception:
            logger.exception(
                "Firestore store init failed — falling back to file store")
    return BacktestRunStore(legacy_path)


__all__ = ["FirestoreRunStore", "build_run_store", "MAX_RUNS"]
