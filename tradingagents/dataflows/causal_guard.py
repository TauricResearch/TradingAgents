"""Event-to-price causal guard (Phase 1, contract section 3.2).

A claim like "the stock absorbed the earnings with a X% move" is only valid
if the price window used starts after the event was actually published and
falls on the right kind of session. This module answers exactly that
question, deterministically, for any ticker/date/event — the BRK-B case
(Q3 published Saturday 2026-11-07, report run Sunday 2026-11-08, last
session Friday 2026-11-06) is the regression fixture, not a special rule.

Three outcomes, per the contract:

- ``NOT_YET_OBSERVABLE``: no session has traded after the event yet. Any
  "market reaction" claim is temporally false.
- ``OBSERVABLE``: post-event prices exist and are validated; the window is
  reported explicitly.
- ``INSUFFICIENT_DATA``: no reliable prices or timestamps to decide.

A close *before* the publication can never be a post-event reaction, and an
article merely existing does not prove a price impact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

# Statuses the contract's decision schema (section 8) carries verbatim.
NOT_YET_OBSERVABLE = "NOT_YET_OBSERVABLE"
OBSERVABLE = "OBSERVABLE"
# The post-event session is trading right now: a price move exists but it is
# not yet a confirmed close. §5 requires these to be different verdicts - an
# intraday reaction is not the EOD reaction a strategy may trade on.
OBSERVABLE_INTRADAY = "OBSERVABLE_INTRADAY"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


def _parse_date(value: str | date | datetime | None) -> date | None:
    """Parse YYYY-MM-DD (or date/datetime) to a plain date; None if unusable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass(frozen=True)
class CausalVerdict:
    """The causal status of a post-event price window, with its evidence."""

    status: str
    event_date: str | None          # YYYY-MM-DD the event was published
    last_session_before: str | None  # last trading session on/before the event
    first_session_after: str | None  # first trading session strictly after it
    reason: str

    @property
    def reaction_claim_allowed(self) -> bool:
        """Whether a 'the market reacted to this event' claim can be true yet.

        Only an ``OBSERVABLE`` verdict allows it. An ``OBSERVABLE_INTRADAY``
        result means a move is happening but no session has closed since the
        event, so the reaction is not settled — and a strategy that needs a
        confirmed close must not be told otherwise (§5).
        """
        return self.status == OBSERVABLE

    @property
    def reaction_in_progress(self) -> bool:
        """Whether the post-event session is trading right now.

        The distinction the 19:24 report collapsed: an intraday move is
        observable as *movement*, and is not the same evidence as a closed
        session's reaction.
        """
        return self.status == OBSERVABLE_INTRADAY

    @property
    def needs_confirmed_close(self) -> bool:
        """Whether a confirmed-close strategy must wait for this verdict."""
        return self.status == OBSERVABLE_INTRADAY


def last_session_on_or_before(sessions: list[str], day: str | date | datetime | None) -> str | None:
    """The latest session date strictly usable at ``day`` (on or before it).

    ``sessions`` are YYYY-MM-DD trading dates, any order. Returns None when
    no session qualifies.
    """
    day_d = _parse_date(day)
    if day_d is None:
        return None
    eligible = [s for s in sessions if (_d := _parse_date(s)) is not None and _d <= day_d]
    return max(eligible) if eligible else None


def first_session_after(sessions: list[str], day: str | date | datetime | None) -> str | None:
    """The earliest session date strictly after ``day``, or None if none yet."""
    day_d = _parse_date(day)
    if day_d is None:
        return None
    eligible = [s for s in sessions if (_d := _parse_date(s)) is not None and _d > day_d]
    return min(eligible) if eligible else None


