"""OHLCV finality (§3 of P2): is this price a settled close, or still moving?

The data lineage audit found F5: the 19:24 report called 576.74 the "verified
close" at 15:01 New York time, with the session open until 16:00. Every
indicator, the entry decision and the +24.2% figure rested on a number that was
still changing. `ohlcv.py` already documented the hazard at line 152 and
mitigated it with a cache TTL, which bounds staleness but cannot make a partial
candle final.

This module attaches a finality status to a bar, using the exchange calendar the
repository already has rather than a second time model. Five states, because
three would conflate cases that behave differently:

``EOD_CONFIRMED``
    The session closed and enough time has passed that the vendor's figure is
    settled. The only state an EOD strategy may use.
``EOD_PENDING_CONFIRMATION``
    The session closed recently — the vendor may still restate it, so it is not
    yet final.
``INTRADAY_PARTIAL``
    The session is trading: the price exists and is not a close.
``STALE``
    The bar is older than the expected last session, so the series is behind.
``UNKNOWN``
    No timestamp, or a calendar that cannot judge the date.

A six-minute grace period after the close decides pending versus confirmed. It
is a policy, not a measurement: vendors restate the final print shortly after
16:00, and calling a bar final the instant the bell rings would certify a figure
that can still change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

# The exchange whose sessions decide finality, as a parameter so a caller can
# analyse another market without a second implementation.
DEFAULT_EXCHANGE_TZ = "America/New_York"

# How long after the close a vendor's daily bar is treated as settled. Chosen
# conservatively: the cost of waiting is a delayed analysis, the cost of not
# waiting is certifying a price that later changes.
DEFAULT_SETTLEMENT_GRACE = timedelta(minutes=6)


class BarFinality(StrEnum):
    """What may be concluded about a price bar's completeness."""

    EOD_CONFIRMED = "EOD_CONFIRMED"
    EOD_PENDING_CONFIRMATION = "EOD_PENDING_CONFIRMATION"
    INTRADAY_PARTIAL = "INTRADAY_PARTIAL"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


# The states an end-of-day strategy may build on. One member, stated once so the
# rule cannot drift: a pending bar is not a close.
_EOD_USABLE = frozenset({BarFinality.EOD_CONFIRMED})


@dataclass(frozen=True)
class BarProvenance:
    """A price with the temporal facts that decide what it may be used for.

    The audit asked for session date, exchange timezone, observation timestamp,
    source timestamp, finality, last confirmed close, source and calendar. All of
    them travel together, so a consumer never has to reconstruct them.
    """

    session_date: str | None
    exchange_timezone: str
    observation_timestamp: str | None
    source_timestamp: str | None
    finality: BarFinality
    last_confirmed_close: str | None
    source: str
    session_calendar: str = "NYSE"
    reason: str = ""

    @property
    def usable_for_eod(self) -> bool:
        """Whether an end-of-day strategy may use this price."""
        return self.finality in _EOD_USABLE

    @property
    def usable_for_intraday(self) -> bool:
        """Whether an intraday analysis may use it, explicitly labelled.

        A partial bar is legitimate evidence of a move in progress; it is not
        legitimate evidence of a close. The distinction is the caller's to
        respect, and this flag is what lets it.
        """
        return self.finality in (BarFinality.INTRADAY_PARTIAL,
                                 BarFinality.EOD_CONFIRMED)

    @property
    def is_provisional(self) -> bool:
        return self.finality is not BarFinality.EOD_CONFIRMED

    def summary(self) -> dict:
        return {
            "session_date": self.session_date,
            "exchange_timezone": self.exchange_timezone,
            "observation_timestamp": self.observation_timestamp,
            "source_timestamp": self.source_timestamp,
            "finality": str(self.finality),
            "last_confirmed_close": self.last_confirmed_close,
            "source": self.source,
            "session_calendar": self.session_calendar,
            "usable_for_eod": self.usable_for_eod,
            "usable_for_intraday": self.usable_for_intraday,
            "is_provisional": self.is_provisional,
            "reason": self.reason,
        }


