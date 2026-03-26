"""Factory for creating the appropriate report store backend.

Returns a :class:`MongoReportStore` when a MongoDB connection string is
configured, otherwise falls back to the filesystem :class:`ReportStore`.

Usage::

    from tradingagents.portfolio.store_factory import create_report_store

    store = create_report_store(run_id="a1b2c3d4")
    store.save_scan("2026-03-20", {...})
"""

from __future__ import annotations

import logging
import os
from typing import Union

from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.dual_report_store import DualReportStore

logger = logging.getLogger(__name__)


def create_report_store(
    flow_id: str | None = None,
    *,
    run_id: str | None = None,
    base_dir: str | None = None,
    mongo_uri: str | None = None,
    mongo_db: str | None = None,
) -> Union[ReportStore, "MongoReportStore", DualReportStore]:  # noqa: F821
    """Create and return the appropriate report store.

    Resolution order for the backend:

    1. If *mongo_uri* is passed explicitly, use DualReportStore.
    2. If ``TRADINGAGENTS_MONGO_URI`` env var is set, use DualReportStore.
    3. Fall back to the filesystem :class:`ReportStore`.

    Args:
        flow_id:   Flow identifier grouping all phases of one analysis intent.
                   When set, the store uses timestamp-based report versioning
                   under ``{base}/daily/{date}/{flow_id}/``.
        run_id:    Legacy short identifier (backward compat).  Prefer ``flow_id``
                   for new code.
        base_dir:  Override for the filesystem store's base directory.
        mongo_uri: MongoDB connection string (overrides env var).
        mongo_db:  MongoDB database name (default ``"tradingagents"``).

    Returns:
        A store instance (either ``ReportStore`` or ``DualReportStore``).
    """
    uri = mongo_uri or os.getenv("TRADINGAGENTS_MONGO_URI", "")
    db = mongo_db or os.getenv("TRADINGAGENTS_MONGO_DB", "tradingagents")

    # Filesystem instance (always created as part of Dual or as standalone)
    _base = base_dir or os.getenv("PORTFOLIO_DATA_DIR") or os.getenv(
        "TRADINGAGENTS_REPORTS_DIR", "reports"
    )
    local_store = ReportStore(base_dir=_base, flow_id=flow_id, run_id=run_id)

    if uri:
        try:
            from tradingagents.portfolio.mongo_report_store import MongoReportStore

            mongo_store = MongoReportStore(
                connection_string=uri,
                db_name=db,
                flow_id=flow_id,
                run_id=run_id,
            )
            logger.info(
                "Using Dual report store (local + MongoDB db=%s, flow_id=%s)",
                db, flow_id or run_id,
            )
            return DualReportStore(local_store, mongo_store)
        except Exception:
            logger.warning(
                "MongoDB connection failed — falling back to filesystem store",
                exc_info=True,
            )

    logger.info(
        "Using filesystem report store (base=%s, flow_id=%s)",
        _base, flow_id or run_id,
    )
    return local_store
