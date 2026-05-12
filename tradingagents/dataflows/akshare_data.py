"""AKShare data source module for A-share and HK stock markets.

This module implements the 9 standard data functions required by the
pluggable data-source architecture, using AKShare (free, no API key) as backend.
Function signatures and output formats are fully compatible with tushare_data.py.
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated

import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None

try:
    from stockstats import wrap as stockstats_wrap
except ImportError:
    stockstats_wrap = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper / Utility Functions
# ---------------------------------------------------------------------------


def normalize_akshare_code(symbol: str) -> str:
    """将各种格式转换为 akshare 的 6 位纯数字格式（A股）。

    Examples:
        '600000.SH' -> '600000'
        'SH600000'  -> '600000'
        '600000.SS' -> '600000'
        '600000.SZ' -> '600000'
        'SZ000001'  -> '000001'
        '600000'    -> '600000'
    """
    symbol = symbol.strip().upper()

    # Remove known exchange suffixes: .SH, .SS, .SZ
    for suffix in (".SH", ".SS", ".SZ"):
        if symbol.endswith(suffix):
            return symbol[: -len(suffix)]

    # Handle prefix formats: SH600000, SS600000, SZ000001
    for prefix in ("SH", "SS", "SZ"):
        if symbol.startswith(prefix) and symbol[len(prefix):].isdigit():
            return symbol[len(prefix):]

    # Already pure digits
    if symbol.isdigit():
        return symbol

    # Fallback: return as-is
    return symbol


def _is_hk_ticker(symbol: str) -> bool:
    """检测是否为港股代码。"""
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        return True
    if s.startswith("HK") and s[2:].isdigit():
        return True
    return False


def _normalize_hk_code(symbol: str) -> str:
    """将港股代码转换为 akshare 要求的格式（5位数字，前补零）。

    Examples:
        '0700.HK'  -> '00700'
        '00700.HK' -> '00700'
        'HK0700'   -> '00700'
        'HK00700'  -> '00700'
    """
    s = symbol.strip().upper()
    if s.endswith(".HK"):
        code = s[:-3]
    elif s.startswith("HK"):
        code = s[2:]
    else:
        code = s
    # Pad to 5 digits
    return code.zfill(5)


def _is_fund_or_etf(code: str) -> bool:
    """判断是否为 ETF/基金代码。

    A股ETF/基金代码规则：
    - 上海: 5xxxxx (包含 51xxxx, 56xxxx, 58xxxx 等)
    - 深圳: 15xxxx, 16xxxx
    """
    # Strip any suffix first
    pure_code = code.split(".")[0] if "." in code else code
    # Remove known prefixes
    for prefix in ("SH", "SS", "SZ", "HK"):
        if pure_code.upper().startswith(prefix) and pure_code[len(prefix):].isdigit():
            pure_code = pure_code[len(prefix):]
            break

    if not pure_code.isdigit() or len(pure_code) != 6:
        return False

    if pure_code.startswith("5"):
        return True
    if pure_code.startswith("15") or pure_code.startswith("16"):
        return True
    return False


def _convert_date_input(date_str: str) -> str:
    """Convert date from YYYY-MM-DD to YYYYMMDD for akshare input."""
    return date_str.replace("-", "")


# ---------------------------------------------------------------------------
# Tencent Finance Fallback Helper
# ---------------------------------------------------------------------------


def _tencent_fallback_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Fallback: 使用 akshare 腾讯财经接口获取 A 股/ETF 数据。

    当东方财富历史数据接口(push2his)不可用时，自动降级到腾讯财经数据源。
    无需代理，国内直连。

    注意：腾讯财经接口不支持复权，且只有成交额(amount)没有成交量(volume)。
    """
    if ak is None:
        return ""

    # 转换代码格式: 600000.SH -> sh600000, 000001.SZ -> sz000001
    code = normalize_akshare_code(symbol)
    if code.startswith(('6', '9', '5')):
        tx_symbol = f"sh{code}"
    else:
        tx_symbol = f"sz{code}"

    # 日期格式转换: YYYY-MM-DD -> YYYYMMDD
    tx_start = start_date.replace("-", "")
    tx_end = end_date.replace("-", "")

    try:
        logger.info(f"Falling back to Tencent Finance for {symbol} (as {tx_symbol})")
        df = ak.stock_zh_a_hist_tx(symbol=tx_symbol, start_date=tx_start, end_date=tx_end)

        if df is None or df.empty:
            logger.warning(f"Tencent Finance returned no data for {tx_symbol}")
            return ""

        # 腾讯返回列: date, open, close, high, low, amount
        # 转换为项目标准格式
        lines = []
        lines.append(f"# Stock data for {symbol} from {start_date} to {end_date}")
        lines.append(f"# Total records: {len(df)}")
        lines.append(f"# Data source: Tencent Finance (fallback)")
        lines.append(f"# Note: No adjust data available from this source")
        lines.append(f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        lines.append("Date,Open,High,Low,Close,Adj Close,Volume")

        for _, row in df.iterrows():
            # 腾讯没有 volume，用 amount 代替（标注在注释中）
            # Adj Close = Close（无复权数据）
            date_str = str(row['date'])
            # 确保日期格式为 YYYY-MM-DD
            if len(date_str) == 8:  # YYYYMMDD
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

            lines.append(
                f"{date_str},{row['open']:.4f},{row['high']:.4f},"
                f"{row['low']:.4f},{row['close']:.4f},{row['close']:.4f},"
                f"{int(row['amount'])}"
            )

        logger.info(f"Tencent Finance fallback successful for {tx_symbol}: {len(df)} records")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Tencent Finance fallback also failed for {tx_symbol}: {type(e).__name__}: {e}")
        return ""


# ---------------------------------------------------------------------------
# Indicator descriptions (same as tushare_data.py)
# ---------------------------------------------------------------------------

INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages."
    ),
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
        "Tips: Can be volatile; complement with additional filters."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with upper and lower bands to spot breakouts or reversals."
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
        "Tips: It's a reactive measure; use as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes."
    ),
}


