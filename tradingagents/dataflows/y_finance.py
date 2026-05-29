from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import numpy as np
import yfinance as yf
import os
import logging
from .stockstats_utils import StockstatsUtils, _clean_dataframe, yf_retry, load_ohlcv, filter_financials_by_date
from .config import get_config

logger = logging.getLogger(__name__)


def _is_historical_curr_date(curr_date: str | None) -> bool:
    """Return True iff curr_date is meaningfully in the past (i.e. backtest mode).

    yfinance / Alpha Vantage `info` and `OVERVIEW` payloads are real-time
    snapshots: 52-week high/low, market cap, TTM ratios, 50/200d MAs, etc.
    are computed against TODAY. When curr_date is in the past, returning
    those fields would leak future information into a historical decision.

    A 2-day buffer covers "today's data freshly available" cases without
    misclassifying genuine backtests.
    """
    if not curr_date:
        return False
    try:
        target = pd.to_datetime(curr_date).normalize()
        today = pd.Timestamp.today().normalize()
        return (today - target).days > 2
    except Exception:
        return False

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

    # Header timestamps the data window only; do NOT print datetime.now() since
    # the LLM would learn the real wall-clock date during a backtest.
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n\n"

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
        "close_5_ema": (
            "5 EMA: A very fast moving average for 1-5 day trading. "
            "Usage: Detect immediate momentum shifts, failed bounces, and quick reclaim/loss of short-term trend. "
            "Tips: Noisy by itself; compare with close_10_ema and close_20_ema."
        ),
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
            "20 EMA: A short swing-trend average. "
            "Usage: Separate healthy pullbacks from short-term trend damage. "
            "Tips: For fast trading, require price and the 5/10 EMA stack to confirm."
        ),
        "close_5_sma": (
            "5 SMA: A fast average of recent closes. "
            "Usage: Smooth the last trading week and identify very short-term support/resistance."
        ),
        "close_10_sma": (
            "10 SMA: A two-week average of recent closes. "
            "Usage: Track short-term mean reversion and quick trend changes."
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
        "volume": (
            "VOL: Raw daily traded volume. "
            "Usage: Gauge participation behind a price move; large up-days on expanding volume confirm trend, while breakouts on shrinking volume often fail. "
            "Tips: Compare today's volume to a moving-average baseline (e.g. volume_50_sma); single readings are noisy without a reference level."
        ),
        "volume_50_sma": (
            "MAVOL (50): 50-day simple moving average of volume, the standard baseline for 'normal' participation. "
            "Usage: Treat today's volume / MAVOL ratio as a volume z-score — >1.5x with a price hold above key support is the classical 放量站稳 signal; <0.7x on a breakout suggests weak conviction. "
            "Tips: Pair with price-structure indicators (boll_ub, close_50_sma) so volume context confirms — not replaces — the price signal."
        ),
        "volume_20_sma": (
            "MAVOL (20): 20-day simple moving average of volume, a faster participation baseline for short-term trades. "
            "Usage: Compare today's volume to the last month of trading activity; this reacts faster than volume_50_sma."
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
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None
):
    """Get company fundamentals overview from yfinance.

    yfinance `info` is a real-time snapshot — every numeric field (52W
    high/low, market cap, TTM ratios, MAs) is measured against TODAY, so
    returning the full payload during a historical backtest leaks future
    information. When curr_date is in the past, only structural fields
    (name/sector/industry/business summary) are returned, with an explicit
    notice to the LLM that historical fundamentals are unavailable.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"

        is_historical = _is_historical_curr_date(curr_date)

        # Time-invariant identification fields. Safe at any date.
        structural_fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
        ]

        # Time-variant fields. Returning these during a backtest is a leak.
        time_variant_fields = [
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

        fields = structural_fields if is_historical else structural_fields + time_variant_fields

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# As-of date: {curr_date or 'live'}\n"
        if is_historical:
            header += (
                "# NOTE: Real-time fundamentals (52W high/low, market cap, TTM ratios, "
                "MAs, etc.) are NOT available for historical dates and have been omitted "
                "to prevent look-ahead bias. Use balance_sheet/cashflow/income_statement "
                "for filed historical figures.\n"
            )
        header += "\n"

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
        
        # Header uses curr_date (the simulated trading date), not datetime.now(),
        # to avoid leaking the real wall-clock date to the LLM during backtest.
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# As-of date: {curr_date or 'live'}\n\n"

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
        
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# As-of date: {curr_date or 'live'}\n\n"

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
        
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# As-of date: {curr_date or 'live'}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
):
    """Get insider transactions data from yfinance, filtered by curr_date.

    yfinance returns ALL historical insider transactions; without filtering
    this leaks future transactions into a backtest. We drop any row whose
    transaction date is strictly after curr_date.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)

        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        # Filter rows to those whose transaction date is on or before curr_date.
        # yfinance uses "Start Date" as the transaction-effective date.
        if curr_date:
            cutoff = pd.to_datetime(curr_date).normalize()
            date_col = next(
                (c for c in ("Start Date", "Date", "start_date", "date") if c in data.columns),
                None,
            )
            if date_col is not None:
                dates = pd.to_datetime(data[date_col], errors="coerce")
                data = data[dates.notna() & (dates <= cutoff)]

        if data.empty:
            return f"No insider transactions for {ticker} on or before {curr_date}"

        csv_string = data.to_csv()

        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# As-of date: {curr_date or 'live'}\n\n"

        return header + csv_string
        
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


