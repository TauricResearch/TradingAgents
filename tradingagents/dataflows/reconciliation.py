"""Cross-vendor price reconciliation for OHLCV data.

The routing layer serves a single vendor's OHLCV per call (first successful
vendor wins), so two vendors can report different closes for the same session
and the difference stays invisible. This module compares two raw OHLCV CSV
strings — one per vendor — over their shared trading days and surfaces the
largest divergence with its date and magnitude.

It is deliberately a *best-effort reader*, not a data source: it never
raises for parse/shape differences, never mutates the CSVs it is given, and
returns ``None`` (nothing to report) whenever the two sources can't be
compared. Callers append its note to the primary vendor's result without
ever altering that result.

The comparison is ticker-agnostic: it only needs a date column and a close
column in each CSV, which both the yfinance (``Close``) and Alpha Vantage
(``close``) daily-series formats provide. It compares the *same* metric on
the *same* dates, so no adjustment basis needs to be assumed up front — a
vendor's stated basis travels in its data header, not here.
"""

from __future__ import annotations

import csv
import io
import logging

logger = logging.getLogger(__name__)

# Relative divergence above this is worth flagging; at/below it the two vendors
# are close enough that the spread is rounding/sourcing noise, not a signal.
_DIVERGENCE_THRESHOLD = 0.005  # 0.5 %

_CLOSE_ALIASES = ("close", "adj close", "adjusted close")
_DATE_ALIASES = ("date", "timestamp")


def _header_index(header: list[str], aliases: tuple[str, ...]) -> int | None:
    for idx, name in enumerate(header):
        if name in aliases:
            return idx
    return None


def parse_close_series(csv_text: str) -> dict[str, float]:
    """Map ``date -> close`` for every usable row of an OHLCV CSV.

    Tolerates a leading ``#`` comment header (both our vendor formats emit
    one) and any column ordering, locating the date and close columns by
    header name. Returns an empty dict — never raises — when the input has no
    parsable rows or no recognisable close column, so a malformed vendor
    payload can't crash a reconciliation that only annotates the result.
    """
    if not csv_text:
        return {}
    rows: list[list[str]] = []
    for line in csv_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(next(csv.reader(io.StringIO(line))))
        except (csv.Error, StopIteration):
            continue
    if len(rows) < 2:
        return {}

    header = [c.strip().lower() for c in rows[0]]
    date_idx = _header_index(header, _DATE_ALIASES)
    close_idx = _header_index(header, _CLOSE_ALIASES)
    if date_idx is None:
        date_idx = 0  # both vendor formats put the date in the first cell
    if close_idx is None:
        return {}  # no close column we can trust — don't guess one

    series: dict[str, float] = {}
    for row in rows[1:]:
        if date_idx >= len(row) or close_idx >= len(row):
            continue
        date = row[date_idx].strip()
        if not date:
            continue
        try:
            close = float(row[close_idx])
        except (TypeError, ValueError):
            continue
        series[date] = close
    return series


def build_reconciliation_note(
    symbol: str,
    primary_csv: str,
    comparison_csv: str,
    max_days: int = 30,
) -> str | None:
    """A human-readable divergence note comparing two vendors' closes.

    Compares the trailing ``max_days`` of *shared* trading days (the part of
    the window that feeds the report) and reports the largest deviation,
    plus the latest-day spread. Returns ``None`` — the caller then appends
    nothing — when there is no shared overlap, fewer than two shared days,
    or no deviation above the threshold.
    """
    a = parse_close_series(primary_csv)
    b = parse_close_series(comparison_csv)
    shared = sorted(set(a) & set(b))
    if len(shared) < 2:
        return None
    shared = shared[-max_days:]

    max_dev = 0.0
    max_date = ""
    max_pct = 0.0
    for date in shared:
        va, vb = a[date], b[date]
        denom = max(abs(va), abs(vb))
        if denom == 0:
            continue
        pct = abs(va - vb) / denom
        if pct > max_dev:
            max_dev, max_date, max_pct = pct, date, pct
    if max_dev < _DIVERGENCE_THRESHOLD:
        return None

    latest = shared[-1]
    latest_note = (
        f" Latest session ({latest}): "
        f"primary {a[latest]:.2f} vs comparison {b[latest]:.2f} "
        f"(spread {abs(a[latest] - b[latest]):.2f})."
    )
    return (
        f"CROSS-VENDOR NOTE ({symbol}): {len(shared)} shared trading days "
        f"compared between the primary vendor and a second source. "
        f"Largest deviation on {max_date}: {max_pct * 100:.2f}% "
        f"(primary {a[max_date]:.2f} vs comparison {b[max_date]:.2f})."
        f"{latest_note} This is an informational cross-check between two "
        f"independent data sources; it does not change the primary result "
        f"above, and a difference this size is commonly a price-adjustment or "
        f"sourcing-basis difference, not a market move."
    )
