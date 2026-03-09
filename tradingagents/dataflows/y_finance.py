from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging
import yfinance as yf
import os
from .stockstats_utils import StockstatsUtils

_logger = logging.getLogger(__name__)

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Try Alpaca first (10k calls/min, 7yr history)
    try:
        from .alpaca_data import alpaca_available, get_bars_csv
        if alpaca_available():
            result = get_bars_csv(symbol, start_date, end_date)
            if not result.startswith("Error"):
                return result
            _logger.info("Alpaca bars failed, falling back to yfinance for %s", symbol)
    except Exception as e:
        _logger.debug("Alpaca unavailable: %s", e)

    # Fallback: yfinance
    ticker = yf.Ticker(symbol.upper())
    data = ticker.history(start=start_date, end=end_date)

    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv()
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
    from .config import get_config
    import pandas as pd
    from stockstats import wrap
    import os
    
    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"
    
    if not online:
        # Local data path
        try:
            data = pd.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
            df = wrap(data)
        except FileNotFoundError:
            raise Exception("Stockstats fail: Yahoo Finance data not fetched yet!")
    else:
        # Online data fetching with caching
        today_date = pd.Timestamp.today()
        curr_date_dt = pd.to_datetime(curr_date)
        
        end_date = today_date
        start_date = today_date - pd.DateOffset(years=15)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")
        
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        data_file = os.path.join(
            config["data_cache_dir"],
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )
        
        if os.path.exists(data_file):
            data = pd.read_csv(data_file)
            data["Date"] = pd.to_datetime(data["Date"])
        else:
            data = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            data = data.reset_index()
            data.to_csv(data_file, index=False)
        
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
        info = ticker_obj.info

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
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get balance sheet data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_balance_sheet
        else:
            data = ticker_obj.balance_sheet
            
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
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get cash flow data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_cashflow
        else:
            data = ticker_obj.cashflow
            
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
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None
):
    """Get income statement data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        
        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_income_stmt
        else:
            data = ticker_obj.income_stmt
            
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
        data = ticker_obj.insider_transactions
        
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


# --- Macro data functions (used by interface.py routing) ---
# These are thin wrappers that delegate to yfinance directly.
# The actual @tool versions live in agents/utils/macro_data_tools.py.

import json as _json


def _safe_get_yf(info, key, default=None):
    val = info.get(key)
    return default if val is None else val


def _fmt_num(val):
    if val is None:
        return None
    if abs(val) >= 1e12:
        return f"${val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


def _period_return(ticker_obj, months):
    import pandas as pd
    try:
        end_dt = pd.Timestamp.today()
        start_dt = end_dt - pd.DateOffset(months=months)
        data = ticker_obj.history(start=start_dt.strftime("%Y-%m-%d"), end=end_dt.strftime("%Y-%m-%d"))
        if data.empty or len(data) < 2:
            return None
        return ((data["Close"].iloc[-1] / data["Close"].iloc[0]) - 1) * 100
    except Exception:
        return None


def get_company_profile(ticker, curr_date=None):
    """Get company profile via yfinance (plain function for interface routing)."""
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        if not info or not info.get("longName"):
            return _json.dumps({"error": f"No data for {ticker}", "ticker": ticker})
        mc = _safe_get_yf(info, "marketCap")
        cat = "large_cap" if mc and mc >= 10e9 else "mid_cap" if mc and mc >= 2e9 else "small_cap" if mc and mc >= 300e6 else "micro_cap" if mc else "unknown"
        profile = {
            "company_name": _safe_get_yf(info, "longName", "Unknown"),
            "ticker": ticker.upper(),
            "sector": _safe_get_yf(info, "sector", "Unknown"),
            "industry": _safe_get_yf(info, "industry", "Unknown"),
            "description": _safe_get_yf(info, "longBusinessSummary", ""),
            "market_cap": mc,
            "market_cap_formatted": _fmt_num(mc),
            "market_cap_category": cat,
            "current_price": _safe_get_yf(info, "currentPrice") or _safe_get_yf(info, "regularMarketPrice"),
        }
        return _json.dumps(profile, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e), "ticker": ticker})


_SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Discretionary": "XLY",
    "Consumer Defensive": "XLP",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Basic Materials": "XLB",
    "Materials": "XLB",
    "Communication Services": "XLC",
}

_SECTOR_ETFS = {
    "SPY": "S&P 500",
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
    "XLV": "Health Care", "XLI": "Industrials", "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples", "XLU": "Utilities", "XLRE": "Real Estate",
    "XLB": "Materials", "XLC": "Communication Services",
}


def get_macro_indicators(curr_date=None):
    """Get macro indicators. VIX/TNX from yfinance (indices), sector ETFs from Alpaca."""
    results = {}

    # VIX and TNX are indices — yfinance only (Alpaca doesn't serve index tickers)
    try:
        vix = yf.Ticker("^VIX")
        vd = vix.history(period="5d")
        if not vd.empty:
            results["vix_level"] = round(vd["Close"].iloc[-1], 2)
    except Exception:
        pass
    try:
        tnx = yf.Ticker("^TNX")
        td = tnx.history(period="5d")
        if not td.empty:
            results["ten_year_yield"] = round(td["Close"].iloc[-1], 3)
    except Exception:
        pass

    # Sector ETF performance — Alpaca first (10k calls/min), yfinance fallback
    try:
        from .alpaca_data import alpaca_available, get_sector_etf_performance
        if alpaca_available():
            perf = get_sector_etf_performance(list(_SECTOR_ETFS.keys()))
            if perf:
                sector_performance = {}
                for sym, data in perf.items():
                    sector_performance[sym] = {
                        "name": _SECTOR_ETFS.get(sym, sym),
                        "return_1m": data.get("return_1m"),
                        "return_3m": data.get("return_3m"),
                        "price": data.get("price"),
                    }
                results["sector_performance"] = sector_performance
    except Exception as e:
        _logger.debug("Alpaca sector ETFs failed: %s", e)

    # Fallback: yfinance for sector ETFs
    if "sector_performance" not in results:
        sector_performance = {}
        for sym, name in _SECTOR_ETFS.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="3mo")
                if hist.empty or len(hist) < 5:
                    continue
                close = hist["Close"]
                current = float(close.iloc[-1])
                ret_1m = round((current - float(close.iloc[-22])) / float(close.iloc[-22]) * 100, 2) if len(close) >= 22 else None
                ret_3m = round((current - float(close.iloc[-63])) / float(close.iloc[-63]) * 100, 2) if len(close) >= 63 else None
                sector_performance[sym] = {"name": name, "return_1m": ret_1m, "return_3m": ret_3m, "price": current}
            except Exception:
                pass
        if sector_performance:
            results["sector_performance"] = sector_performance

    return _json.dumps(results, default=str)


def get_sector_rotation(ticker, curr_date=None):
    """Get sector rotation data with relative performance vs SPY."""
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info or {}
        sector = _safe_get_yf(info, "sector", "Unknown")
        sector_etf = _SECTOR_ETF_MAP.get(sector)

        result = {"ticker": ticker.upper(), "sector": sector, "sector_etf": sector_etf}

        if not sector_etf:
            return _json.dumps(result, default=str)

        # Get sector ETF + SPY performance for relative strength
        etfs_to_fetch = [sector_etf, "SPY"]
        perf = {}

        try:
            from .alpaca_data import alpaca_available, get_sector_etf_performance
            if alpaca_available():
                perf = get_sector_etf_performance(etfs_to_fetch)
        except Exception:
            pass

        # Fallback: yfinance
        if not perf:
            for sym in etfs_to_fetch:
                try:
                    hist = yf.Ticker(sym).history(period="3mo")
                    if hist.empty or len(hist) < 5:
                        continue
                    close = hist["Close"]
                    current = float(close.iloc[-1])
                    ret_1m = round((current - float(close.iloc[-22])) / float(close.iloc[-22]) * 100, 2) if len(close) >= 22 else None
                    ret_3m = round((current - float(close.iloc[-63])) / float(close.iloc[-63]) * 100, 2) if len(close) >= 63 else None
                    perf[sym] = {"return_1m": ret_1m, "return_3m": ret_3m, "price": current}
                except Exception:
                    pass

        # Compute relative strength vs SPY
        spy_data = perf.get("SPY", {})
        etf_data = perf.get(sector_etf, {})
        spy_1m = spy_data.get("return_1m")
        spy_3m = spy_data.get("return_3m")
        etf_1m = etf_data.get("return_1m")
        etf_3m = etf_data.get("return_3m")

        if etf_1m is not None and spy_1m is not None:
            result["stock_sector_vs_spy_1m"] = round(etf_1m - spy_1m, 2)
        if etf_3m is not None and spy_3m is not None:
            result["stock_sector_vs_spy_3m"] = round(etf_3m - spy_3m, 2)

        # Rank sector among all sector ETFs (from macro_indicators cache or fresh)
        try:
            macro_raw = get_macro_indicators()
            macro = _json.loads(macro_raw) if isinstance(macro_raw, str) else macro_raw
            sector_perf = macro.get("sector_performance", {})
            # Rank by 1M return (exclude SPY from ranking)
            ranked = sorted(
                [(s, d.get("return_1m", -999)) for s, d in sector_perf.items() if s != "SPY"],
                key=lambda x: x[1], reverse=True,
            )
            for i, (sym, _) in enumerate(ranked, 1):
                if sym == sector_etf:
                    result["stock_sector_rank"] = i
                    result["total_sectors"] = len(ranked)
                    break
        except Exception:
            pass

        return _json.dumps(result, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e)})


def get_institutional_flow(ticker):
    """Get institutional flow data via yfinance including 13F holders and insider transactions."""
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info or {}

        # Base metrics
        result = {
            "ticker": ticker.upper(),
            "average_volume": _safe_get_yf(info, "averageVolume"),
            "average_volume_10d": _safe_get_yf(info, "averageVolume10days"),
            "float_shares": _safe_get_yf(info, "floatShares"),
            "shares_short": _safe_get_yf(info, "sharesShort"),
            "shares_short_prior": _safe_get_yf(info, "sharesShortPriorMonth"),
            "short_ratio": _safe_get_yf(info, "shortRatio"),
            "held_percent_institutions": _safe_get_yf(info, "heldPercentInstitutions"),
            "held_percent_insiders": _safe_get_yf(info, "heldPercentInsiders"),
        }

        # Volume ratio (10d vs avg)
        vol_10d = _safe_get_yf(info, "averageVolume10days")
        vol_avg = _safe_get_yf(info, "averageVolume")
        if vol_10d and vol_avg and vol_avg > 0:
            result["volume_ratio"] = round(vol_10d / vol_avg, 2)

        # Short % of float
        float_shares = _safe_get_yf(info, "floatShares")
        shares_short = _safe_get_yf(info, "sharesShort")
        if float_shares and shares_short and float_shares > 0:
            result["short_pct_of_float"] = round(shares_short / float_shares * 100, 2)

        # Short interest trend (current vs prior month)
        prior = _safe_get_yf(info, "sharesShortPriorMonth")
        if shares_short is not None and prior is not None and prior > 0:
            pct_change = (shares_short - prior) / prior * 100
            result["short_interest_change_pct"] = round(pct_change, 1)
            if pct_change > 5:
                result["short_interest_trend"] = "rising"
            elif pct_change < -5:
                result["short_interest_trend"] = "falling"
            else:
                result["short_interest_trend"] = "stable"

        # Float turnover (5d volume / float)
        if vol_10d and float_shares and float_shares > 0:
            result["float_turnover_5d_pct"] = round(vol_10d * 5 / float_shares * 100, 2)

        # Top institutional holders (13F data)
        try:
            holders = t.institutional_holders
            if holders is not None and not holders.empty:
                top = holders.head(10).to_dict("records")
                result["top_institutional_holders"] = [
                    {
                        "holder": str(r.get("Holder", "")),
                        "shares": int(r["Shares"]) if r.get("Shares") else None,
                        "pct_out": round(float(r["% Out"]) * 100, 2) if r.get("% Out") else None,
                        "value": float(r["Value"]) if r.get("Value") else None,
                    }
                    for r in top
                ]
                result["top_holders_count"] = len(top)
        except Exception:
            pass

        # Insider transactions
        try:
            insiders = t.insider_transactions
            if insiders is not None and not insiders.empty:
                recent = insiders.head(10).to_dict("records")
                buys = sum(1 for r in recent if "Purchase" in str(r.get("Text", "")))
                sells = sum(1 for r in recent if "Sale" in str(r.get("Text", "")))
                result["insider_buys_recent"] = buys
                result["insider_sells_recent"] = sells
                if buys > sells:
                    result["insider_transaction_signal"] = "buying"
                elif sells > buys:
                    result["insider_transaction_signal"] = "selling"
                else:
                    result["insider_transaction_signal"] = "none"
        except Exception:
            pass

        return _json.dumps(result, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e)})


def get_earnings_estimates(ticker):
    """Get earnings estimates via yfinance (plain function for interface routing)."""
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        return _json.dumps({
            "ticker": ticker.upper(),
            "trailing_eps": _safe_get_yf(info, "trailingEps"),
            "forward_eps": _safe_get_yf(info, "forwardEps"),
            "current_price": _safe_get_yf(info, "currentPrice") or _safe_get_yf(info, "regularMarketPrice"),
        }, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e)})


def get_valuation_peers(ticker):
    """Get valuation peer data via yfinance (plain function for interface routing)."""
    try:
        t = yf.Ticker(ticker.upper())
        info = t.info
        return _json.dumps({
            "ticker": ticker.upper(),
            "trailing_pe": _safe_get_yf(info, "trailingPE"),
            "forward_pe": _safe_get_yf(info, "forwardPE"),
            "peg_ratio": _safe_get_yf(info, "pegRatio"),
            "price_to_book": _safe_get_yf(info, "priceToBook"),
            "ev_to_ebitda": _safe_get_yf(info, "enterpriseToEbitda"),
        }, default=str)
    except Exception as e:
        return _json.dumps({"error": str(e)})