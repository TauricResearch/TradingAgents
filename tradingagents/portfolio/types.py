"""Type definitions for the Portfolio module.

Centralizes TypedDict schemas and type aliases to ensure consistency across
database clients, configuration, and models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypedDict


class PortfolioConfig(TypedDict, total=False):
    """Typed configuration dictionary for portfolio operations.

    All fields are optional (total=False) to match flexible env var sourcing.
    """

    supabase_connection_string: str
    data_dir: str
    mongo_uri: str
    mongo_db: str
    max_positions: int
    max_position_pct: float
    max_sector_pct: float
    min_cash_pct: float
    default_budget: float
    results_dir: str


class ReportDocument(TypedDict, total=False):
    """MongoDB report document schema.

    Represents a single report (scan, analysis, risk metrics, etc.) stored
    in the MongoDB ``reports`` collection. All fields except ``_id`` follow
    this schema; ``_id`` is added by MongoDB.
    """

    run_id: str
    date: str
    report_type: str
    ticker: str | None
    portfolio_id: str | None
    data: dict[str, Any]
    markdown: str | None
    created_at: datetime


# Type alias for Supabase RealDictCursor rows
type RealDictRow = dict[str, Any]