# --- Options chain ---------------------------------------------------------

_OPTIONS_CACHE_VERSION = 1
_OPTIONS_NEAR_EXPIRIES = 4  # number of nearest expiries to pull
_OPTIONS_ATM_BAND_PCT = 0.05  # ±5% of spot defines "near-the-money" for skew


def _options_cache_dir() -> str:
    """Resolve the options-chain cache directory under the configured data dir."""
    base = get_config().get("data_cache_dir") or os.path.join(
        os.path.dirname(__file__), "data_cache"
    )
    path = os.path.join(base, "options")
    os.makedirs(path, exist_ok=True)
    return path


def _options_cache_path(ticker: str, snapshot_date: str) -> str:
    return os.path.join(
        _options_cache_dir(), f"{ticker.upper()}-options-{snapshot_date}.parquet"
    )


def _load_options_snapshot(ticker: str, snapshot_date: str) -> pd.DataFrame | None:
    path = _options_cache_path(ticker, snapshot_date)
    if not os.path.exists(path):
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def _previous_options_snapshot(
    ticker: str, snapshot_date: str, max_lookback: int = 10
) -> tuple[pd.DataFrame, str] | tuple[None, None]:
    """Find the most recent cached snapshot strictly before snapshot_date."""
    target = pd.to_datetime(snapshot_date).normalize()
    cache_dir = _options_cache_dir()
    prefix = f"{ticker.upper()}-options-"
    candidates: list[tuple[pd.Timestamp, str]] = []
    for fn in os.listdir(cache_dir):
        if not fn.startswith(prefix) or not fn.endswith(".parquet"):
            continue
        date_part = fn[len(prefix) : -len(".parquet")]
        try:
            ts = pd.to_datetime(date_part).normalize()
        except Exception:
            continue
        if ts < target and (target - ts).days <= max_lookback:
            candidates.append((ts, os.path.join(cache_dir, fn)))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    ts, path = candidates[0]
    try:
        return pd.read_parquet(path), ts.strftime("%Y-%m-%d")
    except Exception:
        return None, None


def _fetch_options_chain_live(ticker_obj: yf.Ticker, max_expiries: int) -> pd.DataFrame:
    """Fetch and stack puts/calls across the nearest N expiries into one frame."""
    # Retry on empty: Yahoo's options endpoint returns an empty tuple (rather
    # than raising) when throttled, so an empty list here is usually transient.
    expirations = list(yf_retry(lambda: ticker_obj.options, retry_on_empty=True) or [])
    if not expirations:
        return pd.DataFrame()
    selected = expirations[:max_expiries]
    frames: list[pd.DataFrame] = []
    last_error: Exception | None = None
    for expiry in selected:
        try:
            chain = yf_retry(lambda e=expiry: ticker_obj.option_chain(e))
        except Exception as e:
            last_error = e
            logger.warning(f"Failed to fetch option chain for expiry {expiry}: {e}")
            continue
        for side, df in (("call", chain.calls), ("put", chain.puts)):
            if df is None or df.empty:
                continue
            df = df.copy()
            df["expiration"] = expiry
            df["side"] = side
            frames.append(df)
    if not frames:
        # We had expiries but pulled zero rows. If every expiry raised, surface
        # the real cause instead of returning empty (which the caller reports as
        # "no options data" and masks a throttle/network failure).
        if last_error is not None:
            raise last_error
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Normalize column presence — yfinance fields vary across versions.
    for col in ("strike", "lastPrice", "bid", "ask", "volume",
                "openInterest", "impliedVolatility"):
        if col not in out.columns:
            out[col] = np.nan
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0).astype(int)
    out["openInterest"] = (
        pd.to_numeric(out["openInterest"], errors="coerce").fillna(0).astype(int)
    )
    out["impliedVolatility"] = pd.to_numeric(out["impliedVolatility"], errors="coerce")
    out["strike"] = pd.to_numeric(out["strike"], errors="coerce")
    return out


