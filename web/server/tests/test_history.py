"""Unit tests for web.server.history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from web.server import history


_NOW = datetime(2026, 6, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixed_now(monkeypatch):
    """Pin history.now_utc() to a fixed instant so the resolver is deterministic."""
    monkeypatch.setattr(history, "now_utc", lambda: _NOW)


def test_resolve_range_1d_returns_one_day_window_at_1m(fixed_now):
    start, end, interval = history.resolve_range("1d", earliest_started_at=None)
    assert interval == "1m"
    assert end == _NOW
    assert start == _NOW - timedelta(days=1)


def test_resolve_range_5d_returns_five_day_window_at_1m(fixed_now):
    _, _, interval = history.resolve_range("5d", earliest_started_at=None)
    assert interval == "1m"


def test_resolve_range_1mo_returns_thirty_day_window_at_1h(fixed_now):
    _, _, interval = history.resolve_range("1mo", earliest_started_at=None)
    assert interval == "1h"  # 30d > 7d → 1h


def test_resolve_range_3mo_returns_ninety_day_window_at_1d(fixed_now):
    _, _, interval = history.resolve_range("3mo", earliest_started_at=None)
    assert interval == "1d"  # 90d > 60d → 1d


def test_resolve_range_all_caps_at_one_year_at_1d(fixed_now):
    _, _, interval = history.resolve_range("all", earliest_started_at=None)
    assert interval == "1d"


def test_resolve_range_auto_uses_earliest_run_started_at(fixed_now):
    earliest = _NOW - timedelta(days=12)
    start, end, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert start == earliest
    assert end == _NOW
    assert interval == "1h"  # 12d → 1h


def test_resolve_range_auto_with_no_runs_raises(fixed_now):
    with pytest.raises(ValueError, match="no runs"):
        history.resolve_range("auto", earliest_started_at=None)


def test_resolve_range_invalid_preset_raises(fixed_now):
    with pytest.raises(ValueError, match="invalid preset"):
        history.resolve_range("bogus", earliest_started_at=None)


def test_resolve_range_seven_day_span_still_picks_1m(fixed_now):
    earliest = _NOW - timedelta(days=7)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1m"


def test_resolve_range_sixty_day_span_picks_1h(fixed_now):
    earliest = _NOW - timedelta(days=60)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1h"