# ---------------------------------------------------------------------------
# 9 Core Data Functions
# ---------------------------------------------------------------------------


def get_akshare_stock(
    symbol: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """Get OHLCV stock price data from AKShare with adjusted close price."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        ak_start = _convert_date_input(start_date)
        ak_end = _convert_date_input(end_date)

        df = None
        ak_failed = False

        if _is_hk_ticker(symbol):
            # 港股 (no Tencent Finance fallback for HK via this path)
            hk_code = _normalize_hk_code(symbol)
            logger.info(f"Fetching HK stock data for {hk_code}")
            df = ak.stock_hk_hist(
                symbol=hk_code,
                period="daily",
                start_date=ak_start,
                end_date=ak_end,
                adjust="qfq",
            )
        elif _is_fund_or_etf(symbol):
            # ETF/基金
            code = normalize_akshare_code(symbol)
            logger.info(f"Detected ETF/fund code {code}, using fund_etf_hist_em API")
            try:
                df = ak.fund_etf_hist_em(
                    symbol=code,
                    period="daily",
                    start_date=ak_start,
                    end_date=ak_end,
                    adjust="qfq",
                )
            except Exception as e:
                logger.warning(f"akshare fund_etf_hist_em failed for {symbol}: {type(e).__name__}: {e}")
                ak_failed = True
        else:
            # A股
            code = normalize_akshare_code(symbol)
            logger.info(f"Fetching A-share stock data for {code}")
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=ak_start,
                    end_date=ak_end,
                    adjust="qfq",
                )
            except Exception as e:
                logger.warning(f"akshare stock_zh_a_hist failed for {symbol}: {type(e).__name__}: {e}")
                ak_failed = True

        # 如果 akshare 调用失败或返回空数据，降级到腾讯财经
        if ak_failed or df is None or df.empty:
            if not _is_hk_ticker(symbol):
                logger.warning(f"akshare returned no data for {symbol}, trying Tencent Finance fallback")
                fallback_result = _tencent_fallback_stock(symbol, start_date, end_date)
                if fallback_result:
                    return fallback_result
            return (f"No stock data found for symbol '{symbol}' between {start_date} and {end_date}. "
                    f"Both akshare (eastmoney) and Tencent Finance failed.")

        # Map Chinese column names to English
        col_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
        }
        df = df.rename(columns=col_map)

        # Ensure required columns exist (akshare may return different column names)
        # Try alternate English column names from HK data
        alt_col_map = {
            "Date": "date",
            "Open": "open",
            "Close": "close",
            "High": "high",
            "Low": "low",
            "Volume": "volume",
        }
        df = df.rename(columns=alt_col_map)

        # Validate required columns
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            return f"Error: Missing columns {missing} in data for {symbol}"

        # Sort by date ascending
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Adj Close = Close in qfq (forward-adjusted) mode
        df["adj_close"] = df["close"]

        # Format date
        df["date_fmt"] = df["date"].dt.strftime("%Y-%m-%d")

        # Round price columns
        for col in ["open", "high", "low", "close", "adj_close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype(int)

        # Build CSV output (same format as tushare_data.py)
        code_display = normalize_akshare_code(symbol) if not _is_hk_ticker(symbol) else _normalize_hk_code(symbol)
        header = f"# Stock data for {code_display} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
        for _, row in df.iterrows():
            lines.append(
                f"{row['date_fmt']},{row['open']:.2f},{row['high']:.2f},"
                f"{row['low']:.2f},{row['close']:.2f},{row['adj_close']:.2f},"
                f"{row['volume']}"
            )

        return header + "\n".join(lines) + "\n"

    except Exception as e:
        # 顶层异常兜底：尝试腾讯财经 fallback
        if not _is_hk_ticker(symbol):
            logger.warning(f"akshare top-level exception for {symbol}: {type(e).__name__}: {e}, trying Tencent Finance")
            fallback_result = _tencent_fallback_stock(symbol, start_date, end_date)
            if fallback_result:
                return fallback_result
        return f"Error retrieving stock data for {symbol}: {str(e)}"


def get_akshare_indicators(
    symbol: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Number of days to look back"],
) -> str:
    """Get technical indicator values computed from AKShare daily data."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    supported_indicators = list(INDICATOR_DESCRIPTIONS.keys())
    if indicator not in supported_indicators:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Please choose from: {supported_indicators}"
        )

    if stockstats_wrap is None:
        return (
            "Error: stockstats is not installed. "
            "Please install it with: pip install stockstats"
        )

    try:
        # Calculate date range with extra buffer for indicator warm-up
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        buffer_days = look_back_days + 300
        start_date_dt = curr_date_dt - timedelta(days=buffer_days)
        ak_start = start_date_dt.strftime("%Y%m%d")
        ak_end = curr_date_dt.strftime("%Y%m%d")
        tx_start = start_date_dt.strftime("%Y%m%d")
        tx_end = curr_date_dt.strftime("%Y%m%d")

        df = None
        ak_failed = False

        if _is_hk_ticker(symbol):
            hk_code = _normalize_hk_code(symbol)
            df = ak.stock_hk_hist(
                symbol=hk_code, period="daily",
                start_date=ak_start, end_date=ak_end, adjust="qfq",
            )
        elif _is_fund_or_etf(symbol):
            code = normalize_akshare_code(symbol)
            try:
                df = ak.fund_etf_hist_em(
                    symbol=code, period="daily",
                    start_date=ak_start, end_date=ak_end, adjust="qfq",
                )
            except Exception as e:
                logger.warning(f"akshare fund_etf_hist_em failed for {symbol} (indicators): {type(e).__name__}: {e}")
                ak_failed = True
        else:
            code = normalize_akshare_code(symbol)
            try:
                df = ak.stock_zh_a_hist(
                    symbol=code, period="daily",
                    start_date=ak_start, end_date=ak_end, adjust="qfq",
                )
            except Exception as e:
                logger.warning(f"akshare stock_zh_a_hist failed for {symbol} (indicators): {type(e).__name__}: {e}")
                ak_failed = True

        # 腾讯财经 fallback for indicators data
        if (ak_failed or df is None or df.empty) and not _is_hk_ticker(symbol):
            tx_code = normalize_akshare_code(symbol)
            tx_symbol = f"sh{tx_code}" if tx_code.startswith(('6', '9', '5')) else f"sz{tx_code}"
            logger.warning(f"akshare returned no data for {symbol} (indicators), trying Tencent Finance fallback")
            try:
                logger.info(f"Falling back to Tencent Finance for indicators: {tx_symbol}")
                tx_df = ak.stock_zh_a_hist_tx(symbol=tx_symbol, start_date=tx_start, end_date=tx_end)
                if tx_df is not None and not tx_df.empty:
                    # 腾讯返回列: date, open, close, high, low, amount
                    # amount -> volume（对技术指标计算够用）
                    df = pd.DataFrame({
                        "date": tx_df["date"],
                        "open": tx_df["open"],
                        "high": tx_df["high"],
                        "low": tx_df["low"],
                        "close": tx_df["close"],
                        "volume": tx_df["amount"],
                    })
                    logger.info(f"Tencent Finance fallback successful for indicators {tx_symbol}: {len(df)} records")
                else:
                    logger.warning(f"Tencent Finance returned no data for indicators {tx_symbol}")
            except Exception as tx_e:
                logger.warning(f"Tencent Finance fallback also failed for indicators {tx_symbol}: {type(tx_e).__name__}: {tx_e}")

        if df is None or df.empty:
            return f"No stock data found for symbol '{symbol}' to compute indicators"

        # Map columns
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
        }
        alt_col_map = {
            "Date": "date", "Open": "open", "Close": "close",
            "High": "high", "Low": "low", "Volume": "volume",
        }
        df = df.rename(columns=col_map).rename(columns=alt_col_map)

        # Sort ascending by date
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)

        # Build DataFrame for stockstats
        stock_df = pd.DataFrame({
            "date": df["date"].dt.strftime("%Y-%m-%d"),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce"),
        })
        stock_df = stock_df.dropna(subset=["close"])

        # Wrap with stockstats and calculate indicator
        ss_df = stockstats_wrap(stock_df)
        ss_df[indicator]  # Trigger calculation

        # Build date -> value mapping
        indicator_map = {}
        for _, row in ss_df.iterrows():
            date_str = row["date"]
            val = row[indicator]
            if pd.isna(val):
                indicator_map[date_str] = "N/A"
            else:
                indicator_map[date_str] = f"{val:.2f}"

        # Generate output for the look_back_days range
        display_start_dt = curr_date_dt - timedelta(days=look_back_days)
        lines = []
        current_dt = display_start_dt
        while current_dt <= curr_date_dt:
            date_str = current_dt.strftime("%Y-%m-%d")
            if date_str in indicator_map:
                lines.append(f"{date_str}: {indicator_map[date_str]}")
            else:
                lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")
            current_dt += timedelta(days=1)

        result = (
            f"## {indicator} values from {display_start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + "\n".join(lines)
            + "\n\n"
            + INDICATOR_DESCRIPTIONS.get(indicator, "No description available.")
        )
        return result

    except Exception as e:
        return f"Error retrieving indicators for {symbol}: {str(e)}"


