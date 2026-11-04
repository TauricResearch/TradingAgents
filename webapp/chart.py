"""Price closes for the web console's chart, point-in-time.

The report text cites prices and indicators; the page draws them as a small
line so the analysis reads against the actual series. The data comes from the
same vendor path the agents' tools use, filtered to the analysis date, so the
chart never shows a bar the run could not have seen.
"""

from __future__ import annotations

import datetime

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.vendors.yahoo.market import get_closes

# The window the chart shows: weeks before the analysis date, days after.
DAYS_BEFORE = 60
DAYS_AFTER = 10


def closes_for_chart(ticker: str, analysis_date: str) -> dict:
    """Daily closes around ``analysis_date``, never past it for a historical run.

    A historical run reads the series as it stood on its date: bars after it
    are withheld, exactly as the tools behind the analysts withhold them. A
    current-date run may show the few sessions since, up to today.
    """
    end = datetime.date.fromisoformat(analysis_date)
    if not is_historical(analysis_date):
        end = datetime.date.today()
    start = end - datetime.timedelta(days=DAYS_BEFORE)
    # get_closes' end is exclusive, so ask one past the last day shown.
    series = get_closes(ticker, start.isoformat(), (end + datetime.timedelta(days=1)).isoformat())
    if series is None or series.empty:
        return {"ticker": ticker, "analysis_date": analysis_date, "closes": []}
    stamps = getattr(series.index, "tz", None)
    if stamps is not None:
        series = series.tz_localize(None)
    closes = [
        {"date": index.strftime("%Y-%m-%d"), "close": round(float(value), 6)}
        for index, value in series.items()
        if value == value and value > 0  # drop NaN and non-positive rows
        and index.date() <= end          # a historical run never sees a later bar
    ]
    return {"ticker": ticker, "analysis_date": analysis_date, "closes": closes}