def evaluate_post_event_pricing(
    event_published_at: str | date | datetime | None,
    sessions: list[str],
    *,
    as_of_date: str | date | datetime | None = None,
    session_still_open: bool = False,
) -> CausalVerdict:
    """Whether post-event prices exist for an event published at a known time.

    ``sessions`` is the market calendar (XNYS trading dates, YYYY-MM-DD) the
    run has validated. ``as_of_date`` is the analysis date; it defaults to
    today. The verdict is a pure function of these inputs: no network, no
    LLM, no per-ticker special cases.

    ``session_still_open`` says whether the latest post-event session is
    trading at the moment of analysis. When it is, the verdict is
    ``OBSERVABLE_INTRADAY``: a move is happening, but no close has settled, so
    it is not the reaction a confirmed-close strategy may trade on. Without
    this flag an intraday price would be indistinguishable from a closed
    session's — which is exactly the confusion the 19:24 report made.

    An unknown publication time is ``INSUFFICIENT_DATA`` by design: the
    contract forbids inventing ``published_at``, and a causal claim without
    it cannot be checked.
    """
    event_d = _parse_date(event_published_at)
    if event_d is None:
        return CausalVerdict(
            status=INSUFFICIENT_DATA,
            event_date=None,
            last_session_before=None,
            first_session_after=None,
            reason="event publication time is unknown; a causal claim cannot be checked",
        )

    as_of_d = _parse_date(as_of_date) or datetime.now().date()
    known_sessions = sorted(s for s in sessions if _parse_date(s) is not None)
    last_before = last_session_on_or_before(known_sessions, event_d)
    first_after = first_session_after(known_sessions, event_d)

    if first_after is None:
        # No session has traded after the event (yet): the weekend case.
        # A session on the event day itself does not count — it may have
        # closed before the publication, so it is not a post-event price.
        return CausalVerdict(
            status=NOT_YET_OBSERVABLE,
            event_date=f"{event_d:%Y-%m-%d}",
            last_session_before=last_before,
            first_session_after=None,
            reason=(
                f"no trading session after {event_d:%Y-%m-%d} has occurred as of "
                f"{as_of_d:%Y-%m-%d}; any market-reaction claim is not yet checkable"
            ),
        )

    if _parse_date(first_after) > as_of_d:
        # A session exists on the calendar after the event but is in the
        # future relative to the analysis date: still not observable.
        return CausalVerdict(
            status=NOT_YET_OBSERVABLE,
            event_date=f"{event_d:%Y-%m-%d}",
            last_session_before=last_before,
            first_session_after=first_after,
            reason=(
                f"the first post-event session ({first_after}) is after the "
                f"analysis date ({as_of_d:%Y-%m-%d})"
            ),
        )

    if session_still_open:
        return CausalVerdict(
            status=OBSERVABLE_INTRADAY,
            event_date=f"{event_d:%Y-%m-%d}",
            last_session_before=last_before,
            first_session_after=first_after,
            reason=(
                f"the post-event session {first_after} is still trading: the "
                "reaction is observable as movement but no close has settled, "
                "so it is not an end-of-day reaction"
            ),
        )

    return CausalVerdict(
        status=OBSERVABLE,
        event_date=f"{event_d:%Y-%m-%d}",
        last_session_before=last_before,
        first_session_after=first_after,
        reason=(
            f"post-event prices available from {first_after} "
            f"(event published {event_d:%Y-%m-%d})"
        ),
    )


def check_reaction_window(
    window_start: str | date | datetime,
    window_end: str | date | datetime,
    event_published_at: str | date | datetime | None,
) -> tuple[bool, str]:
    """Whether a price window may back a 'market reaction to the event' claim.

    The whole window must start strictly after the publication. Returns
    ``(allowed, reason)``; an unknown publication time is never allowed.
    """
    event_d = _parse_date(event_published_at)
    if event_d is None:
        return False, "event publication time is unknown; the window cannot be checked"
    start_d = _parse_date(window_start)
    end_d = _parse_date(window_end)
    if start_d is None or end_d is None:
        return False, "window bounds are not valid dates"
    if start_d < end_d and start_d > event_d:
        return True, f"window {start_d:%Y-%m-%d}..{end_d:%Y-%m-%d} starts after the event"
    if start_d <= event_d:
        return False, (
            f"window starts {start_d:%Y-%m-%d}, on or before the event "
            f"({event_d:%Y-%m-%d}): a pre-event close cannot be a post-event reaction"
        )
    return False, "window is empty or inverted"


def sessions_between(start: str | date | datetime, end: str | date | datetime) -> list[str]:
    """Calendar dates from ``start`` to ``end`` inclusive, as YYYY-MM-DD.

    A helper for tests and callers that have no market calendar handy; it
    returns *calendar* days, not trading days. Production callers should
    pass a validated XNYS calendar to ``evaluate_post_event_pricing``.
    """
    start_d, end_d = _parse_date(start), _parse_date(end)
    if start_d is None or end_d is None or start_d > end_d:
        return []
    days = (end_d - start_d).days
    return [f"{start_d + timedelta(days=i):%Y-%m-%d}" for i in range(days + 1)]
