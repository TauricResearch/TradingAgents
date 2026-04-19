# Copyright 2026 herald.k, HongSoo Kim
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pre-compute all technical indicators in pure Python code.

Layer 1 of the two-layer architecture (Issue #542):
  Layer 1 — Calculation (this module): deterministic, fast, accurate
  Layer 2 — Interpretation (LLM): contextual analysis of pre-computed values
"""

from datetime import datetime
from dateutil.relativedelta import relativedelta

from .y_finance import _get_stock_stats_bulk


# Indicators grouped by category for structured output
INDICATOR_CATEGORIES = {
    "Moving Averages": {
        "close_50_sma": "50 SMA",
        "close_200_sma": "200 SMA",
        "close_10_ema": "10 EMA",
    },
    "MACD": {
        "macd": "MACD",
        "macds": "MACD Signal",
        "macdh": "MACD Histogram",
    },
    "Momentum": {
        "rsi": "RSI(14)",
    },
    "Volatility": {
        "boll": "Bollinger Middle",
        "boll_ub": "Bollinger Upper",
        "boll_lb": "Bollinger Lower",
        "atr": "ATR(14)",
    },
    "Volume": {
        "vwma": "VWMA",
    },
}

# Flat list of all default indicators
DEFAULT_INDICATORS = [
    ind for inds in INDICATOR_CATEGORIES.values() for ind in inds
]


def compute_all_indicators(
    symbol: str,
    curr_date: str,
    look_back_days: int = 30,
) -> str:
    """Compute all technical indicators and return a formatted Markdown summary.

    Args:
        symbol: Ticker symbol (e.g. "AAPL").
        curr_date: Current trading date in YYYY-mm-dd format.
        look_back_days: Number of days to look back for context.

    Returns:
        Markdown-formatted string with indicator values and context.
    """
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")

    # Collect indicator data — _get_stock_stats_bulk returns {date_str: value_str}
    indicator_data = {}
    for ind_key in DEFAULT_INDICATORS:
        try:
            indicator_data[ind_key] = _get_stock_stats_bulk(symbol, ind_key, curr_date)
        except Exception:
            indicator_data[ind_key] = {}

    # Find the most recent trading date with data
    latest_date = _find_latest_date(indicator_data, curr_dt)
    if latest_date is None:
        return f"No indicator data available for {symbol} near {curr_date}"

    # Build the summary
    lines = [f"## Technical Indicators for {symbol.upper()} ({latest_date}, {look_back_days}-day window)\n"]

    for category, indicators in INDICATOR_CATEGORIES.items():
        lines.append(f"### {category}")
        for ind_key, label in indicators.items():
            value = _get_value(indicator_data, ind_key, latest_date)
            context = _get_context(indicator_data, ind_key, latest_date, curr_dt, look_back_days)
            if context:
                lines.append(f"- {label}: {value} ({context})")
            else:
                lines.append(f"- {label}: {value}")
        lines.append("")

    # Add recent price context from moving average data
    price_context = _build_price_context(indicator_data, latest_date, curr_dt, look_back_days)
    if price_context:
        lines.append(price_context)

    return "\n".join(lines)


def _find_latest_date(indicator_data: dict, curr_dt: datetime) -> str | None:
    """Find the most recent trading date that has indicator data."""
    # Check dates going backwards from curr_date
    for days_back in range(7):
        check_dt = curr_dt - relativedelta(days=days_back)
        check_str = check_dt.strftime("%Y-%m-%d")
        # If any indicator has data for this date, use it
        for data in indicator_data.values():
            if check_str in data and data[check_str] != "N/A":
                return check_str
    return None


def _get_value(indicator_data: dict, ind_key: str, date_str: str) -> str:
    """Get the indicator value for a specific date, formatted to 2 decimal places."""
    data = indicator_data.get(ind_key, {})
    raw = data.get(date_str, "N/A")
    if raw == "N/A":
        return "N/A"
    try:
        return f"{float(raw):.2f}"
    except (ValueError, TypeError):
        return str(raw)


def _get_context(
    indicator_data: dict, ind_key: str, latest_date: str,
    curr_dt: datetime, look_back_days: int,
) -> str:
    """Generate brief context string for an indicator (e.g. trend direction)."""
    data = indicator_data.get(ind_key, {})
    current_val = data.get(latest_date, "N/A")
    if current_val == "N/A":
        return ""

    try:
        current = float(current_val)
    except (ValueError, TypeError):
        return ""

    # RSI context
    if ind_key == "rsi":
        if current >= 70:
            return "overbought"
        elif current <= 30:
            return "oversold"
        elif current >= 60:
            return "approaching overbought"
        elif current <= 40:
            return "approaching oversold"
        return "neutral"

    # MACD Histogram context
    if ind_key == "macdh":
        if current > 0:
            return "positive, bullish momentum"
        elif current < 0:
            return "negative, bearish momentum"
        return "flat"

    # For moving averages, compare with the most recent close (use boll as proxy)
    # No generic context needed — the LLM interprets relative to price
    return ""


def _build_price_context(
    indicator_data: dict, latest_date: str,
    curr_dt: datetime, look_back_days: int,
) -> str:
    """Build a price context section using Bollinger Middle as close proxy."""
    # Bollinger Middle (boll) is essentially the 20-day SMA of close, close proxy
    boll_data = indicator_data.get("boll", {})
    if not boll_data:
        return ""

    # Find high/low over look_back period
    values = []
    for days_back in range(look_back_days + 1):
        check_dt = curr_dt - relativedelta(days=days_back)
        check_str = check_dt.strftime("%Y-%m-%d")
        val = boll_data.get(check_str, "N/A")
        if val != "N/A":
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                pass

    if not values:
        return ""

    high = max(values)
    low = min(values)
    current = values[0] if values else 0

    return (
        f"### Price Context (Bollinger Middle as proxy)\n"
        f"- Current: {current:.2f} | {look_back_days}d High: {high:.2f} | {look_back_days}d Low: {low:.2f}\n"
    )
