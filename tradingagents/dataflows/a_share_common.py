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

    Accepts any of: ``600519``, ``SH600519``, ``600519.SH``, ``sh600519``.
    """
    s = symbol.strip().upper().replace(" ", "")
    if not s:
        raise ValueError("Ticker symbol cannot be empty.")

    m = _SUFFIX_RE.fullmatch(s)
    if m:
        return f"{m.group(1)}.{m.group(2)}"

    m = _PREFIX_RE.fullmatch(s)
    if m:
        return f"{m.group(2)}.{m.group(1)}"

    if _BARE_RE.fullmatch(s):
        return f"{s}.{infer_exchange(s)}"

    raise ValueError(
        f"Unsupported A-share symbol format: '{symbol}'. "
        "Use a 6-digit code such as 600519, SH600519, or 600519.SH."
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
