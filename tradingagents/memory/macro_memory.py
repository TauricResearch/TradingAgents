"""Macro memory — learn from past regime-level market context.

Stores macro regime states (VIX level, risk-on/off call, sector thesis, key
themes) and later associates outcomes, enabling agents to *reflect* on
regime accuracy and adjust forward-looking bias accordingly.

Unlike ReflexionMemory (which is per-ticker), MacroMemory operates at the
market-wide level. Each record captures the macro environment on a given date,
independent of any single security.

Backed by MongoDB when available; falls back to a local JSON file when not.

Schema (``macro_memory`` collection)::

    {
        "regime_date":   str,          # ISO date "2026-03-26"
        "vix_level":     float,        # e.g. 25.3
        "macro_call":    str,          # "risk-on" | "risk-off" | "neutral" | "transition"
        "sector_thesis": str,          # free-form regime summary
        "key_themes":    list,         # list of top macro theme strings
        "run_id":        str | None,
        "outcome":       dict | None,  # filled later by record_outcome()
        "created_at":    datetime,
    }

Usage::

    from tradingagents.memory.macro_memory import MacroMemory

    mem = MacroMemory("mongodb://localhost:27017")
    mem.record_macro_state(
        date="2026-03-26",
        vix_level=25.3,
        macro_call="risk-off",
        sector_thesis="Energy under pressure, Fed hawkish",
        key_themes=["rate hikes", "oil volatility"],
    )
    context = mem.build_macro_context(limit=3)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COLLECTION = "macro_memory"

_VALID_MACRO_CALLS = {"risk-on", "risk-off", "neutral", "transition"}


class MacroMemory:
    """MongoDB-backed macro regime memory.

    Falls back to a local JSON file when MongoDB is unavailable, so the
    feature always works (though with degraded query performance on the
    local variant).
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str = "tradingagents",
        fallback_path: str | Path = "reports/macro_memory.json",
    ) -> None:
        self._col = None
        self._fallback_path = Path(fallback_path)

        if mongo_uri:
            try:
                from pymongo import DESCENDING, MongoClient

                client = MongoClient(mongo_uri)
                db = client[db_name]
                self._col = db[_COLLECTION]
                self._col.create_index([("regime_date", DESCENDING)])
                self._col.create_index("created_at")
                logger.info("MacroMemory using MongoDB (db=%s)", db_name)
            except Exception:
                logger.warning(
                    "MacroMemory: MongoDB unavailable — using local file",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Record macro state
    # ------------------------------------------------------------------

    def record_macro_state(
        self,
        date: str,
        vix_level: float,
        macro_call: str,
        sector_thesis: str,
        key_themes: list[str],
        run_id: str | None = None,
    ) -> None:
        """Store a macro regime state for later reflection.

        Args:
            date:          ISO date string, e.g. "2026-03-26".
            vix_level:     VIX index level at the time of the call.
            macro_call:    Regime classification: "risk-on", "risk-off",
                           "neutral", or "transition".
            sector_thesis: Free-form summary of the prevailing sector view.
            key_themes:    Top macro themes driving the regime call.
            run_id:        Optional run identifier for traceability.
        """
        normalized_call = macro_call.lower()
        if normalized_call not in _VALID_MACRO_CALLS:
            logger.warning(
                "MacroMemory: unexpected macro_call %r (expected one of %s)",
                macro_call,
                _VALID_MACRO_CALLS,
            )

        doc: dict[str, Any] = {
            "regime_date": date,
            "vix_level": float(vix_level),
            "macro_call": normalized_call,
            "sector_thesis": sector_thesis,
            "key_themes": list(key_themes),
            "run_id": run_id,
            "outcome": None,
            "created_at": datetime.now(timezone.utc),
        }

        if self._col is not None:
            self._col.insert_one(doc)
        else:
            # Local JSON fallback uses ISO string (JSON has no datetime type)
            doc["created_at"] = doc["created_at"].isoformat()
            self._append_local(doc)

    # ------------------------------------------------------------------
    # Record outcome (feedback loop)
    # ------------------------------------------------------------------

    def record_outcome(self, date: str, outcome: dict[str, Any]) -> bool:
        """Attach outcome to the most recent macro state for a given date.

        Args:
            date:    ISO date string matching the original ``regime_date``.
            outcome: Dict with evaluation data, e.g.::

                {
                    "evaluation_date": "2026-04-26",
                    "vix_at_evaluation": 18.2,
                    "regime_confirmed": True,
                    "notes": "Risk-off call was correct; market sold off",
                }

        Returns:
            True if a matching state was found and updated.
        """
        if self._col is not None:
            from pymongo import DESCENDING

            doc = self._col.find_one_and_update(
                {"regime_date": date, "outcome": None},
                {"$set": {"outcome": outcome}},
                sort=[("created_at", DESCENDING)],
            )
            return doc is not None
        else:
            return self._update_local_outcome(date, outcome)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_recent(self, limit: int = 3) -> list[dict[str, Any]]:
        """Return most recent macro states, newest first.

        Args:
            limit: Maximum number of results.
        """
        if self._col is not None:
            from pymongo import DESCENDING

            cursor = self._col.find(
                {},
                {"_id": 0},
            ).sort("regime_date", DESCENDING).limit(limit)
            return list(cursor)
        else:
            return self._load_recent_local(limit)

    def build_macro_context(self, limit: int = 3) -> str:
        """Build a human-readable context string from recent macro states.

        Suitable for injection into agent prompts. Returns a multi-line string
        summarising recent regime calls and outcomes.

        Format example::

            - [2026-03-20] risk-off (VIX: 25.3)
              Thesis: Energy sector under pressure, Fed hawkish
              Themes: ['rate hikes', 'oil volatility']
              Outcome: pending

        Args:
            limit: How many past states to include.

        Returns:
            Multi-line string summarising recent macro regime states.
        """
        recent = self.get_recent(limit=limit)
        if not recent:
            return "No prior macro regime states recorded."

        lines: list[str] = []
        for rec in recent:
            dt = rec.get("regime_date", "?")
            call = rec.get("macro_call", "?")
            vix = rec.get("vix_level", "?")
            thesis = rec.get("sector_thesis", "")[:300]
            themes = rec.get("key_themes", [])

            outcome = rec.get("outcome")
            if outcome:
                confirmed = outcome.get("regime_confirmed", "?")
                notes = outcome.get("notes", "")
                outcome_str = f"  Outcome: confirmed={confirmed} — {notes}" if notes else f"  Outcome: confirmed={confirmed}"
            else:
                outcome_str = "  Outcome: pending"

            lines.append(
                f"- [{dt}] {call} (VIX: {vix})\n"
                f"  Thesis: {thesis}\n"
                f"  Themes: {themes}\n"
                f"{outcome_str}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Local JSON fallback
    # ------------------------------------------------------------------

    def _load_all_local(self) -> list[dict[str, Any]]:
        """Load all records from the local JSON file."""
        if not self._fallback_path.exists():
            return []
        try:
            return json.loads(self._fallback_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    def _save_all_local(self, records: list[dict[str, Any]]) -> None:
        """Overwrite the local JSON file with all records."""
        self._fallback_path.parent.mkdir(parents=True, exist_ok=True)
        self._fallback_path.write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )

    def _append_local(self, doc: dict[str, Any]) -> None:
        """Append a single record to the local file."""
        records = self._load_all_local()
        records.append(doc)
        self._save_all_local(records)

    def _load_recent_local(self, limit: int) -> list[dict[str, Any]]:
        """Load and sort all records by regime_date descending from the local file."""
        records = self._load_all_local()
        records.sort(key=lambda r: r.get("regime_date", ""), reverse=True)
        return records[:limit]

    def _update_local_outcome(self, date: str, outcome: dict[str, Any]) -> bool:
        """Update the most recent matching macro state in the local file."""
        records = self._load_all_local()
        # Iterate newest first (reversed insertion order is a proxy)
        for rec in reversed(records):
            if rec.get("regime_date") == date and rec.get("outcome") is None:
                rec["outcome"] = outcome
                self._save_all_local(records)
                return True
        return False
