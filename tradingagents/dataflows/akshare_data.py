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

    raise ValueError(f"Cannot normalize ticker: {ticker!r}")


# Cache for name-to-code mappings, populated lazily
_name_cache: Optional[dict] = None
_hk_name_cache: Optional[dict] = None


def _ensure_name_cache():
    """Populate A-share name→code cache from AKShare."""
    global _name_cache
    if _name_cache is None:
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            _name_cache = dict(zip(df['name'], df['code']))
        except Exception:
            _name_cache = {}


def _ensure_hk_name_cache():
    """Populate HK name→code cache from AKShare."""
    global _hk_name_cache
    if _hk_name_cache is None:
        try:
            import akshare as ak
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
        _ensure_hk_name_cache()
        if _hk_name_cache and name in _hk_name_cache:
            code = _hk_name_cache[name].zfill(5)
            return f"{code}.HK"
        raise ValueError(f"Cannot resolve Chinese name: {name!r}")

    # Plain numeric code — auto-suffix
    code, exchange = _normalize_akshare_ticker(name)
    suffix = {'shanghai': '.SS', 'shenzhen': '.SZ', 'hongkong': '.HK'}
    return f"{code}{suffix[exchange]}"
