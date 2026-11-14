"""财报数据 (东方财富): 业绩报表、分红送配、历史业绩报表。

    yjbb             最近一个已基本披露完毕的报告期的业绩报表      每个报告期一次; 披露季内每 7 天补一次
    fhps             最近一个年报期的分红送配                       同上 (宽限 90 天)
    yjbb_hist_<期>   历史各报告期的业绩报表 (只保留 ROE / 净利润)   每个报告期一次

历史报告期由行业日度数据 (sw_daily) 覆盖的每个月末推算: 每个月末取当时已基本披露完毕的报告期,
保证用这些数据做回测时没有前视。
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from tradingagents.dataflows.vendors.akshare import store

log = logging.getLogger(__name__)

YJBB_HIST_COLS = ["股票代码", "净资产收益率", "净利润-同比增长", "净利润-净利润"]


# ---------------------------------------------------------------------------
# 报告期
# ---------------------------------------------------------------------------
def latest_report_date(today: dt.date) -> tuple[str, float]:
    """最近一个已基本披露完毕的报告期 (YYYYMMDD) 及其 ROE 年化系数。"""
    y = today.year
    cands = [(dt.date(y, 10, 31), f"{y}0930", 4 / 3), (dt.date(y, 8, 31), f"{y}0630", 2.0),
             (dt.date(y, 4, 30), f"{y}0331", 4.0), (dt.date(y, 4, 30), f"{y-1}1231", 1.0),
             (dt.date(y - 1, 10, 31), f"{y-1}0930", 4 / 3)]
    for deadline, rd, k in cands:
        if today > deadline:
            return rd, k
    return f"{y-1}0630", 2.0


def latest_annual(today: dt.date) -> str:
    """最近一个已披露完毕的年报期。"""
    return f"{today.year - 1}1231" if today > dt.date(today.year, 4, 30) else f"{today.year - 2}1231"


def in_season(today: dt.date, report_date: str, grace_days: int = 20) -> bool:
    """报告期结束后到披露截止日 + grace_days 之间视为披露季, 需要定期补充晚披露的公司。"""
    rd = dt.datetime.strptime(report_date, "%Y%m%d").date()
    deadline = {"0331": dt.date(rd.year, 4, 30), "0630": dt.date(rd.year, 8, 31),
                "0930": dt.date(rd.year, 10, 31), "1231": dt.date(rd.year + 1, 4, 30)}[report_date[4:]]
    return rd < today <= deadline + dt.timedelta(days=grace_days)


def report_dates_needed(sw_daily: pd.DataFrame, today: dt.date | None = None) -> list[str]:
    """sw_daily 覆盖区间内每个月末对应的 '已基本披露完毕' 报告期 (去重, 升序)。"""
    dates = pd.DatetimeIndex(pd.to_datetime(sw_daily["发布日期"], errors="coerce").dropna().unique()).sort_values()
    month_ends = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max()
    rds = {latest_report_date(m.date())[0] for m in month_ends}
    if today is not None:
        rds.add(latest_report_date(today)[0])
    return sorted(rds)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
def fetch_financials(refresh: bool = False, sw_daily: pd.DataFrame | None = None,
                     history: bool = True) -> dict[str, pd.DataFrame]:
    """sw_daily: 申万一级日度数据, 用来确定需要哪些历史报告期 (history=True 时)。"""
    today = store.now_cst().date()
    raw: dict[str, pd.DataFrame] = {}

    def get(name, fn, policy):
        try:
            raw[name] = store.cached(name, fn, policy, refresh)
            log.info("  ✓ %-14s%7d 行  [报告期 %s]", name, len(raw[name]), policy[1])
        except Exception as e:
            log.warning("  ✗ %-14s %s", name, e)

    rd, _ = latest_report_date(today)
    get("yjbb", lambda: store.ak().stock_yjbb_em(date=rd), ("period", rd, in_season(today, rd)))
    ad = latest_annual(today)
    get("fhps", lambda: store.ak().stock_fhps_em(date=ad), ("period", ad, in_season(today, ad, grace_days=90)))

    if history and sw_daily is not None and len(sw_daily):
        parts, miss = [], []
        for prd in report_dates_needed(sw_daily):
            if prd == rd and "yjbb" in raw:
                df = raw["yjbb"]
            else:
                try:
                    df = store.cached(f"yjbb_hist_{prd}",
                                      lambda prd=prd: store.ak().stock_yjbb_em(date=prd)[YJBB_HIST_COLS],
                                      ("period", prd, in_season(today, prd)), refresh)
                except Exception as e:
                    miss.append(f"{prd}: {e}")
                    continue
            parts.append(df[[c for c in YJBB_HIST_COLS if c in df.columns]].assign(报告期=prd))
        if parts:
            raw["yjbb_hist"] = pd.concat(parts, ignore_index=True)
            log.info("  ✓ %-14s%7d 行  [%d 个报告期]%s", "yjbb_hist", len(raw["yjbb_hist"]), len(parts),
                     f"  缺 {len(miss)} 期: {miss[:2]}" if miss else "")
    return raw
