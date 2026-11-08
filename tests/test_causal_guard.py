"""Phase 1 — event-to-price causal guard tests (contract section 3.2).

The BRK-B case is the regression fixture: Q3 published Saturday 2026-11-07,
last XNYS session Friday 2026-11-06, report run Sunday 2026-11-08. The guard
must answer NOT_YET_OBSERVABLE there — for any ticker, since the rule is
calendar-based, never hardcoded. Pure functions, frozen dates, no network.
"""

from __future__ import annotations

import pytest

from tradingagents.dataflows.causal_guard import (
    INSUFFICIENT_DATA,
    NOT_YET_OBSERVABLE,
    OBSERVABLE,
    check_reaction_window,
    evaluate_post_event_pricing,
    first_session_after,
    last_session_on_or_before,
    sessions_between,
)

# A realistic XNYS slice around the fixture: Fri 11-06 trades, the weekend
# does not, Mon 11-09 is the next session.
XNYS = ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]


# ---------------------------------------------------------------------------
# The BRK-B regression case (contract section 9, test 1)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_weekend_release_before_next_session_is_not_yet_observable():
    """Sat release, Sun report: Monday has not traded -> NOT_YET_OBSERVABLE.

    Monday 11-09 is on the calendar but is after the Sunday analysis date,
    so the verdict reports it as the (future) first post-event session while
    still withholding the reaction claim.
    """
    verdict = evaluate_post_event_pricing(
        "2026-11-07", XNYS, as_of_date="2026-11-08"
    )
    assert verdict.status == NOT_YET_OBSERVABLE
    assert verdict.last_session_before == "2026-11-06"
    assert verdict.first_session_after == "2026-11-09"  # known but not yet traded
    assert not verdict.reaction_claim_allowed


@pytest.mark.unit
def test_friday_close_is_not_a_post_event_reaction():
    """The window check rejects a pre-event close as a 'reaction'."""
    allowed, reason = check_reaction_window(
        "2026-11-06", "2026-11-06", "2026-11-07"
    )
    assert not allowed
    assert "before the event" in reason


@pytest.mark.unit
def test_reaction_window_after_event_is_allowed():
    allowed, reason = check_reaction_window(
        "2026-11-09", "2026-11-10", "2026-11-07"
    )
    assert allowed
    assert "after the event" in reason


@pytest.mark.unit
def test_unknown_publication_time_is_insufficient_data():
    """No invented published_at: an unknown time blocks the causal claim."""
    verdict = evaluate_post_event_pricing(None, XNYS, as_of_date="2026-11-08")
    assert verdict.status == INSUFFICIENT_DATA
    assert not verdict.reaction_claim_allowed


@pytest.mark.unit
def test_unparseable_publication_date_is_insufficient_not_crash():
    verdict = evaluate_post_event_pricing("not-a-date", XNYS, as_of_date="2026-11-08")
    assert verdict.status == INSUFFICIENT_DATA


# ---------------------------------------------------------------------------
# Observable path and calendar edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_session_after_event_makes_reaction_observable():
    """Once Monday has traded, the reaction window exists and is reported."""
    verdict = evaluate_post_event_pricing(
        "2026-11-07", XNYS, as_of_date="2026-11-09"
    )
    assert verdict.status == OBSERVABLE
    assert verdict.first_session_after == "2026-11-09"
    assert verdict.reaction_claim_allowed


@pytest.mark.unit
def test_future_session_on_calendar_is_still_not_observable():
    """A calendar entry after the analysis date does not make it observable."""
    verdict = evaluate_post_event_pricing(
        "2026-11-07", XNYS, as_of_date="2026-11-08"
    )
    # Monday 11-09 is on the calendar but after the Sunday analysis date.
    assert verdict.status == NOT_YET_OBSERVABLE


@pytest.mark.unit
def test_same_day_publication_after_close_is_not_observable():
    """An event published on a trading day: that session is not post-event.

    The session may have closed before the publication, so the first usable
    session is strictly the next one.
    """
    verdict = evaluate_post_event_pricing(
        "2026-11-06", XNYS, as_of_date="2026-11-06"
    )
    assert verdict.status == NOT_YET_OBSERVABLE
    assert verdict.last_session_before == "2026-11-06"


@pytest.mark.unit
def test_empty_calendar_is_not_yet_observable_not_a_crash():
    verdict = evaluate_post_event_pricing("2026-11-07", [], as_of_date="2026-11-08")
    assert verdict.status == NOT_YET_OBSERVABLE


@pytest.mark.unit
def test_as_of_defaults_to_today():
    """Without an explicit analysis date the guard uses today's date."""
    verdict = evaluate_post_event_pricing("2999-01-01", XNYS)
    assert verdict.status == NOT_YET_OBSERVABLE


# ---------------------------------------------------------------------------
# Calendar helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_last_session_on_or_before_picks_the_latest_eligible():
    assert last_session_on_or_before(XNYS, "2026-11-08") == "2026-11-06"
    assert last_session_on_or_before(XNYS, "2026-11-06") == "2026-11-06"
    assert last_session_on_or_before(XNYS, "2026-11-03") is None
    assert last_session_on_or_before(XNYS, None) is None


@pytest.mark.unit
def test_first_session_after_is_strict():
    assert first_session_after(XNYS, "2026-11-07") == "2026-11-09"
    assert first_session_after(XNYS, "2026-11-09") == "2026-11-10"
    assert first_session_after(XNYS, "2026-11-10") is None


@pytest.mark.unit
def test_sessions_between_is_inclusive_and_ordered():
    assert sessions_between("2026-11-06", "2026-11-09") == [
        "2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09",
    ]
    assert sessions_between("2026-11-09", "2026-11-06") == []
