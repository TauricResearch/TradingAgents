"""Shared pytest fixtures for portfolio tests.

Fixtures provided:

- ``tmp_reports`` — temporary directory used as ReportStore base_dir
- ``sample_portfolio`` — a Portfolio instance for testing (not persisted)
- ``sample_holding`` — a Holding instance for testing (not persisted)
- ``sample_trade`` — a Trade instance for testing (not persisted)
- ``sample_snapshot`` — a PortfolioSnapshot instance for testing
- ``report_store`` — a ReportStore instance backed by tmp_reports
- ``mock_supabase_client`` — MagicMock of SupabaseClient for unit tests

Supabase integration tests use ``pytest.mark.skipif`` to auto-skip when
``SUPABASE_URL`` is not set in the environment.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Skip marker for Supabase integration tests
# ---------------------------------------------------------------------------

requires_supabase = pytest.mark.skipif(
    not os.getenv("SUPABASE_URL"),
    reason="SUPABASE_URL not set — skipping Supabase integration tests",
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
def sample_portfolio(sample_portfolio_id: str):
    """Return an unsaved Portfolio instance for testing."""
    # TODO: implement — construct a Portfolio dataclass with test values
    raise NotImplementedError


@pytest.fixture
def sample_holding(sample_portfolio_id: str, sample_holding_id: str):
    """Return an unsaved Holding instance for testing."""
    # TODO: implement — construct a Holding dataclass with test values
    raise NotImplementedError


@pytest.fixture
def sample_trade(sample_portfolio_id: str):
    """Return an unsaved Trade instance for testing."""
    # TODO: implement — construct a Trade dataclass with test values
    raise NotImplementedError


@pytest.fixture
def sample_snapshot(sample_portfolio_id: str):
    """Return an unsaved PortfolioSnapshot instance for testing."""
    # TODO: implement — construct a PortfolioSnapshot dataclass with test values
    raise NotImplementedError


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
def report_store(tmp_reports: Path):
    """ReportStore instance backed by a temporary directory."""
    # TODO: implement — return ReportStore(base_dir=tmp_reports)
    raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock Supabase client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_supabase_client():
    """MagicMock of SupabaseClient for unit tests that don't hit the DB."""
    # TODO: implement — return MagicMock(spec=SupabaseClient)
    raise NotImplementedError
