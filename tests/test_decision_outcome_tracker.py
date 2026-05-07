"""Tests for the Decision Outcome Tracker (P2).

Covers:
- Property 9: Decision Log Append-Only Invariant
- Property 10: Decision Resolution Alpha Computation
- Property 11: Cross-Ticker Lessons Ordering and Filtering
- Property 12: Cross-Ticker Context Field Completeness
- Unit tests for recording, resolution, and cross-ticker learning
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from tradingagents.agents.utils.decision_outcome_tracker import (
    DecisionOutcomeTracker,
    DecisionRecord,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """Provide a temporary data cache directory."""
    return str(tmp_path)


@pytest.fixture
def tracker(tmp_cache_dir):
    """Provide a fresh DecisionOutcomeTracker instance."""
    return DecisionOutcomeTracker(data_cache_dir=tmp_cache_dir, holding_period_days=5)


def _mock_price_fetcher(returns: dict[str, float | None]):
    """Create a mock price fetcher that returns predefined values."""

    def fetcher(ticker: str, start_date: str, end_date: str) -> float | None:
        return returns.get(ticker)

    return fetcher


# ---------------------------------------------------------------------------
# Property 9: Decision Log Append-Only Invariant
# ---------------------------------------------------------------------------


class TestAppendOnlyInvariant:
    """Property 9: First N records unchanged after appending (N+1)th."""

    # Feature: upstream-feature-adoption, Property 9: Decision Log Append-Only Invariant

    def test_append_preserves_existing_records(self, tracker):
        """After appending N+1 records, first N are byte-identical."""
        # Append 5 records
        for i in range(5):
            tracker.record_decision(
                ticker=f"TICK{i}",
                trade_date=f"2026-01-{10 + i:02d}",
                rating="Buy",
                rationale_summary=f"Rationale {i}",
            )

        # Read the file content after 5 records
        with open(tracker.log_path, encoding="utf-8") as f:
            lines_before = f.readlines()

        assert len(lines_before) == 5

        # Append one more
        tracker.record_decision(
            ticker="TICK5",
            trade_date="2026-01-15",
            rating="Sell",
            rationale_summary="Rationale 5",
        )

        # Read the file content after 6 records
        with open(tracker.log_path, encoding="utf-8") as f:
            lines_after = f.readlines()

        assert len(lines_after) == 6
        # First 5 lines must be byte-identical
        assert lines_before == lines_after[:5]

    def test_multiple_appends_preserve_order(self, tracker):
        """Records maintain insertion order across multiple appends."""
        tickers = ["AAPL", "MSFT", "GOOG", "TSLA", "AMZN"]
        for ticker in tickers:
            tracker.record_decision(
                ticker=ticker,
                trade_date="2026-01-10",
                rating="Hold",
                rationale_summary=f"Analysis for {ticker}",
            )

        records = tracker._read_all_records()
        assert [r.ticker for r in records] == tickers

    def test_append_does_not_modify_content(self, tracker):
        """Verify exact JSON content is preserved on append."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong earnings",
        )

        with open(tracker.log_path, encoding="utf-8") as f:
            first_line = f.readline()

        data = json.loads(first_line)
        assert data["ticker"] == "AAPL"
        assert data["trade_date"] == "2026-01-10"
        assert data["rating"] == "Buy"
        assert data["status"] == "pending"
        assert data["actual_return"] is None


# ---------------------------------------------------------------------------
# Property 10: Decision Resolution Alpha Computation
# ---------------------------------------------------------------------------


