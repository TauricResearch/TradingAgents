from typing import Annotated
from datetime import datetime
from dateutil.relativedelta import relativedelta
import yfinance as yf
import os
from .stockstats_utils import StockstatsUtils
from .markets import normalize_symbol, is_nifty_50_stock

def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Normalize symbol for yfinance (adds .NS suffix for NSE stocks)
    normalized_symbol = normalize_symbol(symbol, target="yfinance")

    # Create ticker object
    ticker = yf.Ticker(normalized_symbol)

    # Fetch historical data for the specified date range
    data = ticker.history(start=start_date, end=end_date)

    # Check if data is empty
    if data.empty:
        return (
            f"No data found for symbol '{normalized_symbol}' between {start_date} and {end_date}"
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
    header = f"# Stock data for {normalized_symbol} from {start_date} to {end_date}\n"
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
        # Short-term Moving Average
        "close_20_sma": (
            "20 SMA: A short-term trend indicator and Bollinger Band baseline. "
            "Usage: Identify short-term trend direction and mean-reversion levels. "
            "Tips: More responsive than 50 SMA; works well for swing trading setups."
        ),
        "close_5_ema": (
            "5 EMA: An ultra-responsive short-term average. "
            "Usage: Capture very short-term momentum shifts and identify immediate trend direction. "
            "Tips: Highly sensitive to noise; best used as a trigger in conjunction with slower averages."
        ),
        # Trend Strength
        "adx": (
            "ADX: Average Directional Index measures trend strength regardless of direction. "
            "Usage: Values above 25 suggest a strong trend; below 20 suggests ranging/consolidation. "
            "Tips: Combine with +DI/-DI for directional bias; ADX alone doesn't indicate direction."
        ),
        # Mean Reversion
        "cci": (
            "CCI: Commodity Channel Index measures price deviation from its statistical mean. "
            "Usage: Values above +100 signal overbought; below -100 signal oversold. "
            "Tips: Effective for identifying cyclical turns; combine with trend indicators to avoid false reversals."
        ),
        # Stochastic Oscillator
        "kdjk": (
            "Stochastic %K: Compares closing price to the price range over a period. "
            "Usage: Values above 80 suggest overbought; below 20 suggest oversold conditions. "
            "Tips: Complements RSI with a different calculation method; crossovers with %D provide entry signals."
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
        # IMPORTANT: Use curr_date as end_date for backtesting accuracy
        # This ensures we only use data available at the backtest date (point-in-time)
        curr_date_dt = pd.to_datetime(curr_date)

        end_date = curr_date_dt  # Use backtest date, NOT today's date
        start_date = curr_date_dt - pd.DateOffset(years=2)  # Reduced from 15 years for faster fetching
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


def _filter_fundamentals_by_date(data, curr_date):
    """
    Filter fundamentals data to only include reports available on or before curr_date.
    This ensures point-in-time accuracy for backtesting.

    yfinance returns fundamentals with report dates as column headers.
    Financial reports are typically published 30-45 days after quarter end.
    We filter to only include columns (report dates) that are at least 45 days before curr_date.
    """
    import pandas as pd

    if data.empty or curr_date is None:
        return data

    try:
        curr_date_dt = pd.to_datetime(curr_date)
        # Financial reports have SEC deadlines (10-K: 60-90 days, 10-Q: 40-45 days)
        # However, many companies file later and data vendors need processing time
        # Using 60 days as conservative estimate to prevent future data leakage
        publication_delay_days = 60

        # Filter columns (report dates) to only include those available at curr_date
        valid_columns = []
        for col in data.columns:
            try:
                report_date = pd.to_datetime(col)
                # Report would have been published ~60 days after report_date
                estimated_publish_date = report_date + pd.Timedelta(days=publication_delay_days)
                if estimated_publish_date <= curr_date_dt:
                    valid_columns.append(col)
            except:
                # If column can't be parsed as date, keep it (might be a label column)
                valid_columns.append(col)

        if valid_columns:
            return data[valid_columns]
        else:
            return data.iloc[:, :0]  # Return empty dataframe with same index
    except Exception as e:
        print(f"Warning: Could not filter fundamentals by date: {e}")
        return data


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for point-in-time filtering"] = None
):
    """Get balance sheet data from yfinance, filtered by curr_date for backtesting accuracy."""
    try:
        # Normalize symbol for yfinance (adds .NS suffix for NSE stocks)
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_balance_sheet
        else:
            data = ticker_obj.balance_sheet

        if data.empty:
            return f"No balance sheet data found for symbol '{normalized_ticker}'"

        # Filter by curr_date for point-in-time accuracy in backtesting
        data = _filter_fundamentals_by_date(data, curr_date)

        if data.empty:
            return f"No balance sheet data available for {normalized_ticker} as of {curr_date}"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Balance Sheet data for {normalized_ticker} ({freq})\n"
        if curr_date:
            header += f"# Point-in-time data as of: {curr_date}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {normalized_ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for point-in-time filtering"] = None
):
    """Get cash flow data from yfinance, filtered by curr_date for backtesting accuracy."""
    try:
        # Normalize symbol for yfinance (adds .NS suffix for NSE stocks)
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_cashflow
        else:
            data = ticker_obj.cashflow

        if data.empty:
            return f"No cash flow data found for symbol '{normalized_ticker}'"

        # Filter by curr_date for point-in-time accuracy in backtesting
        data = _filter_fundamentals_by_date(data, curr_date)

        if data.empty:
            return f"No cash flow data available for {normalized_ticker} as of {curr_date}"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Cash Flow data for {normalized_ticker} ({freq})\n"
        if curr_date:
            header += f"# Point-in-time data as of: {curr_date}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {normalized_ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for point-in-time filtering"] = None
):
    """Get income statement data from yfinance, filtered by curr_date for backtesting accuracy."""
    try:
        # Normalize symbol for yfinance (adds .NS suffix for NSE stocks)
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        if freq.lower() == "quarterly":
            data = ticker_obj.quarterly_income_stmt
        else:
            data = ticker_obj.income_stmt

        if data.empty:
            return f"No income statement data found for symbol '{normalized_ticker}'"

        # Filter by curr_date for point-in-time accuracy in backtesting
        data = _filter_fundamentals_by_date(data, curr_date)

        if data.empty:
            return f"No income statement data available for {normalized_ticker} as of {curr_date}"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Income Statement data for {normalized_ticker} ({freq})\n"
        if curr_date:
            header += f"# Point-in-time data as of: {curr_date}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {normalized_ticker}: {str(e)}"


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get comprehensive company fundamentals from yfinance (.info)."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)
        info = ticker_obj.info

        if not info or len(info) < 5:
            return f"No fundamentals data found for symbol '{normalized_ticker}'"

        # Select the most useful keys for analysis
        key_groups = {
            "Valuation": ["marketCap", "enterpriseValue", "trailingPE", "forwardPE",
                          "priceToBook", "priceToSalesTrailing12Months", "enterpriseToRevenue",
                          "enterpriseToEbitda"],
            "Profitability": ["profitMargins", "operatingMargins", "grossMargins",
                              "returnOnAssets", "returnOnEquity", "revenueGrowth",
                              "earningsGrowth", "earningsQuarterlyGrowth"],
            "Dividends": ["dividendRate", "dividendYield", "payoutRatio",
                          "fiveYearAvgDividendYield", "trailingAnnualDividendRate"],
            "Financial Health": ["totalCash", "totalDebt", "debtToEquity",
                                 "currentRatio", "quickRatio", "freeCashflow",
                                 "operatingCashflow", "totalRevenue", "ebitda"],
            "Trading": ["currentPrice", "targetHighPrice", "targetLowPrice",
                        "targetMeanPrice", "recommendationKey", "numberOfAnalystOpinions",
                        "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "fiftyDayAverage",
                        "twoHundredDayAverage", "beta", "volume", "averageVolume"],
            "Company Info": ["sector", "industry", "fullTimeEmployees", "country", "city"],
        }

        sections = []
        sections.append(f"# Fundamentals for {normalized_ticker}")
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append(f"# Company: {info.get('longName', info.get('shortName', ticker))}")
        sections.append("")

        for group_name, keys in key_groups.items():
            group_lines = []
            for key in keys:
                val = info.get(key)
                if val is not None:
                    group_lines.append(f"  {key}: {val}")
            if group_lines:
                sections.append(f"## {group_name}")
                sections.extend(group_lines)
                sections.append("")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_analyst_recommendations(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get analyst recommendations summary and recent upgrades/downgrades from yfinance."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Analyst Recommendations for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        # Recommendations summary (buy/sell/hold counts)
        try:
            rec_summary = ticker_obj.recommendations_summary
            if rec_summary is not None and not rec_summary.empty:
                sections.append("## Analyst Consensus")
                csv_string = rec_summary.to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Analyst Consensus\nNo recommendations summary available\n")

        # Recent upgrades/downgrades
        try:
            upgrades = ticker_obj.upgrades_downgrades
            if upgrades is not None and not upgrades.empty:
                # Limit to most recent 15 entries
                recent = upgrades.head(15)
                sections.append("## Recent Upgrades/Downgrades")
                csv_string = recent.to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Recent Upgrades/Downgrades\nNo upgrade/downgrade data available\n")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving analyst recommendations for {ticker}: {str(e)}"


def get_earnings_data(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get earnings dates and historical EPS data from yfinance."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Earnings Data for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        # Earnings dates (upcoming and recent)
        try:
            earnings_dates = ticker_obj.earnings_dates
            if earnings_dates is not None and not earnings_dates.empty:
                sections.append("## Earnings Dates (Upcoming & Recent)")
                # Show up to 8 entries
                csv_string = earnings_dates.head(8).to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Earnings Dates\nNo earnings dates available\n")

        # Earnings history (EPS estimates vs actuals)
        try:
            earnings_hist = ticker_obj.earnings_history
            if earnings_hist is not None and not earnings_hist.empty:
                sections.append("## Earnings History (EPS Estimates vs Actuals)")
                csv_string = earnings_hist.to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Earnings History\nNo earnings history available\n")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving earnings data for {ticker}: {str(e)}"


def get_institutional_holders(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get institutional holders and major holders breakdown from yfinance."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Institutional Holders for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        # Major holders (% breakdown)
        try:
            major = ticker_obj.major_holders
            if major is not None and not major.empty:
                sections.append("## Major Holders Breakdown")
                csv_string = major.to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Major Holders Breakdown\nNo major holders data available\n")

        # Top institutional holders
        try:
            inst = ticker_obj.institutional_holders
            if inst is not None and not inst.empty:
                sections.append("## Top Institutional Holders")
                csv_string = inst.head(10).to_csv(index=False)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Top Institutional Holders\nNo institutional holders data available\n")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving institutional holders for {ticker}: {str(e)}"


def get_yfinance_news(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get aggregated news for a ticker from Yahoo Finance's curated feed."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Yahoo Finance News for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        try:
            news = ticker_obj.news
            if news and len(news) > 0:
                for i, article in enumerate(news[:10]):
                    # yfinance news has nested 'content' structure
                    content = article.get("content", article)
                    title = content.get("title", article.get("title", "No title"))
                    provider = content.get("provider", {})
                    publisher = provider.get("displayName", article.get("publisher", "Unknown")) if isinstance(provider, dict) else "Unknown"
                    publish_time = content.get("pubDate", article.get("providerPublishTime", ""))
                    summary = content.get("summary", "")

                    sections.append(f"## Article {i+1}: {title}")
                    sections.append(f"  Publisher: {publisher}")
                    sections.append(f"  Published: {publish_time}")
                    if summary:
                        sections.append(f"  Summary: {summary[:200]}")
                    sections.append("")
            else:
                sections.append("No news articles available from Yahoo Finance.\n")
        except Exception:
            sections.append("Unable to fetch Yahoo Finance news feed.\n")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving Yahoo Finance news for {ticker}: {str(e)}"


def get_analyst_sentiment(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get analyst sentiment: price targets + recommendation distribution from yfinance."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Analyst Sentiment for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        # Analyst price targets
        try:
            targets = ticker_obj.analyst_price_targets
            if targets is not None:
                sections.append("## Analyst Price Targets")
                if isinstance(targets, dict):
                    for k, v in targets.items():
                        sections.append(f"  {k}: {v}")
                else:
                    sections.append(str(targets))
                sections.append("")
        except Exception:
            sections.append("## Analyst Price Targets\nNo price target data available\n")

        # Recommendations summary for sentiment distribution
        try:
            rec_summary = ticker_obj.recommendations_summary
            if rec_summary is not None and not rec_summary.empty:
                sections.append("## Analyst Rating Distribution")
                csv_string = rec_summary.to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            sections.append("## Analyst Rating Distribution\nNo rating distribution data available\n")

        # Current price vs targets for sentiment gauge
        try:
            info = ticker_obj.info
            current_price = info.get("currentPrice")
            target_mean = info.get("targetMeanPrice")
            if current_price and target_mean:
                upside = ((target_mean - current_price) / current_price) * 100
                sections.append("## Price vs Target Analysis")
                sections.append(f"  Current Price: {current_price}")
                sections.append(f"  Mean Target: {target_mean}")
                sections.append(f"  Implied Upside: {upside:.1f}%")
                sentiment = "BULLISH" if upside > 10 else "BEARISH" if upside < -10 else "NEUTRAL"
                sections.append(f"  Analyst Sentiment: {sentiment}")
                sections.append("")
        except Exception:
            pass

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving analyst sentiment for {ticker}: {str(e)}"


def get_sector_performance(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get sector performance context — how is this stock's sector performing vs the market."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Sector Performance Context for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        info = ticker_obj.info
        sector = info.get("sector", "Unknown")
        industry = info.get("industry", "Unknown")
        sections.append(f"## Stock Sector: {sector}")
        sections.append(f"## Industry: {industry}")
        sections.append("")

        # Get stock's own performance metrics
        beta = info.get("beta")
        fifty_day_avg = info.get("fiftyDayAverage")
        two_hundred_day_avg = info.get("twoHundredDayAverage")
        current_price = info.get("currentPrice")
        fifty_two_high = info.get("fiftyTwoWeekHigh")
        fifty_two_low = info.get("fiftyTwoWeekLow")

        sections.append("## Stock vs Moving Averages")
        if current_price and fifty_day_avg:
            pct_vs_50d = ((current_price - fifty_day_avg) / fifty_day_avg) * 100
            sections.append(f"  Current Price: {current_price}")
            sections.append(f"  50-Day Avg: {fifty_day_avg} ({pct_vs_50d:+.1f}%)")
        if current_price and two_hundred_day_avg:
            pct_vs_200d = ((current_price - two_hundred_day_avg) / two_hundred_day_avg) * 100
            sections.append(f"  200-Day Avg: {two_hundred_day_avg} ({pct_vs_200d:+.1f}%)")
        if current_price and fifty_two_high and fifty_two_low:
            range_pct = ((current_price - fifty_two_low) / (fifty_two_high - fifty_two_low)) * 100 if fifty_two_high != fifty_two_low else 50
            sections.append(f"  52-Week Range: {fifty_two_low} - {fifty_two_high} (currently at {range_pct:.0f}% of range)")
        if beta:
            sections.append(f"  Beta: {beta}")
        sections.append("")

        # Nifty50 index comparison (for Indian stocks)
        if is_nifty_50_stock(ticker):
            try:
                end_date = curr_date or datetime.now().strftime("%Y-%m-%d")
                from dateutil.relativedelta import relativedelta as _rd
                start_date_dt = datetime.strptime(end_date, "%Y-%m-%d") - _rd(days=30)
                start_date = start_date_dt.strftime("%Y-%m-%d")

                nifty = yf.Ticker("^NSEI")
                nifty_hist = nifty.history(start=start_date, end=end_date)
                if not nifty_hist.empty:
                    nifty_return = ((nifty_hist['Close'].iloc[-1] - nifty_hist['Close'].iloc[0]) / nifty_hist['Close'].iloc[0]) * 100
                    sections.append("## Nifty50 Index (30-day)")
                    sections.append(f"  Nifty50 Return: {nifty_return:.1f}%")

                stock_hist = ticker_obj.history(start=start_date, end=end_date)
                if not stock_hist.empty:
                    stock_return = ((stock_hist['Close'].iloc[-1] - stock_hist['Close'].iloc[0]) / stock_hist['Close'].iloc[0]) * 100
                    sections.append(f"  {normalized_ticker} Return: {stock_return:.1f}%")
                    alpha = stock_return - nifty_return
                    sections.append(f"  Alpha vs Nifty: {alpha:+.1f}%")
                sections.append("")
            except Exception:
                sections.append("## Nifty50 Comparison\nUnable to fetch index data\n")

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving sector performance for {ticker}: {str(e)}"


def get_earnings_calendar(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date for reference"] = None,
) -> str:
    """Get upcoming earnings and dividend calendar from yfinance."""
    try:
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)

        sections = [f"# Earnings & Dividend Calendar for {normalized_ticker}"]
        if curr_date:
            sections.append(f"# As of: {curr_date}")
        sections.append("")

        # Calendar data
        try:
            calendar = ticker_obj.calendar
            if calendar is not None:
                if isinstance(calendar, dict):
                    for k, v in calendar.items():
                        sections.append(f"  {k}: {v}")
                else:
                    sections.append(str(calendar))
                sections.append("")
        except Exception:
            sections.append("No calendar data available\n")

        # Earnings dates for more detail
        try:
            earnings_dates = ticker_obj.earnings_dates
            if earnings_dates is not None and not earnings_dates.empty:
                sections.append("## Upcoming & Recent Earnings Dates")
                csv_string = earnings_dates.head(4).to_csv(index=True)
                sections.append(csv_string)
                sections.append("")
        except Exception:
            pass

        # Dividend info
        try:
            info = ticker_obj.info
            div_rate = info.get("dividendRate")
            div_yield = info.get("dividendYield")
            ex_div_date = info.get("exDividendDate")
            if div_rate or div_yield:
                sections.append("## Dividend Information")
                if div_rate:
                    sections.append(f"  Dividend Rate: {div_rate}")
                if div_yield:
                    sections.append(f"  Dividend Yield: {div_yield * 100:.2f}%")
                if ex_div_date:
                    try:
                        from datetime import datetime as _dt
                        ex_date_str = _dt.fromtimestamp(ex_div_date).strftime("%Y-%m-%d")
                        sections.append(f"  Ex-Dividend Date: {ex_date_str}")
                    except Exception:
                        sections.append(f"  Ex-Dividend Date: {ex_div_date}")
                sections.append("")
        except Exception:
            pass

        return "\n".join(sections)

    except Exception as e:
        return f"Error retrieving earnings calendar for {ticker}: {str(e)}"


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"]
):
    """Get insider transactions data from yfinance."""
    try:
        # Normalize symbol for yfinance (adds .NS suffix for NSE stocks)
        normalized_ticker = normalize_symbol(ticker, target="yfinance")
        ticker_obj = yf.Ticker(normalized_ticker)
        data = ticker_obj.insider_transactions

        if data is None or data.empty:
            # Check if this is an NSE stock - insider data may not be available
            if is_nifty_50_stock(ticker):
                return (f"Note: SEC-style insider transaction data is not available for Indian NSE stocks like {normalized_ticker}. "
                        f"For Indian stocks, insider trading disclosures are filed with SEBI and available through NSE/BSE websites.")
            return f"No insider transactions data found for symbol '{normalized_ticker}'"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Insider Transactions data for {normalized_ticker}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {normalized_ticker}: {str(e)}"