def _get_spot_price(ticker_obj: yf.Ticker) -> float | None:
    """Best-effort spot price for IV/skew anchoring."""
    try:
        hist = yf_retry(lambda: ticker_obj.history(period="5d"))
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    try:
        info = yf_retry(lambda: ticker_obj.fast_info)
        price = getattr(info, "last_price", None)
        if price is not None:
            return float(price)
    except Exception:
        pass
    return None


def _pc_ratio(chain: pd.DataFrame, field: str) -> float | None:
    calls = chain.loc[chain["side"] == "call", field].sum()
    puts = chain.loc[chain["side"] == "put", field].sum()
    if calls <= 0:
        return None
    return float(puts) / float(calls)


def _near_atm_iv(chain: pd.DataFrame, spot: float, expiry: str) -> dict:
    """Average IV in the ±band around spot, plus put-call IV skew at that band."""
    band_lo = spot * (1 - _OPTIONS_ATM_BAND_PCT)
    band_hi = spot * (1 + _OPTIONS_ATM_BAND_PCT)
    near = chain[(chain["expiration"] == expiry) & chain["strike"].between(band_lo, band_hi)]
    if near.empty:
        return {"atm_iv": None, "put_iv": None, "call_iv": None, "skew": None}
    call_iv = near.loc[near["side"] == "call", "impliedVolatility"].mean()
    put_iv = near.loc[near["side"] == "put", "impliedVolatility"].mean()
    atm_iv = near["impliedVolatility"].mean()
    skew = None
    if pd.notna(put_iv) and pd.notna(call_iv):
        skew = float(put_iv - call_iv)
    return {
        "atm_iv": None if pd.isna(atm_iv) else float(atm_iv),
        "put_iv": None if pd.isna(put_iv) else float(put_iv),
        "call_iv": None if pd.isna(call_iv) else float(call_iv),
        "skew": skew,
    }


def _max_pain(chain: pd.DataFrame, expiry: str) -> float | None:
    """Strike that minimizes total option holder payoff at expiration."""
    exp_chain = chain[chain["expiration"] == expiry]
    strikes = sorted(exp_chain["strike"].dropna().unique())
    if not strikes:
        return None
    calls = exp_chain[exp_chain["side"] == "call"][["strike", "openInterest"]]
    puts = exp_chain[exp_chain["side"] == "put"][["strike", "openInterest"]]
    best_strike, best_pain = None, None
    for s in strikes:
        call_pain = ((s - calls["strike"]).clip(lower=0) * calls["openInterest"]).sum()
        put_pain = ((puts["strike"] - s).clip(lower=0) * puts["openInterest"]).sum()
        total = float(call_pain + put_pain)
        if best_pain is None or total < best_pain:
            best_pain, best_strike = total, float(s)
    return best_strike


def _top_oi_strikes(chain: pd.DataFrame, expiry: str, side: str, n: int = 5) -> pd.DataFrame:
    sub = chain[
        (chain["expiration"] == expiry) & (chain["side"] == side)
    ][["strike", "openInterest", "volume", "impliedVolatility"]]
    return sub.sort_values("openInterest", ascending=False).head(n).reset_index(drop=True)


