"""Formatting and indicators shared by vendors that fetch a daily OHLCV frame themselves.

A vendor builds a DataFrame with ``Date, Open, High, Low, Close, Volume`` (naive
dates, oldest first) and hands it here, so its ``get_stock_data`` and
``get_indicators`` read exactly like Yahoo's to the agents.
"""

from datetime import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors.yahoo.market import INDICATOR_DESCRIPTIONS
from tradingagents.dataflows.vendors.yahoo.ohlcv import _assert_ohlcv_not_stale

COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def format_stock_data(data, symbol, canonical, start_date, end_date, source):
    """The CSV block ``get_stock_data`` returns, rows between start and end inclusive."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")
    rows = data[(data["Date"] >= pd.Timestamp(start_date)) & (data["Date"] <= pd.Timestamp(end_date))].copy()
    if rows.empty:
        raise NoMarketDataError(symbol, canonical, f"no rows between {start_date} and {end_date}")
    _assert_ohlcv_not_stale(rows, end_date, symbol, canonical)
    for col in ["Open", "High", "Low", "Close"]:
        rows[col] = rows[col].round(6 if rows[col].abs().max() < 10 else 2)
    rows["Date"] = rows["Date"].dt.strftime("%Y-%m-%d")
    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date} (source: {source})\n"
    header += f"# Total records: {len(rows)}\n\n"
    return header + rows[COLUMNS].to_csv(index=False)


def indicator_window(data, symbol, canonical, indicator, as_of_date, look_back_days):
    """The text block ``get_indicators`` returns for one indicator, newest day first."""
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS)}"
        )
    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    before = as_of_dt - relativedelta(days=look_back_days)

    # Only bars up to the analysis date feed the indicator: no look-ahead.
    frame = data[data["Date"] <= pd.Timestamp(as_of_dt)].copy()
    if frame.empty:
        raise NoMarketDataError(symbol, canonical, f"no price rows on or before {as_of_date}")
    _assert_ohlcv_not_stale(frame, as_of_date, symbol, canonical)
    df = wrap(frame[COLUMNS].reset_index(drop=True))
    df[indicator]  # stockstats computes the column on first access
    values = {
        d.strftime("%Y-%m-%d"): ("N/A" if pd.isna(v) else str(v))
        for d, v in zip(frame["Date"], df[indicator], strict=True)
    }

    lines, day = [], as_of_dt
    while day >= before:
        key = day.strftime("%Y-%m-%d")
        lines.append(f"{key}: {values.get(key, 'N/A: Not a trading day (weekend or holiday)')}")
        day -= relativedelta(days=1)
    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {as_of_date}:\n\n"
        + "\n".join(lines) + "\n\n\n" + INDICATOR_DESCRIPTIONS[indicator]
    )
