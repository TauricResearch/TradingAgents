"""The exchange calendar (§5): holidays and early closes, stated not guessed.

``session.py`` reasons about weekends and the regular 09:30-16:00 session. That
covers the regression case — an 18:37 Rome analysis is 12:37 New York, inside
the session — but not two things that make a bar look settled when it is not:

**Holidays.** A weekday holiday has no session, so a bar dated that day is
stale by definition. Treating it as a normal trading day is how a Friday close
gets compared against a Tuesday that never traded.

**Early closes.** On the day before Independence Day, Thanksgiving Friday and
Christmas Eve the NYSE closes at 13:00. Judging those days by the 16:00 default
would call a 14:00 bar *complete* — and it is not: the session ended two hours
earlier and the bar at 14:00 belongs to no session at all.

The calendar is data, not inference. A hardcoded list of holidays is preferable
to computing Easter and presidential decrees at runtime, and it says its own
coverage: a year outside the table is ``UNCOVERED``, not "trading as usual".
That distinction matters — silently assuming a normal session for an unknown
year is exactly the failure this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

# Regular session, and the two early-close times the NYSE uses.
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)

# Full-day market holidays, by year. US equity markets observe these; a year
# absent from the table is UNCOVERED rather than assumed.
HOLIDAYS: dict[int, frozenset[str]] = {
    2025: frozenset({
        "2025-01-01",  # New Year's Day
        "2025-01-09",  # National Day of Mourning (Carter)
        "2025-01-20",  # Martin Luther King Jr. Day
        "2025-02-17",  # Washington's Birthday
        "2025-04-18",  # Good Friday
        "2025-05-26",  # Memorial Day
        "2025-06-19",  # Juneteenth
        "2025-07-04",  # Independence Day
        "2025-09-01",  # Labor Day
        "2025-11-27",  # Thanksgiving
        "2025-12-25",  # Christmas
    }),
    2026: frozenset({
        "2026-01-01",  # New Year's Day
        "2026-01-19",  # Martin Luther King Jr. Day
        "2026-02-16",  # Washington's Birthday
        "2026-04-03",  # Good Friday
        "2026-05-25",  # Memorial Day
        "2026-06-19",  # Juneteenth
        "2026-07-03",  # Independence Day observed (4th is a Saturday)
        "2026-09-07",  # Labor Day
        "2026-11-26",  # Thanksgiving
        "2026-12-25",  # Christmas
    }),
    2027: frozenset({
        "2027-01-01",  # New Year's Day
        "2027-01-18",  # Martin Luther King Jr. Day
        "2027-02-15",  # Washington's Birthday
        "2027-03-26",  # Good Friday
        "2027-05-31",  # Memorial Day
        "2027-06-18",  # Juneteenth observed (19th is a Saturday)
        "2027-07-05",  # Independence Day observed (4th is a Sunday)
        "2027-09-06",  # Labor Day
        "2027-11-25",  # Thanksgiving
        "2027-12-24",  # Christmas observed (25th is a Saturday)
    }),
}

# Sessions that close at 13:00. These are the NYSE's published early closes:
# the Friday after Thanksgiving, Christmas Eve, and the day before
# Independence Day when it falls on a weekday.
EARLY_CLOSES: dict[int, frozenset[str]] = {
    2025: frozenset({"2025-07-03", "2025-11-28", "2025-12-24"}),
    2026: frozenset({"2026-11-27", "2026-12-24"}),
    2027: frozenset({"2027-11-26"}),
}

# The range the tables above actually describe.
COVERED_YEARS = frozenset(HOLIDAYS) & frozenset(EARLY_CLOSES)


class DayKind:
    """What kind of trading day a date is."""

    TRADING = "TRADING"
    EARLY_CLOSE = "EARLY_CLOSE"
    HOLIDAY = "HOLIDAY"
    WEEKEND = "WEEKEND"
    UNCOVERED = "UNCOVERED"   # a year the calendar does not describe
    UNPARSEABLE = "UNPARSEABLE"


@dataclass(frozen=True)
class SessionDay:
    """One calendar day's session, with what was actually known about it."""

    day: str | None
    kind: str
    opens: time | None
    closes: time | None
    reason: str = ""

    @property
    def trades(self) -> bool:
        """Whether any session occurs on this day."""
        return self.kind in (DayKind.TRADING, DayKind.EARLY_CLOSE)

    @property
    def is_covered(self) -> bool:
        """Whether the calendar actually describes this year."""
        return self.kind is not DayKind.UNCOVERED

    @property
    def close_time(self) -> time | None:
        return self.closes if self.trades else None

    def summary(self) -> dict:
        return {
            "session_date": self.day,
            "day_kind": self.kind,
            "opens": self.opens.strftime("%H:%M") if self.opens else None,
            "closes": self.closes.strftime("%H:%M") if self.closes else None,
            "trades": self.trades,
            "is_covered": self.is_covered,
            "reason": self.reason,
        }


