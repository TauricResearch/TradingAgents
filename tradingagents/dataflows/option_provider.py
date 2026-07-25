"""Sina ETF option quotes (hq.sinajs.cn) -- T-quote + Greeks + IV, zero key.

Covers 50ETF/300ETF/STAR50ETF/500ETF options.  Sina returns GBK-encoded
comma-separated values behind a ``var hq_str_XXX="..."`` shell.  The Greeks
parser skips 3 empty fields (``raw[1:4]``) or Delta/IV misalign.  See
a-stock-data SKILL.md §9.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import requests

from .china_data import ChinaDataUnavailableError

_SINA_OPT_HDR = {"User-Agent": "Mozilla/5.0", "Referer": "https://stock.finance.sina.com.cn/"}
_SINA_OPT_LIST_URL = "https://hq.sinajs.cn/list="


def _sina_opt_list(param: str) -> list[str]:
    """Fetch one Sina option quote line; return the comma-separated values."""
    resp = requests.get(f"{_SINA_OPT_LIST_URL}{param}", headers=_SINA_OPT_HDR, timeout=10)
    resp.encoding = "gbk"
    text = resp.text
    return text.split('"')[1].split(",") if '"' in text else []


def _opt_f(x: str) -> Any:
    try:
        return float(x)
    except (TypeError, ValueError):
        return x


def get_a_share_option_tquote(option_code: str) -> str:
    """ETF option T-quote (T型报价) via Sina.

    Returns bid/ask/last/open-interest/strike/limit-up-down for one option
    contract code (e.g. ``10000001``).
    """
    v = _sina_opt_list(f"CON_OP_{option_code}")
    if len(v) < 43:
        raise ChinaDataUnavailableError(f"Sina returned no T-quote for option {option_code}.")
    row = {
        "Name": v[37],
        "Last": _opt_f(v[2]),
        "Bid": _opt_f(v[1]),
        "Ask": _opt_f(v[3]),
        "Bid Vol": _opt_f(v[0]),
        "Ask Vol": _opt_f(v[4]),
        "Open Interest": _opt_f(v[5]),
        "Pct %": _opt_f(v[6]),
        "Strike": _opt_f(v[7]),
        "Prev Close": _opt_f(v[8]),
        "Open": _opt_f(v[9]),
        "Limit Up": _opt_f(v[10]),
        "Limit Down": _opt_f(v[11]),
        "High": _opt_f(v[39]),
        "Low": _opt_f(v[40]),
        "Volume": _opt_f(v[41]),
        "Amount": _opt_f(v[42]),
    }
    _capture_vendor_raw({"raw": v}, metadata={"provider": "sina", "dataset": "option_tquote", "ticker": option_code})
    return "\n".join(
        [
            f"# China ETF option T-quote for {option_code}",
            "# Source: sina",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# Note: Sina hq.sinajs.cn; GBK-encoded; Referer required.",
            "",
            pd.DataFrame([row]).to_csv(index=False),
        ]
    )


def get_a_share_option_greeks(option_code: str) -> str:
    """ETF option Greeks + implied volatility (希腊字母+IV) via Sina.

    Returns delta/gamma/theta/vega/IV (exchange-computed, no local BSM).
    IV is a decimal (0.1735 = 17.35%).
    """
    raw = _sina_opt_list(f"CON_SO_{option_code}")
    if len(raw) < 16:
        raise ChinaDataUnavailableError(f"Sina returned no Greeks for option {option_code}.")
    v = [raw[0]] + raw[4:]  # raw[1:4] are 3 empty strings; skip or fields misalign
    row = {
        "Name": v[0],
        "Volume": _opt_f(v[1]),
        "Delta": _opt_f(v[2]),
        "Gamma": _opt_f(v[3]),
        "Theta": _opt_f(v[4]),
        "Vega": _opt_f(v[5]),
        "IV": _opt_f(v[6]),
        "High": _opt_f(v[7]),
        "Low": _opt_f(v[8]),
        "Strike": _opt_f(v[10]),
        "Last": _opt_f(v[11]),
        "Theory": _opt_f(v[12]),
    }
    _capture_vendor_raw({"raw": raw}, metadata={"provider": "sina", "dataset": "option_greeks", "ticker": option_code})
    return "\n".join(
        [
            f"# China ETF option Greeks for {option_code}",
            "# Source: sina",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# Note: Sina hq.sinajs.cn; IV is a decimal (0.1735 = 17.35%); exchange-computed, no local BSM.",
            "",
            pd.DataFrame([row]).to_csv(index=False),
        ]
    )


def _capture_vendor_raw(data: Any, *, metadata: dict[str, Any]) -> None:
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(data, metadata=dict(metadata))