class TestResolutionAlpha:
    """Property 10: alpha == actual_return - benchmark_return."""

    # Feature: upstream-feature-adoption, Property 10: Decision Resolution Alpha Computation

    def test_alpha_equals_actual_minus_benchmark(self, tracker):
        """Resolved record has alpha = actual_return - benchmark_return."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Strong fundamentals",
        )

        # Mock: AAPL returned 5%, SPY returned 2%
        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": 0.02})
        resolved = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)

        assert len(resolved) == 1
        record = resolved[0]
        assert record.status == "resolved"
        assert record.actual_return == pytest.approx(0.05, abs=1e-6)
        assert record.benchmark_return == pytest.approx(0.02, abs=1e-6)
        assert record.alpha == pytest.approx(0.03, abs=1e-6)

    def test_negative_alpha(self, tracker):
        """Alpha is negative when stock underperforms benchmark."""
        tracker.record_decision(
            ticker="TSLA",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Momentum play",
        )

        fetcher = _mock_price_fetcher({"TSLA": -0.03, "SPY": 0.01})
        resolved = tracker.resolve_pending("TSLA", "2026-01-10", price_fetcher=fetcher)

        assert len(resolved) == 1
        assert resolved[0].alpha == pytest.approx(-0.04, abs=1e-6)

    def test_zero_alpha_when_matching_benchmark(self, tracker):
        """Alpha is zero when stock matches benchmark exactly."""
        tracker.record_decision(
            ticker="MSFT",
            trade_date="2026-01-01",
            rating="Hold",
            rationale_summary="Fair value",
        )

        fetcher = _mock_price_fetcher({"MSFT": 0.015, "SPY": 0.015})
        resolved = tracker.resolve_pending("MSFT", "2026-01-10", price_fetcher=fetcher)

        assert len(resolved) == 1
        assert resolved[0].alpha == pytest.approx(0.0, abs=1e-6)

    def test_benchmark_defaults_to_zero_when_unavailable(self, tracker):
        """When SPY data is unavailable, benchmark defaults to 0."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Strong",
        )

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": None})
        resolved = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)

        assert len(resolved) == 1
        assert resolved[0].benchmark_return == pytest.approx(0.0, abs=1e-6)
        assert resolved[0].alpha == pytest.approx(0.05, abs=1e-6)


# ---------------------------------------------------------------------------
# Property 11: Cross-Ticker Lessons Ordering and Filtering
# ---------------------------------------------------------------------------


