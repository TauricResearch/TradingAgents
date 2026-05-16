"""Unit tests for TradingAgents Desktop v3 database layer and utility modules.

Tests cover:
- HistoryDB: all 7 new table CRUD operations
- Frozen dataclass immutability
- Foreign key cascade on schedule delete
- validated_result_dir path validation
- discover_report_files report discovery
- migrate() dry-run mode
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from desktop.state.database import (
    AlertHistoryRow,
    AlertRow,
    AnalysisRow,
    HistoryDB,
    LogEntryRow,
    PositionRow,
    RecommendationOutcomeRow,
    RecommendationRow,
    ScheduleRow,
    ScheduleRunRow,
)
from desktop.utils.paths import validated_result_dir
from desktop.utils.reports import discover_report_files


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path: Path) -> HistoryDB:
    """Create a fresh HistoryDB backed by a temp file."""
    return HistoryDB(db_path=tmp_path / "test.db")


@pytest.fixture()
def db_with_analysis(db: HistoryDB) -> tuple[HistoryDB, int]:
    """DB with one completed analysis row (needed as FK parent for recommendations)."""
    aid = db.insert_analysis(
        ticker="AAPL",
        date="2026-01-15",
        provider="openai",
        model="gpt-4o",
    )
    db.mark_completed(aid)
    return db, aid


# ═══════════════════════════════════════════════════════════════════════════
# Frozen dataclass immutability
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenDataclasses:
    """Verify that all DTO dataclasses are truly frozen."""

    @pytest.mark.unit
    def test_analysis_row_frozen(self) -> None:
        row = AnalysisRow(
            id=1, ticker="AAPL", date="2026-01-01", provider="openai",
            model="gpt-4o", status="completed", started_at="2026-01-01T00:00:00",
            completed_at=None, config_json="{}", result_dir=None,
            error_text=None, selected_analysts="",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.ticker = "MSFT"  # type: ignore[misc]

    @pytest.mark.unit
    def test_recommendation_row_frozen(self) -> None:
        row = RecommendationRow(
            id=1, analysis_id=1, ticker="AAPL", verdict="BUY",
            confidence=8, price_at_analysis=150.0, stop_loss=140.0,
            entry_trigger=148.0, profit_target=170.0, review_date=None,
            is_active=1, created_at="2026-01-01T00:00:00",
            deactivated_at=None, notes=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.verdict = "SELL"  # type: ignore[misc]

    @pytest.mark.unit
    def test_recommendation_outcome_row_frozen(self) -> None:
        row = RecommendationOutcomeRow(
            id=1, recommendation_id=1, check_date="2026-01-10",
            days_elapsed=10, price_at_check=155.0, return_pct=3.33,
            stop_hit=0, target_hit=0, high_since=156.0, low_since=149.0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.return_pct = 5.0  # type: ignore[misc]

    @pytest.mark.unit
    def test_alert_row_frozen(self) -> None:
        row = AlertRow(
            id=1, recommendation_id=1, ticker="AAPL", alert_type="stop_loss",
            target_price=140.0, direction="below", triggered_at=None,
            triggered_price=None, is_active=1, created_at="2026-01-01T00:00:00",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.is_active = 0  # type: ignore[misc]

    @pytest.mark.unit
    def test_alert_history_row_frozen(self) -> None:
        row = AlertHistoryRow(
            id=1, alert_id=1, fired_at="2026-01-05T12:00:00",
            price=139.50, message="Stop loss hit", seen=0,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.seen = 1  # type: ignore[misc]

    @pytest.mark.unit
    def test_schedule_row_frozen(self) -> None:
        row = ScheduleRow(
            id=1, name="Daily scan", watchlist="AAPL,MSFT",
            cron_expr="0 9 * * 1-5", timezone="America/New_York",
            is_enabled=1, last_run=None, next_run=None,
            created_at="2026-01-01T00:00:00",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.is_enabled = 0  # type: ignore[misc]

    @pytest.mark.unit
    def test_schedule_run_row_frozen(self) -> None:
        row = ScheduleRunRow(
            id=1, schedule_id=1, started_at="2026-01-01T09:00:00",
            completed_at=None, status="running",
            tickers_json='["AAPL"]', results_json=None,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.status = "completed"  # type: ignore[misc]

    @pytest.mark.unit
    def test_position_row_frozen(self) -> None:
        row = PositionRow(
            id=1, ticker="AAPL", quantity=100.0, avg_price=150.0,
            date_opened="2026-01-01", notes=None,
            updated_at="2026-01-01T00:00:00",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.quantity = 200.0  # type: ignore[misc]

    @pytest.mark.unit
    def test_log_entry_row_frozen(self) -> None:
        row = LogEntryRow(
            id=1, analysis_id=1, timestamp="2026-01-01T00:00:00",
            entry_type="System", content="started",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            row.content = "changed"  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# Recommendations CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestRecommendationsCRUD:
    """Test recommendations table insert, get, list, deactivate."""

    @pytest.mark.unit
    def test_insert_and_get(self, db_with_analysis: tuple[HistoryDB, int]) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid,
            ticker="AAPL",
            verdict="BUY",
            confidence=8,
            price_at_analysis=150.0,
            stop_loss=140.0,
            entry_trigger=148.0,
            profit_target=170.0,
            review_date="2026-02-15",
            notes="Strong earnings",
        )
        assert rec_id >= 1

        rec = db.get_recommendation(rec_id)
        assert rec is not None
        assert rec.ticker == "AAPL"
        assert rec.verdict == "BUY"
        assert rec.confidence == 8
        assert rec.price_at_analysis == 150.0
        assert rec.stop_loss == 140.0
        assert rec.entry_trigger == 148.0
        assert rec.profit_target == 170.0
        assert rec.review_date == "2026-02-15"
        assert rec.is_active == 1
        assert rec.deactivated_at is None
        assert rec.notes == "Strong earnings"

    @pytest.mark.unit
    def test_get_nonexistent_returns_none(self, db: HistoryDB) -> None:
        assert db.get_recommendation(999) is None

    @pytest.mark.unit
    def test_ticker_uppercased(self, db_with_analysis: tuple[HistoryDB, int]) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="aapl", verdict="hold",
        )
        rec = db.get_recommendation(rec_id)
        assert rec is not None
        assert rec.ticker == "AAPL"
        assert rec.verdict == "HOLD"

    @pytest.mark.unit
    def test_list_active_recommendations(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        r1 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        r2 = db.insert_recommendation(
            analysis_id=aid, ticker="MSFT", verdict="HOLD",
        )
        db.deactivate_recommendation(r1)

        active = db.list_active_recommendations()
        assert len(active) == 1
        assert active[0].id == r2

    @pytest.mark.unit
    def test_list_all_recommendations(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        db.insert_recommendation(analysis_id=aid, ticker="AAPL", verdict="BUY")
        db.insert_recommendation(analysis_id=aid, ticker="MSFT", verdict="HOLD")

        all_recs = db.list_all_recommendations()
        assert len(all_recs) == 2
        # Newest first
        assert all_recs[0].ticker == "MSFT"
        assert all_recs[1].ticker == "AAPL"

    @pytest.mark.unit
    def test_deactivate_recommendation(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        db.deactivate_recommendation(rec_id)

        rec = db.get_recommendation(rec_id)
        assert rec is not None
        assert rec.is_active == 0
        assert rec.deactivated_at is not None

    @pytest.mark.unit
    def test_deactivate_older_for_ticker(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        r1 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        r2 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="HOLD",
        )
        r3 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="SELL",
        )

        count = db.deactivate_older_for_ticker("AAPL", keep_id=r3)
        assert count == 2

        # r3 should still be active
        rec3 = db.get_recommendation(r3)
        assert rec3 is not None
        assert rec3.is_active == 1

        # r1 and r2 should be inactive
        for rid in (r1, r2):
            rec = db.get_recommendation(rid)
            assert rec is not None
            assert rec.is_active == 0

    @pytest.mark.unit
    def test_deactivate_older_for_ticker_case_insensitive(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        """deactivate_older_for_ticker uppercases the ticker argument."""
        db, aid = db_with_analysis
        r1 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        r2 = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="SELL",
        )
        count = db.deactivate_older_for_ticker("aapl", keep_id=r2)
        assert count == 1

    @pytest.mark.unit
    def test_get_recommendation_by_analysis(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        rec = db.get_recommendation_by_analysis(aid)
        assert rec is not None
        assert rec.ticker == "AAPL"

    @pytest.mark.unit
    def test_get_recommendation_by_analysis_none(self, db: HistoryDB) -> None:
        assert db.get_recommendation_by_analysis(999) is None


# ═══════════════════════════════════════════════════════════════════════════
# Recommendation Outcomes CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestRecommendationOutcomesCRUD:
    """Test recommendation_outcomes table insert and list."""

    @pytest.mark.unit
    def test_insert_and_list(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
            price_at_analysis=150.0,
        )

        oid1 = db.insert_outcome(
            recommendation_id=rec_id,
            days_elapsed=7,
            price_at_check=155.0,
            return_pct=3.33,
            stop_hit=False,
            target_hit=False,
            high_since=156.0,
            low_since=149.0,
        )
        oid2 = db.insert_outcome(
            recommendation_id=rec_id,
            days_elapsed=30,
            price_at_check=165.0,
            return_pct=10.0,
            stop_hit=False,
            target_hit=True,
            high_since=167.0,
            low_since=148.0,
        )
        assert oid1 >= 1
        assert oid2 >= 1

        outcomes = db.get_outcomes(rec_id)
        assert len(outcomes) == 2
        # Ordered by days_elapsed ASC
        assert outcomes[0].days_elapsed == 7
        assert outcomes[1].days_elapsed == 30
        assert outcomes[1].target_hit == 1

    @pytest.mark.unit
    def test_list_for_nonexistent_recommendation(self, db: HistoryDB) -> None:
        outcomes = db.get_outcomes(999)
        assert outcomes == []

    @pytest.mark.unit
    def test_list_all_outcomes_with_min_days(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        db.insert_outcome(
            recommendation_id=rec_id, days_elapsed=3,
            price_at_check=151.0, return_pct=0.67,
        )
        db.insert_outcome(
            recommendation_id=rec_id, days_elapsed=14,
            price_at_check=158.0, return_pct=5.33,
        )

        all_outcomes = db.list_all_outcomes(min_days=10)
        assert len(all_outcomes) == 1
        assert all_outcomes[0].days_elapsed == 14


# ═══════════════════════════════════════════════════════════════════════════
# Alerts CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertsCRUD:
    """Test alerts table insert, list_active, list_for_recommendation, trigger."""

    @pytest.mark.unit
    def test_insert_and_list_active(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )

        a1 = db.insert_alert(
            recommendation_id=rec_id,
            ticker="AAPL",
            alert_type="stop_loss",
            target_price=140.0,
            direction="below",
        )
        a2 = db.insert_alert(
            recommendation_id=rec_id,
            ticker="AAPL",
            alert_type="profit_target",
            target_price=170.0,
            direction="above",
        )
        assert a1 >= 1
        assert a2 >= 1

        active = db.list_active_alerts()
        assert len(active) == 2

    @pytest.mark.unit
    def test_list_alerts_for_recommendation(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        db.insert_alert(
            recommendation_id=rec_id,
            ticker="AAPL",
            alert_type="stop_loss",
            target_price=140.0,
            direction="below",
        )
        db.insert_alert(
            recommendation_id=rec_id,
            ticker="AAPL",
            alert_type="entry_trigger",
            target_price=148.0,
            direction="below",
        )

        alerts = db.list_alerts_for_recommendation(rec_id)
        assert len(alerts) == 2
        # Ordered by alert_type ASC
        assert alerts[0].alert_type == "entry_trigger"
        assert alerts[1].alert_type == "stop_loss"

    @pytest.mark.unit
    def test_trigger_alert(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id,
            ticker="AAPL",
            alert_type="stop_loss",
            target_price=140.0,
            direction="below",
        )

        db.trigger_alert(alert_id, price=139.50)

        # Should no longer appear in active alerts
        active = db.list_active_alerts()
        assert len(active) == 0

        # Should appear in full list for the recommendation with trigger data
        all_alerts = db.list_alerts_for_recommendation(rec_id)
        assert len(all_alerts) == 1
        triggered = all_alerts[0]
        assert triggered.is_active == 0
        assert triggered.triggered_price == 139.50
        assert triggered.triggered_at is not None

    @pytest.mark.unit
    def test_ticker_uppercased_on_insert(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id,
            ticker="aapl",
            alert_type="custom",
            target_price=160.0,
            direction="above",
        )
        alerts = db.list_alerts_for_recommendation(rec_id)
        assert alerts[0].ticker == "AAPL"


# ═══════════════════════════════════════════════════════════════════════════
# Alert History CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestAlertHistoryCRUD:
    """Test alert_history table insert, list_all, count_unseen, mark_all_seen."""

    @pytest.mark.unit
    def test_insert_and_list_all(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id, ticker="AAPL",
            alert_type="stop_loss", target_price=140.0, direction="below",
        )

        h1 = db.insert_alert_history(
            alert_id=alert_id, price=139.50, message="Stop loss triggered",
        )
        h2 = db.insert_alert_history(
            alert_id=alert_id, price=138.00, message="Price still falling",
        )
        assert h1 >= 1
        assert h2 >= 1

        history = db.list_all_alert_history()
        assert len(history) == 2
        # Both inserted in the same second, so ORDER BY fired_at DESC
        # falls back to insertion order. Just verify both are present.
        messages = {h.message for h in history}
        assert messages == {"Stop loss triggered", "Price still falling"}

    @pytest.mark.unit
    def test_count_unseen(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id, ticker="AAPL",
            alert_type="stop_loss", target_price=140.0, direction="below",
        )

        db.insert_alert_history(
            alert_id=alert_id, price=139.50, message="Alert 1",
        )
        db.insert_alert_history(
            alert_id=alert_id, price=138.00, message="Alert 2",
        )

        assert db.count_unseen_alert_history() == 2

    @pytest.mark.unit
    def test_mark_all_seen(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id, ticker="AAPL",
            alert_type="stop_loss", target_price=140.0, direction="below",
        )

        h1 = db.insert_alert_history(
            alert_id=alert_id, price=139.50, message="Alert 1",
        )
        h2 = db.insert_alert_history(
            alert_id=alert_id, price=138.00, message="Alert 2",
        )

        db.mark_alerts_seen([h1, h2])

        assert db.count_unseen_alert_history() == 0

        all_history = db.list_all_alert_history()
        for entry in all_history:
            assert entry.seen == 1

    @pytest.mark.unit
    def test_mark_seen_empty_list_is_noop(self, db: HistoryDB) -> None:
        """mark_alerts_seen with empty list should not error."""
        db.mark_alerts_seen([])  # should not raise

    @pytest.mark.unit
    def test_list_unseen_alert_history(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        db, aid = db_with_analysis
        rec_id = db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )
        alert_id = db.insert_alert(
            recommendation_id=rec_id, ticker="AAPL",
            alert_type="stop_loss", target_price=140.0, direction="below",
        )

        h1 = db.insert_alert_history(
            alert_id=alert_id, price=139.50, message="Unseen alert",
        )
        h2 = db.insert_alert_history(
            alert_id=alert_id, price=138.00, message="Also unseen",
        )
        db.mark_alerts_seen([h1])

        unseen = db.list_unseen_alert_history()
        assert len(unseen) == 1
        assert unseen[0].id == h2


# ═══════════════════════════════════════════════════════════════════════════
# Schedules CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestSchedulesCRUD:
    """Test schedules table insert, list, update_enabled, update_last_run,
    update_next_run, and delete with cascade."""

    @pytest.mark.unit
    def test_insert_and_list(self, db: HistoryDB) -> None:
        s1 = db.insert_schedule(
            name="Morning scan",
            watchlist="AAPL,MSFT,GOOG",
            cron_expr="0 9 * * 1-5",
        )
        s2 = db.insert_schedule(
            name="Weekly review",
            watchlist="SPY,QQQ",
            cron_expr="0 18 * * 5",
            timezone="UTC",
        )
        assert s1 >= 1
        assert s2 >= 1

        schedules = db.list_schedules()
        assert len(schedules) == 2
        # Newest first
        assert schedules[0].name == "Weekly review"
        assert schedules[0].timezone == "UTC"
        assert schedules[1].name == "Morning scan"
        assert schedules[1].timezone == "America/New_York"

    @pytest.mark.unit
    def test_update_enabled(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        schedules = db.list_schedules()
        assert schedules[0].is_enabled == 1

        db.update_schedule_enabled(sid, is_enabled=False)

        schedules = db.list_schedules()
        assert schedules[0].is_enabled == 0

        db.update_schedule_enabled(sid, is_enabled=True)
        schedules = db.list_schedules()
        assert schedules[0].is_enabled == 1

    @pytest.mark.unit
    def test_update_last_run(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        db.update_schedule_last_run(
            sid, last_run="2026-01-15T09:00:00", next_run="2026-01-16T09:00:00"
        )

        schedules = db.list_schedules()
        assert schedules[0].last_run == "2026-01-15T09:00:00"
        assert schedules[0].next_run == "2026-01-16T09:00:00"

    @pytest.mark.unit
    def test_update_next_run(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        db.update_schedule_last_run(
            sid, last_run="2026-01-15T09:00:00", next_run="2026-01-16T09:00:00"
        )

        # Update only next_run, last_run should be preserved
        db.update_schedule_next_run(sid, next_run="2026-01-17T09:00:00")

        schedules = db.list_schedules()
        assert schedules[0].last_run == "2026-01-15T09:00:00"
        assert schedules[0].next_run == "2026-01-17T09:00:00"

    @pytest.mark.unit
    def test_delete_schedule(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="To delete", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        assert len(db.list_schedules()) == 1

        db.delete_schedule(sid)
        assert len(db.list_schedules()) == 0

    @pytest.mark.unit
    def test_delete_schedule_cascades_runs(self, db: HistoryDB) -> None:
        """Deleting a schedule must also remove its schedule_runs."""
        sid = db.insert_schedule(
            name="Cascade test", watchlist="AAPL,MSFT", cron_expr="0 9 * * *",
        )
        rid1 = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL", "MSFT"])
        rid2 = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL"])

        runs_before = db.list_schedule_runs(sid)
        assert len(runs_before) == 2

        db.delete_schedule(sid)

        # Schedule gone
        assert len(db.list_schedules()) == 0
        # Runs also gone
        runs_after = db.list_schedule_runs(sid)
        assert len(runs_after) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Schedule Runs CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestScheduleRunsCRUD:
    """Test schedule_runs table insert, update, and list."""

    @pytest.mark.unit
    def test_insert_and_list(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL,MSFT", cron_expr="0 9 * * *",
        )
        rid = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL", "MSFT"])
        assert rid >= 1

        runs = db.list_schedule_runs(sid)
        assert len(runs) == 1
        assert runs[0].status == "running"
        assert runs[0].tickers_json == '["AAPL", "MSFT"]'
        assert runs[0].results_json is None

    @pytest.mark.unit
    def test_update_run_status(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        rid = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL"])

        db.update_schedule_run(
            rid,
            status="completed",
            results=[{"ticker": "AAPL", "verdict": "BUY"}],
        )

        runs = db.list_schedule_runs(sid)
        assert runs[0].status == "completed"
        assert runs[0].completed_at is not None
        assert '"verdict": "BUY"' in (runs[0].results_json or "")

    @pytest.mark.unit
    def test_update_run_without_results(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        rid = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL"])

        db.update_schedule_run(rid, status="failed")

        runs = db.list_schedule_runs(sid)
        assert runs[0].status == "failed"
        assert runs[0].results_json is None

    @pytest.mark.unit
    def test_list_respects_limit(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        for _ in range(5):
            db.insert_schedule_run(schedule_id=sid, tickers=["AAPL"])

        runs = db.list_schedule_runs(sid, limit=3)
        assert len(runs) == 3

    @pytest.mark.unit
    def test_runs_ordered_newest_first(self, db: HistoryDB) -> None:
        sid = db.insert_schedule(
            name="Test", watchlist="AAPL", cron_expr="0 9 * * *",
        )
        r1 = db.insert_schedule_run(schedule_id=sid, tickers=["AAPL"])
        r2 = db.insert_schedule_run(schedule_id=sid, tickers=["MSFT"])

        runs = db.list_schedule_runs(sid)
        assert runs[0].id == r2
        assert runs[1].id == r1


# ═══════════════════════════════════════════════════════════════════════════
# Positions CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TestPositionsCRUD:
    """Test positions table insert (upsert), list, update, and delete."""

    @pytest.mark.unit
    def test_upsert_and_list(self, db: HistoryDB) -> None:
        pid = db.upsert_position(
            ticker="AAPL",
            quantity=100.0,
            avg_price=150.0,
            date_opened="2026-01-15",
            notes="Core holding",
        )
        assert pid >= 1

        positions = db.list_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.ticker == "AAPL"
        assert pos.quantity == 100.0
        assert pos.avg_price == 150.0
        assert pos.date_opened == "2026-01-15"
        assert pos.notes == "Core holding"

    @pytest.mark.unit
    def test_upsert_updates_existing(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="AAPL", quantity=100.0, avg_price=150.0)
        db.upsert_position(ticker="AAPL", quantity=200.0, avg_price=155.0)

        positions = db.list_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 200.0
        assert positions[0].avg_price == 155.0

    @pytest.mark.unit
    def test_ticker_uppercased(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="aapl", quantity=50.0, avg_price=145.0)
        positions = db.list_positions()
        assert positions[0].ticker == "AAPL"

    @pytest.mark.unit
    def test_delete_position(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="AAPL", quantity=100.0, avg_price=150.0)
        db.upsert_position(ticker="MSFT", quantity=50.0, avg_price=400.0)

        db.delete_position("AAPL")

        positions = db.list_positions()
        assert len(positions) == 1
        assert positions[0].ticker == "MSFT"

    @pytest.mark.unit
    def test_delete_case_insensitive(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="AAPL", quantity=100.0, avg_price=150.0)
        db.delete_position("aapl")
        assert len(db.list_positions()) == 0

    @pytest.mark.unit
    def test_positions_ordered_alphabetically(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="MSFT", quantity=50.0, avg_price=400.0)
        db.upsert_position(ticker="AAPL", quantity=100.0, avg_price=150.0)
        db.upsert_position(ticker="GOOG", quantity=25.0, avg_price=175.0)

        positions = db.list_positions()
        tickers = [p.ticker for p in positions]
        assert tickers == ["AAPL", "GOOG", "MSFT"]

    @pytest.mark.unit
    def test_upsert_with_none_optionals(self, db: HistoryDB) -> None:
        db.upsert_position(ticker="AAPL", quantity=100.0, avg_price=150.0)
        positions = db.list_positions()
        assert positions[0].date_opened is None
        assert positions[0].notes is None


# ═══════════════════════════════════════════════════════════════════════════
# validated_result_dir
# ═══════════════════════════════════════════════════════════════════════════


class TestValidatedResultDir:
    """Test the SEC-01 path traversal prevention in validated_result_dir."""

    @pytest.mark.unit
    def test_valid_path_under_results(self) -> None:
        base = Path.home() / ".tradingagents" / "results"
        valid_path = str(base / "2026-01-15_AAPL")
        result = validated_result_dir(valid_path)
        assert result is not None
        assert result == Path(valid_path).resolve()

    @pytest.mark.unit
    def test_path_outside_results_returns_none(self) -> None:
        assert validated_result_dir("/tmp/evil_results") is None

    @pytest.mark.unit
    def test_traversal_attack_returns_none(self) -> None:
        base = Path.home() / ".tradingagents" / "results"
        attack = str(base / ".." / ".." / "etc" / "passwd")
        assert validated_result_dir(attack) is None

    @pytest.mark.unit
    def test_prefix_collision_returns_none(self) -> None:
        """results_evil/ should NOT match results/."""
        base = Path.home() / ".tradingagents" / "results_evil"
        assert validated_result_dir(str(base / "some_dir")) is None

    @pytest.mark.unit
    def test_empty_string_returns_none(self) -> None:
        assert validated_result_dir("") is None

    @pytest.mark.unit
    def test_results_base_itself_is_valid(self) -> None:
        base = Path.home() / ".tradingagents" / "results"
        result = validated_result_dir(str(base))
        assert result is not None


# ═══════════════════════════════════════════════════════════════════════════
# discover_report_files
# ═══════════════════════════════════════════════════════════════════════════


class TestDiscoverReportFiles:
    """Test report file discovery across all three layout formats."""

    @pytest.mark.unit
    def test_numbered_subdirectories_layout(self, tmp_path: Path) -> None:
        """New format: 1_analysts/, 2_research/, etc."""
        analysts = tmp_path / "1_analysts"
        analysts.mkdir()
        (analysts / "fundamentals.md").write_text("# Fundamentals")
        (analysts / "market.md").write_text("# Market")

        research = tmp_path / "2_research"
        research.mkdir()
        (research / "bull.md").write_text("# Bull")

        sections = discover_report_files(tmp_path)
        assert len(sections) == 3
        # Check titles contain phase and file labels
        titles = [title for title, _ in sections]
        assert any("Analysts" in t and "Fundamentals" in t for t in titles)
        assert any("Research" in t and "Bull" in t for t in titles)

    @pytest.mark.unit
    def test_flat_reports_directory_layout(self, tmp_path: Path) -> None:
        """Old format: reports/ subdirectory."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "market_report.md").write_text("# Market")
        (reports_dir / "sentiment_report.md").write_text("# Sentiment")

        sections = discover_report_files(tmp_path)
        assert len(sections) == 2
        titles = [title for title, _ in sections]
        assert "Market Analysis" in titles
        assert "Social Sentiment" in titles

    @pytest.mark.unit
    def test_fallback_root_md_files(self, tmp_path: Path) -> None:
        """Fallback: .md files directly in root."""
        (tmp_path / "fundamentals_report.md").write_text("# Fundamentals")
        (tmp_path / "news_report.md").write_text("# News")
        # complete_report.md should be excluded
        (tmp_path / "complete_report.md").write_text("# Complete")

        sections = discover_report_files(tmp_path)
        assert len(sections) == 2
        titles = [title for title, _ in sections]
        assert "Fundamentals Analysis" in titles
        assert "News Analysis" in titles

    @pytest.mark.unit
    def test_empty_directory(self, tmp_path: Path) -> None:
        sections = discover_report_files(tmp_path)
        assert sections == []

    @pytest.mark.unit
    def test_numbered_dirs_take_priority_over_reports_subdir(
        self, tmp_path: Path
    ) -> None:
        """If numbered subdirs exist, reports/ is ignored."""
        analysts = tmp_path / "1_analysts"
        analysts.mkdir()
        (analysts / "fundamentals.md").write_text("# Fund")

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "market_report.md").write_text("# Market")

        sections = discover_report_files(tmp_path)
        assert len(sections) == 1
        assert "Analysts" in sections[0][0]

    @pytest.mark.unit
    def test_unknown_file_gets_fallback_title(self, tmp_path: Path) -> None:
        """Files not in FILE_TITLES get a humanized stem."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "custom_analysis.md").write_text("# Custom")

        sections = discover_report_files(tmp_path)
        assert len(sections) == 1
        assert sections[0][0] == "Custom Analysis"

    @pytest.mark.unit
    def test_paths_are_correct(self, tmp_path: Path) -> None:
        """Returned paths should be the actual file paths."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        md_file = reports_dir / "market_report.md"
        md_file.write_text("# Market")

        sections = discover_report_files(tmp_path)
        assert sections[0][1] == md_file


