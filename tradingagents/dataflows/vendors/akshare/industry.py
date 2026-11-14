"""申万行业数据 (申万宏源研究): 一级 / 二级行业列表、行业日度估值、成分股。

    sw_first        申万一级行业列表 (31 个)                     每周一次
    sw_second       申万二级行业列表 (约 124 个, 带"上级行业")     每周一次
    sw_daily        申万一级行业日度估值 (首次回补 5 年)           增量 ts/sw_daily.parquet
    sw_daily2       申万二级行业日度估值 (首次回补 3 年)           增量 ts/sw_daily2.parquet
    sw_comp         一级行业成分股 (个股 -> 一级行业)              每周一次
    sw_second_cons  二级行业成分股 (个股 -> 二级行业)              每周一次

申万宏源无三级行业接口, 只覆盖一级 / 二级。
"""
from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from tradingagents.dataflows.vendors.akshare import store

log = logging.getLogger(__name__)

L1_YEARS = 5                           # 申万一级日度历史回补年数
L2_YEARS = 3                           # 申万二级日度历史回补年数 (首次约 1900 页请求)

# 申万二级行业代码 -> 所属一级行业名称 (申万 2021 版官方分类, 静态映射, 不依赖外部接口)
SW2_PARENT = {
    "801011": "农林牧渔", "801012": "农林牧渔", "801014": "农林牧渔", "801015": "农林牧渔", "801016": "农林牧渔", "801017": "农林牧渔",
    "801018": "农林牧渔", "801019": "农林牧渔", "801032": "基础化工", "801033": "基础化工", "801034": "基础化工", "801036": "基础化工",
    "801037": "基础化工", "801038": "基础化工", "801039": "基础化工", "801043": "钢铁", "801044": "钢铁", "801045": "钢铁",
    "801051": "有色金属", "801053": "有色金属", "801054": "有色金属", "801055": "有色金属", "801056": "有色金属", "801072": "机械设备",
    "801074": "机械设备", "801076": "机械设备", "801077": "机械设备", "801078": "机械设备", "801081": "电子", "801082": "电子",
    "801083": "电子", "801084": "电子", "801085": "电子", "801086": "电子", "801092": "汽车", "801093": "汽车",
    "801095": "汽车", "801096": "汽车", "801101": "计算机", "801102": "通信", "801103": "计算机", "801104": "计算机",
    "801111": "家用电器", "801112": "家用电器", "801113": "家用电器", "801114": "家用电器", "801115": "家用电器", "801116": "家用电器",
    "801117": "家用电器", "801124": "食品饮料", "801125": "食品饮料", "801126": "食品饮料", "801127": "食品饮料", "801128": "食品饮料",
    "801129": "食品饮料", "801131": "纺织服饰", "801132": "纺织服饰", "801133": "纺织服饰", "801141": "轻工制造", "801142": "轻工制造",
    "801143": "轻工制造", "801145": "轻工制造", "801151": "医药生物", "801152": "医药生物", "801153": "医药生物", "801154": "医药生物",
    "801155": "医药生物", "801156": "医药生物", "801161": "公用事业", "801163": "公用事业", "801178": "交通运输", "801179": "交通运输",
    "801181": "房地产", "801183": "房地产", "801191": "非银金融", "801193": "非银金融", "801194": "非银金融", "801202": "商贸零售",
    "801203": "商贸零售", "801204": "商贸零售", "801206": "商贸零售", "801207": "商贸零售", "801216": "社会服务", "801218": "社会服务",
    "801219": "社会服务", "801223": "通信", "801231": "综合", "801711": "建筑材料", "801712": "建筑材料", "801713": "建筑材料",
    "801721": "建筑装饰", "801722": "建筑装饰", "801723": "建筑装饰", "801724": "建筑装饰", "801726": "建筑装饰", "801731": "电力设备",
    "801733": "电力设备", "801735": "电力设备", "801736": "电力设备", "801737": "电力设备", "801738": "电力设备", "801741": "国防军工",
    "801742": "国防军工", "801743": "国防军工", "801744": "国防军工", "801745": "国防军工", "801764": "传媒", "801765": "传媒",
    "801766": "传媒", "801767": "传媒", "801769": "传媒", "801782": "银行", "801783": "银行", "801784": "银行",
    "801785": "银行", "801881": "汽车", "801951": "煤炭", "801952": "煤炭", "801961": "石油石化", "801962": "石油石化",
    "801963": "石油石化", "801971": "环保", "801972": "环保", "801981": "美容护理", "801982": "美容护理", "801983": "美容护理",
    "801991": "交通运输", "801992": "交通运输", "801993": "社会服务", "801994": "社会服务", "801995": "传媒",
}