class TestCrossTickerOrdering:
    """Property 11: At most N records, excludes target, ordered by abs(alpha) desc."""

    # Feature: upstream-feature-adoption, Property 11: Cross-Ticker Lessons Ordering and Filtering

    def test_excludes_target_ticker(self, tracker):
        """Cross-ticker lessons exclude the current analysis target."""
        # Add resolved records for multiple tickers
        self._add_resolved_record(tracker, "AAPL", "2026-01-01", 0.05, 0.02)
        self._add_resolved_record(tracker, "MSFT", "2026-01-02", 0.03, 0.01)
        self._add_resolved_record(tracker, "GOOG", "2026-01-03", -0.02, 0.01)

        lessons = tracker.get_cross_ticker_lessons(exclude_ticker="AAPL", n=10)
        assert "AAPL" not in lessons
        assert "MSFT" in lessons
        assert "GOOG" in lessons

    def test_returns_at_most_n_records(self, tracker):
        """Returns at most N lessons."""
        for i in range(10):
            self._add_resolved_record(
                tracker, f"TICK{i}", f"2026-01-{10 + i:02d}", 0.01 * (i + 1), 0.005
            )

        lessons = tracker.get_cross_ticker_lessons(exclude_ticker="EXCLUDED", n=3)
        # Count the bullet points
        bullet_count = lessons.count("- **")
        assert bullet_count <= 3

    def test_ordered_by_abs_alpha_descending(self, tracker):
        """Lessons are ordered by absolute alpha, largest first."""
        self._add_resolved_record(tracker, "SMALL", "2026-01-01", 0.01, 0.005)  # alpha=0.005
        self._add_resolved_record(tracker, "BIG", "2026-01-02", 0.10, 0.01)  # alpha=0.09
        self._add_resolved_record(tracker, "NEG", "2026-01-03", -0.08, 0.01)  # alpha=-0.09

        lessons = tracker.get_cross_ticker_lessons(exclude_ticker="EXCLUDED", n=10)
        # BIG and NEG should appear before SMALL (both have abs(alpha) = 0.09 vs 0.005)
        big_pos = lessons.find("BIG")
        neg_pos = lessons.find("NEG")
        small_pos = lessons.find("SMALL")
        assert big_pos < small_pos or neg_pos < small_pos

    def test_empty_when_no_resolved_records(self, tracker):
        """Returns empty string when no resolved records exist."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Pending",
        )
        lessons = tracker.get_cross_ticker_lessons(exclude_ticker="MSFT", n=3)
        assert lessons == ""

    @staticmethod
    def _add_resolved_record(
        tracker: DecisionOutcomeTracker,
        ticker: str,
        trade_date: str,
        actual_return: float,
        benchmark_return: float,
    ):
        """Helper to directly write a resolved record."""
        record = DecisionRecord(
            ticker=ticker,
            trade_date=trade_date,
            rating="Buy",
            rationale_summary=f"Analysis for {ticker}",
            status="resolved",
            recorded_at="2026-01-01T00:00:00+00:00",
            actual_return=actual_return,
            benchmark_return=benchmark_return,
            alpha=actual_return - benchmark_return,
            resolved_at="2026-01-10T00:00:00+00:00",
        )
        tracker._write_record(record)


# ---------------------------------------------------------------------------
# Property 12: Cross-Ticker Context Field Completeness
# ---------------------------------------------------------------------------


class TestCrossTickerFieldCompleteness:
    """Property 12: Output contains ticker, trade_date, rating, outcome, lesson."""

    # Feature: upstream-feature-adoption, Property 12: Cross-Ticker Context Field Completeness

    def test_output_contains_required_fields(self, tracker):
        """Each lesson line contains ticker, date, rating, and outcome info."""
        record = DecisionRecord(
            ticker="AAPL",
            trade_date="2026-01-15",
            rating="Buy",
            rationale_summary="Strong earnings beat with raised guidance",
            status="resolved",
            recorded_at="2026-01-15T14:30:00+00:00",
            actual_return=0.032,
            benchmark_return=0.011,
            alpha=0.021,
            resolved_at="2026-01-20T09:00:00+00:00",
        )
        tracker._write_record(record)

        lessons = tracker.get_cross_ticker_lessons(exclude_ticker="MSFT", n=3)

        # Must contain ticker
        assert "AAPL" in lessons
        # Must contain trade_date
        assert "2026-01-15" in lessons
        # Must contain rating
        assert "Buy" in lessons
        # Must contain outcome (actual return percentage)
        assert "%" in lessons
        # Must contain rationale/lesson text
        assert "Strong earnings" in lessons


# ---------------------------------------------------------------------------
# Unit Tests: Recording
# ---------------------------------------------------------------------------


class TestRecordDecision:
    """Unit tests for record_decision()."""

    def test_creates_file_on_first_write(self, tracker):
        """Log file is created on first record_decision call."""
        assert not tracker.log_path.exists()
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong fundamentals",
        )
        assert tracker.log_path.exists()

    def test_noop_on_empty_rating(self, tracker):
        """No record is appended when rating is empty."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="",
            rationale_summary="Should not be recorded",
        )
        assert not tracker.log_path.exists()

    def test_noop_on_none_rating(self, tracker):
        """No record is appended when rating is None."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating=None,
            rationale_summary="Should not be recorded",
        )
        assert not tracker.log_path.exists()

    def test_noop_on_whitespace_rating(self, tracker):
        """No record is appended when rating is whitespace only."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="   ",
            rationale_summary="Should not be recorded",
        )
        assert not tracker.log_path.exists()

    def test_record_has_pending_status(self, tracker):
        """New records always have status 'pending'."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong",
        )
        records = tracker._read_all_records()
        assert len(records) == 1
        assert records[0].status == "pending"

    def test_record_has_iso_timestamp(self, tracker):
        """recorded_at is a valid ISO timestamp."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong",
        )
        records = tracker._read_all_records()
        # Should parse without error
        datetime.fromisoformat(records[0].recorded_at)

    def test_record_fields_match_input(self, tracker):
        """Record fields match the input arguments."""
        tracker.record_decision(
            ticker="MSFT",
            trade_date="2026-02-15",
            rating="Sell",
            rationale_summary="Weak guidance",
        )
        records = tracker._read_all_records()
        r = records[0]
        assert r.ticker == "MSFT"
        assert r.trade_date == "2026-02-15"
        assert r.rating == "Sell"
        assert r.rationale_summary == "Weak guidance"
        assert r.actual_return is None
        assert r.benchmark_return is None
        assert r.alpha is None
        assert r.resolved_at is None

    def test_valid_jsonl_format(self, tracker):
        """Each line in the log is valid JSON."""
        tracker.record_decision("AAPL", "2026-01-10", "Buy", "Reason 1")
        tracker.record_decision("MSFT", "2026-01-11", "Sell", "Reason 2")

        with open(tracker.log_path, encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)  # Should not raise
                assert "ticker" in data
                assert "status" in data


