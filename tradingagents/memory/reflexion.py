"""Reflexion memory — learn from past trading decisions.

Stores agent decisions with rationale and later associates actual market
outcomes, enabling agents to *reflect* on the accuracy of their previous
calls and adjust their confidence accordingly.

Backed by MongoDB when available; falls back to a local JSON file when not.

Schema (``reflexion`` collection)::

    {
        "ticker":          str,          # "AAPL"
        "decision_date":   str,          # ISO date "2026-03-20"
        "decision":        str,          # "BUY" | "SELL" | "HOLD" | "SKIP"
        "rationale":       str,          # free-form reasoning
        "confidence":      str,          # "high" | "medium" | "low"
        "source":          str,          # "pipeline" | "portfolio" | "auto"
        "run_id":          str | None,
        "outcome":         dict | None,  # filled later by record_outcome()
        "created_at":      datetime,
    }

Usage::

    from tradingagents.memory.reflexion import ReflexionMemory

    mem = ReflexionMemory("mongodb://localhost:27017")
    mem.record_decision("AAPL", "2026-03-20", "BUY", "Strong fundamentals", "high")
    history = mem.get_history("AAPL", limit=5)
    context = mem.build_context("AAPL", limit=3)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_COLLECTION = "reflexion"


class ReflexionMemory:
    """MongoDB-backed reflexion memory.

    Falls back to a local JSON file when MongoDB is unavailable, so the
    feature always works (though with degraded query performance on the
    local variant).
    """

    def __init__(
        self,
        mongo_uri: str | None = None,
        db_name: str = "tradingagents",
        fallback_path: str | Path = "reports/reflexion.json",
        collection_name: str = "reflexion",
    ) -> None:
        self._col = None
        self._fallback_path = Path(fallback_path)

        if mongo_uri:
            try:
                from pymongo import DESCENDING, MongoClient

                client = MongoClient(mongo_uri)
                db = client[db_name]
                self._col = db[collection_name]
                self._col.create_index(
                    [("ticker", 1), ("decision_date", DESCENDING)]
                )
                self._col.create_index("created_at")
                logger.info("ReflexionMemory using MongoDB (db=%s)", db_name)
            except Exception:
                logger.warning(
                    "ReflexionMemory: MongoDB unavailable — using local file",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Record decision
    # ------------------------------------------------------------------

    def record_decision(
        self,
        ticker: str,
        date: str,
        decision: str,
        rationale: str,
        confidence: str = "medium",
        source: str = "pipeline",
        run_id: str | None = None,
    ) -> None:
        """Store a trading decision for later reflection.

        Args:
            ticker:     Ticker symbol.
            date:       ISO date string.
            decision:   "BUY", "SELL", "HOLD", or "SKIP".
            rationale:  Agent's reasoning.
            confidence: "high", "medium", or "low".
            source:     Which pipeline produced the decision.
            run_id:     Optional run identifier.
        """
        doc = {
            "ticker": ticker.upper(),
            "decision_date": date,
            "decision": decision.upper(),
            "rationale": rationale,
            "confidence": confidence.lower(),
            "source": source,
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

    def record_outcome(
        self,
        ticker: str,
        decision_date: str,
        outcome: dict[str, Any],
    ) -> bool:
        """Attach an outcome to the most recent decision for a ticker+date.

        Args:
            ticker:        Ticker symbol.
            decision_date: The date the original decision was made.
            outcome:       Dict with evaluation data, e.g.::

                {
                    "evaluation_date": "2026-04-20",
                    "price_at_decision": 185.0,
                    "price_at_evaluation": 195.0,
                    "price_change_pct": 5.4,
                    "correct": True,
                }

        Returns:
            True if a matching decision was found and updated.
        """
        if self._col is not None:
            from pymongo import DESCENDING

            doc = self._col.find_one_and_update(
                {
                    "ticker": ticker.upper(),
                    "decision_date": decision_date,
                    "outcome": None,
                },
                {"$set": {"outcome": outcome}},
                sort=[("created_at", DESCENDING)],
            )
            return doc is not None
        else:
            return self._update_local_outcome(ticker.upper(), decision_date, outcome)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_history(
        self,
        ticker: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return the most recent decisions for *ticker*, newest first.

        Args:
            ticker: Ticker symbol.
            limit:  Maximum number of results.
        """
        if self._col is not None:
            from pymongo import DESCENDING

            cursor = self._col.find(
                {"ticker": ticker.upper()},  # Hard metadata filter — prevents cross-ticker contamination
                {"_id": 0},
            ).sort("decision_date", DESCENDING).limit(limit)
            return list(cursor)
        else:
            return self._load_local(ticker.upper(), limit)

    def build_context(self, ticker: str, limit: int = 3) -> str:
        """Build a human-readable context string from past decisions.

        Suitable for injection into agent system prompts::

            context = memory.build_context("AAPL", limit=3)
            system_prompt = f"...\\n\\nPast decisions:\\n{context}"

        Args:
            ticker: Ticker symbol.
            limit:  How many past decisions to include.

        Returns:
            Multi-line string summarising recent decisions and outcomes.
        """
        history = self.get_history(ticker, limit=limit)
        if not history:
            return f"No prior decisions recorded for {ticker.upper()}."

        lines: list[str] = []
        for rec in history:
            dt = rec.get("decision_date", "?")
            dec = rec.get("decision", "?")
            conf = rec.get("confidence", "?")
            rat = rec.get("rationale", "")[:200]

            outcome = rec.get("outcome")
            if outcome:
                pct = outcome.get("price_change_pct", "?")
                correct = outcome.get("correct", "?")
                outcome_str = f"  Outcome: {pct}% change, correct={correct}"
            else:
                outcome_str = "  Outcome: pending"

            lines.append(
                f"- [{dt}] {dec} (confidence: {conf})\n"
                f"  Rationale: {rat}\n{outcome_str}"
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

    def _load_local(self, ticker: str, limit: int) -> list[dict[str, Any]]:
        """Load and filter records for a ticker from the local file."""
        records = self._load_all_local()
        filtered = [r for r in records if r.get("ticker") == ticker]  # Hard metadata filter — local fallback
        filtered.sort(key=lambda r: r.get("decision_date", ""), reverse=True)
        return filtered[:limit]

    def _update_local_outcome(
        self, ticker: str, decision_date: str, outcome: dict[str, Any]
    ) -> bool:
        """Update the most recent matching decision in the local file."""
        records = self._load_all_local()
        # Find matching records (newest first)
        for rec in reversed(records):
            if (
                rec.get("ticker") == ticker
                and rec.get("decision_date") == decision_date
                and rec.get("outcome") is None
            ):
                rec["outcome"] = outcome
                self._save_all_local(records)
                return True
        return False
