"""市场层面数据: 指数行情、国债收益率、申万A指估值、两融、波动率、宏观、新发基金、产业资本增减持。

数据源注册表 (market_sources):
    ("cached", fn, policy)                 整表下载 + 分层缓存 (store.cached)
    ("inc", fetch(start), date_col, start) 本地 parquet 增量补齐 (store.incremental)

fetch_market() -> {name: 原始 DataFrame}, 每个源独立 try/except, 失败只跳过该源。
"""
from __future__ import annotations

import datetime as dt
import logging
import math

import pandas as pd

from tradingagents.dataflows.vendors.akshare import settings, store

log = logging.getLogger(__name__)

_SW_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "Chrome/114.0.0.0 Safari/537.36")


def sw_index_analysis(symbol: str, swindexcode: str, start: str, end: str) -> pd.DataFrame:
    """申万宏源研究-指数日度分析 (单指数, 按代码过滤, 避免全市场分页过慢)。

    数据源: 申万宏源研究 (www.swsresearch.com)。akshare 只提供按类别的全量分页接口, 这里直接按指数代码请求。"""
    store.ak()                                   # 确认已安装并注入默认 HTTP 超时
    from akshare.index.index_research_sw import _sw_session

    url = "https://www.swsresearch.com/institute-sw/api/index_analysis/index_analysis_report/"
    params = {
        "page": "1", "page_size": "50", "index_type": symbol,
        "start_date": "-".join([start[:4], start[4:6], start[6:]]),
        "end_date": "-".join([end[:4], end[4:6], end[6:]]),
        "type": "DAY", "swindexcode": swindexcode,
    }
    headers = {"User-Agent": _SW_UA}
    r = _sw_session().get(url, params=params, headers=headers)
    total = r.json()["data"]["count"]
    parts = []
    for page in range(1, math.ceil(total / 50) + 1):
        params.update({"page": page})
        r = _sw_session().get(url, params=params, headers=headers)
        parts.append(pd.DataFrame(r.json()["data"]["results"]))
    big = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    big = big.rename(columns={
        "swindexcode": "指数代码", "swindexname": "指数名称", "bargaindate": "日期",
        "closeindex": "收盘指数", "bargainamount": "成交量", "markup": "涨跌幅",
        "turnoverrate": "换手率", "pe": "市盈率", "pb": "市净率", "meanprice": "均价",
        "bargainsumrate": "成交额占比", "negotiablessharesum1": "流通市值",
        "negotiablessharesum2": "平均流通市值", "dp": "股息率"})
    # 申万接口日期带时区 (+08:00), 统一转成 naive, 避免与其他 tz-naive 数据源混合时报错
    big["日期"] = store.to_local_dates(big["日期"])
    return big


def market_sources(with_insider: bool = False) -> dict:
    ak = store.ak()

    def idx(sym):
        return ("inc", lambda s: ak.stock_zh_index_daily_em(symbol=sym, start_date=s), "date", settings.START_DATE)

    today = dt.date.today().strftime("%Y%m%d")
    src = {
        # 估值/股息率/换手率/流通市值: 申万宏源研究 市场表征 -> 申万A指 (801003), 增量
        "sw_market": ("inc", lambda s: sw_index_analysis("市场表征", "801003", s, today),
                      "日期", settings.START_DATE),
        # 指数行情与国债: 增量
        "csi_all": idx("sh000985"),     # 中证全指
        "sh_comp": idx("sh000001"),     # 上证综指
        "sz_comp": idx("sz399106"),     # 深证综指
        "bond": ("inc", lambda s: ak.bond_zh_us_rate(start_date=s), "日期", settings.START_DATE),
        # 两融 / 波动率: 全量接口, 按交易日缓存
        "margin_sh": ("cached", ak.macro_china_market_margin_sh, "daily"),
        "margin_sz": ("cached", ak.macro_china_market_margin_sz, "daily"),
        "qvix": ("cached", ak.index_option_50etf_qvix, "daily"),
        # 宏观: 月度数据, 按交易日缓存 (单次请求, 成本低, 保证发布当天就能用上)
        "m_supply": ("cached", ak.macro_china_money_supply, "daily"),
        "tsf": ("cached", ak.macro_china_shrzgm, "daily"),
        "ppi": ("cached", ak.macro_china_ppi, "daily"),
        "pmi": ("cached", ak.macro_china_pmi, "daily"),
        "new_funds": ("cached", ak.fund_new_found_em, "daily"),
    }
    if with_insider:  # 全量明细, 首次数分钟, 按周更新
        src["insider"] = ("cached", lambda: ak.stock_ggcg_em(symbol="全部"), "weekly")
    return src


def fetch_market(refresh: bool = False, with_insider: bool = False,
                 only: set[str] | None = None) -> dict[str, pd.DataFrame]:
    """下载 / 读取市场层面数据。only: 只处理这些名字 (默认全部)。"""
    raw = {}
    for name, spec in market_sources(with_insider).items():
        if only and name not in only:
            continue
        try:
            if spec[0] == "cached":
                raw[name] = store.cached(name, spec[1], spec[2], refresh)
            else:
                _, fetch, date_col, full_start = spec
                raw[name] = store.incremental(name, fetch, date_col, full_start, refresh)
            log.info("  ✓ %-11s%7d 行", name, len(raw[name]))
        except Exception as e:
            log.warning("  ✗ %-11s %s", name, e)
            store.FALLBACKS[name] = f"拉取失败且无本地数据: {type(e).__name__}"
    return raw
