"""Helpers that mark data sources that are not point-in-time snapshots."""

from __future__ import annotations

from datetime import date, datetime


LOOKAHEAD_CAVEAT_TEMPLATE = (
    "NOTE: OVERVIEW/company-info metrics reflect the LATEST snapshot, "
    "not point-in-time as of {date}. Treat valuation ratios with caution "
    "in historical backtests.\n\n"
)


def historical_snapshot_caveat(curr_date: str | None) -> str:
    """Return a caveat when latest-only vendor data is used for a past date."""
    if not curr_date:
        return ""
    try:
        requested = datetime.strptime(curr_date, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    if requested < date.today():
        return LOOKAHEAD_CAVEAT_TEMPLATE.format(date=curr_date)
    return ""