# ═══════════════════════════════════════════════════════════════════════════
# migrate() dry-run
# ═══════════════════════════════════════════════════════════════════════════


class TestMigrateDryRun:
    """Test the migration module in dry_run mode with mock data."""

    @pytest.mark.unit
    def test_dry_run_with_no_analyses(self, db: HistoryDB) -> None:
        from desktop.utils.migrate_historical import MigrationStats, migrate

        stats = migrate(db=db, dry_run=True)
        assert isinstance(stats, MigrationStats)
        assert stats.total_analyses == 0
        assert stats.already_migrated == 0
        assert stats.migrated_ok == 0
        assert stats.migrated_unknown == 0
        assert stats.skipped_no_file == 0
        assert stats.skipped_error == 0

    @pytest.mark.unit
    def test_dry_run_skips_no_result_dir(self, db: HistoryDB) -> None:
        from desktop.utils.migrate_historical import migrate

        # Insert analysis with no result_dir
        aid = db.insert_analysis(
            ticker="AAPL", date="2026-01-15", provider="openai", model="gpt-4o",
        )
        db.mark_completed(aid)

        stats = migrate(db=db, dry_run=True)
        assert stats.total_analyses == 1
        assert stats.skipped_no_file == 1

    @pytest.mark.unit
    def test_dry_run_skips_missing_file(self, db: HistoryDB, tmp_path: Path) -> None:
        from desktop.utils.migrate_historical import migrate

        # result_dir exists but no final_trade_decision.md inside it
        result_dir = tmp_path / "results" / "2026-01-15_AAPL"
        result_dir.mkdir(parents=True)

        aid = db.insert_analysis(
            ticker="AAPL", date="2026-01-15", provider="openai", model="gpt-4o",
            result_dir=str(result_dir),
        )
        db.mark_completed(aid)

        stats = migrate(db=db, dry_run=True)
        assert stats.total_analyses == 1
        assert stats.skipped_no_file == 1

    @pytest.mark.unit
    def test_dry_run_counts_successful_extraction(
        self, db: HistoryDB, tmp_path: Path
    ) -> None:
        from desktop.services.recommendation_extractor import (
            ExtractedRecommendation,
        )
        from desktop.utils.migrate_historical import migrate

        result_dir = tmp_path / "results" / "2026-01-15_AAPL"
        result_dir.mkdir(parents=True)
        decision_file = result_dir / "final_trade_decision.md"
        decision_file.write_text("# Decision\n## Verdict: **BUY**\n")

        aid = db.insert_analysis(
            ticker="AAPL", date="2026-01-15", provider="openai", model="gpt-4o",
            result_dir=str(result_dir),
        )
        db.mark_completed(aid)

        mock_rec = ExtractedRecommendation(
            ticker="AAPL", verdict="BUY", confidence=8,
            stop_loss=140.0, entry_trigger=148.0, profit_target=170.0,
        )
        with patch(
            "desktop.utils.migrate_historical.extract_from_file",
            return_value=mock_rec,
        ):
            stats = migrate(db=db, dry_run=True)

        assert stats.total_analyses == 1
        assert stats.migrated_ok == 1
        # Dry run: no actual DB writes
        assert len(db.list_all_recommendations()) == 0

    @pytest.mark.unit
    def test_dry_run_counts_unknown_verdict(
        self, db: HistoryDB, tmp_path: Path
    ) -> None:
        from desktop.services.recommendation_extractor import (
            ExtractedRecommendation,
        )
        from desktop.utils.migrate_historical import migrate

        result_dir = tmp_path / "results" / "2026-01-15_AAPL"
        result_dir.mkdir(parents=True)
        (result_dir / "final_trade_decision.md").write_text("# No verdict\n")

        aid = db.insert_analysis(
            ticker="AAPL", date="2026-01-15", provider="openai", model="gpt-4o",
            result_dir=str(result_dir),
        )
        db.mark_completed(aid)

        mock_rec = ExtractedRecommendation(ticker="AAPL", verdict="UNKNOWN")
        with patch(
            "desktop.utils.migrate_historical.extract_from_file",
            return_value=mock_rec,
        ):
            stats = migrate(db=db, dry_run=True)

        assert stats.migrated_unknown == 1
        assert stats.migrated_ok == 0

    @pytest.mark.unit
    def test_dry_run_skips_already_migrated(
        self, db_with_analysis: tuple[HistoryDB, int]
    ) -> None:
        from desktop.utils.migrate_historical import migrate

        db, aid = db_with_analysis
        # Pre-create a recommendation for this analysis
        db.insert_recommendation(
            analysis_id=aid, ticker="AAPL", verdict="BUY",
        )

        stats = migrate(db=db, dry_run=True)
        assert stats.already_migrated == 1
        assert stats.migrated_ok == 0

    @pytest.mark.unit
    def test_dry_run_handles_extraction_error(
        self, db: HistoryDB, tmp_path: Path
    ) -> None:
        from desktop.utils.migrate_historical import migrate

        result_dir = tmp_path / "results" / "2026-01-15_AAPL"
        result_dir.mkdir(parents=True)
        (result_dir / "final_trade_decision.md").write_text("corrupt data")

        aid = db.insert_analysis(
            ticker="AAPL", date="2026-01-15", provider="openai", model="gpt-4o",
            result_dir=str(result_dir),
        )
        db.mark_completed(aid)

        with patch(
            "desktop.utils.migrate_historical.extract_from_file",
            side_effect=ValueError("Parse error"),
        ):
            stats = migrate(db=db, dry_run=True)

        assert stats.skipped_error == 1

    @pytest.mark.unit
    def test_migration_stats_frozen(self) -> None:
        from desktop.utils.migrate_historical import MigrationStats

        stats = MigrationStats(
            total_analyses=10, already_migrated=2, migrated_ok=5,
            migrated_unknown=1, skipped_no_file=1, skipped_error=1,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            stats.total_analyses = 20  # type: ignore[misc]


# ═══════════════════════════════════════════════════════════════════════════
# Schema and DB init
# ═══════════════════════════════════════════════════════════════════════════


class TestDBInit:
    """Test database initialisation and schema creation."""

    @pytest.mark.unit
    def test_creates_db_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "new.db"
        assert not db_path.exists()
        HistoryDB(db_path=db_path)
        assert db_path.exists()

    @pytest.mark.unit
    def test_idempotent_schema(self, tmp_path: Path) -> None:
        """Creating HistoryDB twice on same file should not error."""
        db_path = tmp_path / "test.db"
        HistoryDB(db_path=db_path)
        HistoryDB(db_path=db_path)  # should not raise

    @pytest.mark.unit
    def test_foreign_keys_enabled(self, tmp_path: Path) -> None:
        """Verify that PRAGMA foreign_keys is ON."""
        db = HistoryDB(db_path=tmp_path / "fk_test.db")
        conn = db._connect()
        try:
            row = conn.execute("PRAGMA foreign_keys").fetchone()
            assert row[0] == 1
        finally:
            conn.close()