def _sw_class(symbol: str) -> pd.DataFrame:
    df = store.ak().index_realtime_sw(symbol=symbol)
    df = df.rename(columns={"指数代码": "行业代码", "指数名称": "行业名称"})
    return df[["行业代码", "行业名称"]]


def _sw_second() -> pd.DataFrame:
    df = _sw_class("二级行业")
    code = df["行业代码"].astype(str).str.extract(r"(\d{6})")[0]
    df["上级行业"] = code.map(SW2_PARENT).fillna("")
    return df


def _daily_fetcher(level: str, today: dt.date):
    """按年分段请求申万行业日度估值 (首次回补时单次请求过大容易失败)。"""
    def fetch(start: str) -> pd.DataFrame:
        s0 = dt.datetime.strptime(start, "%Y%m%d").date()
        parts = []
        for y in range(s0.year, today.year + 1):
            a_ = max(s0, dt.date(y, 1, 1)).strftime("%Y%m%d")
            b_ = min(today, dt.date(y, 12, 31)).strftime("%Y%m%d")
            parts.append(store.ak().index_analysis_daily_sw(symbol=level, start_date=a_, end_date=b_))
            log.info("    · 申万%s日度 %s–%s", level, a_, b_)
        return pd.concat(parts, ignore_index=True)
    return fetch


def _components(codes: list[str], code_col: str) -> pd.DataFrame:
    out = []
    for c in codes:
        try:
            d = store.ak().index_component_sw(symbol=c)
            d[code_col] = c
            out.append(d)
        except Exception as ex:
            log.warning("    ! 成分股 %s: %s", c, ex)
    return pd.concat(out, ignore_index=True)


def _codes(df: pd.DataFrame) -> list[str]:
    return df["行业代码"].astype(str).str.extract(r"(\d{6})")[0].dropna().tolist()


def fetch_industry(refresh: bool = False, years: int = L1_YEARS) -> dict[str, pd.DataFrame]:
    today = store.now_cst().date()
    raw: dict[str, pd.DataFrame] = {}

    def get(name, fn, policy):
        try:
            raw[name] = store.cached(name, fn, policy, refresh)
            log.info("  ✓ %-14s%7d 行  [%s]", name, len(raw[name]), policy)
        except Exception as e:
            log.warning("  ✗ %-14s %s", name, e)

    def inc(name, level, start):
        try:
            raw[name] = store.incremental(name, _daily_fetcher(level, today), "发布日期", start,
                                          refresh, key_cols=("指数代码",))
            log.info("  ✓ %-14s%7d 行  [增量]", name, len(raw[name]))
        except Exception as e:
            log.warning("  ✗ %-14s %s", name, e)

    get("sw_first", lambda: _sw_class("一级行业"), "weekly")
    get("sw_second", _sw_second, "weekly")
    inc("sw_daily", "一级行业", f"{today.year - years}0101")
    inc("sw_daily2", "二级行业", f"{today.year - L2_YEARS}0101")
    if "sw_first" in raw:
        codes = _codes(raw["sw_first"])
        get("sw_comp", lambda: _components(codes, "行业代码"), "weekly")
    if "sw_second" in raw:
        codes2 = _codes(raw["sw_second"])
        get("sw_second_cons", lambda: _components(codes2, "二级代码"), "weekly")
    return raw