def get_akshare_fundamentals(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get company fundamentals from AKShare (PE, PB, market cap, etc.)."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        if _is_hk_ticker(ticker):
            return f"Fundamentals for HK stocks are not yet supported via AKShare: {ticker}"

        code = normalize_akshare_code(ticker)

        # Get company basic info
        info_df = None
        try:
            info_df = ak.stock_individual_info_em(symbol=code)
        except Exception as e:
            logger.debug(f"Failed to get stock_individual_info_em for {code}: {e}")

        # Get realtime quote for PE/PB/market cap
        quote_df = None
        try:
            quote_df = ak.stock_zh_a_spot_em()
            if quote_df is not None and not quote_df.empty:
                quote_df = quote_df[quote_df["代码"] == code]
        except Exception as e:
            logger.debug(f"Failed to get realtime quote for {code}: {e}")

        if (info_df is None or info_df.empty) and (quote_df is None or quote_df.empty):
            return f"No fundamentals data found for symbol '{ticker}'"

        # Build output
        header = f"# Company Fundamentals for {code}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        fields = []

        # Parse info_df (it's a two-column DataFrame: item, value)
        if info_df is not None and not info_df.empty:
            info_dict = {}
            for _, row in info_df.iterrows():
                key = str(row.iloc[0]) if len(row) >= 2 else ""
                val = row.iloc[1] if len(row) >= 2 else ""
                info_dict[key] = val

            fields.append(("Name", info_dict.get("股票简称", info_dict.get("名称"))))
            fields.append(("Full Name", info_dict.get("公司名称")))
            fields.append(("Industry", info_dict.get("行业")))
            fields.append(("List Date", info_dict.get("上市时间")))
            fields.append(("Total Share", info_dict.get("总股本")))
            fields.append(("Float Share", info_dict.get("流通股")))

        # Parse realtime quote
        if quote_df is not None and not quote_df.empty:
            q = quote_df.iloc[0]
            col_map = {
                "最新价": "Close Price",
                "换手率": "Turnover Rate",
                "市盈率-动态": "PE Ratio (TTM)",
                "市净率": "PB Ratio",
                "总市值": "Total Market Cap",
                "流通市值": "Float Market Cap",
                "60日涨跌幅": "60D Change (%)",
                "年初至今涨跌幅": "YTD Change (%)",
            }
            for cn_col, en_label in col_map.items():
                if cn_col in q.index:
                    fields.append((en_label, q[cn_col]))

        lines = []
        for label, value in fields:
            if value is not None and str(value) != "" and str(value) != "nan":
                lines.append(f"{label}: {value}")

        if not lines:
            return f"No fundamentals data found for symbol '{ticker}'"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_akshare_balance_sheet(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet data from AKShare."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        if _is_hk_ticker(ticker):
            return f"Balance sheet for HK stocks is not yet supported via AKShare: {ticker}"

        code = normalize_akshare_code(ticker)
        logger.info(f"Fetching balance sheet for {code}")

        df = ak.stock_balance_sheet_by_report_em(symbol=code)

        if df is None or df.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Filter by curr_date if provided
        if curr_date and "REPORT_DATE" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce")
            df = df[df["REPORT_DATE"] <= ref_date]
        elif curr_date and "报告日期" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["报告日期"] = pd.to_datetime(df["报告日期"], errors="coerce")
            df = df[df["报告日期"] <= ref_date]

        if df.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Take the most recent 4 periods
        num_periods = 4
        df = df.head(num_periods)

        # Transpose: rows become indicators, columns become report periods
        # Identify the date column
        date_col = None
        for candidate in ["REPORT_DATE", "报告日期"]:
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col:
            col_names = df[date_col].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d") if pd.notna(x) else str(x)
            ).tolist()
            df = df.drop(columns=[date_col], errors="ignore")
        else:
            col_names = [f"Period_{i}" for i in range(len(df))]

        # Remove non-financial metadata columns
        skip_cols = ["SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
                     "ORG_CODE", "ORG_TYPE", "REPORT_TYPE", "REPORT_DATE_NAME",
                     "SECURITY_TYPE_CODE", "NOTICE_DATE", "UPDATE_DATE",
                     "股票代码", "股票简称"]
        df = df.drop(columns=[c for c in skip_cols if c in df.columns], errors="ignore")

        result_df = df.T
        result_df.columns = col_names

        # Remove rows where all values are NaN
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Balance Sheet data for {code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_akshare_cashflow(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow statement data from AKShare."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        if _is_hk_ticker(ticker):
            return f"Cash flow for HK stocks is not yet supported via AKShare: {ticker}"

        code = normalize_akshare_code(ticker)
        logger.info(f"Fetching cash flow for {code}")

        df = ak.stock_cash_flow_sheet_by_report_em(symbol=code)

        if df is None or df.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        # Filter by curr_date if provided
        if curr_date and "REPORT_DATE" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce")
            df = df[df["REPORT_DATE"] <= ref_date]
        elif curr_date and "报告日期" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["报告日期"] = pd.to_datetime(df["报告日期"], errors="coerce")
            df = df[df["报告日期"] <= ref_date]

        if df.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        # Take the most recent 4 periods
        num_periods = 4
        df = df.head(num_periods)

        # Identify the date column
        date_col = None
        for candidate in ["REPORT_DATE", "报告日期"]:
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col:
            col_names = df[date_col].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d") if pd.notna(x) else str(x)
            ).tolist()
            df = df.drop(columns=[date_col], errors="ignore")
        else:
            col_names = [f"Period_{i}" for i in range(len(df))]

        # Remove non-financial metadata columns
        skip_cols = ["SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
                     "ORG_CODE", "ORG_TYPE", "REPORT_TYPE", "REPORT_DATE_NAME",
                     "SECURITY_TYPE_CODE", "NOTICE_DATE", "UPDATE_DATE",
                     "股票代码", "股票简称"]
        df = df.drop(columns=[c for c in skip_cols if c in df.columns], errors="ignore")

        result_df = df.T
        result_df.columns = col_names

        # Remove rows where all values are NaN
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Cash Flow data for {code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_akshare_income_statement(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from AKShare."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        if _is_hk_ticker(ticker):
            return f"Income statement for HK stocks is not yet supported via AKShare: {ticker}"

        code = normalize_akshare_code(ticker)
        logger.info(f"Fetching income statement for {code}")

        df = ak.stock_profit_sheet_by_report_em(symbol=code)

        if df is None or df.empty:
            return f"No income statement data found for symbol '{ticker}'"

        # Filter by curr_date if provided
        if curr_date and "REPORT_DATE" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce")
            df = df[df["REPORT_DATE"] <= ref_date]
        elif curr_date and "报告日期" in df.columns:
            ref_date = pd.to_datetime(curr_date)
            df["报告日期"] = pd.to_datetime(df["报告日期"], errors="coerce")
            df = df[df["报告日期"] <= ref_date]

        if df.empty:
            return f"No income statement data found for symbol '{ticker}'"

        # Take the most recent 4 periods
        num_periods = 4
        df = df.head(num_periods)

        # Identify the date column
        date_col = None
        for candidate in ["REPORT_DATE", "报告日期"]:
            if candidate in df.columns:
                date_col = candidate
                break

        if date_col:
            col_names = df[date_col].apply(
                lambda x: pd.to_datetime(x).strftime("%Y-%m-%d") if pd.notna(x) else str(x)
            ).tolist()
            df = df.drop(columns=[date_col], errors="ignore")
        else:
            col_names = [f"Period_{i}" for i in range(len(df))]

        # Remove non-financial metadata columns
        skip_cols = ["SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR",
                     "ORG_CODE", "ORG_TYPE", "REPORT_TYPE", "REPORT_DATE_NAME",
                     "SECURITY_TYPE_CODE", "NOTICE_DATE", "UPDATE_DATE",
                     "股票代码", "股票简称"]
        df = df.drop(columns=[c for c in skip_cols if c in df.columns], errors="ignore")

        result_df = df.T
        result_df.columns = col_names

        # Remove rows where all values are NaN
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Income Statement data for {code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_akshare_insider_transactions(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
) -> str:
    """Get insider (executive) trading records from AKShare."""
    if ak is None:
        return "Error: akshare is not installed. Please install it with: pip install akshare"

    try:
        if _is_hk_ticker(ticker):
            return f"Insider transactions for HK stocks are not yet supported via AKShare: {ticker}"

        code = normalize_akshare_code(ticker)
        logger.info(f"Fetching insider transactions for {code}")

        try:
            df = ak.stock_hold_management_detail_em(symbol=code)
        except Exception as e:
            logger.warning(f"stock_hold_management_detail_em not available for {code}: {e}")
            return (
                f"Insider transactions data is not available for '{ticker}'. "
                f"The AKShare interface may have changed or the data is unavailable."
            )

        if df is None or df.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        header = f"# Insider Transactions data for {code}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        # Detect column names (akshare may return Chinese columns)
        # Common columns: 变动日期, 变动人, 变动股数, 变动方向, 变动均价, 变动原因
        date_col = None
        for candidate in ["变动日期", "公告日期", "END_DATE", "ann_date"]:
            if candidate in df.columns:
                date_col = candidate
                break

        holder_col = None
        for candidate in ["变动人", "董监高姓名", "HOLDER_NAME"]:
            if candidate in df.columns:
                holder_col = candidate
                break

        vol_col = None
        for candidate in ["变动股数", "变动数量", "CHANGE_SHARES"]:
            if candidate in df.columns:
                vol_col = candidate
                break

        type_col = None
        for candidate in ["变动方向", "变动类型", "CHANGE_TYPE"]:
            if candidate in df.columns:
                type_col = candidate
                break

        price_col = None
        for candidate in ["变动均价", "成交均价", "AVERAGE_PRICE"]:
            if candidate in df.columns:
                price_col = candidate
                break

        reason_col = None
        for candidate in ["变动原因", "变动事由", "CHANGE_REASON"]:
            if candidate in df.columns:
                reason_col = candidate
                break

        lines = ["Date,Holder Name,Change Volume,Change Type,Price,Change Reason"]
        for _, row in df.iterrows():
            date_val = str(row.get(date_col, "")) if date_col else ""
            holder = str(row.get(holder_col, "")) if holder_col else ""
            vol = str(row.get(vol_col, "")) if vol_col else ""
            change_type = str(row.get(type_col, "")) if type_col else ""
            price = str(row.get(price_col, "")) if price_col else ""
            reason = str(row.get(reason_col, "")) if reason_col else ""
            lines.append(f"{date_val},{holder},{vol},{change_type},{price},{reason}")

        return header + "\n".join(lines) + "\n"

    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def get_akshare_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """Get news for a specific ticker from the news service."""
    from .news_service import get_news_service_news
    return get_news_service_news(ticker, start_date, end_date)


def get_akshare_global_news(
    curr_date: Annotated[str, "Current date in YYYY-MM-DD format"],
    look_back_days: int = None,
    limit: int = None,
) -> str:
    """Get global market news from the news service."""
    from .news_service import get_news_service_global_news
    return get_news_service_global_news(curr_date, look_back_days, limit)