def _parse(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _session_close_for(day: str, exchange_tz: str) -> tuple[datetime | None, str]:
    """The close of ``day``'s session, and whether that day trades at all.

    Delegates to ``math/exchange_calendar`` — the repository's one source of
    truth for holidays and early closes — so a 13:00 close is honoured without
    re-deriving a calendar here.
    """
    from tradingagents.dataflows.math.exchange_calendar import session_day

    info = session_day(day)
    if not info.trades:
        return None, info.kind
    zone = ZoneInfo(exchange_tz)
    close_time = info.close_time or time(16, 0)
    return datetime.combine(
        datetime.fromisoformat(day).date(), close_time, tzinfo=zone), info.kind


def assess_finality(
    observation_timestamp: str | datetime | None,
    *,
    session_date: str | None = None,
    exchange_tz: str = DEFAULT_EXCHANGE_TZ,
    source: str = "yfinance",
    source_timestamp: str | datetime | None = None,
    settlement_grace: timedelta = DEFAULT_SETTLEMENT_GRACE,
    now: str | datetime | None = None,
    last_expected_session: str | None = None,
) -> BarProvenance:
    """Judge a bar against the exchange session that produced it.

    ``observation_timestamp`` is when the analysis read the price; ``now`` is
    when finality is judged, defaulting to the observation. A caller judging a
    stored bar later can pass ``now`` and get the finality it would have had.

    ``last_expected_session`` lets a caller state which session the series
    *should* reach. A bar older than that is ``STALE`` — a gap in the data,
    which is a different problem from a bar that is merely provisional.
    """
    moment = _parse(observation_timestamp)
    judged_at = _parse(now) or moment or datetime.now(tz=UTC)

    if moment is None:
        return BarProvenance(
            session_date=session_date, exchange_timezone=exchange_tz,
            observation_timestamp=None,
            source_timestamp=(str(source_timestamp)
                              if source_timestamp is not None else None),
            finality=BarFinality.UNKNOWN, last_confirmed_close=None,
            source=source,
            reason="no observation timestamp: a price without a time is not a close",
        )

    day = session_date or moment.astimezone(
        ZoneInfo(exchange_tz)).date().isoformat()
    if last_expected_session and day < last_expected_session:
        return BarProvenance(
            session_date=day, exchange_timezone=exchange_tz,
            observation_timestamp=moment.isoformat(),
            source_timestamp=(str(source_timestamp)
                              if source_timestamp is not None else None),
            finality=BarFinality.STALE,
            last_confirmed_close=last_expected_session, source=source,
            reason=(f"the bar is for {day} but the series should reach "
                    f"{last_expected_session}"),
        )

    close_at, day_kind = _session_close_for(day, exchange_tz)
    if close_at is None:
        return BarProvenance(
            session_date=day, exchange_timezone=exchange_tz,
            observation_timestamp=moment.isoformat(),
            source_timestamp=(str(source_timestamp)
                              if source_timestamp is not None else None),
            finality=BarFinality.UNKNOWN, last_confirmed_close=None,
            source=source,
            reason=(f"{day} is not a trading day ({day_kind}), so a bar dated "
                    "that day cannot be a close"),
        )

    local = moment.astimezone(ZoneInfo(exchange_tz))
    judged_local = judged_at.astimezone(ZoneInfo(exchange_tz))
    if judged_local < close_at:
        # The session that owns the bar is still trading.
        return BarProvenance(
            session_date=day, exchange_timezone=exchange_tz,
            observation_timestamp=local.isoformat(),
            source_timestamp=(str(source_timestamp)
                              if source_timestamp is not None else None),
            finality=BarFinality.INTRADAY_PARTIAL,
            last_confirmed_close=_previous_close(day, exchange_tz),
            source=source,
            reason=(f"the session closes at {close_at:%H:%M} and the "
                    f"observation is at {judged_local:%H:%M}: the bar is a "
                    "partial candle, not a close"),
        )

    if judged_local < close_at + settlement_grace:
        return BarProvenance(
            session_date=day, exchange_timezone=exchange_tz,
            observation_timestamp=local.isoformat(),
            source_timestamp=(str(source_timestamp)
                              if source_timestamp is not None else None),
            finality=BarFinality.EOD_PENDING_CONFIRMATION,
            last_confirmed_close=_previous_close(day, exchange_tz),
            source=source,
            reason=("the session has closed but the vendor may still restate "
                    "the print"),
        )

    return BarProvenance(
        session_date=day, exchange_timezone=exchange_tz,
        observation_timestamp=local.isoformat(),
        source_timestamp=(str(source_timestamp)
                          if source_timestamp is not None else None),
        finality=BarFinality.EOD_CONFIRMED,
        last_confirmed_close=day, source=source,
        reason="",
    )


def _previous_close(day: str, exchange_tz: str) -> str | None:
    """The last session before ``day`` whose close is settled."""
    from tradingagents.dataflows.math.exchange_calendar import (
        previous_trading_day,
    )

    return previous_trading_day(day)


def describe_series(finalities: list[BarFinality]) -> dict:
    """Whether a price series includes a bar that is still forming.

    An indicator computed over a partial last bar is not wrong arithmetic — it
    is arithmetic over a number that is still changing. This is what lets the
    result declare that, so a report can label it instead of presenting it as an
    end-of-day figure.
    """
    partial = [f for f in finalities if f is not BarFinality.EOD_CONFIRMED]
    return {
        "bars_total": len(finalities),
        "bars_confirmed": len(finalities) - len(partial),
        "includes_partial_bar": any(
            f is BarFinality.INTRADAY_PARTIAL for f in finalities),
        "includes_unconfirmed_bar": bool(partial),
        "last_bar_finality": str(finalities[-1]) if finalities else None,
    }
