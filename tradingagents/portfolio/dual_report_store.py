"""Dual report store that persists to both local filesystem and MongoDB.

Delegates all save_* calls to both a :class:`ReportStore` and a
:class:`MongoReportStore`.  Load methods prioritize the MongoDB store if
available, otherwise fall back to the filesystem.

MongoDB is **best-effort**: any exception from the Mongo backend (network
timeout, SSL error, auth failure, etc.) is caught, logged as a warning, and
the operation gracefully continues using only the local filesystem store.
This means a flaky or unreachable Atlas cluster never crashes a run.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from tradingagents.portfolio.report_store import ReportStore
    from tradingagents.portfolio.mongo_report_store import MongoReportStore

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class DualReportStore:
    """Report store that writes to two backends simultaneously.

    MongoDB operations are wrapped in :meth:`_try_mongo` so that any network
    or auth error degrades gracefully to filesystem-only operation instead of
    crashing the calling code.
    """

    def __init__(self, local_store: ReportStore, mongo_store: MongoReportStore) -> None:
        self._local = local_store
        self._mongo = mongo_store

    # ------------------------------------------------------------------
    # Internal resilience helper
    # ------------------------------------------------------------------

    def _try_mongo(self, fn: Callable[[], _T], default: _T) -> _T:
        """Call *fn* against the Mongo backend; return *default* on any error.

        Logs a WARNING with the exception details so operators can see that
        MongoDB is degraded without the error killing the run.
        """
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MongoDB operation failed (degrading to local-only): %s: %s",
                type(exc).__name__,
                exc,
            )
            return default

    @property
    def flow_id(self) -> str | None:
        """The flow identifier set on this store, if any."""
        return self._local.flow_id

    @property
    def run_id(self) -> str | None:
        """The run/flow identifier (flow_id takes precedence)."""
        return self._local.run_id

    # ------------------------------------------------------------------
    # Macro Scan
    # ------------------------------------------------------------------

    def save_scan(self, date: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_scan(date, data)
        self._try_mongo(lambda: self._mongo.save_scan(date, data), None)
        return local_result

    def load_scan(self, date: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_scan(date), None) or self._local.load_scan(date)

    # ------------------------------------------------------------------
    # Per-Ticker Analysis
    # ------------------------------------------------------------------

    def save_analysis(self, date: str, ticker: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_analysis(date, ticker, data)
        self._try_mongo(lambda: self._mongo.save_analysis(date, ticker, data), None)
        return local_result

    def load_analysis(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_analysis(date, ticker), None) or self._local.load_analysis(date, ticker)

    # ------------------------------------------------------------------
    # Holding Reviews
    # ------------------------------------------------------------------

    def save_holding_review(self, date: str, ticker: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_holding_review(date, ticker, data)
        self._try_mongo(lambda: self._mongo.save_holding_review(date, ticker, data), None)
        return local_result

    def load_holding_review(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_holding_review(date, ticker), None) or self._local.load_holding_review(date, ticker)

    # ------------------------------------------------------------------
    # Risk Metrics
    # ------------------------------------------------------------------

    def save_risk_metrics(self, date: str, portfolio_id: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_risk_metrics(date, portfolio_id, data)
        self._try_mongo(lambda: self._mongo.save_risk_metrics(date, portfolio_id, data), None)
        return local_result

    def load_risk_metrics(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_risk_metrics(date, portfolio_id), None) or self._local.load_risk_metrics(date, portfolio_id)

    # ------------------------------------------------------------------
    # PM Decisions
    # ------------------------------------------------------------------

    def save_pm_decision(
        self,
        date: str,
        portfolio_id: str,
        data: dict[str, Any],
        markdown: str | None = None,
    ) -> Any:
        local_result = self._local.save_pm_decision(date, portfolio_id, data, markdown=markdown)
        self._try_mongo(lambda: self._mongo.save_pm_decision(date, portfolio_id, data, markdown=markdown), None)
        return local_result

    def load_pm_decision(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_pm_decision(date, portfolio_id), None) or self._local.load_pm_decision(date, portfolio_id)

    # ------------------------------------------------------------------
    # Execution Results
    # ------------------------------------------------------------------

    def save_execution_result(self, date: str, portfolio_id: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_execution_result(date, portfolio_id, data)
        self._try_mongo(lambda: self._mongo.save_execution_result(date, portfolio_id, data), None)
        return local_result

    def load_execution_result(self, date: str, portfolio_id: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_execution_result(date, portfolio_id), None) or self._local.load_execution_result(date, portfolio_id)

    # ------------------------------------------------------------------
    # Run Meta / Events persistence
    # ------------------------------------------------------------------

    def save_run_meta(self, date: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_run_meta(date, data)
        self._try_mongo(lambda: self._mongo.save_run_meta(date, data), None)
        return local_result

    def load_run_meta(self, date: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_run_meta(date), None) or self._local.load_run_meta(date)

    def save_run_events(self, date: str, events: list[dict[str, Any]]) -> Any:
        local_result = self._local.save_run_events(date, events)
        self._try_mongo(lambda: self._mongo.save_run_events(date, events), None)
        return local_result

    def load_run_events(self, date: str) -> list[dict[str, Any]]:
        mongo_events = self._try_mongo(lambda: self._mongo.load_run_events(date), None)
        if mongo_events:
            return mongo_events
        return self._local.load_run_events(date)

    def list_run_metas(self) -> list[dict[str, Any]]:
        mongo_metas = self._try_mongo(lambda: self._mongo.list_run_metas(), None)
        if mongo_metas:
            return mongo_metas
        return self._local.list_run_metas()

    # ------------------------------------------------------------------
    # Analyst / Trader Checkpoints
    # ------------------------------------------------------------------

    def save_analysts_checkpoint(self, date: str, ticker: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_analysts_checkpoint(date, ticker, data)
        self._try_mongo(lambda: self._mongo.save_analysts_checkpoint(date, ticker, data), None)
        return local_result

    def load_analysts_checkpoint(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_analysts_checkpoint(date, ticker), None) or self._local.load_analysts_checkpoint(date, ticker)

    def save_trader_checkpoint(self, date: str, ticker: str, data: dict[str, Any]) -> Any:
        local_result = self._local.save_trader_checkpoint(date, ticker, data)
        self._try_mongo(lambda: self._mongo.save_trader_checkpoint(date, ticker, data), None)
        return local_result

    def load_trader_checkpoint(self, date: str, ticker: str) -> dict[str, Any] | None:
        return self._try_mongo(lambda: self._mongo.load_trader_checkpoint(date, ticker), None) or self._local.load_trader_checkpoint(date, ticker)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear_portfolio_stage(self, date: str, portfolio_id: str) -> list[str]:
        local_deleted = self._local.clear_portfolio_stage(date, portfolio_id)
        self._try_mongo(lambda: self._mongo.clear_portfolio_stage(date, portfolio_id), None)
        return local_deleted

    def list_pm_decisions(self, portfolio_id: str) -> list[Any]:
        # Mongo returns dicts, Local returns Paths.  Prefer Mongo for rich data.
        mongo_results = self._try_mongo(lambda: self._mongo.list_pm_decisions(portfolio_id), None)
        if mongo_results:
            return mongo_results
        return self._local.list_pm_decisions(portfolio_id)

    def list_analyses_for_date(self, date: str) -> list[str]:
        mongo_results = self._try_mongo(lambda: self._mongo.list_analyses_for_date(date), [])
        local_results = self._local.list_analyses_for_date(date)
        return list(set(mongo_results) | set(local_results))