def _unusual_contracts(chain: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Contracts where today's volume materially exceeds open interest."""
    sub = chain[(chain["openInterest"] > 0) & (chain["volume"] > chain["openInterest"])].copy()
    if sub.empty:
        return sub
    sub["vol_oi_ratio"] = sub["volume"] / sub["openInterest"]
    return sub.sort_values("volume", ascending=False).head(n)[
        ["expiration", "side", "strike", "volume", "openInterest", "vol_oi_ratio", "impliedVolatility"]
    ].reset_index(drop=True)


def _snapshot_deltas(
    current: pd.DataFrame, previous: pd.DataFrame, n: int = 5
) -> pd.DataFrame:
    """Day-over-day OI / Volume / IV changes per contract."""
    if previous is None or previous.empty or current.empty:
        return pd.DataFrame()
    key = ["expiration", "side", "strike"]
    merged = current.merge(
        previous[key + ["openInterest", "volume", "impliedVolatility"]],
        on=key,
        how="inner",
        suffixes=("", "_prev"),
    )
    if merged.empty:
        return merged
    merged["oi_delta"] = merged["openInterest"] - merged["openInterest_prev"]
    merged["vol_delta"] = merged["volume"] - merged["volume_prev"]
    merged["iv_delta"] = merged["impliedVolatility"] - merged["impliedVolatility_prev"]
    merged["abs_oi_delta"] = merged["oi_delta"].abs()
    return merged.sort_values("abs_oi_delta", ascending=False).head(n)[
        ["expiration", "side", "strike", "openInterest_prev", "openInterest",
         "oi_delta", "volume", "vol_delta", "impliedVolatility", "iv_delta"]
    ].reset_index(drop=True)


def _df_to_md(df: pd.DataFrame, float_cols: list[str] | None = None) -> str:
    """Render a small DataFrame as a pipe-table without requiring tabulate."""
    if df is None or df.empty:
        return "_(none)_\n"
    out = df.copy()
    if float_cols:
        for c in float_cols:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce").round(4)
    cols = list(out.columns)
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    rows = []
    for _, r in out.iterrows():
        rows.append("| " + " | ".join(_cell(r[c]) for c in cols) + " |")
    return "\n".join([header, sep, *rows]) + "\n"


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        return f"{v:g}"
    return str(v)


def get_options_chain(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
):
    """Options-chain snapshot with P/C ratio, ATM IV/skew, max pain, and unusual activity.

    yfinance only exposes the live option chain — there is no historical
    endpoint. We cache each snapshot to parquet so subsequent live calls can
    surface day-over-day deltas, and so a backtest that previously cached
    data can still read it. For historical dates with no cached snapshot we
    refuse to fall back to the live chain (look-ahead bias).
    """
    if not curr_date:
        curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
    is_historical = _is_historical_curr_date(curr_date)

    cached = _load_options_snapshot(ticker, curr_date)
    chain: pd.DataFrame | None = None
    spot: float | None = None
    source_note = ""

    ticker_obj = yf.Ticker(ticker.upper())

    if cached is not None and not cached.empty:
        chain = cached
        spot = _get_spot_price(ticker_obj) if not is_historical else None
        if spot is None and "underlying_price" in cached.columns:
            try:
                spot = float(cached["underlying_price"].dropna().iloc[0])
            except Exception:
                spot = None
        source_note = f"loaded cached snapshot for {curr_date}"
    elif is_historical:
        return (
            f"# Options chain for {ticker.upper()}\n"
            f"# As-of date: {curr_date}\n\n"
            "NOTE: yfinance does not expose historical option chains and no cached "
            f"snapshot exists for {curr_date}. To enable historical options signals, "
            "run this tool live and let the cache accumulate, or wire a paid vendor "
            "(Polygon / ORATS / Unusual Whales) into the options_data category.\n"
        )
    else:
        try:
            chain = _fetch_options_chain_live(ticker_obj, _OPTIONS_NEAR_EXPIRIES)
        except Exception as e:
            return f"Error retrieving options chain for {ticker}: {e}"
        if chain is None or chain.empty:
            return f"No options data found for symbol '{ticker}'"
        spot = _get_spot_price(ticker_obj)
        if spot is not None:
            chain["underlying_price"] = spot
        chain["snapshot_date"] = curr_date
        try:
            chain.to_parquet(_options_cache_path(ticker, curr_date), index=False)
            source_note = f"fetched live and cached to {curr_date}.parquet"
        except Exception as e:
            source_note = f"fetched live (cache write failed: {e})"

    if chain is None or chain.empty:
        return f"No options data found for symbol '{ticker}'"

    # ---- Signals ----------------------------------------------------------
    pc_vol = _pc_ratio(chain, "volume")
    pc_oi = _pc_ratio(chain, "openInterest")

    expiries = sorted(chain["expiration"].dropna().unique())
    near_expiry = expiries[0] if expiries else None

    iv_block = (
        _near_atm_iv(chain, spot, near_expiry)
        if (spot is not None and near_expiry is not None)
        else {"atm_iv": None, "put_iv": None, "call_iv": None, "skew": None}
    )
    pc_vol_near = (
        _pc_ratio(chain[chain["expiration"] == near_expiry], "volume")
        if near_expiry else None
    )
    pc_oi_near = (
        _pc_ratio(chain[chain["expiration"] == near_expiry], "openInterest")
        if near_expiry else None
    )

    max_pain = _max_pain(chain, near_expiry) if near_expiry else None
    top_call_oi = _top_oi_strikes(chain, near_expiry, "call") if near_expiry else pd.DataFrame()
    top_put_oi = _top_oi_strikes(chain, near_expiry, "put") if near_expiry else pd.DataFrame()
    unusual = _unusual_contracts(chain)

    prev_chain, prev_date = _previous_options_snapshot(ticker, curr_date)
    deltas = _snapshot_deltas(chain, prev_chain) if prev_chain is not None else pd.DataFrame()

    # ---- Format report ----------------------------------------------------
    lines: list[str] = []
    lines.append(f"# Options chain signals for {ticker.upper()}")
    lines.append(f"# As-of date: {curr_date}")
    lines.append(f"# Source: {source_note}")
    lines.append(f"# Spot: {spot:.2f}" if spot is not None else "# Spot: unknown")
    lines.append(f"# Expiries covered: {', '.join(expiries) if expiries else 'none'}")
    lines.append(f"# Near-expiry used for IV/max-pain: {near_expiry or 'n/a'}")
    lines.append("")

    def _fmt(v, digits=2):
        return f"{v:.{digits}f}" if isinstance(v, (int, float)) and v is not None else "n/a"

    lines.append("## 1. Put/Call ratios")
    lines.append(f"- All expiries — Volume P/C: {_fmt(pc_vol)} | OI P/C: {_fmt(pc_oi)}")
    lines.append(
        f"- Near-expiry ({near_expiry}) — Volume P/C: {_fmt(pc_vol_near)} | "
        f"OI P/C: {_fmt(pc_oi_near)}"
    )
    lines.append(
        "- Interpretation: vol P/C >1.2 is put-heavy (bearish/hedging); <0.7 is "
        "call-heavy (bullish/speculative); ~1.0 is balanced."
    )
    lines.append("")

    lines.append(f"## 2. Near-expiry ATM IV / skew  (band ±{int(_OPTIONS_ATM_BAND_PCT*100)}% of spot)")
    lines.append(f"- ATM IV: {_fmt(iv_block['atm_iv'], 4)}")
    lines.append(f"- Call-leg IV: {_fmt(iv_block['call_iv'], 4)}  |  Put-leg IV: {_fmt(iv_block['put_iv'], 4)}")
    lines.append(
        f"- Put-Call IV skew: {_fmt(iv_block['skew'], 4)} "
        "(positive = puts more expensive → downside fear)"
    )
    lines.append("")

    lines.append(f"## 3. Max pain & high-OI strikes  (expiry {near_expiry})")
    lines.append(f"- Max pain: {_fmt(max_pain)}")
    lines.append("- Top call OI strikes (resistance magnets):")
    lines.append(_df_to_md(top_call_oi, ["impliedVolatility"]))
    lines.append("- Top put OI strikes (support magnets):")
    lines.append(_df_to_md(top_put_oi, ["impliedVolatility"]))

    lines.append("## 4. Unusual activity (today's volume > open interest)")
    lines.append(_df_to_md(unusual, ["impliedVolatility", "vol_oi_ratio"]))

    if not deltas.empty:
        lines.append(f"## 5. Day-over-day deltas vs cached snapshot {prev_date}")
        lines.append(_df_to_md(deltas, ["impliedVolatility", "iv_delta"]))
    else:
        lines.append("## 5. Day-over-day deltas")
        lines.append(
            "_(no prior cached snapshot within 10 days — deltas unavailable; "
            "run again tomorrow to start the time series)_\n"
        )

    return "\n".join(lines)
