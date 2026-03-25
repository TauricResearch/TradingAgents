"""MongoDB document store for Portfolio Manager reports.

Drop-in replacement for the filesystem :class:`ReportStore` that persists
every report as a MongoDB document.  Multiple same-day runs naturally coexist
because each document carries a ``run_id`` and ``created_at`` timestamp —
no files are ever overwritten.

Required dependency: ``pymongo >= 4.12``.

Usage::

    from tradingagents.portfolio.mongo_report_store import MongoReportStore

    store = MongoReportStore("mongodb://localhost:27017", run_id="a1b2c3d4")
    store.save_scan("2026-03-20", {"watchlist": ["AAPL"]})
    data = store.load_scan("2026-03-20")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from tradingagents.portfolio.exceptions import ReportStoreError

logger = logging.getLogger(__name__)

# Canonical collection names
_REPORTS_COLLECTION = "reports"


class MongoReportStore:
    """MongoDB-backed report store.

    Each report is a document in the ``reports`` collection with the schema::

        {
            "run_id":        str,          # short hex id for the run
            "date":          str,          # ISO date string "2026-03-20"
            "report_type":   str,          # scan | analysis | holding_review
                                           #   | risk_metrics | pm_decision
                                           #   | execution_result
            "ticker":        str | None,   # uppercase ticker (analysis, holding_review)
            "portfolio_id":  str | None,   # portfolio UUID (risk, decision, execution)
            "data":          dict,         # the actual report payload
            "markdown":      str | None,   # optional markdown (pm_decision only)
            "created_at":    datetime,     # UTC timestamp
        }

    All load methods return the **most recent** document for a given
    ``(date, report_type [, ticker | portfolio_id])`` tuple, ordered by
    ``created_at DESC``.  Pass a specific ``run_id`` to ``load_*`` via
    ``load_scan(date, run_id=run_id)`` to pin to a particular run.
    """

    def __init__(
        self,
        connection_string: str,
        db_name: str = "tradingagents",
        run_id: str | None = None,
    ) -> None:
        self._run_id = run_id
        try:
            self._client: MongoClient = MongoClient(connection_string)
            self._db: Database = self._client[db_name]
            self._col: Collection = self._db[_REPORTS_COLLECTION]
        except Exception as exc:
            raise ReportStoreError(f"MongoDB connection failed: {exc}") from exc
        self.ensure_indexes()

    @property
    def run_id(self) -> str | None:
        return self._run_id

    def ensure_indexes(self) -> None:
        """Create indexes for efficient querying (idempotent)."""
        self._col.create_index([("date", DESCENDING), ("report_type", 1)])
        self._col.create_index(
            [("date", DESCENDING), ("report_type", 1), ("ticker", 1)]
        )
        self._col.create_index(
            [("date", DESCENDING), ("report_type", 1), ("portfolio_id", 1)]
        )
        self._col.create_index("run_id")
        self._col.create_index("created_at")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save(
        self,
        date: str,
        report_type: str,
        data: dict[str, Any],
        *,
        ticker: str | None = None,
        portfolio_id: str | None = None,
        markdown: str | None = None,
    ) -> str:
        """Insert a report document.  Returns the inserted document's _id."""
        doc = {
            "run_id": self._run_id,
            "date": date,
            "report_type": report_type,
            "ticker": ticker.upper() if ticker else None,
            "portfolio_id": portfolio_id,
            "data": data,
            "markdown": markdown,
            "created_at": datetime.now(timezone.utc),
        }
        try:
            result = self._col.insert_one(doc)
            return str(result.inserted_id)
        except Exception as exc:
            raise ReportStoreError(
                f"MongoDB insert failed ({report_type}): {exc}"
            ) from exc

    def _load(
        self,
        date: str,
        report_type: str,
        *,
        ticker: str | None = None,
        portfolio_id: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Load the most recent document matching the query.

        When *run_id* is provided, only documents from that run are considered.
        Otherwise the most recent (by ``created_at``) is returned.
        """
        query: dict[str, Any] = {"date": date, "report_type": report_type}
        if ticker:
            query["ticker"] = ticker.upper()
        if portfolio_id:
            query["portfolio_id"] = portfolio_id
        if run_id:
            query["run_id"] = run_id

        doc = self._col.find_one(query, sort=[("created_at", DESCENDING)])
        if doc is None:
            return None
        return doc.get("data")

    # ------------------------------------------------------------------
    # Macro Scan
    # ------------------------------------------------------------------

    def save_scan(self, date: str, data: dict[str, Any]) -> str:
        return self._save(date, "scan", data)

    def load_scan(self, date: str, *, run_id: str | None = None) -> dict[str, Any] | None:
        return self._load(date, "scan", run_id=run_id)

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> str:
        return self._save(date, "analysis", data, ticker=ticker)

    def load_analysis(
        self, date: str, ticker: str, *, run_id: str | None = None
    ) -> dict[str, Any] | None:
        return self._load(date, "analysis", ticker=ticker, run_id=run_id)

    # ------------------------------------------------------------------
    # Holding Reviews
    # ------------------------------------------------------------------

    def save_holding_review(
        self, date: str, ticker: str, data: dict[str, Any]
    ) -> str:
        return self._save(date, "holding_review", data, ticker=ticker)

    def load_holding_review(
        self, date: str, ticker: str, *, run_id: str | None = None
    ) -> dict[str, Any] | None:
        return self._load(date, "holding_review", ticker=ticker, run_id=run_id)

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def save_risk_metrics(
        self, date: str, portfolio_id: str, data: dict[str, Any]
    ) -> str:
        return self._save(date, "risk_metrics", data, portfolio_id=portfolio_id)

    def load_risk_metrics(
        self, date: str, portfolio_id: str, *, run_id: str | None = None
    ) -> dict[str, Any] | None:
        return self._load(
            date, "risk_metrics", portfolio_id=portfolio_id, run_id=run_id
        )

    # ------------------------------------------------------------------
    # PM Decisions
    # ------------------------------------------------------------------

    def save_pm_decision(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
        markdown: str | None = None,
    ) -> str:
        return self._save(
            date, "pm_decision", data,
            portfolio_id=portfolio_id, markdown=markdown,
        )

    def load_pm_decision(
        self, date: str, portfolio_id: str, *, run_id: str | None = None
    ) -> dict[str, Any] | None:
        return self._load(
            date, "pm_decision", portfolio_id=portfolio_id, run_id=run_id
        )

    # ------------------------------------------------------------------
    # Execution Results
    # ------------------------------------------------------------------

    def save_execution_result(
        self, date: str, portfolio_id: str, data: dict[str, Any]
    ) -> str:
        return self._save(
            date, "execution_result", data, portfolio_id=portfolio_id,
        )

    def load_execution_result(
        self, date: str, portfolio_id: str, *, run_id: str | None = None
    ) -> dict[str, Any] | None:
        return self._load(
            date, "execution_result", portfolio_id=portfolio_id, run_id=run_id,
        )

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_portfolio_stage(self, date: str, portfolio_id: str) -> list[str]:
        """Delete PM decision and execution result documents for a given date/portfolio."""
        deleted = []
        for rtype in ("pm_decision", "execution_result"):
            result = self._col.delete_many(
                {"date": date, "report_type": rtype, "portfolio_id": portfolio_id}
            )
            if result.deleted_count:
                deleted.append(rtype)
        return deleted

    def list_pm_decisions(self, portfolio_id: str) -> list[dict[str, Any]]:
        """Return all PM decisions for a portfolio, newest first.

        Excludes ``_id`` (BSON ObjectId) which is not JSON-serializable.
        """
        return list(
            self._col.find(
                {"report_type": "pm_decision", "portfolio_id": portfolio_id},
                {"_id": 0},
                sort=[("date", DESCENDING), ("created_at", DESCENDING)],
            )
        )

    def list_analyses_for_date(self, date: str) -> list[str]:
        """Return ticker symbols that have an analysis for the given date."""
        docs = self._col.find(
            {"date": date, "report_type": "analysis"},
            {"ticker": 1},
        )
        return list({d["ticker"] for d in docs if d.get("ticker")})
