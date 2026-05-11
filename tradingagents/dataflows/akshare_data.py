"""AKShare data vendor for A-shares (Shanghai/Shenzhen) and Hong Kong stocks."""

import re
from typing import Optional, Tuple


def _is_chinese_name(name: str) -> bool:
    """Check if input contains Chinese characters."""
    return bool(re.search(r'[一-鿿]', name))


def _normalize_akshare_ticker(ticker: str) -> Tuple[str, str]:
    """Normalize a ticker to AKShare code and exchange.

    Args:
        ticker: Raw ticker, e.g. '600000', '600000.SS', '0700.HK'

    Returns:
        (code, exchange) where code is the plain digits and exchange
        is 'shanghai', 'shenzhen', or 'hongkong'
    """
    ticker = ticker.strip().upper()

    # Hong Kong: .HK suffix or 5-digit code starting with 0
    if ticker.endswith('.HK'):
        code = ticker.replace('.HK', '').lstrip('0') or '0'
        return (code.zfill(5), 'hongkong')

    # Strip exchange suffix for A-shares
    if ticker.endswith('.SS'):
        code = ticker.replace('.SS', '')
        return (code, 'shanghai')
    if ticker.endswith('.SZ'):
        code = ticker.replace('.SZ', '')
        return (code, 'shenzhen')

    # Plain numeric code — detect exchange from first digit
    if ticker.isdigit():
        # 5-digit code starting with 0 — Hong Kong (check before general '0' rule)
        if len(ticker) == 5 and ticker.startswith('0'):
            return (ticker, 'hongkong')
        if ticker.startswith('6'):
            return (ticker, 'shanghai')
        if ticker.startswith(('0', '3', '8')):
            return (ticker, 'shenzhen')

    return (ticker, 'unknown')


# Cache for name-to-code mappings, populated lazily
_name_cache: Optional[dict] = None
_hk_name_cache: Optional[dict] = None


def _ensure_name_cache():
    """Populate A-share name→code cache from AKShare."""
    global _name_cache
    if _name_cache is None:
        try:
            df = ak.stock_info_a_code_name()
            _name_cache = dict(zip(df['name'], df['code']))
        except Exception:
            _name_cache = {}


def _ensure_hk_name_cache():
    """Populate HK name→code cache from AKShare."""
    global _hk_name_cache
    if _hk_name_cache is None:
        try:
            df = ak.stock_hk_spot_em()
            _hk_name_cache = dict(zip(df['名称'], df['代码']))
        except Exception:
            _hk_name_cache = {}


def resolve_ticker_name(name: str) -> str:
    """Resolve a ticker name to exchange-suffixed format.

    Handles:
    - Chinese stock names: '贵州茅台' → '600519.SS', '腾讯控股' → '00700.HK'
    - Plain A-share codes: '600000' → '600000.SS'
    - Already suffixed codes: '600000.SS' → '600000.SS' (pass-through)

    Args:
        name: Stock name or ticker code

    Returns:
        Exchange-suffixed ticker string
    """
    name = name.strip()

    # Already suffixed — pass through
    if name.upper().endswith(('.SS', '.SZ', '.HK')):
        return name

    # Chinese name — look up
    if _is_chinese_name(name):
        _ensure_name_cache()
        if _name_cache and name in _name_cache:
            code = _name_cache[name]
            # Determine exchange from first digit
            if code.startswith('6'):
                return f"{code}.SS"
            else:
                return f"{code}.SZ"
        # Fuzzy match: try substring matching (e.g. '茅台' matches '贵州茅台')
        if _name_cache:
            matches = [n for n in _name_cache if name in n]
            if len(matches) == 1:
                code = _name_cache[matches[0]]
                if code.startswith('6'):
                    return f"{code}.SS"
                else:
                    return f"{code}.SZ"
        _ensure_hk_name_cache()
        if _hk_name_cache and name in _hk_name_cache:
            code = _hk_name_cache[name].zfill(5)
            return f"{code}.HK"
        if _hk_name_cache:
            matches = [n for n in _hk_name_cache if name in n]
            if len(matches) == 1:
                code = _hk_name_cache[matches[0]].zfill(5)
                return f"{code}.HK"
        raise ValueError(f"Cannot resolve Chinese name: {name!r}")

    # Plain numeric code — auto-suffix
    code, exchange = _normalize_akshare_ticker(name)
    suffix = {'shanghai': '.SS', 'shenzhen': '.SZ', 'hongkong': '.HK'}
    return f"{code}{suffix[exchange]}"


