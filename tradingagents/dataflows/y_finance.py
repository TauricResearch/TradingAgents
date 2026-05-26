from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import yfinance as yf
import os
from .stockstats_utils import (
    StockstatsUtils,
    _clean_dataframe,
    yf_retry,
    load_ohlcv,
    filter_financials_by_date,
    _min_bars_required,
)
from .symbol_utils import normalize_symbol, NoMarketDataError

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Resolve broker/forex symbols to Yahoo's convention (XAUUSD+ -> GC=F).
    canonical = normalize_symbol(symbol)
    ticker = yf.Ticker(canonical)

    # Fetch historical data for the specified date range
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))

    # Empty result means the symbol is unknown/delisted. Raise a typed error
    # instead of returning prose: the routing layer turns it into a single
    # unambiguous "no data" signal so the agent never fabricates a price.
    if data.empty:
        raise NoMarketDataError(
            symbol, canonical, f"no rows between {start_date} and {end_date}"
        )

    # Remove timezone info from index for cleaner output
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # Convert DataFrame to CSV string
    csv_string = data.to_csv()

    # Add header information; note the resolved symbol when it differs so the
    # agent (and user) can see which instrument was actually priced.
    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string

def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        "close_20_ema": (
            "20 EMA: The most-watched intermediate trend line. "
            "Usage: Dynamic support/resistance in trending markets; price holding the 20 EMA = trend intact. "
            "Tips: Bridges the gap between 10 EMA (noisy) and 50 SMA (laggy)."
        ),
        "close_50_ema": (
            "50 EMA: Medium-term EMA — reacts faster than 50 SMA at the same window. "
            "Usage: Use instead of 50 SMA when you want quicker trend-change confirmation. "
            "Tips: Often used as a stop-loss reference in trend-following strategies."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis (ADX)."
        ),
        "kdjk": (
            "KDJ-K: Stochastic K line. Faster oscillator than RSI; ranges 0–100. "
            "Usage: Crosses above K-D = bullish; crosses below = bearish. Above 80 = overbought, below 20 = oversold. "
            "Tips: KDJ catches turning points RSI misses in range-bound markets; pair with kdjd."
        ),
        "kdjd": (
            "KDJ-D: Stochastic D line — smoothed K. "
            "Usage: K crossing D is the canonical signal. D acts as confirmation. "
            "Tips: Use with kdjk; together they're more robust than RSI in choppy regimes."
        ),
        "cci": (
            "CCI: Commodity Channel Index. Measures deviation from mean price. "
            "Usage: ±100 = standard overbought/oversold (fade); ±200 = breakout zone (follow). "
            "Tips: Dual-purpose — interpret CCI based on regime: trending → follow extremes, ranging → fade them."
        ),
        # Trend Strength
        "adx": (
            "ADX: Average Directional Index. Measures TREND STRENGTH (not direction). "
            "Usage: ADX > 25 = strong trend (ride it, don't fade); ADX < 20 = ranging market (fade extremes). "
            "Tips: Critical context for RSI/CCI/KDJ — overbought in strong trend ≠ overbought in chop. Always include in your selection."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates.
    # The bulk dict contains ONLY trading days (rows present in OHLCV).
    # Non-trading days (weekends/holidays) simply aren't keys.
    trading_day_lines = []
    non_trading_day_count = 0
    insufficient_history_count = 0

    try:
        indicator_data, total_bars_at_curr = _get_stock_stats_bulk(
            symbol, indicator, curr_date
        )

        # Apply the same strict-window guard the single-value path uses:
        # if total available bars < indicator's required window, the entire
        # range is unreliable — return one explicit ERROR_INSUFFICIENT_HISTORY
        # instead of a list of fabricable values.
        min_bars = _min_bars_required(indicator)
        if min_bars and total_bars_at_curr < min_bars:
            return (
                f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
                f"ERROR_INSUFFICIENT_HISTORY: indicator '{indicator}' requires at "
                f"least {min_bars} prior bars but only {total_bars_at_curr} are "
                f"available for {symbol} on or before {curr_date}. "
                f"Any value computed from a partial window is misleading. "
                f"Do NOT approximate or treat partial-window values as valid; "
                f"report the data gap explicitly in your report.\n\n"
                + best_ind_params.get(indicator, "No description available.")
            )

        current_dt = curr_date_dt
        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')
            if date_str in indicator_data:
                value = indicator_data[date_str]
                if value == "__NAN__":
                    # Indicator window not yet filled on this specific date,
                    # even though prior days were OK (early in history).
                    insufficient_history_count += 1
                    trading_day_lines.append(
                        f"{date_str}: ERROR_INSUFFICIENT_HISTORY (window not filled)"
                    )
                else:
                    trading_day_lines.append(f"{date_str}: {value}")
            else:
                non_trading_day_count += 1
            current_dt = current_dt - relativedelta(days=1)

        ind_string = "\n".join(trading_day_lines) + "\n"

    except NoMarketDataError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        print(f"Error getting bulk stockstats data: {e}")
        # Fallback to per-day calls (now also using structured ERROR_* tokens
        # via the patched StockstatsUtils.get_stock_stats).
        ind_string = ""
        current_dt = curr_date_dt
        while current_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, current_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{current_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            current_dt = current_dt - relativedelta(days=1)

    footer_parts = []
    if non_trading_day_count:
        footer_parts.append(
            f"[{non_trading_day_count} non-trading days (weekends/holidays) in window — excluded from list above]"
        )
    if insufficient_history_count:
        footer_parts.append(
            f"[{insufficient_history_count} trading days had insufficient history for '{indicator}' window — flagged inline]"
        )
    footer = ("\n" + "\n".join(footer_parts) + "\n") if footer_parts else ""

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + footer
        + "\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"]
):
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.

    Returns a 2-tuple ``(date_to_value, total_bars_at_curr)``:
      - ``date_to_value``: dict mapping trading-day ``YYYY-MM-DD`` strings to
        either the numeric value as ``str(...)`` OR the sentinel ``"__NAN__"``
        when the indicator's rolling window is not yet filled on that date.
      - ``total_bars_at_curr``: number of OHLCV bars available on or before
        ``curr_date`` — used by callers to apply the strict-window guard.
    """
    from stockstats import wrap

    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator

    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]
        if pd.isna(indicator_value):
            # Sentinel — distinct from "weekend/holiday" (which is just
            # absence from this dict). The outer loop translates this into
            # an ERROR_INSUFFICIENT_HISTORY message for that specific date.
            result_dict[date_str] = "__NAN__"
        else:
            result_dict[date_str] = str(indicator_value)

    total_bars_at_curr = int(len(df))
    return result_dict, total_bars_at_curr


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[
        str, "The current trading date you are trading on, YYYY-mm-dd"
    ],
) -> str:

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except NoMarketDataError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        print(
            f"Error getting stockstats indicator data for indicator {indicator} on {curr_date}: {e}"
        )
        return ""

    return str(indicator_value)


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get company fundamentals overview from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            raise NoMarketDataError(ticker, canonical, "no fundamentals returned")

        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        # yfinance returns a stub dict (e.g. {"trailingPegRatio": None}) for
        # unknown symbols, so `info` is truthy but every field is empty. Treat
        # "no usable fields" as no data rather than emitting a bare header the
        # agent might fabricate around.
        if not lines:
            raise NoMarketDataError(ticker, canonical, "no fundamental fields returned")

        header = f"# Company Fundamentals for {canonical}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no balance sheet data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Balance Sheet data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no cash flow data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Cash Flow data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            raise NoMarketDataError(ticker, canonical, "no income statement data")

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Income Statement data for {canonical} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except NoMarketDataError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions data from yfinance."""
    canonical = normalize_symbol(ticker)
    try:
        ticker_obj = yf.Ticker(canonical)
        data = yf_retry(lambda: ticker_obj.insider_transactions)

        # Empty is normal here (many valid symbols have no insider filings),
        # so report it plainly rather than treating the symbol as invalid.
        if data is None or data.empty:
            return f"No insider transactions reported for symbol '{canonical}'"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Insider Transactions data for {canonical}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"