# ---------------------------------------------------------------------------
# Unit Tests: Resolution
# ---------------------------------------------------------------------------


class TestResolvePending:
    """Unit tests for resolve_pending()."""

    def test_does_not_resolve_before_holding_period(self, tracker):
        """Records within holding period are not resolved."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong",
        )

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": 0.02})
        # Only 3 days later (holding period is 5)
        resolved = tracker.resolve_pending("AAPL", "2026-01-13", price_fetcher=fetcher)
        assert len(resolved) == 0

    def test_resolves_after_holding_period(self, tracker):
        """Records are resolved once holding period has elapsed."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong",
        )

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": 0.02})
        # 6 days later (holding period is 5)
        resolved = tracker.resolve_pending("AAPL", "2026-01-16", price_fetcher=fetcher)
        assert len(resolved) == 1
        assert resolved[0].status == "resolved"

    def test_leaves_pending_when_price_unavailable(self, tracker):
        """Records stay pending when price data is unavailable."""
        tracker.record_decision(
            ticker="AAPL",
            trade_date="2026-01-10",
            rating="Buy",
            rationale_summary="Strong",
        )

        fetcher = _mock_price_fetcher({"AAPL": None, "SPY": 0.02})
        resolved = tracker.resolve_pending("AAPL", "2026-01-16", price_fetcher=fetcher)
        assert len(resolved) == 0

        # Verify still pending in log
        records = tracker._read_all_records()
        assert records[0].status == "pending"

    def test_only_resolves_matching_ticker(self, tracker):
        """Only resolves pending records for the specified ticker."""
        tracker.record_decision("AAPL", "2026-01-01", "Buy", "Apple analysis")
        tracker.record_decision("MSFT", "2026-01-01", "Sell", "Microsoft analysis")

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "MSFT": -0.03, "SPY": 0.01})
        resolved = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)

        assert len(resolved) == 1
        assert resolved[0].ticker == "AAPL"

        # MSFT should still be pending
        records = tracker._read_all_records()
        msft_records = [r for r in records if r.ticker == "MSFT"]
        assert msft_records[0].status == "pending"

    def test_does_not_re_resolve_already_resolved(self, tracker):
        """Already resolved records are not processed again."""
        tracker.record_decision("AAPL", "2026-01-01", "Buy", "Analysis")

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": 0.02})
        # First resolution
        resolved1 = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)
        assert len(resolved1) == 1

        # Second resolution attempt — should find nothing pending
        resolved2 = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)
        assert len(resolved2) == 0

    def test_resolved_at_is_set(self, tracker):
        """Resolved records have a valid resolved_at timestamp."""
        tracker.record_decision("AAPL", "2026-01-01", "Buy", "Analysis")

        fetcher = _mock_price_fetcher({"AAPL": 0.05, "SPY": 0.02})
        resolved = tracker.resolve_pending("AAPL", "2026-01-10", price_fetcher=fetcher)

        assert resolved[0].resolved_at is not None
        datetime.fromisoformat(resolved[0].resolved_at)  # Should not raise


# ---------------------------------------------------------------------------
# Unit Tests: Cross-Ticker Lessons
# ---------------------------------------------------------------------------


class TestGetCrossTickerLessons:
    """Unit tests for get_cross_ticker_lessons()."""

    def test_empty_log_returns_empty_string(self, tracker):
        """Empty log returns empty string."""
        result = tracker.get_cross_ticker_lessons(exclude_ticker="AAPL", n=3)
        assert result == ""

    def test_only_pending_records_returns_empty(self, tracker):
        """Only pending records returns empty string."""
        tracker.record_decision("MSFT", "2026-01-01", "Buy", "Analysis")
        result = tracker.get_cross_ticker_lessons(exclude_ticker="AAPL", n=3)
        assert result == ""

    def test_all_records_from_excluded_ticker_returns_empty(self, tracker):
        """When all resolved records are from excluded ticker, returns empty."""
        record = DecisionRecord(
            ticker="AAPL",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Analysis",
            status="resolved",
            recorded_at="2026-01-01T00:00:00+00:00",
            actual_return=0.05,
            benchmark_return=0.02,
            alpha=0.03,
            resolved_at="2026-01-06T00:00:00+00:00",
        )
        tracker._write_record(record)

        result = tracker.get_cross_ticker_lessons(exclude_ticker="AAPL", n=3)
        assert result == ""

    def test_includes_header(self, tracker):
        """Output includes a header section."""
        record = DecisionRecord(
            ticker="MSFT",
            trade_date="2026-01-01",
            rating="Buy",
            rationale_summary="Strong cloud growth",
            status="resolved",
            recorded_at="2026-01-01T00:00:00+00:00",
            actual_return=0.04,
            benchmark_return=0.01,
            alpha=0.03,
            resolved_at="2026-01-06T00:00:00+00:00",
        )
        tracker._write_record(record)

        result = tracker.get_cross_ticker_lessons(exclude_ticker="AAPL", n=3)
        assert "Cross-Ticker Decision Lessons" in result


