"""Tencent Finance realtime valuation (qt.gtimg.cn) -- no IP ban, zero key.

Provides PE(TTM)/PB/market-cap/turnover/price-limits that mootdx does not
carry.  Independent of EastMoney's rate-limit plane, so it stays usable when
EastMoney bans an IP.  See a-stock-data SKILL.md §1.2.

Field index map (verified against a-stock-data V3.4.1, correcting the common
"Tencent field 43 = PB" error -- 43 is amplitude%, 46 is PB):
  3=price, 32=change%, 38=turnover%, 39=PE_TTM, 44=market_cap(yi),
  45=float_market_cap(yi), 46=PB, 47=limit_up, 48=limit_down.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import requests

from .china_data import ChinaDataUnavailableError
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol


def _tencent_prefix(ticker: str) -> str:
    canonical = normalize_ticker_symbol(ticker)
    if canonical.endswith((".SS", ".SH")):
        return "sh"
    if canonical.endswith(".BJ"):
        return "bj"
    return "sz"


def _parse_tencent_line(line: str) -> dict[str, Any] | None:
    """Parse one ``v_sh600519="..."`` line into a valuation row."""
    if "=" not in line or '"' not in line:
        return None
    key = line.split("=")[0].split("_")[-1]
    vals = line.split('"')[1].split("~")
    if len(vals) < 53:
        return None
    code = key[2:]
    return {
        "Code": code,
        "Name": vals[1],
        "Price": float(vals[3]) if vals[3] else 0,
        "Change %": round(float(vals[32]) if vals[32] else 0, 2),
        "Turnover %": round(float(vals[38]) if vals[38] else 0, 2),
        "PE TTM": float(vals[39]) if vals[39] else 0,
        "Market Cap (yi)": float(vals[44]) if vals[44] else 0,
        "Float Cap (yi)": float(vals[45]) if vals[45] else 0,
        "PB": float(vals[46]) if vals[46] else 0,
        "Limit Up": float(vals[47]) if vals[47] else 0,
        "Limit Down": float(vals[48]) if vals[48] else 0,
    }


def get_a_share_valuation(ticker: str) -> str:
    """A-share realtime valuation (PE/PB/market-cap/turnover/limits) via Tencent.

    Tencent's qt.gtimg.cn endpoint is not rate-limited and never IP-bans,
    making it an independent source for the valuation fields mootdx does not
    carry.  Values are realtime (not TTM-reported fundamentals).
    """
    canonical = normalize_ticker_symbol(ticker)
    if not is_a_share_ticker(canonical):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    code = to_akshare_symbol(canonical)
    url = f"https://qt.gtimg.cn/q={_tencent_prefix(ticker)}{code}"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    except requests.RequestException as exc:
        raise ChinaDataUnavailableError(f"Tencent quote request failed for {ticker}: {type(exc).__name__}") from exc
    text = resp.content.decode("gbk", errors="ignore")
    row: dict[str, Any] | None = None
    for line in text.strip().split(";"):
        parsed = _parse_tencent_line(line)
        if parsed and parsed["Code"] == code:
            row = parsed
            break
    if not row:
        raise ChinaDataUnavailableError(f"Tencent returned no quote for {code}.")
    _capture_vendor_raw({"raw": text, "row": row}, metadata={"provider": "tencent", "dataset": "valuation", "ticker": ticker})
    return "\n".join(
        [
            f"# China A-share realtime valuation for {canonical}",
            "# Source: tencent",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# Note: Tencent qt.gtimg.cn; no IP ban; PE/PB/market-cap are realtime (not TTM-reported fundamentals).",
            "",
            pd.DataFrame([row]).to_csv(index=False),
        ]
    )


def _capture_vendor_raw(data: Any, *, metadata: dict[str, Any]) -> None:
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(data, metadata=dict(metadata))