# --- AKShare data tool functions ---

import os

# AKShare fetches data from Chinese sources (East Money, Sina, etc.) which
# can be blocked by HTTP proxies. Clear proxy settings before importing.
for _env_var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
                 "ALL_PROXY", "all_proxy"):
    os.environ.pop(_env_var, None)

import pandas as pd
from datetime import datetime

import akshare as ak


_COL_MAP = {
    '日期': 'Date', '开盘': 'Open', '收盘': 'Close',
    '最高': 'High', '最低': 'Low', '成交量': 'Volume',
}


def _resolve_any_ticker(symbol: str) -> str:
    """Resolve a ticker that may be a Chinese name, plain code, or suffixed code.

    Returns the AKShare-compatible code string, or the original symbol
    if it cannot be resolved (caller handles the error downstream).
    """
    if _is_chinese_name(symbol):
        try:
            return resolve_ticker_name(symbol)
        except ValueError:
            return symbol
    # Try normalization to detect invalid tickers early — if it fails,
    # pass the symbol through so the downstream AKShare call returns
    # a clean "No data found" error instead of a ValueError crash.
    try:
        _normalize_akshare_ticker(symbol)
    except ValueError:
        return symbol
    return symbol


def get_akshare_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Get OHLCV stock data from AKShare.

    Args:
        symbol: Ticker symbol (e.g. '600000', '600000.SS', '0700.HK', '贵州茅台')
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV-formatted string with header
    """
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    symbol = _resolve_any_ticker(symbol)
    code, exchange = _normalize_akshare_ticker(symbol)

    try:
        if exchange == 'hongkong':
            df = ak.stock_hk_hist(
                symbol=code,
                period="daily",
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
            )
            existing = {k: v for k, v in _COL_MAP.items() if k in df.columns}
            df = df.rename(columns=existing)
            output_cols = [c for c in existing.values() if c in df.columns]
            df = df[output_cols]
        else:
            # Use Sina (not East Money) to avoid proxy/VPN blocks
            df = ak.stock_zh_a_daily(
                symbol=_sina_stock_code(code, exchange),
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', ''),
                adjust="qfq",
            )
            col_sina = {
                'date': 'Date', 'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume',
            }
            existing = {k: v for k, v in col_sina.items() if k in df.columns}
            df = df.rename(columns=existing)
            output_cols = [c for c in existing.values() if c in df.columns]
            df = df[output_cols]
    except Exception as e:
        return f"Error retrieving stock data for {symbol}: {str(e)}"

    if df is None or df.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    for col in ['Open', 'High', 'Low', 'Close']:
        if col in df.columns:
            df[col] = df[col].round(2)

    csv_string = df.to_csv(index=False)
    header = (
        f"# Stock data for {code} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def get_akshare_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Get company fundamentals from AKShare (TongHuaShun financial abstract)."""
    ticker = _resolve_any_ticker(ticker)
    code, exchange = _normalize_akshare_ticker(ticker)

    if exchange == 'hongkong':
        return f"No fundamentals data available for HK stock '{code}' via AKShare"

    # Try THS financial abstract first (works reliably), fall back to East Money
    try:
        df = ak.stock_financial_abstract_ths(symbol=code)
    except Exception:
        df = None

    if df is not None and not df.empty:
        # Get the most recent row (latest fiscal period)
        latest = df.iloc[-1]
        lines = [f"{col}: {latest[col]}" for col in df.columns
                 if col not in ('报告期', '净利润同比增长率') and latest[col] and str(latest[col]) != 'False']
    else:
        # Fallback: try East Money individual info
        try:
            df = ak.stock_individual_info_em(symbol=code)
        except Exception as e:
            return f"Error retrieving fundamentals for {ticker}: {str(e)}"

        if df is None or df.empty:
            return f"No fundamentals data found for symbol '{ticker}'"

        lines = []
        for _, row in df.iterrows():
            item = str(row.iloc[0]) if len(row) > 0 else ""
            value = str(row.iloc[1]) if len(row) > 1 else ""
            lines.append(f"{item}: {value}")

    header = (
        f"# Company Fundamentals for {ticker.upper()}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + "\n".join(lines)
    return header + "\n".join(lines)


def _financial_csv(ticker: str, freq: str, label: str, df) -> str:
    """Format a financial statement DataFrame as CSV with header."""
    if df is None or df.empty:
        return f"No {label.lower()} data found for symbol '{ticker}'"
    csv_string = df.to_csv(index=False)
    header = (
        f"# {label} data for {ticker.upper()} ({freq})\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def _hk_unsupported(ticker: str, data_type: str) -> str:
    """Return a message for unsupported HK stock data types."""
    code, _ = _normalize_akshare_ticker(ticker)
    return f"No {data_type} data available for HK stock '{code}' via AKShare"


def _sina_stock_code(code: str, exchange: str) -> str:
    """Convert to Sina-format stock code: sh688222 or sz000001."""
    prefix = 'sh' if exchange == 'shanghai' else 'sz'
    return f'{prefix}{code}'


def get_akshare_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    ticker = _resolve_any_ticker(ticker)
    code, exchange = _normalize_akshare_ticker(ticker)
    if exchange == 'hongkong':
        return _hk_unsupported(ticker, "balance sheet")
    try:
        df = ak.stock_financial_report_sina(
            stock=_sina_stock_code(code, exchange), symbol='资产负债表'
        )
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"
    return _financial_csv(ticker, freq, "Balance Sheet", df)


def get_akshare_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    ticker = _resolve_any_ticker(ticker)
    code, exchange = _normalize_akshare_ticker(ticker)
    if exchange == 'hongkong':
        return _hk_unsupported(ticker, "income statement")
    try:
        df = ak.stock_financial_report_sina(
            stock=_sina_stock_code(code, exchange), symbol='利润表'
        )
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"
    return _financial_csv(ticker, freq, "Income Statement", df)


def get_akshare_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    ticker = _resolve_any_ticker(ticker)
    code, exchange = _normalize_akshare_ticker(ticker)
    if exchange == 'hongkong':
        return _hk_unsupported(ticker, "cash flow")
    try:
        df = ak.stock_financial_report_sina(
            stock=_sina_stock_code(code, exchange), symbol='现金流量表'
        )
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"
    return _financial_csv(ticker, freq, "Cash Flow", df)


def get_akshare_news(ticker: str, start_date: str, end_date: str) -> str:
    """Get stock-specific news from AKShare (East Money)."""
    ticker = _resolve_any_ticker(ticker)
    code, exchange = _normalize_akshare_ticker(ticker)

    try:
        df = ak.stock_news_em(symbol=code)
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"

    if df is None or df.empty:
        return f"No news found for {ticker}"

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    news_lines = []
    for _, row in df.iterrows():
        title = row.get("title", str(row.iloc[0]) if len(row) > 0 else "")
        pub_time = row.get("发布时间", str(row.iloc[3]) if len(row) > 3 else "")
        content = row.get("content", str(row.iloc[2]) if len(row) > 2 else "")

        if pub_time:
            try:
                pub_str = str(pub_time)[:10]
                pub_dt = datetime.strptime(pub_str, "%Y-%m-%d")
                if not (start_dt <= pub_dt <= end_dt):
                    continue
            except (ValueError, TypeError):
                pass

        news_lines.append(f"### {title}")
        if content:
            news_lines.append(str(content)[:500])
        news_lines.append("")

    if not news_lines:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n" + "\n".join(news_lines)


def get_akshare_global_news(curr_date: str, look_back_days: int = 7, limit: int = 10) -> str:
    """Get macro/economic news relevant to Chinese markets."""
    try:
        df = ak.news_economic_baidu()
    except Exception as e:
        return f"Error fetching global news: {str(e)}"

    if df is None or df.empty:
        return f"No global news found for {curr_date}"

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    from dateutil.relativedelta import relativedelta
    start_dt = curr_dt - relativedelta(days=look_back_days)

    news_lines = []
    count = 0
    for _, row in df.iterrows():
        if count >= limit:
            break
        title = row.get("title", str(row.iloc[0]) if len(row) > 0 else "")
        date_str = str(row.get("date", str(row.iloc[2]) if len(row) > 2 else ""))[:10]
        content = row.get("content", str(row.iloc[1]) if len(row) > 1 else "")

        try:
            pub_dt = datetime.strptime(date_str, "%Y-%m-%d")
            if pub_dt < start_dt or pub_dt > curr_dt:
                continue
        except (ValueError, TypeError):
            pass

        news_lines.append(f"### {title}")
        if content:
            news_lines.append(str(content)[:500])
        news_lines.append("")
        count += 1

    if not news_lines:
        return f"No global news found for {curr_date}"

    start_str = start_dt.strftime("%Y-%m-%d")
    return f"## China Market News, from {start_str} to {curr_date}:\n\n" + "\n".join(news_lines)


def get_akshare_indicators(symbol: str, indicator: str, curr_date: str, look_back_days: int) -> str:
    """Get technical indicator values using AKShare OHLCV + stockstats."""
    from stockstats import wrap
    from dateutil.relativedelta import relativedelta

    symbol = _resolve_any_ticker(symbol)
    code, exchange = _normalize_akshare_ticker(symbol)

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days + 365)

    start_str = start_dt.strftime("%Y%m%d")
    end_str = curr_dt.strftime("%Y%m%d")

    try:
        if exchange == 'hongkong':
            df = ak.stock_hk_hist(symbol=code, period="daily",
                                  start_date=start_str, end_date=end_str, adjust="qfq")
        else:
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start_str, end_date=end_str, adjust="qfq")
    except Exception as e:
        return f"Error fetching data for indicator '{indicator}': {str(e)}"

    if df is None or df.empty:
        return ""

    existing = {k: v for k, v in _COL_MAP.items() if k in df.columns}
    df = df.rename(columns=existing)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    for c in ['Open', 'High', 'Low', 'Close']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['Close'])
    df = df[df['Date'] <= pd.to_datetime(curr_date)]

    wrapped = wrap(df)
    wrapped["Date"] = wrapped["Date"].dt.strftime("%Y-%m-%d")
    wrapped[indicator]

    result_dt = curr_dt
    lines = []
    while result_dt >= curr_dt - relativedelta(days=look_back_days):
        date_str = result_dt.strftime("%Y-%m-%d")
        matching = wrapped[wrapped["Date"].str.startswith(date_str)]
        if not matching.empty:
            val = matching[indicator].values[0]
            lines.append(f"{date_str}: {val if not pd.isna(val) else 'N/A: Not a trading day (weekend or holiday)'}")
        else:
            lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")
        result_dt -= relativedelta(days=1)

    result_str = f"## {indicator} values from {(curr_dt - relativedelta(days=look_back_days)).strftime('%Y-%m-%d')} to {curr_date}:\n\n"
    result_str += "\n".join(lines)
    result_str += f"\n\n{indicator}: Technical indicator calculated from AKShare OHLCV data."
    return result_str


def get_akshare_insider_transactions(ticker: str) -> str:
    """Insider transactions are not available via AKShare."""
    return f"No insider transactions data available for '{ticker}' via AKShare"
