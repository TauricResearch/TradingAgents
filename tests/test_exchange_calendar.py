"""The exchange calendar (§5): holidays and early closes, and what they imply.

``session.py`` alone reasons about weekends and a 09:30-16:00 session. Two
things make that insufficient, and both were untested:

**A holiday has no session**, so a bar dated Thanksgiving is not a close at
all — it is a stale price wearing today's date.

**An early close at 13:00** makes a 14:30 bar belong to *no* session. Judging
it by the 16:00 default would call it a settled close and certify a price no
session ever produced.

The calendar states its own coverage: a year outside the table is
``UNCOVERED``, not "trading as usual". Silently assuming a normal session for
an unknown year is precisely the failure this module prevents.
"""

from __future__ import annotations

from tradingagents.dataflows.math.exchange_calendar import (
    COVERED_YEARS,
    DayKind,
    is_trading_day,
    last_completed_session,
    previous_trading_day,
    session_day,
)
from tradingagents.dataflows.math.session import assess_bar


class TestHolidays:
    def test_thanksgiving_is_not_a_trading_day(self):
        info = session_day("2026-11-26")
        assert info.kind == DayKind.HOLIDAY
        assert info.trades is False
        assert info.close_time is None

    def test_a_regular_weekday_is_a_trading_day(self):
        info = session_day("2026-11-06")
        assert info.kind == DayKind.TRADING
        assert info.trades is True

    def test_a_weekend_does_not_trade(self):
        assert session_day("2026-11-07").kind == DayKind.WEEKEND
        assert is_trading_day("2026-11-08") is False

    def test_the_observed_independence_day_is_a_holiday(self):
        """2026-07-04 is a Saturday, so the market closes on the 3rd."""
        assert session_day("2026-07-03").kind == DayKind.HOLIDAY
        assert is_trading_day("2026-07-02") is True


class TestEarlyCloses:
    def test_the_friday_after_thanksgiving_closes_at_13(self):
        info = session_day("2026-11-27")
        assert info.kind == DayKind.EARLY_CLOSE
        assert info.trades is True
        assert info.close_time.hour == 13

    def test_christmas_eve_closes_at_13(self):
        assert session_day("2026-12-24").close_time.hour == 13

    def test_a_regular_day_closes_at_16(self):
        assert session_day("2026-11-06").close_time.hour == 16


class TestUncoveredYears:
    def test_a_year_outside_the_table_is_not_assumed_trading(self):
        info = session_day("2031-06-03")
        assert info.kind == DayKind.UNCOVERED
        assert info.is_covered is False
        assert info.trades is False

    def test_the_coverage_is_stated(self):
        assert min(COVERED_YEARS) <= 2026 <= max(COVERED_YEARS)

    def test_previous_trading_day_refuses_an_uncovered_year(self):
        """Better no answer than a wrong date derived from an unknown calendar."""
        assert previous_trading_day("2031-06-03") is None


class TestPreviousTradingDay:
    def test_monday_after_a_normal_weekend_resolves_to_friday(self):
        assert previous_trading_day("2026-11-09") == "2026-11-06"

    def test_the_day_after_a_holiday_resolves_past_it(self):
        assert previous_trading_day("2026-11-27") == "2026-11-25"

    def test_a_holiday_itself_resolves_to_the_prior_session(self):
        assert previous_trading_day("2026-11-26") == "2026-11-25"


class TestBarsOnSpecialDays:
    """The behaviour the calendar exists to change."""

    def test_a_bar_on_a_holiday_is_not_a_close(self):
        assessment = assess_bar("2026-11-26", analysis_time="2026-11-27T10:00:00-05:00")
        assert assessment.is_complete is False
        assert "not a trading day" in assessment.reason

    def test_a_bar_after_an_early_close_is_not_a_close(self):
        """14:30 on a 13:00 close day belongs to no session."""
        assessment = assess_bar("2026-11-27T14:30:00",
                                analysis_time="2026-11-27T15:30:00-05:00")
        assert assessment.is_complete is False
        assert "outside the session's hours" in assessment.reason

    def test_a_bar_at_the_early_close_is_a_close(self):
        assessment = assess_bar("2026-11-27T13:00:00",
                                analysis_time="2026-11-27T15:30:00-05:00")
        assert assessment.is_complete is True

    def test_a_bar_before_the_early_close_is_still_forming(self):
        assessment = assess_bar("2026-11-27T12:00:00",
                                analysis_time="2026-11-27T15:30:00-05:00")
        assert assessment.is_complete is False

    def test_a_bar_at_the_regular_close_is_still_a_close(self):
        """The inclusive bound: 16:00 is the session's last moment."""
        assessment = assess_bar("2026-11-06T16:00:00",
                                analysis_time="2026-11-09T12:37:00-05:00")
        assert assessment.is_complete is True

    def test_an_intraday_bar_on_a_normal_day_is_still_forming(self):
        assessment = assess_bar("2026-11-09T15:30:00",
                                analysis_time="2026-11-09T18:37:00+01:00")
        assert assessment.is_complete is False

    def test_an_uncovered_year_is_assessed_on_the_regular_session(self):
        """No verified calendar, so the regular close is used — not a refusal."""
        assessment = assess_bar("2031-06-03T16:00:00",
                                analysis_time="2031-06-04T10:00:00-04:00")
        assert assessment.is_complete is True


class TestLastCompletedSession:
    def test_before_the_close_the_previous_session_answers(self):
        assert last_completed_session(
            "2026-11-09T12:00:00-05:00", close_time=None,
            session_date="2026-11-09") == "2026-11-06"

    def test_after_the_close_the_day_itself_answers(self):
        assert last_completed_session(
            "2026-11-09T17:00:00-05:00", close_time=None,
            session_date="2026-11-09") == "2026-11-09"
