from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import yfinance as yf
import os
from .stockstats_utils import StockstatsUtils, _clean_dataframe, yf_retry, load_ohlcv, filter_financials_by_date

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Create ticker object
    ticker = yf.Ticker(symbol.upper())

    # Fetch historical data for the specified date range
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))

    # Check if data is empty
    if data.empty:
        return (
            f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
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

    # Add header information
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
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
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
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

    # Optimized: Get stock data once and calculate indicators for all dates
    try:
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

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
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

    data = load_ohlcv(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    
    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator
    
    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]
        
        # Handle NaN/None values
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
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
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
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
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"

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

        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get balance sheet data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get cash flow data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None
):
    """Get income statement data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        data = filter_financials_by_date(data, curr_date)

        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)
        
        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"
            
        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()
        
        # Add header information
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def _fmt_num(value, as_int: bool = False) -> str:
    """Format a numeric value for the markdown tables; 'n/a' when missing."""
    if value is None:
        return "n/a"
    try:
        if pd.isna(value):
            return "n/a"
    except (TypeError, ValueError):
        return str(value)
    try:
        return f"{int(value)}" if as_int else f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value) -> str:
    """Format a fractional value (e.g. 0.048) as a signed percentage string."""
    if value is None:
        return "n/a"
    try:
        if pd.isna(value):
            return "n/a"
        return f"{float(value):+.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _render_estimates_table(estimates_df, header_label: str) -> list:
    """Render a yfinance estimates DataFrame (earnings_estimate / revenue_estimate) as markdown."""
    lines = [
        f"### {header_label}",
        "| Period | Avg | Low | High | # Analysts | YoY Growth |",
        "|---|---|---|---|---|---|",
    ]
    for period, row in estimates_df.iterrows():
        lines.append(
            f"| {period} "
            f"| {_fmt_num(row.get('avg'))} "
            f"| {_fmt_num(row.get('low'))} "
            f"| {_fmt_num(row.get('high'))} "
            f"| {_fmt_num(row.get('numberOfAnalysts'), as_int=True)} "
            f"| {_fmt_pct(row.get('growth'))} |"
        )
    return lines


def get_earnings_context(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
    near_earnings_window: Annotated[int, "trading-day threshold for the 'near earnings' flag"] = 5,
) -> str:
    """Earnings calendar awareness: next event, consensus, surprises, recommendations.

    Returns one markdown string with four sections so the Fundamentals Analyst
    can reason about catalyst risk near earnings releases. The surprise history
    is filtered to fiscal periods ending on or before ``curr_date`` to prevent
    look-ahead bias; consensus estimates and recommendation counts come from
    yfinance as a current snapshot (yfinance does not expose historical
    snapshots of these series).
    """
    ticker_upper = ticker.upper()
    curr_ts = pd.to_datetime(curr_date) if curr_date else pd.Timestamp.today().normalize()

    sections = [f"# Earnings Context for {ticker_upper} (as of {curr_ts.strftime('%Y-%m-%d')})"]

    try:
        ticker_obj = yf.Ticker(ticker_upper)
    except Exception as e:
        return f"Error retrieving earnings context for {ticker}: {e}"

    # --- Next earnings event ---
    sections.append("\n## Next Earnings Event")
    try:
        calendar = yf_retry(lambda: ticker_obj.calendar) or {}
        raw_dates = calendar.get("Earnings Date") or []
        dates_idx = pd.to_datetime(list(raw_dates), errors="coerce")
        if getattr(dates_idx, "tz", None) is not None:
            dates_idx = dates_idx.tz_localize(None)
        future = sorted(d for d in dates_idx if pd.notna(d) and d >= curr_ts)
        if future:
            next_date = future[0]
            td_until = max(0, len(pd.bdate_range(start=curr_ts, end=next_date)) - 1)
            is_near = td_until <= near_earnings_window
            sections.append(f"- Date: {next_date.strftime('%Y-%m-%d')}")
            sections.append(f"- Trading days until: {td_until}")
            sections.append(
                f"- Near earnings (within {near_earnings_window} trading days): "
                + ("YES — elevated catalyst risk" if is_near else "NO")
            )
        else:
            sections.append("- No upcoming earnings date scheduled.")
    except Exception:
        sections.append("- (unavailable)")

    # --- Consensus estimates (EPS + revenue, upcoming quarters) ---
    sections.append("\n## Consensus Estimates (upcoming periods)")
    try:
        eps_est = yf_retry(lambda: ticker_obj.earnings_estimate)
        if eps_est is not None and not eps_est.empty:
            sections.extend(_render_estimates_table(eps_est, "EPS"))
        else:
            sections.append("### EPS\n- (unavailable)")
    except Exception:
        sections.append("### EPS\n- (unavailable)")
    try:
        rev_est = yf_retry(lambda: ticker_obj.revenue_estimate)
        if rev_est is not None and not rev_est.empty:
            sections.extend(_render_estimates_table(rev_est, "Revenue"))
        else:
            sections.append("### Revenue\n- (unavailable)")
    except Exception:
        sections.append("### Revenue\n- (unavailable)")

    # --- Earnings surprise history (look-ahead-safe) ---
    sections.append(f"\n## Earnings Surprise History (≤ {curr_ts.strftime('%Y-%m-%d')})")
    try:
        history = yf_retry(lambda: ticker_obj.earnings_history)
        if history is not None and not history.empty:
            hist = history.copy()
            hist.index = pd.to_datetime(hist.index, errors="coerce")
            if getattr(hist.index, "tz", None) is not None:
                hist.index = hist.index.tz_localize(None)
            hist = hist[hist.index.notna() & (hist.index <= curr_ts)].sort_index(
                ascending=False
            ).head(4)
            if not hist.empty:
                sections.append("| Quarter Ended | Estimate | Actual | Surprise |")
                sections.append("|---|---|---|---|")
                for ts, row in hist.iterrows():
                    sections.append(
                        f"| {pd.Timestamp(ts).strftime('%Y-%m-%d')} "
                        f"| {_fmt_num(row.get('epsEstimate'))} "
                        f"| {_fmt_num(row.get('epsActual'))} "
                        f"| {_fmt_pct(row.get('surprisePercent'))} |"
                    )
            else:
                sections.append("- (no reported earnings on or before curr_date)")
        else:
            sections.append("- (unavailable)")
    except Exception:
        sections.append("- (unavailable)")

    # --- Analyst recommendations snapshot ---
    sections.append("\n## Analyst Recommendations Snapshot")
    try:
        rec = yf_retry(lambda: ticker_obj.recommendations_summary)
        if rec is None or (hasattr(rec, "empty") and rec.empty):
            rec = yf_retry(lambda: ticker_obj.recommendations)
        if rec is not None and not rec.empty:
            sections.append("| Period | Strong Buy | Buy | Hold | Sell | Strong Sell |")
            sections.append("|---|---|---|---|---|---|")
            for _, row in rec.iterrows():
                sections.append(
                    f"| {row.get('period', '?')} "
                    f"| {_fmt_num(row.get('strongBuy'), as_int=True)} "
                    f"| {_fmt_num(row.get('buy'), as_int=True)} "
                    f"| {_fmt_num(row.get('hold'), as_int=True)} "
                    f"| {_fmt_num(row.get('sell'), as_int=True)} "
                    f"| {_fmt_num(row.get('strongSell'), as_int=True)} |"
                )
        else:
            sections.append("- (unavailable)")
    except Exception:
        sections.append("- (unavailable)")

    return "\n".join(sections)