"""A-share (China mainland stock market) common utilities.

Provides ticker symbol normalization, exchange detection, trade calendar
lookup, and date helpers used by all akshare-based data fetchers.

Only loaded when the akshare vendor is active — does not add any import
overhead for users who stick with yfinance / alpha_vantage.
"""

from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd

# ── IPv4 workaround for broken IPv6 routes (e.g. macOS Surge proxy) ────
_ipv4_patched = False


def ensure_ipv4():
    """Monkey-patch socket.getaddrinfo to prefer IPv4.

    Called automatically before akshare network requests. Some networks
    (macOS with Surge proxy, certain ISPs) have broken IPv6 routes to
    East Money servers. This resolves ``RemoteDisconnected`` errors.
    """
    global _ipv4_patched
    if _ipv4_patched:
        return
    import socket
    _orig = socket.getaddrinfo

    def _ipv4_first(host, port, family=0, type=0, proto=0, flags=0):
        try:
            results = _orig(host, port, socket.AF_INET, type, proto, flags)
            if results:
                return results
        except socket.gaierror:
            pass
        return _orig(host, port, family, type, proto, flags)

    socket.getaddrinfo = _ipv4_first
    _ipv4_patched = True


# ── Exchange prefix tables ──────────────────────────────────────────────
_SH_PREFIXES = ("600", "601", "603", "605", "688", "689")
_SZ_PREFIXES = ("000", "001", "002", "003", "300", "301")
_BJ_PREFIXES = (
    "430", "431", "832", "833", "834", "835", "836", "837", "838", "839",
    "870", "871", "872", "873", "874", "875", "876", "877", "878", "879",
    "920",
)

_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_PREFIX_RE = re.compile(r"^(SH|SZ|BJ)(\d{6})$", re.IGNORECASE)
_BARE_RE = re.compile(r"^\d{6}$")
_DIGITS_RE = re.compile(r"\d{6}")

# Chinese stock name → ticker code mapping.
# Keys are Chinese names that LLM agents may pass instead of numeric codes.
# Both full names and common short names are included.
_NAME_TO_CODE: dict[str, str] = {
    # --- Blue-chip / Large-cap ---
    "Kweichow Moutai": "600519", "Moutai": "600519",
    "贵州茅台": "600519", "茅台": "600519",
    "Ping An Insurance": "601318", "Ping An": "601318",
    "中国平安": "601318", "平安": "601318",
    "China Merchants Bank": "600036",
    "招商银行": "600036", "招行": "600036",
    "CATL": "300750", "宁德时代": "300750",
    "BYD": "002594", "比亚迪": "002594",
    "Huayou Cobalt": "603799", "华友钴业": "603799", "华友": "603799",
    "LONGi Green Energy": "601012", "隆基绿能": "601012", "隆基": "601012",
    "Wuliangye": "000858", "五粮液": "000858",
    "Haitian Flavouring": "603288", "海天味业": "603288", "海天": "603288",
    "Hengrui Medicine": "600276", "恒瑞医药": "600276", "恒瑞": "600276",
    "Mindray Medical": "300760", "迈瑞医疗": "300760", "迈瑞": "300760",
    "WuXi AppTec": "603259", "药明康德": "603259", "药明": "603259",
    "China Tourism Group": "601888", "中国中免": "601888", "中免": "601888",
    "China Yangtze Power": "600900", "长江电力": "600900",
    # --- Banks ---
    "ICBC": "601398", "工商银行": "601398", "工行": "601398",
    "CCB": "601939", "建设银行": "601939", "建行": "601939",
    "ABC": "601288", "农业银行": "601288", "农行": "601288",
    "Bank of China": "601988", "中国银行": "601988",
    # --- Industrials / Materials ---
    "Sany Heavy": "600031", "三一重工": "600031", "三一": "600031",
    "SMIC": "688981", "中芯国际": "688981", "中芯": "688981",
    "BOE Technology": "000725", "京东方": "000725",
    "Zijin Mining": "601899", "紫金矿业": "601899", "紫金": "601899",
    "China Shenhua": "601088", "中国神华": "601088", "神华": "601088",
    "Baoshan Steel": "600019", "宝钢股份": "600019", "宝钢": "600019",
    # --- Real estate / Consumer ---
    "Vanke": "000002", "万科": "000002",
    "Gree Electric": "000651", "格力电器": "000651", "格力": "000651",
    "Midea Group": "000333", "美的集团": "000333", "美的": "000333",
    "Haier Smart Home": "600690", "海尔智家": "600690", "海尔": "600690",
    "SF Holding": "002352", "顺丰控股": "002352", "顺丰": "002352",
    # --- Financials ---
    "CITIC Securities": "600030", "中信证券": "600030", "中信": "600030",
    "East Money": "300059", "东方财富": "300059",
    # --- New Energy ---
    "Sungrow Power": "300274", "阳光电源": "300274",
    "Tongwei": "600438", "通威股份": "600438", "通威": "600438",
    "Tianqi Lithium": "002466", "天齐锂业": "002466", "天齐": "002466",
    "Ganfeng Lithium": "002460", "赣锋锂业": "002460", "赣锋": "002460",
    "Qinghai Salt Lake": "000792", "盐湖股份": "000792", "盐湖": "000792",
    "Northern Rare Earth": "600111", "北方稀土": "600111",
    "China Rare Earth": "000831", "中国稀土": "000831",
    # --- Auto ---
    "Great Wall Motor": "601633", "长城汽车": "601633",
    "Seres Group": "601127", "赛力斯": "601127",
    # --- HK-listed (reference only, not A-share) ---
    "Xiaomi": "01810", "小米集团": "01810",
    "Tencent": "00700", "腾讯控股": "00700",
}


