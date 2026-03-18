"""Finnhub technical indicator functions.

Provides technical analysis indicators (SMA, EMA, MACD, RSI, BBANDS, ATR)
via the Finnhub /indicator endpoint.  Output format mirrors the Alpha Vantage
indicator output so downstream agents see consistent data regardless of vendor.
"""

from datetime import datetime, timedelta
from typing import Literal

from .finnhub_common import (
    FinnhubError,
    ThirdPartyParseError,
    _make_api_request,
    _now_str,
    _to_unix_timestamp,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Supported indicators and their Finnhub indicator name
_INDICATOR_CONFIG: dict[str, dict] = {
    "sma": {
        "indicator": "sma",
        "description": (
            "SMA: Simple Moving Average. Smooths price data over N periods to "
            "identify trend direction. Lags price — combine with faster indicators "
            "for timely signals."
        ),
        "value_key": "sma",
    },
    "ema": {
        "indicator": "ema",
        "description": (
            "EMA: Exponential Moving Average. Gives more weight to recent prices "
            "than SMA, reacting faster to price changes. Useful for short-term trend "
            "identification and dynamic support/resistance."
        ),
        "value_key": "ema",
    },
    "macd": {
        "indicator": "macd",
        "description": (
            "MACD: Moving Average Convergence/Divergence. Computes momentum via "
            "differences of EMAs. Look for crossovers and divergence as signals of "
            "trend changes. Confirm with other indicators in sideways markets."
        ),
        "value_key": "macd",
    },
    "rsi": {
        "indicator": "rsi",
        "description": (
            "RSI: Relative Strength Index. Measures momentum to flag overbought "
            "(>70) and oversold (<30) conditions. In strong trends RSI may remain "
            "extreme — always cross-check with trend analysis."
        ),
        "value_key": "rsi",
    },
    "bbands": {
        "indicator": "bbands",
        "description": (
            "BBANDS: Bollinger Bands. Upper, middle (SMA), and lower bands "
            "representing 2 standard deviations from the middle. Signals potential "
            "overbought/oversold zones and breakout areas."
        ),
        "value_key": "upperBand",  # primary value; lowerBand and middleBand also returned
    },
    "atr": {
        "indicator": "atr",
        "description": (
            "ATR: Average True Range. Averages true range to measure volatility. "
            "Used for setting stop-loss levels and adjusting position sizes based on "
            "current market volatility."
        ),
        "value_key": "atr",
    },
}

SupportedIndicator = Literal["sma", "ema", "macd", "rsi", "bbands", "atr"]

# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def get_indicator_finnhub(
    symbol: str,
    indicator: SupportedIndicator,
    start_date: str,
    end_date: str,
    time_period: int = 14,
    series_type: str = "close",
    **params: object,
) -> str:
    """Fetch a technical indicator series from Finnhub /indicator.

    Calls the Finnhub ``/indicator`` endpoint for the given symbol and date
    range, then formats the result as a labelled time-series string that matches
    the output style of ``alpha_vantage_indicator.get_indicator``.

    Args:
        symbol: Equity ticker symbol (e.g. "AAPL").
        indicator: One of ``'sma'``, ``'ema'``, ``'macd'``, ``'rsi'``,
            ``'bbands'``, ``'atr'``.
        start_date: Inclusive start date in YYYY-MM-DD format.
        end_date: Inclusive end date in YYYY-MM-DD format.
        time_period: Number of data points used for indicator calculation
            (default 14).  Maps to the ``timeperiod`` Finnhub parameter.
        series_type: Price field used for calculation — ``'close'``,
            ``'open'``, ``'high'``, or ``'low'`` (default ``'close'``).
        **params: Additional keyword arguments forwarded to the Finnhub
            endpoint (e.g. ``fastPeriod``, ``slowPeriod`` for MACD).

    Returns:
        Formatted multi-line string with date-value pairs and a description,
        mirroring the Alpha Vantage indicator format.

    Raises:
        ValueError: When an unsupported indicator name is provided.
        FinnhubError: On API-level errors or when the symbol returns no data.
        ThirdPartyParseError: When the response cannot be parsed.
    """
    indicator_lower = indicator.lower()
    if indicator_lower not in _INDICATOR_CONFIG:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Supported indicators: {sorted(_INDICATOR_CONFIG.keys())}"
        )

    config = _INDICATOR_CONFIG[indicator_lower]
    finnhub_indicator = config["indicator"]
    description = config["description"]
    primary_value_key = config["value_key"]

    # Finnhub /indicator uses Unix timestamps
    from_ts = _to_unix_timestamp(start_date)
    # Add an extra day to end_date to include it fully
    to_ts = _to_unix_timestamp(end_date) + 86400

    request_params: dict = {
        "symbol": symbol,
        "resolution": "D",
        "from": from_ts,
        "to": to_ts,
        "indicator": finnhub_indicator,
        "timeperiod": time_period,
        "seriestype": series_type,
    }
    # Merge any caller-supplied extra params (e.g. fastPeriod, slowPeriod for MACD)
    request_params.update(params)

    data = _make_api_request("indicator", request_params)

    # Finnhub returns parallel lists: "t" for timestamps and indicator-named lists
    timestamps: list[int] = data.get("t", [])
    status = data.get("s")

    if status == "no_data" or not timestamps:
        raise FinnhubError(
            f"No indicator data returned for symbol={symbol}, "
            f"indicator={indicator}, start={start_date}, end={end_date}"
        )

    if status != "ok":
        raise FinnhubError(
            f"Unexpected indicator response status '{status}' for "
            f"symbol={symbol}, indicator={indicator}"
        )

    # Build the result string — handle multi-value indicators like MACD and BBANDS
    result_lines: list[str] = [
        f"## {indicator.upper()} values from {start_date} to {end_date} — Finnhub",
        f"## Symbol: {symbol} | Time Period: {time_period} | Series: {series_type}",
        "",
    ]

    if indicator_lower == "macd":
        macd_vals: list[float | None] = data.get("macd", [])
        signal_vals: list[float | None] = data.get("macdSignal", [])
        hist_vals: list[float | None] = data.get("macdHist", [])

        result_lines.append(f"{'Date':<12} {'MACD':>12} {'Signal':>12} {'Histogram':>12}")
        result_lines.append("-" * 50)

        for ts, macd, signal, hist in zip(timestamps, macd_vals, signal_vals, hist_vals):
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            macd_s = f"{macd:.4f}" if macd is not None else "N/A"
            sig_s = f"{signal:.4f}" if signal is not None else "N/A"
            hist_s = f"{hist:.4f}" if hist is not None else "N/A"
            result_lines.append(f"{date_str:<12} {macd_s:>12} {sig_s:>12} {hist_s:>12}")

    elif indicator_lower == "bbands":
        upper_vals: list[float | None] = data.get("upperBand", [])
        middle_vals: list[float | None] = data.get("middleBand", [])
        lower_vals: list[float | None] = data.get("lowerBand", [])

        result_lines.append(f"{'Date':<12} {'Upper':>12} {'Middle':>12} {'Lower':>12}")
        result_lines.append("-" * 50)

        for ts, upper, middle, lower in zip(timestamps, upper_vals, middle_vals, lower_vals):
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            u_s = f"{upper:.4f}" if upper is not None else "N/A"
            m_s = f"{middle:.4f}" if middle is not None else "N/A"
            l_s = f"{lower:.4f}" if lower is not None else "N/A"
            result_lines.append(f"{date_str:<12} {u_s:>12} {m_s:>12} {l_s:>12}")

    else:
        # Single-value indicators: SMA, EMA, RSI, ATR
        values: list[float | None] = data.get(primary_value_key, [])

        result_lines.append(f"{'Date':<12} {indicator.upper():>12}")
        result_lines.append("-" * 26)

        for ts, value in zip(timestamps, values):
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
            val_s = f"{value:.4f}" if value is not None else "N/A"
            result_lines.append(f"{date_str:<12} {val_s:>12}")

    result_lines.append("")
    result_lines.append(description)

    return "\n".join(result_lines)