# ---------------------------------------------------------------------------
# Unit Tests: DecisionRecord dataclass
# ---------------------------------------------------------------------------


class TestDecisionRecord:
    """Unit tests for DecisionRecord serialization."""

    def test_to_dict_roundtrip(self):
        """to_dict and from_dict are inverse operations."""
        record = DecisionRecord(
            ticker="AAPL",
            trade_date="2026-01-15",
            rating="Buy",
            rationale_summary="Strong earnings",
            status="resolved",
            recorded_at="2026-01-15T14:30:00+00:00",
            actual_return=0.032,
            benchmark_return=0.011,
            alpha=0.021,
            resolved_at="2026-01-20T09:00:00+00:00",
        )
        data = record.to_dict()
        restored = DecisionRecord.from_dict(data)
        assert restored == record

    def test_from_dict_with_missing_optional_fields(self):
        """from_dict handles missing optional fields gracefully."""
        data = {
            "ticker": "AAPL",
            "trade_date": "2026-01-15",
            "rating": "Buy",
            "rationale_summary": "Strong",
            "status": "pending",
            "recorded_at": "2026-01-15T14:30:00+00:00",
        }
        record = DecisionRecord.from_dict(data)
        assert record.actual_return is None
        assert record.benchmark_return is None
        assert record.alpha is None
        assert record.resolved_at is None


# ---------------------------------------------------------------------------
# Unit Tests: Malformed JSONL handling
# ---------------------------------------------------------------------------


class TestMalformedJsonl:
    """Tests for graceful handling of malformed log entries."""

    def test_skips_malformed_lines(self, tracker):
        """Malformed JSONL lines are skipped without error."""
        # Write a valid record
        tracker.record_decision("AAPL", "2026-01-10", "Buy", "Valid")

        # Manually append a malformed line
        with open(tracker.log_path, "a", encoding="utf-8") as f:
            f.write("this is not valid json\n")

        # Write another valid record
        tracker.record_decision("MSFT", "2026-01-11", "Sell", "Also valid")

        records = tracker._read_all_records()
        assert len(records) == 2
        assert records[0].ticker == "AAPL"
        assert records[1].ticker == "MSFT"

    def test_skips_empty_lines(self, tracker):
        """Empty lines in the log are skipped."""
        tracker.record_decision("AAPL", "2026-01-10", "Buy", "Valid")

        # Manually append empty lines
        with open(tracker.log_path, "a", encoding="utf-8") as f:
            f.write("\n\n\n")

        tracker.record_decision("MSFT", "2026-01-11", "Sell", "Also valid")

        records = tracker._read_all_records()
        assert len(records) == 2


# ---------------------------------------------------------------------------
# Unit Tests: Log path
# ---------------------------------------------------------------------------


class TestLogPath:
    """Tests for log_path property."""

    def test_log_path_location(self, tmp_cache_dir):
        """Log path is at {data_cache_dir}/decision_log.jsonl."""
        tracker = DecisionOutcomeTracker(data_cache_dir=tmp_cache_dir)
        expected = Path(tmp_cache_dir) / "decision_log.jsonl"
        assert tracker.log_path == expected

    def test_creates_parent_directory(self, tmp_path):
        """Parent directory is created if it doesn't exist."""
        nested_dir = str(tmp_path / "nested" / "deep" / "cache")
        tracker = DecisionOutcomeTracker(data_cache_dir=nested_dir)
        tracker.record_decision("AAPL", "2026-01-10", "Buy", "Test")
        assert tracker.log_path.exists()