def infer_exchange(code: str) -> str:
    """Infer the exchange from a 6-digit A-share code."""
    if code.startswith(_SH_PREFIXES):
        return "SH"
    if code.startswith(_SZ_PREFIXES):
        return "SZ"
    if code.startswith(_BJ_PREFIXES):
        return "BJ"
    raise ValueError(
        f"Cannot infer exchange for A-share code '{code}'. "
        "Expected a 6-digit Shanghai (600xxx/601xxx/603xxx/605xxx/688xxx), "
        "Shenzhen (000xxx/001xxx/002xxx/003xxx/300xxx/301xxx), or "
        "Beijing (430xxx/83x/920xxx) code."
    )


def normalize_ashare_symbol(symbol: str) -> str:
    """Normalize user input to ``600519.SH`` / ``000001.SZ`` / ``430047.BJ``.

    Accepts any of: ``600519``, ``SH600519``, ``600519.SH``, ``sh600519``,
    or a Chinese/English stock name like ``Huayou Cobalt``, ``Moutai``, ``CATL``.
    """
    s = symbol.strip().upper().replace(" ", "")
    if not s:
        raise ValueError("Ticker symbol cannot be empty.")

    # 1. Try standard formats first
    m = _SUFFIX_RE.fullmatch(s)
    if m:
        return f"{m.group(1)}.{m.group(2)}"

    m = _PREFIX_RE.fullmatch(s)
    if m:
        return f"{m.group(2)}.{m.group(1)}"

    if _BARE_RE.fullmatch(s):
        return f"{s}.{infer_exchange(s)}"

    # 2. Try Chinese name lookup (case-insensitive for original input)
    s_orig = symbol.strip()
    if s_orig in _NAME_TO_CODE:
        code = _NAME_TO_CODE[s_orig]
        return f"{code}.{infer_exchange(code)}"
    # Also try the uppercased version for edge cases
    if s in _NAME_TO_CODE:
        code = _NAME_TO_CODE[s]
        return f"{code}.{infer_exchange(code)}"

    # 3. Try to extract a 6-digit code from mixed input (e.g., "stock 603799")
    m = _DIGITS_RE.search(symbol)
    if m:
        code = m.group()
        return f"{code}.{infer_exchange(code)}"

    raise ValueError(
        f"Unsupported A-share symbol format: '{symbol}'. "
        "Use a 6-digit code such as 600519, SH600519, 600519.SH, "
        "or a Chinese/English stock name like 'Huayou Cobalt', 'Moutai', 'CATL'."
    )


def to_plain_code(symbol: str) -> str:
    """Return the bare 6-digit code (no exchange suffix)."""
    return normalize_ashare_symbol(symbol).split(".", 1)[0]


def to_exchange_prefix(symbol: str) -> str:
    """Return the ``SH600519`` / ``SZ000001`` format."""
    code, exchange = normalize_ashare_symbol(symbol).split(".", 1)
    return f"{exchange}{code}"


def format_date_for_api(date_str: str) -> str:
    """Convert ``YYYY-MM-DD`` to ``YYYYMMDD`` (akshare expects this)."""
    return pd.Timestamp(date_str).strftime("%Y%m%d")


# ── Trade calendar (Sina source, cached per process) ────────────────────

@lru_cache(maxsize=1)
def _get_trade_dates_set() -> set[pd.Timestamp]:
    """Fetch the full A-share trade calendar from Sina and cache it."""
    ensure_ipv4()
    import akshare as ak

    df = ak.tool_trade_date_hist_sina()
    dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    return set(dates.dt.normalize())


def is_trade_date(date_str: str) -> bool:
    """Check whether *date_str* is an A-share trading day."""
    target = pd.Timestamp(date_str).normalize()
    return target in _get_trade_dates_set()


def get_previous_trade_date(date_str: str) -> str:
    """Return the most recent trading day on or before *date_str*."""
    target = pd.Timestamp(date_str).normalize()
    # Generate candidate range and check against calendar
    calendar = sorted(_get_trade_dates_set())
    eligible = [d for d in calendar if d <= target]
    if not eligible:
        raise ValueError(f"No A-share trading date found on or before {date_str}.")
    return eligible[-1].strftime("%Y-%m-%d")


def is_ashare_symbol(symbol: str) -> bool:
    """Return True if *symbol* looks like an A-share ticker."""
    s = symbol.strip().upper().replace(" ", "")
    if _SUFFIX_RE.fullmatch(s) or _PREFIX_RE.fullmatch(s):
        return True
    if _BARE_RE.fullmatch(s):
        try:
            infer_exchange(s)
            return True
        except ValueError:
            return False
    return False
