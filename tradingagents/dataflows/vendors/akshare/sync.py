"""A 股数据同步: 一次运行把各类数据下载 / 增量补齐到 .akshare_data/。

步骤 (STEPS, 可用 only 选择):
    market      市场层面: 指数行情、国债、申万A指估值、两融、QVIX、宏观、新发基金 (、产业资本增减持)
    industry    申万一级 / 二级行业列表、日度估值、成分股
    financials  业绩报表、分红送配、历史业绩报表 (历史报告期依赖 industry 的 sw_daily)
    spot        全市场实时行情 (新浪 -> 东方财富 -> 雪球)
    snapshots   个股日线快照 (依赖 spot): 首次建立 base, 之后每个交易日一个日期目录

每一步都先读本地数据, 只下载缺失的部分; 某一步失败不影响其他步骤。
"""
from __future__ import annotations

import json
import logging
import time

import pandas as pd

from tradingagents.dataflows.vendors.akshare import (
    financials,
    industry,
    market,
    settings,
    snapshots,
    spot,
    store,
)

log = logging.getLogger(__name__)

STEPS = ("market", "industry", "financials", "spot", "snapshots")


def sync_all(only: tuple[str, ...] | list[str] | None = None, refresh: bool = False, with_insider: bool = False,
         allow_intraday: bool = False, workers: int = 4, history_reports: bool = True,
         xq_codes: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """按 STEPS 顺序同步数据, 返回本次读到的原始数据 {name: DataFrame} (快照只写盘, 不返回)。"""
    steps = [s for s in STEPS if not only or s in only]
    unknown = set(only or ()) - set(STEPS)
    if unknown:
        raise ValueError(f"未知步骤 {sorted(unknown)}, 可选: {', '.join(STEPS)}")
    store.FALLBACKS.clear()
    log.info("数据目录: %s", store.root())
    log.info("最近收盘交易日 %s%s", store.last_closed_trade_date(),
             " · 当前为盘中, 当天数据不写入缓存" if store.is_intraday() else "")
    raw: dict[str, pd.DataFrame] = {}
    t0 = time.time()

    if "market" in steps:
        log.info("[market] 市场层面数据")
        raw.update(market.fetch_market(refresh, with_insider))
    if "industry" in steps:
        log.info("[industry] 申万行业")
        raw.update(industry.fetch_industry(refresh))
    if "financials" in steps:
        log.info("[financials] 财报")
        sw_daily = raw.get("sw_daily")
        if sw_daily is None and history_reports and store.ts_path("sw_daily").exists():
            sw_daily = pd.read_parquet(store.ts_path("sw_daily"))
        raw.update(financials.fetch_financials(refresh, sw_daily, history_reports))
    if "spot" in steps or "snapshots" in steps:
        log.info("[spot] 全市场行情")
        try:
            raw["spot"] = spot.fetch_spot(refresh, xq_codes=xq_codes)
            src = raw["spot"]["_source"].iat[0] if "_source" in raw["spot"] and len(raw["spot"]) else "eastmoney"
            log.info("  ✓ %-14s%7d 行  [%s]", "spot", len(raw["spot"]),
                     {"eastmoney": "东方财富", "sina": "新浪", "xq": "雪球 (部分股票)"}.get(src, src))
        except Exception as e:
            log.warning("  ✗ spot           %s", e)
    if "snapshots" in steps and "spot" in raw:
        log.info("[snapshots] 个股日线快照")
        _update_snapshots(raw["spot"], refresh, allow_intraday, workers)

    if store.FALLBACKS:
        log.warning("以下数据本次拉取失败, 使用了旧数据:")
        for k, v in store.FALLBACKS.items():
            log.warning("  - %s: %s", k, v)
    log.info("完成, 用时 %.0f 秒", time.time() - t0)
    return raw


def _update_snapshots(spot_df: pd.DataFrame, refresh: bool, allow_intraday: bool, workers: int) -> dict | None:
    try:
        res = snapshots.update(spot_df, store.ak().stock_zh_a_hist, workers=workers,
                               spot_is_stale="spot" in store.FALLBACKS,
                               allow_intraday=allow_intraday, force=refresh)
    except Exception as e:
        log.warning("  ✗ 个股快照失败: %s: %s", type(e).__name__, e)
        return None
    if res["status"] == "ok":
        if res["base_built"]:
            log.info("  ✓ 个股快照: 已建立 base (%d 只, 覆盖到 %s) → %s", res["base_built"], res["date"], res["dir"])
        else:
            log.info("  ✓ 个股快照 %s: 当日 %d 只 → %s%s%s%s", res["date"], res["rows"], res["dir"],
                     f" · 补漏跑 {res['gap_days']} 天" if res["gap_days"] else "",
                     f" · 其中 {res['not_in_base']} 只不在 base 中 (base 之后上市)" if res["not_in_base"] else "",
                     f" · 已合并月份 {', '.join(res['merged'])}" if res.get("merged") else "")
    elif res["status"] == "stale":
        log.warning("  ✗ 个股快照: %s", res["msg"])
    else:
        log.info("  · 个股快照: %s", res["msg"])
    return res


# ---------------------------------------------------------------------------
# 本地数据概况
# ---------------------------------------------------------------------------
_TS_DATE_COLS = ("date", "日期", "发布日期")


def status() -> pd.DataFrame:
    """列出 .akshare_data 中的各类数据及其最新日期 / 缓存键, 不访问网络。"""
    root = settings.data_dir()
    rows = []
    if not root.exists():
        return pd.DataFrame(columns=["类别", "名称", "行数", "最新", "文件"])
    for p in sorted((root / "ts").glob("*.parquet")):
        df = pd.read_parquet(p)
        col = next((c for c in _TS_DATE_COLS if c in df.columns), None)
        last = store.to_local_dates(df[col]).max() if col else pd.NaT
        rows.append({"类别": "增量序列", "名称": p.stem, "行数": len(df),
                     "最新": f"{last:%Y-%m-%d}" if pd.notna(last) else "?", "文件": str(p.relative_to(root))})
    for p in sorted(root.glob("*__*.pkl")):
        name, key = p.stem.split("__", 1)
        rows.append({"类别": "分层缓存", "名称": name, "行数": None, "最新": key,
                     "文件": p.name})
    meta_p = root / "snapshots" / "_meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text())
        days = snapshots.daily_dates()
        n_base = sum(1 for _ in (root / "snapshots" / "base").glob("*.parquet"))
        rows.append({"类别": "个股快照", "名称": "base", "行数": n_base, "最新": meta.get("base_through"),
                     "文件": "snapshots/base/"})
        rows.append({"类别": "个股快照", "名称": "日期目录", "行数": len(days),
                     "最新": days[-1] if days else None, "文件": "snapshots/<YYYYMMDD>/"})
    ref = root / "spot_ref.parquet"
    if ref.exists():
        r = pd.read_parquet(ref)
        rows.append({"类别": "参考数据", "名称": "spot_ref", "行数": len(r),
                     "最新": str(r["ref_date"].max()) if len(r) else None, "文件": ref.name})
    return pd.DataFrame(rows).astype({"行数": "Int64"})