def _parse_day(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def session_day(value: str | date | None) -> SessionDay:
    """What the exchange does on this date, and whether the calendar knows.

    An uncovered year returns ``UNCOVERED`` with no session times rather than
    the regular schedule: a caller that needs certainty can then refuse, and
    one that only needs a rough answer can still see it was not verified.
    """
    day = _parse_day(value)
    if day is None:
        return SessionDay(None, DayKind.UNPARSEABLE, None, None,
                          "the date could not be read")
    iso = day.isoformat()
    if day.weekday() in (5, 6):
        return SessionDay(iso, DayKind.WEEKEND, None, None,
                          "the exchange does not trade at the weekend")
    if day.year not in COVERED_YEARS:
        return SessionDay(
            iso, DayKind.UNCOVERED, None, None,
            f"the calendar covers {min(COVERED_YEARS)}-{max(COVERED_YEARS)}; "
            f"{day.year} is not described, so no session is assumed",
        )
    if iso in HOLIDAYS[day.year]:
        return SessionDay(iso, DayKind.HOLIDAY, None, None,
                          "a full-day market holiday")
    if iso in EARLY_CLOSES[day.year]:
        return SessionDay(iso, DayKind.EARLY_CLOSE, REGULAR_OPEN, EARLY_CLOSE,
                          "the exchange closes early at 13:00")
    return SessionDay(iso, DayKind.TRADING, REGULAR_OPEN, REGULAR_CLOSE,
                      "a regular session")


def is_trading_day(value: str | date | None) -> bool:
    """Whether any session occurs on this date."""
    return session_day(value).trades


def previous_trading_day(value: str | date | None) -> str | None:
    """The most recent trading day strictly before ``value``.

    Walks back through the calendar rather than subtracting one weekday, so a
    Monday after a holiday weekend resolves to the Friday before it, not to the
    holiday. Returns ``None`` when the calendar cannot answer — an uncovered
    year has no trustworthy "previous".
    """
    day = _parse_day(value)
    if day is None:
        return None
    if day.year not in COVERED_YEARS:
        return None
    from datetime import timedelta

    candidate = day - timedelta(days=1)
    for _ in range(30):
        if candidate.year in COVERED_YEARS:
            info = session_day(candidate)
            if info.trades:
                return info.day
        elif candidate.year < min(COVERED_YEARS):
            return None
        candidate -= timedelta(days=1)
    return None


def last_completed_session(now: str | date | None, close_time: time,
                           *, session_date: str | date | None = None) -> str | None:
    """The last session whose close has settled as of ``now``.

    ``session_date`` is the date of the bar or analysis; when that day is still
    trading, the answer is the previous trading day. When it has closed, it is
    the day itself — with the *day's own* close time, so an early close is
    treated as settled from 13:00 rather than from 16:00.
    """

    day = _parse_day(session_date) or _parse_day(now)
    if day is None:
        return None
    if in_session(now, session_date=day, close_time=close_time):
        return previous_trading_day(day)
    info = session_day(day)
    if info.trades:
        return info.day
    return previous_trading_day(day)


def in_session(moment: str | date | None, *, session_date: str | date | None,
               close_time: time) -> bool:
    """Whether ``moment`` falls inside a session, at its own day's hours.

    A date-only moment is at midnight, before any session, so it is never
    "in session" — which is what a bar dated today (with no clock) needs.
    """
    from datetime import datetime

    if not isinstance(moment, str) or "T" not in moment and ":" not in moment:
        return False
    try:
        stamp = datetime.fromisoformat(str(moment).replace("Z", "+00:00"))
    except ValueError:
        return False
    day = _parse_day(session_date) or stamp.date()
    info = session_day(day)
    if not info.trades:
        return False
    local = stamp.timetz().replace(tzinfo=None) if stamp.tzinfo else stamp.time()
    closes = info.close_time or close_time
    opens = info.opens or REGULAR_OPEN
    return opens <= local < closes
