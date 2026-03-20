"""Shared pytest fixtures for portfolio tests.

Fixtures provided:

- ``tmp_reports`` -- temporary directory used as ReportStore base_dir
- ``sample_portfolio`` -- a Portfolio instance for testing (not persisted)
- ``sample_holding`` -- a Holding instance for testing (not persisted)
- ``sample_trade`` -- a Trade instance for testing (not persisted)
- ``sample_snapshot`` -- a PortfolioSnapshot instance for testing
- ``report_store`` -- a ReportStore instance backed by tmp_reports
- ``mock_supabase_client`` -- MagicMock of SupabaseClient for unit tests

Supabase integration tests use ``pytest.mark.skipif`` to auto-skip when
``SUPABASE_CONNECTION_STRING`` is not set in the environment.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.portfolio.models import (
    Holding,
    Portfolio,
    PortfolioSnapshot,
    Trade,
)
from tradingagents.portfolio.report_store import ReportStore
from tradingagents.portfolio.supabase_client import SupabaseClient

# ---------------------------------------------------------------------------
# Skip marker for Supabase integration tests
# ---------------------------------------------------------------------------

requires_supabase = pytest.mark.skipif(
    not os.getenv("SUPABASE_CONNECTION_STRING"),
    reason="SUPABASE_CONNECTION_STRING not set -- skipping integration tests",
)


# ---------------------------------------------------------------------------
# Data fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_portfolio_id() -> str:
    """Return a fixed UUID for deterministic testing."""
    return "11111111-1111-1111-1111-111111111111"


@pytest.fixture
def sample_holding_id() -> str:
    """Return a fixed UUID for deterministic testing."""
    return "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def sample_portfolio(sample_portfolio_id: str) -> Portfolio:
    """Return an unsaved Portfolio instance for testing."""
    return Portfolio(
        portfolio_id=sample_portfolio_id,
        name="Test Portfolio",
        cash=50_000.0,
        initial_cash=100_000.0,
        currency="USD",
        created_at="2026-03-20T00:00:00Z",
        updated_at="2026-03-20T00:00:00Z",
        report_path="reports/daily/2026-03-20/portfolio",
        metadata={"strategy": "test"},
    )


@pytest.fixture
def sample_holding(sample_portfolio_id: str, sample_holding_id: str) -> Holding:
    """Return an unsaved Holding instance for testing."""
    return Holding(
        holding_id=sample_holding_id,
        portfolio_id=sample_portfolio_id,
        ticker="AAPL",
        shares=100.0,
        avg_cost=150.0,
        sector="Technology",
        industry="Consumer Electronics",
        created_at="2026-03-20T00:00:00Z",
        updated_at="2026-03-20T00:00:00Z",
    )


@pytest.fixture
def sample_trade(sample_portfolio_id: str) -> Trade:
    """Return an unsaved Trade instance for testing."""
    return Trade(
        trade_id="33333333-3333-3333-3333-333333333333",
        portfolio_id=sample_portfolio_id,
        ticker="AAPL",
        action="BUY",
        shares=100.0,
        price=150.0,
        total_value=15_000.0,
        trade_date="2026-03-20T10:00:00Z",
        rationale="Strong momentum signal",
        signal_source="scanner",
        metadata={"confidence": 0.85},
    )


@pytest.fixture
def sample_snapshot(sample_portfolio_id: str) -> PortfolioSnapshot:
    """Return an unsaved PortfolioSnapshot instance for testing."""
    return PortfolioSnapshot(
        snapshot_id="44444444-4444-4444-4444-444444444444",
        portfolio_id=sample_portfolio_id,
        snapshot_date="2026-03-20",
        total_value=115_000.0,
        cash=50_000.0,
        equity_value=65_000.0,
        num_positions=2,
        holdings_snapshot=[
            {"ticker": "AAPL", "shares": 100.0, "avg_cost": 150.0},
            {"ticker": "MSFT", "shares": 50.0, "avg_cost": 300.0},
        ],
        metadata={"note": "end of day snapshot"},
    )


# ---------------------------------------------------------------------------
# Filesystem fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_reports(tmp_path: Path) -> Path:
    """Temporary reports directory, cleaned up after each test."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    return reports_dir


@pytest.fixture
def report_store(tmp_reports: Path) -> ReportStore:
    """ReportStore instance backed by a temporary directory."""
    return ReportStore(base_dir=tmp_reports)


# ---------------------------------------------------------------------------
# Mock Supabase client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase_client() -> MagicMock:
    """MagicMock of SupabaseClient for unit tests that don't hit the DB."""
    return MagicMock(spec=SupabaseClient)
