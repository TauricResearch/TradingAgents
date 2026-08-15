"""Resolve optional news windows from real exchange sessions."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import exchange_calendars as xcals

_EXCHANGE_CALENDARS = {
    # NYSE and Nasdaq share the regular US-equity sessions needed by this MVP.
    "NYSE": "XNYS",
    "NASDAQ": "XNYS",
}


@dataclass(frozen=True)
class MarketSessionNewsWindow:
    """Timezone-aware bounds derived from two consecutive exchange sessions."""

    start: datetime
    end: datetime
    exchange: str
    previous_session: date
    target_session: date


def _target_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"target_date must use YYYY-MM-DD, got {value!r}") from exc
    raise ValueError(f"target_date must be a date or YYYY-MM-DD string, got {type(value)}")


def _offset(config: Mapping[str, object], key: str) -> int:
    value = config.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer number of minutes, got {value!r}")
    return value


def resolve_news_window(
    target_date: str | date | datetime,
    config: Mapping[str, object] | None,
) -> MarketSessionNewsWindow | None:
    """Resolve market-session bounds, or return ``None`` for legacy lookback.

    A non-session target date maps to the latest session on or before that date,
    so weekend and holiday analyses never move their cutoff into the future.
    Offset signs are literal: ``+60`` adds an hour and ``-60`` subtracts one.
    """
    if config is None:
        return None

    mode = config.get("mode")
    if mode == "lookback":
        return None
    if mode != "market_session":
        raise ValueError(
            f"Unsupported news window mode {mode!r}; expected 'lookback' or 'market_session'"
        )

    exchange = config.get("exchange")
    if not isinstance(exchange, str) or exchange.upper() not in _EXCHANGE_CALENDARS:
        supported = ", ".join(_EXCHANGE_CALENDARS)
        raise ValueError(f"Unsupported exchange {exchange!r}; expected one of: {supported}")
    exchange = exchange.upper()

    start_anchor = config.get("start_anchor")
    if start_anchor != "previous_market_close":
        raise ValueError(
            f"Unsupported start anchor {start_anchor!r}; expected 'previous_market_close'"
        )
    end_anchor = config.get("end_anchor")
    if end_anchor != "current_market_open":
        raise ValueError(
            f"Unsupported end anchor {end_anchor!r}; expected 'current_market_open'"
        )

    start_offset = _offset(config, "start_offset_minutes")
    end_offset = _offset(config, "end_offset_minutes")
    calendar = xcals.get_calendar(_EXCHANGE_CALENDARS[exchange])

    session = calendar.date_to_session(_target_date(target_date), direction="previous")
    previous_session = calendar.previous_session(session)
    start = (
        calendar.session_close(previous_session).tz_convert(calendar.tz).to_pydatetime()
        + timedelta(minutes=start_offset)
    )
    end = (
        calendar.session_open(session).tz_convert(calendar.tz).to_pydatetime()
        + timedelta(minutes=end_offset)
    )
    if start >= end:
        raise ValueError(
            "Market-session news window is empty or inverted after applying offsets: "
            f"{start.isoformat()} >= {end.isoformat()}"
        )

    return MarketSessionNewsWindow(
        start=start,
        end=end,
        exchange=exchange,
        previous_session=previous_session.date(),
        target_session=session.date(),
    )
