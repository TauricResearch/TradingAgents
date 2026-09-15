"""Decision-point scheduling for a backtest.

A backtest does not run the agent graph every day — a full graph run is minutes
of wall time and real money, and the decisions it produces are position-level
views held for days, not intraday signals. ``decision_dates`` lays out the
calendar of dates the graph will actually be invoked on.

Weekday dates are produced here without a market-holiday calendar on purpose:
adding one would mean either a new dependency or a hand-maintained holiday
table that silently rots, and it is not needed for correctness. A decision that
lands on a market holiday simply has no bar to execute against, and the
portfolio simulator fills it at the next available open — the same rule it
already applies to every decision. The only cost is an occasional graph run
whose fill is one day later, which is visible in the trade list rather than
hidden.
"""

from __future__ import annotations

import pandas as pd


def decision_dates(start: str, end: str, every_n_days: int = 5) -> list[str]:
    """Return the ``yyyy-mm-dd`` dates to run the agent graph on.

    Args:
        start: First candidate date, inclusive (``yyyy-mm-dd``).
        end: Last candidate date, inclusive (``yyyy-mm-dd``).
        every_n_days: Stride in *business* days between decision points. ``1``
            runs every weekday; the default ``5`` runs roughly weekly, which
            matches the 5-day holding window the decision log already uses to
            resolve outcomes.

    Raises:
        ValueError: If the dates are unparseable, ``end`` precedes ``start``, or
            the stride is not positive. These fail loudly rather than quietly
            producing an empty schedule, which would otherwise surface much
            later as a confusing "no decisions" scorecard.
    """
    if every_n_days < 1:
        raise ValueError(f"every_n_days must be >= 1, got {every_n_days}")

    try:
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
    except ValueError as exc:
        raise ValueError(f"Invalid backtest date range {start!r}..{end!r}: {exc}") from exc

    if end_ts < start_ts:
        raise ValueError(f"Backtest end {end!r} precedes start {start!r}")

    weekdays = pd.bdate_range(start=start_ts, end=end_ts)
    return [ts.strftime("%Y-%m-%d") for ts in weekdays[::every_n_days]]
