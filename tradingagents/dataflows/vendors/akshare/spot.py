"""全市场实时行情 (每天一次的 '当日数据'): 按 SPOT_SOURCES 的优先级依次尝试 新浪 -> 东方财富 -> 雪球。

东方财富的接口每页 100 只, 全市场约 59 页。akshare 的实现每隔 0.5–1.5 秒连续请求, 中途任何一页失败就整体作废,
容易触发限流, 且下次又要从第 1 页开始。这里改为:
  · 放慢节奏: 每页间隔 EM_PAUSE (1.5–2.5 秒); 一旦被断开 (限流) 立即停止, 不再继续请求
  · 断点续传: 收盘后的行情不再变化, 已下载的页存到 .akshare_data/spot_pages/<交易日>/, 下次运行只补缺的页
    (盘中行情时刻在变, 不缓存分页)
  · 新浪: 约 10 秒取全市场, 但没有换手率 / 市盈率 / 市净率 / 市值; 用最近一次东财完整数据中的股本、每股收益、
    每股净资产推算补齐 (见 enrich), 60 日 / 年初至今涨跌幅留空
  · 雪球: 逐只查询, 需要 token (环境变量 XQ_TOKEN) 和调用方给出的股票列表 (xq_codes); 只有部分股票,
    当日不保存个股快照
返回的 DataFrame 列名与 akshare.stock_zh_a_spot_em 一致, 另加 _source 列 ('eastmoney' / 'sina' / 'xq')。
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import shutil
import time
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.vendors.akshare import store

log = logging.getLogger(__name__)

EM_URL = "https://82.push2.eastmoney.com/api/qt/clist/get"
EM_PARAMS = {
    "pz": "100", "po": "1", "np": "1", "ut": "bd1d9ddb04089700cf9c27f6f7426281", "fltt": "2", "invt": "2",
    "fid": "f12", "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
    "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f14,f15,f16,f17,f18,f20,f21,f22,f23,f24,f25",
}
EM_FIELDS = {"f2": "最新价", "f3": "涨跌幅", "f4": "涨跌额", "f5": "成交量", "f6": "成交额", "f7": "振幅", "f8": "换手率",
             "f9": "市盈率-动态", "f10": "量比", "f11": "5分钟涨跌", "f12": "代码", "f14": "名称", "f15": "最高",
             "f16": "最低", "f17": "今开", "f18": "昨收", "f20": "总市值", "f21": "流通市值", "f22": "涨速",
             "f23": "市净率", "f24": "60日涨跌幅", "f25": "年初至今涨跌幅"}
EM_PAUSE = (1.5, 2.5)        # 每页之间的间隔 (秒)
EM_TIMEOUT = (10, 20)

# 本次运行的说明 (如 "东方财富被限流, 改用新浪"), 供上层显示
NOTES: dict[str, str] = {}


class SpotIncomplete(Exception):
    """东方财富分页没有全部下载完 (已下载的页已保存, 下次续传)。"""


# ---------------------------------------------------------------------------
# 东方财富 (分页 + 续传)
# ---------------------------------------------------------------------------
def fetch_em_page(pn: int) -> dict:
    """请求东方财富第 pn 页, 返回 {"total": 全市场只数, "rows": [...]}。被限流 / 断开时抛出异常。"""
    import requests
    params = dict(EM_PARAMS, pn=str(pn))
    r = requests.get(EM_URL, params=params, timeout=EM_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    data = r.json().get("data") or {}
    return {"total": int(data.get("total") or 0), "rows": data.get("diff") or []}


def _pages_dir(day: str) -> Path:
    return store.root() / "spot_pages" / day


def fetch_em(day: str, persist: bool, pause: tuple[float, float] | None = None) -> pd.DataFrame:
    """下载东方财富全市场行情。persist=True (收盘后) 时逐页保存, 中断后下次只补缺的页。不全时抛 SpotIncomplete。"""
    pause = pause or EM_PAUSE
    d = _pages_dir(day)
    if persist:
        d.mkdir(parents=True, exist_ok=True)
    meta_p = d / "_meta.json"
    pages: dict[int, list] = {}
    total = None
    if persist and meta_p.exists():
        total = json.loads(meta_p.read_text())["total"]
        for f in d.glob("p*.json"):
            pages[int(f.stem[1:])] = json.loads(f.read_text())
    per = int(EM_PARAMS["pz"])
    try:
        if total is None:
            first = fetch_em_page(1)
            total = first["total"]
            pages[1] = first["rows"]
            if persist:
                (d / "p1.json").write_text(json.dumps(first["rows"], ensure_ascii=False))
                meta_p.write_text(json.dumps({"total": total}))
        n_pages = max(1, math.ceil(total / per))
        for pn in range(1, n_pages + 1):
            if pn in pages:
                continue
            time.sleep(random.uniform(*pause))
            pg = fetch_em_page(pn)
            pages[pn] = pg["rows"]
            if persist:
                (d / f"p{pn}.json").write_text(json.dumps(pg["rows"], ensure_ascii=False))
    except Exception as e:
        n_pages = max(1, math.ceil((total or 0) / per)) if total else None
        raise SpotIncomplete(f"已下载 {len(pages)}/{n_pages or '?'} 页后中断 ({type(e).__name__})"
                             + ("; 已保存进度, 下次运行续传" if persist else "")) from e
    rows = [r for pn in sorted(pages) for r in pages[pn]]
    df = pd.DataFrame(rows).rename(columns=EM_FIELDS)
    df = df[[c for c in EM_FIELDS.values() if c in df.columns]]
    for c in df.columns:
        if c not in ("代码", "名称"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.drop_duplicates("代码").reset_index(drop=True)
    if len(df) < 0.95 * total:
        raise SpotIncomplete(f"只拿到 {len(df)}/{total} 只")
    df["_source"] = "eastmoney"
    if persist:
        shutil.rmtree(d, ignore_errors=True)
    return df


# ---------------------------------------------------------------------------
# 参考数据: 用最近一次东财完整行情推算新浪缺少的字段
# ---------------------------------------------------------------------------
REF_MAX_AGE_DAYS = 7          # 参考数据超过 7 天时, 新浪成功后也顺带用东财刷新一次 (失败不影响)


def _ref_path() -> Path:
    return store.root() / "spot_ref.parquet"


def load_ref() -> pd.DataFrame | None:
    p = _ref_path()
    return pd.read_parquet(p).set_index("code") if p.exists() else None


def update_ref(em: pd.DataFrame, day: str) -> None:
    """从东财完整行情提取 '股本 / 每股收益 / 每股净资产' (变化很慢), 用于推算新浪行情缺少的换手率、市值、PE、PB。"""
    need = {"代码", "最新价", "流通市值", "总市值", "市盈率-动态", "市净率"}
    if not need <= set(em.columns):
        log.warning("    ! 东财行情缺少 %s, 不更新参考数据", sorted(need - set(em.columns)))
        return
    px = pd.to_numeric(em["最新价"], errors="coerce").where(lambda v: v > 0)
    pe = pd.to_numeric(em["市盈率-动态"], errors="coerce").where(lambda v: v != 0)
    pb = pd.to_numeric(em["市净率"], errors="coerce").where(lambda v: v != 0)
    ref = pd.DataFrame({"code": em["代码"].astype(str).str.zfill(6), "ref_date": day,
                        "float_shares": pd.to_numeric(em["流通市值"], errors="coerce") / px,
                        "total_shares": pd.to_numeric(em["总市值"], errors="coerce") / px,
                        "eps": px / pe, "bps": px / pb}).dropna(subset=["float_shares"])
    old = load_ref()
    if old is not None:
        o = old.reset_index()
        ref = pd.concat([o[~o["code"].isin(ref["code"])], ref], ignore_index=True)
    tmp = _ref_path().with_suffix(".tmp")
    ref.to_parquet(tmp, index=False)
    tmp.replace(_ref_path())


def enrich(df: pd.DataFrame, ref: pd.DataFrame | None) -> pd.DataFrame:
    """用参考数据补齐新浪 / 雪球行情缺少的字段: 换手率 (%) = 成交量(手) × 100 ÷ 流通股本; 市值 = 股本 × 价;
    PE = 价 ÷ 每股收益; PB = 价 ÷ 每股净资产。已有值的不覆盖。60 日 / 年初至今涨跌幅无法推算, 保持为空。"""
    if ref is None or not len(df):
        return df
    out = df.copy()
    r = ref.reindex(out["代码"].astype(str).str.zfill(6))
    r.index = out.index
    px = pd.to_numeric(out["最新价"], errors="coerce")
    derived = {"换手率": pd.to_numeric(out["成交量"], errors="coerce") * 100 / r["float_shares"] * 100,
               "流通市值": r["float_shares"] * px, "总市值": r["total_shares"] * px,
               "市盈率-动态": px / r["eps"], "市净率": px / r["bps"]}
    for c, v in derived.items():
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(v) if c in out else v
    return out


# ---------------------------------------------------------------------------
# 新浪
# ---------------------------------------------------------------------------
def fetch_sina() -> pd.DataFrame:
    """新浪全市场行情, 转成东方财富的列名与单位 (成交量: 股 -> 手)。缺少的字段先为空, 再由 enrich() 推算。"""
    s = store.ak().stock_zh_a_spot()
    num = lambda c: pd.to_numeric(s[c], errors="coerce")  # noqa: E731
    out = pd.DataFrame({
        "代码": s["代码"].astype(str).str[-6:], "名称": s["名称"],
        "最新价": num("最新价"), "涨跌幅": num("涨跌幅"), "涨跌额": num("涨跌额"),
        "成交量": num("成交量") / 100, "成交额": num("成交额"),
        "最高": num("最高"), "最低": num("最低"), "今开": num("今开"), "昨收": num("昨收"),
    })
    for c in EM_FIELDS.values():
        if c not in out:
            out[c] = float("nan")
    out["振幅"] = (out["最高"] - out["最低"]) / out["昨收"] * 100
    out["_source"] = "sina"
    out = out.drop_duplicates("代码").reset_index(drop=True)
    if len(out) < 3000:
        raise SpotIncomplete(f"新浪只返回 {len(out)} 只")
    return out


# ---------------------------------------------------------------------------
# 雪球 (逐只查询, 需要 token 与股票列表)
# ---------------------------------------------------------------------------
XQ_ITEMS = {"最新价": ("现价",), "涨跌幅": ("涨幅",), "涨跌额": ("涨跌",), "昨收": ("昨收",), "今开": ("今开",),
            "最高": ("最高",), "最低": ("最低",), "成交量": ("成交量",), "成交额": ("成交额",), "换手率": ("换手率",),
            "市盈率-动态": ("市盈率(动)", "市盈率(TTM)"), "市净率": ("市净率",), "总市值": ("资产总值", "总市值"),
            "流通市值": ("流通值", "流通市值"), "名称": ("名称",)}


def fetch_xq(codes: list[str] | None, token: str | None = None) -> pd.DataFrame:
    """雪球个股行情 (逐只)。需要 token (环境变量 XQ_TOKEN, 即浏览器登录雪球后的 xq_a_token)。返回的只是部分股票。"""
    token = token or os.environ.get("XQ_TOKEN")
    if not token:
        raise RuntimeError("未设置雪球 token (环境变量 XQ_TOKEN)")
    if not codes:
        raise RuntimeError("雪球兜底需要股票列表 (xq_codes)")
    ak = store.ak()
    rows, errs = [], 0
    for c in codes:
        sym = store.to_symbol(c)
        if not sym:
            continue
        try:
            t = ak.stock_individual_spot_xq(symbol=sym, token=token)
        except Exception:
            errs += 1
            if errs >= 3 and not rows:
                raise
            continue
        kv = dict(zip(t["item"].astype(str), t["value"], strict=False))
        row = {"代码": sym[2:]}
        for col, keys in XQ_ITEMS.items():
            row[col] = next((kv[k] for k in keys if k in kv), None)
        rows.append(row)
        time.sleep(0.3)
    if not rows:
        raise SpotIncomplete("雪球没有返回任何股票")
    out = pd.DataFrame(rows)
    for c in EM_FIELDS.values():
        if c not in out:
            out[c] = float("nan")
        elif c not in ("代码", "名称"):
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out["成交量"] = out["成交量"] / 100                 # 股 -> 手
    out["_source"] = "xq"
    return out


# ---------------------------------------------------------------------------
# 调度
# ---------------------------------------------------------------------------
SPOT_SOURCES = ("sina", "em", "xq")      # 数据源优先级: 前一个失败时尝试下一个
SOURCE_CN = {"sina": "新浪", "em": "东方财富", "xq": "雪球"}


def spot_path(day: str) -> Path:
    return store.root() / f"spot__{day}.pkl"


def fetch_spot(refresh: bool = False, xq_codes: list[str] | None = None) -> pd.DataFrame:
    """当日全市场行情, 按 SPOT_SOURCES 的优先级依次尝试; 收盘后取得的全市场数据按交易日缓存 (spot__<日期>.pkl)。

    xq_codes: 新浪与东财都失败时, 用雪球逐只查询的股票 (例如持仓); 不给则跳过雪球。
    都失败时: NOTES["spot_failed"] 记录各数据源的失败原因, 并退回最近一份旧缓存 (记入 store.FALLBACKS);
    连旧缓存都没有则抛出异常。"""
    for k in ("spot_src", "spot_warn", "spot_failed"):
        NOTES.pop(k, None)
    day = store.last_closed_trade_date().strftime("%Y%m%d")
    intraday = store.is_intraday()
    path = spot_path(day)
    if path.exists() and not refresh and not intraday:
        df = _ensure_columns(pd.read_pickle(path))
        log.info("    · spot 命中缓存 %s", path.name)
        _note_source(df)
        return df
    errors: dict[str, str] = {}
    df, used = None, None
    for src in SPOT_SOURCES:
        try:
            if src == "sina":
                df = enrich(fetch_sina(), load_ref())
            elif src == "em":
                df = fetch_em(day, persist=not intraday)
                try:
                    update_ref(df, day)
                except Exception as e:  # 参考数据只是辅助, 失败不影响行情本身
                    log.warning("    ! 更新参考数据失败: %s: %s", type(e).__name__, e)
            elif src == "xq":
                df = enrich(fetch_xq(xq_codes), load_ref())
            used = src
            break
        except Exception as e:
            errors[src] = f"{type(e).__name__}: {e}"
            log.warning("    ! %s行情失败: %s", SOURCE_CN[src], errors[src][:160])
    if df is None:
        NOTES["spot_failed"] = "当日行情数据获取失败 — " + "; ".join(
            f"{SOURCE_CN[k]}: {v[:120]}" for k, v in errors.items())
        olds = sorted(store.root().glob("spot__*.pkl"))
        if olds:
            store.FALLBACKS["spot"] = f"当日行情获取失败, 使用旧缓存 {olds[-1].stem.split('__')[-1]}"
            log.warning("    ! spot 使用旧缓存 %s", olds[-1].name)
            return pd.read_pickle(olds[-1])
        raise RuntimeError(NOTES["spot_failed"])
    df = _ensure_columns(df)
    if errors:
        log.info("    · 改用%s行情: %d 只", SOURCE_CN[used], len(df))
    if used != "xq" and not intraday:                 # 全市场数据才缓存 (雪球只有部分股票)
        df.to_pickle(path)
        for old in store.root().glob("spot__*.pkl"):
            if old != path:
                old.unlink(missing_ok=True)
    # 新浪成功但推算用的参考数据太旧: 顺带用东财刷新 (慢, 失败不影响本次结果)
    ref = load_ref()
    if used == "sina" and not intraday and "em" in SPOT_SOURCES:
        age = ((pd.Timestamp(day) - pd.Timestamp(str(ref["ref_date"].max()))).days
               if ref is not None and len(ref) else 999)
        if age > REF_MAX_AGE_DAYS:
            try:
                log.info("    · 推算换手率 / 市值用的参考数据已 %d 天未更新, 用东方财富刷新 (约 2 分钟)", age)
                em = fetch_em(day, persist=True)
                update_ref(em, day)
                df = enrich(df.drop(columns=["换手率", "流通市值", "总市值", "市盈率-动态", "市净率"]), load_ref())
                df.to_pickle(path)
            except Exception as e:
                log.warning("    ! 东方财富刷新参考数据失败 (不影响本次): %s", type(e).__name__)
    _note_source(df, errors)
    return df


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """不论来自哪个数据源, 都补齐东财格式的全部列 (缺少的为空), 下游代码只需按一种格式处理。"""
    for c in EM_FIELDS.values():
        if c not in df:
            df[c] = float("nan")
    return df


def _note_source(df: pd.DataFrame, errors: dict | None = None) -> None:
    src = df["_source"].iat[0] if "_source" in df and len(df) else "em"
    src = "em" if src == "eastmoney" else src
    ref = load_ref()
    ref_day = str(ref["ref_date"].max()) if ref is not None and len(ref) else ""
    if src == "sina":
        NOTES["spot_src"] = ("新浪全市场行情; 换手率 / 市值 / PE / PB 按 "
                             + (f"{ref_day} 东财数据中的股本与每股指标推算" if ref_day else "参考数据缺失, 这些字段为空")
                             + "; 60 日 / 年初至今涨跌幅为空")
    elif src == "xq":
        failed = "; ".join(f"{SOURCE_CN[k]}: {v[:60]}" for k, v in (errors or {}).items())
        NOTES["spot_warn"] = f"新浪与东方财富都失败 ({failed}), 改用雪球, 只取得 {len(df)} 只; 当日不保存个股快照"
    else:
        NOTES["spot_src"] = "东方财富全市场行情 (字段最全)"
