"""Tests for news timeliness validation (stale item filtering)."""

from datetime import datetime

import pytest

from tradingagents.dataflows.interface import (
    _filter_stale_items,
    _parse_date_best_effort,
)
from tradingagents.dataflows.tavily_news import (
    _is_published_outside_window,
    _parse_published_date,
)


# ---------------------------------------------------------------------------
# _parse_published_date (Tavily-level)
# ---------------------------------------------------------------------------


class TestParsePublishedDate:
    def test_iso_format(self):
        dt = _parse_published_date("2026-05-20T14:30:00")
        assert dt == datetime(2026, 5, 20, 14, 30, 0)

    def test_iso_with_z(self):
        dt = _parse_published_date("2026-05-20T14:30:00Z")
        assert dt == datetime(2026, 5, 20, 14, 30, 0)

    def test_date_only(self):
        dt = _parse_published_date("2026-05-20")
        assert dt == datetime(2026, 5, 20)

    def test_compact_datetime(self):
        dt = _parse_published_date("20260520T143000")
        assert dt == datetime(2026, 5, 20, 14, 30, 0)

    def test_compact_date(self):
        dt = _parse_published_date("20260520")
        assert dt == datetime(2026, 5, 20)

    def test_us_format(self):
        dt = _parse_published_date("May 20, 2026")
        assert dt == datetime(2026, 5, 20)

    def test_empty_string_returns_none(self):
        assert _parse_published_date("") is None
        assert _parse_published_date(None) is None

    def test_garbage_returns_none(self):
        assert _parse_published_date("not a date at all") is None


# ---------------------------------------------------------------------------
# _is_published_outside_window (Tavily-level)
# ---------------------------------------------------------------------------


class TestIsPublishedOutsideWindow:
    def test_within_window(self):
        assert _is_published_outside_window("2026-05-20", "2026-05-15", "2026-05-25") is False

    def test_before_window(self):
        assert _is_published_outside_window("2026-05-10", "2026-05-15", "2026-05-25") is True

    def test_after_window(self):
        assert _is_published_outside_window("2026-05-30", "2026-05-15", "2026-05-25") is True

    def test_on_start_boundary(self):
        assert _is_published_outside_window("2026-05-15", "2026-05-15", "2026-05-25") is False

    def test_on_end_boundary(self):
        assert _is_published_outside_window("2026-05-25", "2026-05-15", "2026-05-25") is False

    def test_unparseable_not_flagged(self):
        assert _is_published_outside_window("unknown", "2026-05-15", "2026-05-25") is False


# ---------------------------------------------------------------------------
# _parse_date_best_effort (interface-level)
# ---------------------------------------------------------------------------


class TestParseDateBestEffort:
    def test_iso_format(self):
        assert _parse_date_best_effort("2026-05-20T14:30:00") == datetime(2026, 5, 20, 14, 30)

    def test_date_only(self):
        assert _parse_date_best_effort("2026-05-20") == datetime(2026, 5, 20)

    def test_alpha_vantage_format(self):
        assert _parse_date_best_effort("20260520T143000") == datetime(2026, 5, 20, 14, 30)

    def test_empty_returns_none(self):
        assert _parse_date_best_effort("") is None


# ---------------------------------------------------------------------------
# _filter_stale_items (interface-level)
# ---------------------------------------------------------------------------


class TestFilterStaleItems:
    def _item(self, published: str) -> dict:
        return {"title": "Test", "published": published, "source": "tavily"}

    def test_keeps_items_within_window(self):
        items = [self._item("2026-05-20"), self._item("2026-05-22")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 2
        assert stale == 0

    def test_filters_items_outside_window(self):
        items = [self._item("2026-05-10"), self._item("2026-05-20")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 1
        assert stale == 1
        assert kept[0]["published"] == "2026-05-20"

    def test_respects_precomputed_stale_flag(self):
        items = [{"title": "Flagged", "published": "2026-05-20", "stale": True}]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 0
        assert stale == 1

    def test_unparseable_dates_kept(self):
        items = [self._item("unknown date format")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 1
        assert stale == 0

    def test_empty_published_kept(self):
        items = [self._item("")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 1
        assert stale == 0

    def test_no_dates_returns_all(self):
        items = [self._item("2026-05-10")]
        kept, stale = _filter_stale_items(items, "", "")
        assert len(kept) == 1
        assert stale == 0

    def test_end_date_inclusive(self):
        items = [self._item("2026-05-25")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 1
        assert stale == 0

    def test_day_after_end_filtered(self):
        items = [self._item("2026-05-26")]
        kept, stale = _filter_stale_items(items, "2026-05-15", "2026-05-25")
        assert len(kept) == 0
        assert stale == 1
