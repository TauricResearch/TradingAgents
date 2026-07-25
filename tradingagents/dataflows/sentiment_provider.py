"""A-share market sentiment (hot lists + concept hits) -- THS + EastMoney, zero key.

- THS hot list (dq.10jqka.com.cn): market-wide popularity ranking with concept tags.
- EastMoney hot concept (emappdata.eastmoney.com): which hot concepts a stock currently hits.

Independent of EastMoney's datacenter rate-limit plane.  See a-stock-data SKILL.md §10.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import requests

from .china_data import ChinaDataUnavailableError
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol

_THS_HOT_URL = "https://dq.10jqka.com.cn/fuyao/hot_list_data/out/hot_list/v1/stock"
_EM_HOT_CONCEPT_URL = "https://emappdata.eastmoney.com/stockrank/getHotStockRankList"
_EM_HOT_BODY = {"appId": "appId01", "globalId": "786e4c21-70dc-435a-93bb-38"}


def get_a_share_hot_list(period: str = "hour") -> str:
    """A-share market hot list (同花顺热榜) via THS.

    ``period`` is 'hour' or 'day'.  Returns market-wide popularity ranking
    with concept tags and rank changes.
    """
    try:
        resp = requests.get(
            _THS_HOT_URL,
            params={"stock_type": "a", "type": period, "list_type": "normal"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        lst = (resp.json().get("data") or {}).get("stock_list") or []
    except (requests.RequestException, ValueError) as exc:
        raise ChinaDataUnavailableError(f"THS hot list request failed: {type(exc).__name__}") from exc
    rows = [
        {
            "Rank": it.get("order"),
            "Code": it.get("code"),
            "Name": it.get("name"),
            "Heat": it.get("rate"),
            "Change %": it.get("rise_and_fall"),
            "Rank Chg": it.get("hot_rank_chg"),
            "Concepts": ",".join((it.get("tag") or {}).get("concept_tag") or []),
            "Tag": (it.get("tag") or {}).get("popularity_tag", ""),
        }
        for it in lst
    ]
    if not rows:
        raise ChinaDataUnavailableError("THS returned no hot-list rows.")
    _capture_vendor_raw({"stock_list": lst}, metadata={"provider": "ths", "dataset": "hot_list", "ticker": None})
    return "\n".join(
        [
            f"# China A-share hot list ({period})",
            "# Source: ths",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Note: THS dq.10jqka.com.cn; period={period}; popularity ranking with concept tags.",
            "",
            pd.DataFrame(rows).to_csv(index=False),
        ]
    )


def get_a_share_hot_concept(ticker: str) -> str:
    """A-share hot concept hits (个股热门概念命中) via EastMoney.

    Returns which hot concepts a stock is currently grouped under, with hit
    counts.  Independent of the datacenter rate-limit plane.
    """
    canonical = normalize_ticker_symbol(ticker)
    if not is_a_share_ticker(canonical):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    code = to_akshare_symbol(canonical)
    prefix = "SH" if code.startswith("6") else "SZ"
    try:
        resp = requests.post(
            _EM_HOT_CONCEPT_URL,
            json={**_EM_HOT_BODY, "srcSecurityCode": prefix + code},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json().get("data") or []
    except (requests.RequestException, ValueError) as exc:
        raise ChinaDataUnavailableError(f"EastMoney hot concept request failed for {ticker}: {type(exc).__name__}") from exc
    rows = [
        {
            "Concept": x.get("conceptName"),
            "BK": x.get("conceptId"),
            "Hit": x.get("hitCount"),
        }
        for x in data
    ]
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no hot-concept rows for {code}.")
    _capture_vendor_raw({"data": data}, metadata={"provider": "eastmoney", "dataset": "hot_concept", "ticker": ticker})
    return "\n".join(
        [
            f"# China A-share hot concept hits for {canonical}",
            "# Source: eastmoney",
            f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "# Note: EastMoney emappdata; which hot concepts this stock currently hits.",
            "",
            pd.DataFrame(rows).to_csv(index=False),
        ]
    )


def _capture_vendor_raw(data: Any, *, metadata: dict[str, Any]) -> None:
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(data, metadata=dict(metadata))
