from datetime import datetime
from typing import Annotated

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta

from .indicator_registry import effective_params, get_spec, resolve_column
from .stockstats_utils import (
    StockstatsUtils,
    _assert_ohlcv_not_stale,
    compute_obv,
    filter_financials_by_date,
    format_supertrend_block,
    format_td_setup_block,
    format_zscore_block,
    load_ohlcv,
    supertrend_by_timeframe,
    td_setup_by_timeframe,
    yf_retry,
    yfinance_timeout,
    zscore_by_timeframe,
)
from .symbol_utils import NoMarketDataError, normalize_symbol


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Resolve broker/forex symbols to Yahoo's convention (XAUUSD+ -> GC=F).
    canonical = normalize_symbol(symbol)
    ticker = yf.Ticker(canonical)

    # yfinance treats ``end`` as EXCLUSIVE, so it would drop the requested
    # end_date row (and the current day when end_date is today). Request one day
    # past end_date so the requested range is actually inclusive (#986/#987).
    end_inclusive = (end_dt + relativedelta(days=1)).strftime("%Y-%m-%d")
    data = yf_retry(lambda: ticker.history(
        start=start_date,
        end=end_inclusive,
        timeout=yfinance_timeout(),
    ))

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

    # Reject a stale frame (e.g. a year-old partial response) before it is
    # formatted into the report. Raises NoMarketDataError, which the router
    # turns into one clear unavailable signal (#1021).
    _assert_ohlcv_not_stale(data, end_date, symbol, canonical)

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

    spec = get_spec(indicator)  # unknown names raise ValueError
    params = effective_params(indicator)  # spec defaults + config overrides

    # TD-9 is not a stockstats handler — compute it from OHLCV across timeframes
    # and return the tiered block (weekly > monthly > daily) directly.
    if spec.custom == "td_9":
        counts = td_setup_by_timeframe(load_ohlcv(symbol, curr_date), curr_date)
        return format_td_setup_block(counts) + "\n\n" + spec.description

    # Z-Score is likewise computed from OHLCV across timeframes, not stockstats.
    if spec.custom == "z_score":
        zscores = zscore_by_timeframe(
            load_ohlcv(symbol, curr_date), curr_date, window=params["window"]
        )
        return (
            format_zscore_block(zscores, window=params["window"])
            + "\n\n"
            + spec.description
        )

    # SuperTrend resamples OHLCV to weekly/monthly bars itself, so it also
    # returns a tiered block rather than a windowed daily listing.
    if spec.custom == "supertrend":
        snapshots = supertrend_by_timeframe(
            load_ohlcv(symbol, curr_date), curr_date, window=params["window"]
        )
        return (
            format_supertrend_block(snapshots, window=params["window"])
            + "\n\n"
            + spec.description
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates
    try:
        if spec.custom == "obv":
            # OBV is computed from OHLCV (not a stockstats handler) but reads
            # like any daily series, so it renders through the same window.
            obv = compute_obv(load_ohlcv(symbol, curr_date))
            indicator_data = {
                date.strftime("%Y-%m-%d"): str(float(value))
                for date, value in obv.items()
            }
        else:
            indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)


        # Generate the date range we need
        current_dt = curr_date_dt
        date_values = []

        while current_dt >= before:
            date_str = current_dt.strftime('%Y-%m-%d')

            # Look up the indicator value for this date
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A: Not a trading day (weekend or holiday)"

            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)

        # Build the result string
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"

    except NoMarketDataError:
        raise  # Unknown/delisted symbol — let the router emit the sentinel
    except Exception as e:
        print(f"Error getting bulk stockstats data: {e}")
        # Fallback to original implementation if bulk method fails
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    # Show effective params in the header only when they differ from the
    # defaults, so unconfigured output stays byte-identical.
    label = indicator
    if params and params != spec.default_params:
        label += " (" + ", ".join(f"{k}={v}" for k, v in params.items()) + ")"

    result_str = (
        f"## {label} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + spec.description
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"]
) -> dict:
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.
    Returns dict mapping date strings to indicator values.
    """
    from stockstats import wrap

    spec = get_spec(indicator)
    column = resolve_column(indicator, effective_params(indicator))

    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Calculate the indicator for all rows at once
    df[column]  # This triggers stockstats to calculate the indicator

    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[column]

        # Handle NaN/None values
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        elif spec.scale != 1.0:
            result_dict[date_str] = str(float(indicator_value) * spec.scale)
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


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
        spec = get_spec(indicator)
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            resolve_column(indicator, effective_params(indicator)),
            curr_date,
        )
        # Non-trading days come back as an explanatory string; only numeric
        # readings are rescaled (stockstats mfi is 0-1, reported as 0-100).
        if spec.scale != 1.0 and not isinstance(indicator_value, str):
            indicator_value = float(indicator_value) * spec.scale
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
