"""Point-in-time rules shared by every dated path: data is served as of the run's date.

- ``as_of`` / ``as_of_window`` clamp a date or window the model asks for to the
  trade date, so no tool reaches a vendor with a later one.
- ``in_window`` trims dated items (news, StockTwits, Reddit) to the analysis
  window: timestamps normalized to UTC, the upper bound exclusive at midnight
  after ``end``, and an undated item kept only when the window reaches the
  present, since a backtest cannot prove it is not from the future (#1126, #1220).
- ``coverage_gap`` reports a window a feed cannot reach as unavailable, not empty.
- ``withhold_live_profile`` withholds present-day snapshots from historical runs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta


def to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-aware; a naive value is assumed to be UTC."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def in_window(pub_dt: datetime | None, start_dt: datetime, end_dt: datetime) -> bool:
    """Whether an item belongs in the half-open window ``[start, end + 1 day)``.

    ``pub_dt`` None means undated: kept only when the window reaches the present.
    """
    end = to_utc(end_dt)
    if pub_dt is not None:
        return to_utc(start_dt) <= to_utc(pub_dt) < end + timedelta(days=1)
    return end >= datetime.now(UTC) - timedelta(days=1)


def get_current_date() -> str:
    """Today's date, YYYY-MM-DD."""
    return date.today().strftime("%Y-%m-%d")


def is_historical(run_date) -> bool:
    """Whether a run is dated before today, so live-only data would come from after it."""
    return bool(run_date) and str(run_date) < get_current_date()


def coverage_gap(
    dates, start_date: str, end_date: str, source: str, subject: str
) -> str | None:
    """Placeholder for a window a feed did not fully observe, else None.

    Yahoo news and the Reddit and StockTwits feeds return their latest items
    whatever window is asked for, so "none found" over a window they never
    observed would claim an absence nobody saw. A window is observed when
    coverage reaches its first day and it ends by today; an empty result is then
    a real absence and this returns None.

    ``dates`` are the returned items' timestamps, plus the lookback start for a
    feed with a fixed lookback. The oldest one bounds coverage only for a feed
    returned newest-first and unbroken in time; a merged or relevance-ranked
    result passes no dates, leaving only the present as the bound.
    """
    now = datetime.now(UTC)
    oldest = min((to_utc(d) for d in dates if d is not None), default=now)
    if datetime.strptime(end_date, "%Y-%m-%d").date() > now.date():
        reason = "the window extends past today"
    elif oldest.date() > datetime.strptime(start_date, "%Y-%m-%d").date():
        reason = "it only serves recent items"
    else:
        return None
    return f"<{source} unavailable for {start_date}..{end_date}: {reason}, so this is not an absence of {subject}>"


def _parse(date: str | None) -> datetime | None:
    try:
        return datetime.strptime(date, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def as_of(requested: str | None, trade_date: str) -> str | None:
    """The date a tool serves: the model's date, but never later than the run's.

    A model can omit the date or pass today's instead of the analysis date, which
    would walk past every point-in-time guard behind the tool. An empty
    ``trade_date`` (a direct call outside a graph run) passes the request through.
    """
    if not trade_date:
        return requested
    parsed = _parse(requested)
    return requested if parsed is not None and parsed <= _parse(trade_date) else trade_date


def as_of_window(start_date: str, end_date: str, trade_date: str) -> tuple[str, str]:
    """``[start, end]`` with its end clamped to the run date.

    A window wholly after the run date keeps its length and moves back to end there.
    An unreadable end reads as the run date, but no window can be guessed from an
    unreadable start, so it raises ValueError for the caller to send back (#1476).
    """
    start, old_end = _parse(start_date), _parse(end_date)
    if start is None:
        raise ValueError(f"start_date {start_date!r} is not a date; give it as YYYY-MM-DD")
    end = as_of(end_date, trade_date)
    if end == end_date or start <= _parse(end):
        return start_date, end
    span = (old_end - start) if old_end is not None and old_end >= start else timedelta(0)
    return f"{_parse(end) - span:%Y-%m-%d}", end


def withhold_live_profile(as_of_date: str | None, label: str) -> str | None:
    """Notice to serve instead of a live-only company profile, or None to serve it.

    Vendor "company overview" endpoints (yfinance ``Ticker.info``, Alpha Vantage
    ``OVERVIEW``) carry no historical vintage — not even name, sector and
    industry, which move when a company renames or is reclassified — so serving
    one into a run dated in the past leaks post-decision information (#1300).
    Every fundamentals vendor withholds on this rule, so switching between them
    cannot reintroduce the leak.
    """
    if not is_historical(as_of_date):
        return None
    return (
        f"# Company Fundamentals for {label}\n"
        f"# Point-in-time as of: {as_of_date}\n\n"
        f"Profile fundamentals are withheld for this date. This vendor serves "
        f"only present-day values with no historical vintage: market "
        f"cap, valuation multiples, the 52-week range and TTM income move with "
        f"today's quote, and even the name, sector and industry reflect today "
        f"rather than {as_of_date} (companies rename and get reclassified). "
        f"Serving them would put post-decision information into a {as_of_date} "
        f"analysis. Statements filed by {as_of_date} are served as filed where "
        f"the filing date is known (SEC EDGAR, for US filers)."
    )


def withhold_undisclosed_trades(as_of_date: str | None, label: str) -> str | None:
    """Notice to serve instead of insider trades with no filing date, or None to serve them.

    A vendor that dates an insider trade by when it happened (Yahoo, Alpha
    Vantage) cannot say when it became public: its Form 4 is filed up to two
    business days later. A past run is told so rather than served trades that
    may not yet have been disclosed.
    """
    if not is_historical(as_of_date):
        return None
    return (
        f"# Insider Transactions for {label}\n"
        f"# Point-in-time as of: {as_of_date}\n\n"
        f"Insider transactions are withheld for this date. This vendor dates a trade "
        f"by when it happened and reports no filing date, so it cannot show which "
        f"trades were public on {as_of_date}."
    )


def withhold_undated_statements(as_of_date: str | None, label: str, title: str) -> str | None:
    """Notice to serve instead of a statement with no filing date, or None to serve it.

    A vendor that dates a statement by the period it covers (Yahoo, Alpha
    Vantage) cannot say when its figures became public: a company files weeks
    after the period ends, so a run dated in that gap would read figures that
    were not yet known. A past run is told so; SEC EDGAR, which dates every
    filing, serves US filers as filed.
    """
    if not is_historical(as_of_date):
        return None
    return (
        f"# {title} for {label}\n"
        f"# Point-in-time as of: {as_of_date}\n\n"
        f"{title} data is withheld for this date. This vendor dates a statement by "
        f"the period it covers and reports no filing date, so it cannot show which "
        f"figures were public on {as_of_date}. SEC EDGAR serves US filers as filed."
    )
