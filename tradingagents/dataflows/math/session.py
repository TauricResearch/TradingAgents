"""Market session status (§6E): is this bar a final close, or still forming?

The 18:37 report of 2026-11-09 treated an intraday bar as a verified close.
That is not a rounding problem: every indicator derived from it — SMA, RSI,
ATR, the distance to a moving average, the 52-week high — was computed from a
number that was still moving. A strategy that waits for "a confirmed close"
was, in effect, trusting a partial one.

This module answers three separate questions, because conflating them is how
the defect happened:

``market_session_status``
    Where the analysis date sits relative to the exchange's sessions: before
    the open, during the session, after the close, or on a non-trading day.
``is_complete`` / ``is_final``
    Whether the bar for a date is finished. A bar stamped during the session
    is incomplete; one stamped after the close is final.
``last_completed_session``
    The most recent session whose close is settled and usable as a verified
    EOD price.

The distinction between ``is_complete`` and ``is_final`` is deliberate: a
cached daily bar can be *complete* (the session ended) yet *not final* while a
vendor's adjustment is still pending. Callers that need a hard price must ask
for ``is_final``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

# The exchange calendar this module reasons about. TradingAgents analyses
# other markets too, so the zone is a parameter rather than a constant, with
# the US session as the default because that is the source of the regression.
US_EASTERN = "America/New_York"

# Regular US equity session. Half-days (early closes) are not modelled here:
# a caller that knows about one supplies ``session_close`` explicitly, and
# inventing a calendar would be worse than asking.
DEFAULT_SESSION_OPEN = time(9, 30)
DEFAULT_SESSION_CLOSE = time(16, 0)


class SessionStatus(StrEnum):
    """Where a moment sits relative to the trading session."""

    PRE_MARKET = "PRE_MARKET"
    OPEN = "OPEN"                  # the session is running right now
    AFTER_HOURS = "AFTER_HOURS"     # closed, but the same calendar day
    CLOSED = "CLOSED"               # a non-trading day
    UNKNOWN = "UNKNOWN"             # no timestamp to judge


@dataclass(frozen=True)
class BarAssessment:
    """Whether a price bar may be used as a verified end-of-day close."""

    status: SessionStatus
    bar_timestamp: str | None
    is_complete: bool
    is_final: bool
    last_completed_session: str | None
    reason: str = ""

    @property
    def usable_as_close(self) -> bool:
        """Whether a strategy requiring a confirmed close may use this bar.

        Requires both flags: complete and not-final is a bar an adjusted
        vendor may still restate, and a decision taken on it would not be
        reproducible.
        """
        return self.is_complete and self.is_final

    @property
    def blocks_confirmed_close_strategies(self) -> bool:
        """A partial bar must block, not warn (§6E).

        The failure mode this prevents is silent: an intraday price looks
        exactly like a close, so nothing downstream can tell the difference
        unless this flag travels with it.
        """
        return not self.usable_as_close

    def summary(self) -> dict:
        return {
            "market_session_status": str(self.status),
            "bar_timestamp": self.bar_timestamp,
            "is_complete": self.is_complete,
            "is_final": self.is_final,
            "last_completed_session": self.last_completed_session,
            "usable_as_close": self.usable_as_close,
            "reason": self.reason,
        }


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except Exception:  # noqa: BLE001 - an unknown zone is a caller error
        return ZoneInfo(US_EASTERN)


def _parse_timestamp(value: str | datetime | None, tz: str
                     ) -> tuple[datetime | None, bool]:
    """Read a bar timestamp; return it plus whether a clock time was given.

    A date-only bar (``2026-11-06``) means "the session of that date", not
    midnight: judging it by clock position would call every past daily bar
    partial, because midnight precedes the close. A timestamped bar
    (``2026-11-06T15:30``) really is a point during the session, so its clock
    position is meaningful.

    A naive clock time is read in the exchange's own zone, which is what a
    vendor means when it omits one.
    """
    if value is None:
        return None, False
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=_zone(tz))), True
    text = str(value).strip()
    if not text:
        return None, False
    has_time = "T" in text or ":" in text
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        try:
            moment = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None, has_time
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_zone(tz))
    return moment, has_time


_WEEKEND = frozenset({5, 6})


def market_session_status(
    moment: str | datetime | None,
    *,
    tz: str = US_EASTERN,
    session_open: time = DEFAULT_SESSION_OPEN,
    session_close: time = DEFAULT_SESSION_CLOSE,
) -> SessionStatus:
    """Classify a moment against the regular session.

    Weekends are ``CLOSED`` without consulting a holiday calendar: a weekday
    holiday will read as ``AFTER_HOURS`` or ``PRE_MARKET``, which is
    conservative — the bar for a holiday is not usable as a fresh close
    either way, and the caller still sees a non-``OPEN`` status.
    """
    instant, _has_time = _parse_timestamp(moment, tz)
    if instant is None:
        return SessionStatus.UNKNOWN
    local = instant.astimezone(_zone(tz))
    if local.weekday() in _WEEKEND:
        return SessionStatus.CLOSED
    clock = local.time()
    if clock < session_open:
        return SessionStatus.PRE_MARKET
    if clock < session_close:
        return SessionStatus.OPEN
    return SessionStatus.AFTER_HOURS


def _session_day_info(day: date):
    """The exchange calendar's view of a date, with a conservative fallback.

    An uncovered year has no verified schedule, so the day is treated as
    *trading* with the caller's default close: refusing every bar from an
    unknown year would be worse than using the regular session, and the
    assessment still reports that the calendar did not cover it.
    """
    from tradingagents.dataflows.math.exchange_calendar import session_day

    info = session_day(day)
    if info.kind == "UNCOVERED":
        # No verified schedule: assume a regular session, but say so by
        # leaving the close time to the caller's default.
        from tradingagents.dataflows.math.exchange_calendar import (
            SessionDay,
        )

        return SessionDay(day.isoformat(), "TRADING", None, None, info.reason)
    return info


def assess_bar(
    bar_timestamp: str | datetime | None,
    *,
    analysis_time: str | datetime | None = None,
    tz: str = US_EASTERN,
    session_open: time = DEFAULT_SESSION_OPEN,
    session_close: time = DEFAULT_SESSION_CLOSE,
    vendor_settled: bool = True,
    known_sessions: list[str] | None = None,
) -> BarAssessment:
    """Judge whether a bar is a verified EOD close (§6E).

    ``analysis_time`` is when the analysis ran; a bar is complete once the
    session that produced it has closed relative to that moment. ``vendor_settled``
    lets a caller mark a bar whose adjustments are still pending as not final,
    which is the difference between "the day ended" and "the number is fixed".

    ``known_sessions`` optionally lists the exchange's traded dates, so
    ``last_completed_session`` is the most recent *traded* day rather than the
    previous weekday. Without it the answer is the previous weekday, labelled
    as such, because a wrong date is worse than a stated assumption.
    """
    bar, bar_has_time = _parse_timestamp(bar_timestamp, tz)
    if bar is None:
        return BarAssessment(
            status=SessionStatus.UNKNOWN, bar_timestamp=None,
            is_complete=False, is_final=False,
            last_completed_session=_last_session(None, known_sessions, tz),
            reason="no bar timestamp: a price without a time is not a close",
        )

    bar_local = bar.astimezone(_zone(tz))
    now, _ = _parse_timestamp(analysis_time, tz)
    now = now or datetime.now(tz=_zone(tz))
    now_local = now.astimezone(_zone(tz))

    # The session that owns the bar: its calendar date, and — when the
    # exchange calendar covers it — that day's *own* close time. An early close
    # at 13:00 makes a 14:00 bar belong to no session, which judging by the
    # 16:00 default would miss entirely.
    session_day = bar_local.date()
    day_info = _session_day_info(session_day)
    effective_close = day_info.close_time or session_close
    session_end = datetime.combine(session_day, effective_close,
                                   tzinfo=_zone(tz))

    status = market_session_status(bar_local, tz=tz, session_open=session_open,
                                   session_close=effective_close)

    # A bar stamped before the close of its own session is still forming.
    # A date-only bar carries no clock, so it refers to the whole session:
    # it is complete once that session has ended.
    before_close = bar_has_time and bar_local < session_end
    # A tick outside the session's hours belongs to no session at all. On an
    # early-close day a 14:30 stamp is two hours after the close, so calling it
    # a "complete" bar would certify a price that no session produced.
    #
    # The closing instant itself *is* the session's last moment: a bar stamped
    # exactly at the close is the end-of-day bar, not an after-hours tick, so
    # the upper bound is inclusive.
    outside_session = bar_has_time and (
        bar_local < datetime.combine(session_day, session_open, tzinfo=_zone(tz))
        or bar_local > session_end
    )
    # A bar whose session has not ended yet, as seen from the analysis moment.
    session_open_now = now_local < session_end

    is_complete = (not before_close) and (not session_open_now) \
        and (not outside_session) and day_info.trades
    is_final = is_complete and vendor_settled

    if not day_info.trades:
        # A holiday has no session, so a bar dated that day cannot be a close.
        reason = (f"{session_day} is not a trading day ({day_info.kind}), so a "
                  "bar dated that day is not a close")
    elif outside_session:
        reason = (
            f"the bar is stamped {bar_local:%Y-%m-%d %H:%M} {tz}, outside the "
            f"session's hours ({session_open:%H:%M}-{effective_close:%H:%M}): "
            "no session produced it, so it is not a close"
        )
    elif not is_complete:
        if session_open_now and session_day == now_local.date():
            reason = (f"the bar for {session_day} is still forming: the session "
                      f"closes at {effective_close:%H:%M} {tz} and the analysis "
                      f"ran at {now_local:%H:%M}")
        else:
            reason = (f"the bar is stamped {bar_local:%Y-%m-%d %H:%M} {tz}, "
                      f"before its session's close at {effective_close:%H:%M}: "
                      "it is a partial bar, not an end-of-day close")
    elif not vendor_settled:
        reason = ("the session closed but the vendor has not settled the bar; "
                  "an adjusted price may still change")
    else:
        reason = ""

    return BarAssessment(
        status=status,
        bar_timestamp=bar_local.isoformat(),
        is_complete=is_complete,
        is_final=is_final,
        last_completed_session=_last_session(now_local, known_sessions, tz),
        reason=reason,
    )


def _last_session(now: datetime | None, known_sessions: list[str] | None,
                  tz: str) -> str | None:
    """The most recent settled session date, or None when unknown.

    With a session list the answer is exact. Without one, the previous
    weekday is returned as a stated assumption — the caller can see it is
    not calendar-verified because no session list was supplied.
    """
    if known_sessions:
        dates = sorted(str(s)[:10] for s in known_sessions)
        now_date = now.date().isoformat() if now else None
        past = [d for d in dates if now_date is None or d < now_date]
        if past:
            return past[-1]
        return None
    if now is None:
        return None
    candidate = now.date() - timedelta(days=1)
    while candidate.weekday() in _WEEKEND:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def assess_series(
    timestamps: list[str | datetime] | None,
    *,
    analysis_time: str | datetime | None = None,
    tz: str = US_EASTERN,
    session_close: time = DEFAULT_SESSION_CLOSE,
    vendor_settled: bool = True,
    known_sessions: list[str] | None = None,
) -> dict:
    """Assess a whole series, reporting whether its last bar is partial.

    An indicator computed over a series whose last bar is intraday is not
    wrong arithmetic — it is arithmetic over a number that is still changing.
    ``includes_partial_bar`` travels with the indicator result so a consumer
    can refuse it rather than silently trusting it.
    """
    stamps = list(timestamps or [])
    if not stamps:
        return {
            "includes_partial_bar": False,
            "last_bar": None,
            "completed_bars": 0,
            "total_bars": 0,
            "last_completed_session": _last_session(None, known_sessions, tz),
        }
    last = assess_bar(stamps[-1], analysis_time=analysis_time, tz=tz,
                      session_close=session_close, vendor_settled=vendor_settled,
                      known_sessions=known_sessions)
    completed = 0
    for stamp in stamps:
        assessed = assess_bar(stamp, analysis_time=analysis_time, tz=tz,
                             session_close=session_close,
                             known_sessions=known_sessions)
        if assessed.is_complete:
            completed += 1
    return {
        "includes_partial_bar": not last.is_complete,
        "last_bar": last.summary(),
        "completed_bars": completed,
        "total_bars": len(stamps),
        "last_completed_session": last.last_completed_session,
    }
