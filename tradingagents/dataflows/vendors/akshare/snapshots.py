"""个股日线快照: 固定不变的初始数据 (base) + 每个交易日一个目录。

目录结构:
    .akshare_data/snapshots/
        base/SH600519.parquet               初始数据: 该股上市 ~ base_through 的全部日线 (建立后不再改动)
        20261109/cross_section.parquet      2026-11-09 当日全市场的交易数据 (一行一只股票, 几百 KB)
        20261110/cross_section.parquet      2026-11-10 当日全市场的交易数据
        _merged/202611.parquet              按月合并缓存 (派生数据): 已结束月份的日期目录合并成一个文件, 删了可重建
        _backfill/                          暂存区 (首次建立 base / 补漏跑的交易日; 可断点续传, 完成后删除)
        _meta.json                          {"layout": 2, "base_through": "20261106", ...}

分析用的数据 = base + base_through 之后的全部日期目录。例如:
    分析 2026-11-09:  base + 20261109
    分析 2026-11-10:  base + 20261109 + 20261110
日期目录是数据的一部分, 不会被删除。读取时已结束的月份用 _merged/ 中的合并文件 (与日期目录内容相同, 只是更快),
当月用日期目录; 合并文件由 _merged/_manifest.json 校验, 日期目录有变化时自动重建。

每次运行 (交易日 D 收盘后):
    1. 还没有 base: 逐只下载上市以来的历史日线 (可断点续传), 全部成功后建立 base (覆盖到 D)
    2. 已有 base: 只下载 D 当日的交易数据 (一次请求: 全市场实时快照), 写入 snapshots/D/
    3. 上次运行之后有漏跑的交易日: 逐只补下载这几天的日线, 每天写入各自的日期目录
    base 之后新上市的股票不需要单独下载历史: 它上市以来的每个交易日都在日期目录里。

价格为不复权价 (与实时行情一致)。历史日线没有 PE/PB/市值, 这些列只在用实时快照生成的行里有值。
source 列: spot = 东方财富实时快照 (字段最全); sina = 新浪行情 (换手率 / 市值 / PE / PB 按东财股本等推算); hist = 历史日线。

读取 (分析用):
    load_stock("SH600519", asof=None)     单只股票的全部日线
    load_daily(start, end)                base 之后各日期目录的全市场数据
    load_cross_section("2026-11-09")      某一天的全市场截面
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from tradingagents.dataflows.vendors.akshare import store as S

log = logging.getLogger(__name__)

LAYOUT = 2
XS_FILE = "cross_section.parquet"

COLUMNS = ["trade_date", "code", "exchange", "name", "open", "high", "low", "close", "pre_close", "volume", "amount",
           "amplitude", "pct_chg", "chg", "turnover", "pe_dynamic", "pb", "total_mv", "float_mv", "volume_ratio",
           "pct_chg_60d", "pct_chg_ytd", "source"]

SPOT_MAP = {"名称": "name", "今开": "open", "最高": "high", "最低": "low", "最新价": "close", "昨收": "pre_close",
            "成交量": "volume", "成交额": "amount", "振幅": "amplitude", "涨跌幅": "pct_chg", "涨跌额": "chg",
            "换手率": "turnover", "市盈率-动态": "pe_dynamic", "市净率": "pb", "总市值": "total_mv", "流通市值": "float_mv",
            "量比": "volume_ratio", "60日涨跌幅": "pct_chg_60d", "年初至今涨跌幅": "pct_chg_ytd"}

HIST_MAP = {"日期": "trade_date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "振幅": "amplitude", "涨跌幅": "pct_chg", "涨跌额": "chg", "换手率": "turnover"}


# ---------------------------------------------------------------------------
# 路径与元数据
# ---------------------------------------------------------------------------
def base_dir() -> Path:
    """快照根目录 (.akshare_data/snapshots)。"""
    return S.snapshot_dir()


def master_dir() -> Path:
    """初始数据目录 (.akshare_data/snapshots/base), 建立后不再改动。"""
    return base_dir() / "base"


def _meta() -> dict:
    p = base_dir() / "_meta.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_meta(m: dict) -> None:
    p = base_dir() / "_meta.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2))
    os.replace(tmp, p)


def base_through() -> str | None:
    """base (初始数据) 覆盖到的交易日 (YYYYMMDD)。"""
    m = _meta()
    return m.get("base_through") if m.get("layout") == LAYOUT and master_dir().is_dir() else None


def daily_dates() -> list[str]:
    """已有截面文件的交易日 (YYYYMMDD), 升序。"""
    return sorted(p.name for p in base_dir().glob("[0-9]" * 8) if (p / XS_FILE).exists()) if base_dir().exists() else []


_symbol = S.to_symbol


# ---------------------------------------------------------------------------
# 规范化与读写
# ---------------------------------------------------------------------------
def _normalize(df: pd.DataFrame, code, name, source: str) -> pd.DataFrame:
    """统一列与类型。code / name 可以是单个值, 也可以是与 df 等长的序列 (截面)。"""
    out = pd.DataFrame(index=df.index)
    for c in COLUMNS:
        out[c] = df[c] if c in df.columns else np.nan
    out["trade_date"] = pd.to_datetime(out["trade_date"])
    out["code"] = pd.Series(code, index=df.index).astype(str).str.zfill(6)
    out["exchange"] = out["code"].map(S.exchange_prefix)
    if name is not None:
        out["name"] = name
    if "pre_close" not in df.columns or df["pre_close"].isna().all():
        out["pre_close"] = (pd.to_numeric(out["close"], errors="coerce") - pd.to_numeric(out["chg"], errors="coerce")).round(4)
    out["source"] = source
    for c in COLUMNS[4:-1]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["name"] = out["name"].astype("string")
    return out[COLUMNS]


def _hist_frame(raw: pd.DataFrame, code: str, name: str | None) -> pd.DataFrame:
    if raw is None or len(raw) == 0:
        return pd.DataFrame(columns=COLUMNS)
    return _normalize(raw.rename(columns=HIST_MAP), code, name, "hist")


def _merge(*parts: pd.DataFrame) -> pd.DataFrame:
    parts = [p for p in parts if p is not None and len(p)]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    # 同一交易日: 实时快照生成的行 (含 PE/PB/市值) 优先于历史日线
    df["_p"] = (df["source"] == "spot").astype(int)
    df = df.sort_values(["trade_date", "_p"]).drop_duplicates("trade_date", keep="last").drop(columns="_p")
    df["name"] = df["name"].ffill().bfill()
    return df.reset_index(drop=True)


def _write(df: pd.DataFrame, path: Path) -> None:
    """原子写入; trade_date 存为日期 (date32), parquet 中显示为 2026-11-06 而非毫秒时间戳。
    先写临时文件再改名: 若目标是旧版遗留的硬链接, 改名只替换这一个目录项, 不会改动其他链接。"""
    out = df.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"]).dt.date
    tmp = path.with_suffix(".parquet.tmp")
    out.to_parquet(tmp, index=False, compression="zstd")
    os.replace(tmp, path)


def _read(path: Path, **kwargs) -> pd.DataFrame:
    """读取快照 parquet, 并把 date32 的 trade_date 转回 datetime64, 便于内部比较/过滤。"""
    df = pd.read_parquet(path, **kwargs)
    if "trade_date" in df.columns:
        df["trade_date"] = pd.to_datetime(df["trade_date"])
    return df


def _write_cross_section(dkey: str, xs: pd.DataFrame) -> Path:
    """写某一交易日的截面: 先写到临时目录, 完成后整体改名, 不会留下写了一半的目录。"""
    final = base_dir() / dkey
    tmp_dir = base_dir() / f".{dkey}.tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    _write(xs.sort_values("code")[COLUMNS].reset_index(drop=True), tmp_dir / XS_FILE)
    if final.exists():
        shutil.rmtree(final)
    os.replace(tmp_dir, final)
    return final / XS_FILE


def _scan_master(trade_date: pd.Timestamp, workers: int = 8) -> pd.DataFrame:
    """从 base 逐文件读出某一交易日的全市场截面 (base 覆盖的日期没有日期目录时使用)。"""
    def one(p):
        x = _read(p, filters=[("trade_date", "==", trade_date)])
        return x if len(x) else None
    files = list(master_dir().glob("*.parquet")) if master_dir().is_dir() else []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        parts = [x for x in ex.map(one, files) if x is not None]
    return pd.concat(parts, ignore_index=True)[COLUMNS] if parts else pd.DataFrame(columns=COLUMNS)


# ---------------------------------------------------------------------------
# 下载
# ---------------------------------------------------------------------------
def _fetch_many(codes: list[str], start: str, end: str, fetch_hist: Callable, stage: Path,
                workers: int, label: str) -> dict:
    """逐只下载 [start, end] 的日线到暂存区; 已在暂存区且数据覆盖到 end 的跳过 (断点续传)。返回 {code: 失败原因}。"""
    stage.mkdir(parents=True, exist_ok=True)
    end_ts = pd.Timestamp(end)

    def _stale(code: str) -> bool:
        """文件不存在, 或已下载的数据未覆盖到 end (中断残留) 时需要重下; 空文件=已确认无数据(退市股), 不重下。"""
        p = stage / f"{_symbol(code)}.parquet"
        if not p.exists():
            return True
        try:
            d = pd.to_datetime(pd.read_parquet(p, columns=["trade_date"])["trade_date"])
            return not d.empty and d.max() < end_ts - pd.Timedelta(days=1)
        except Exception:
            return True

    todo = [c for c in codes if _stale(c)]
    if not todo:
        return {}
    log.info(f"    · {label}: 需下载 {len(todo)} 只 ({start}–{end}), 已完成 {len(codes) - len(todo)} 只")
    fails, done, t0 = {}, 0, time.time()

    def one(code):
        err = None
        for i in range(3):
            try:
                raw = fetch_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
                _write(_hist_frame(raw, code, None), stage / f"{_symbol(code)}.parquet")
                return code, None
            except Exception as e:
                err = e
                time.sleep(1.0 * (i + 1))
        return code, f"{type(err).__name__}: {err}"

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for fut in as_completed([ex.submit(one, c) for c in todo]):
            code, err = fut.result()
            done += 1
            if err:
                fails[code] = err
            if done % 500 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1e-6)
                log.info(f"      {done}/{len(todo)}  {rate:.1f} 只/秒  失败 {len(fails)}")
    return fails


# 补漏跑的交易日时, 允许部分股票下载失败 (通常是东财限流), 不反复重试:
#   第一次失败比例 <= 5%          -> 不重试, 直接继续
#   第一次失败比例 5% ~ 10%       -> 重试 1 次, 无论结果如何都继续
#   第一次失败比例 > 10%          -> 最多重试 2 次, 无论结果如何都继续
# 最终失败比例 <= MAX_MISSING (30%) 时照常写入日期目录 (缺这些股票); 超过则不写入, 下次运行续传。
RETRY_RULES = ((0.05, 0), (0.10, 1), (1.00, 2))      # (第一次失败比例上限, 重试次数)
MAX_MISSING = 0.30
RETRY_PAUSE = 60.0                                    # 每次重试前等待秒数 (让限流缓一缓)


# 1. 第一次丢失的数据比率<=5%的话，就不需要重新尝试下载数据了，直接继续往下执行
# 2. 第一次丢失的数据比率>5%且<=10%的话，就尝试一次，尝试一次后，不管结果如何，直接继续往下执行
# 3. 第一次丢失的数据比率>10%的话，最大尝试两次，不管结果如何，直接继续往下执行
def retries_for(fail_ratio: float) -> int:
    return next(n for lim, n in RETRY_RULES if fail_ratio <= lim)


def _fetch_with_retry(codes: list[str], start: str, end: str, fetch_hist: Callable, stage: Path,
                      workers: int, label: str) -> dict:
    fails = _fetch_many(codes, start, end, fetch_hist, stage, workers, label)
    n = retries_for(len(fails) / max(len(codes), 1))
    for i in range(n):
        if not fails:
            break
        log.info(f"    · 第一次失败 {len(fails)} 只, 等待 {RETRY_PAUSE:.0f} 秒后重试 ({i + 1}/{n})")
        time.sleep(RETRY_PAUSE)
        fails = _fetch_many(codes, start, end, fetch_hist, stage, workers, f"{label} (重试 {i + 1})")
    return fails


# ---------------------------------------------------------------------------
# 每日更新
# ---------------------------------------------------------------------------
def _build_base(codes: list[str], dkey: str, today_xs: pd.DataFrame, fetch_hist: Callable, workers: int,
                force: bool) -> dict:
    """首次运行: 下载上市以来的历史日线, 建立 base (覆盖到 dkey, 当日行用实时快照替换以带上 PE/PB)。"""
    full_dir = base_dir() / "_backfill" / "full"
    log.info("  · 首次建立 base: 逐只回补上市以来的历史日线 (可中断, 再次运行会从断点继续)")
    fails = _fetch_many(codes, "19900101", dkey, fetch_hist, full_dir, workers, "上市以来历史")
    if fails and not force:
        return {"status": "incomplete", "fails": fails,
                "msg": f"{len(fails)} 只下载失败, 已保存进度, 再次运行将继续。例: {list(fails.items())[:5]}"}
    tmp = base_dir() / ".base.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    rows = dict(tuple(today_xs.groupby("code")))
    n = 0
    for f in full_dir.glob("*.parquet"):
        code = f.stem[2:]
        df = _merge(_read(f), rows.get(code))
        if len(df):
            _write(df[COLUMNS], tmp / f.name)
            n += 1
    for code, r in rows.items():                     # 当天有行情、但历史下载为空的股票
        dst = tmp / f"{_symbol(code)}.parquet"
        if not dst.exists():
            _write(r[COLUMNS], dst)
            n += 1
    os.replace(tmp, master_dir())
    _save_meta({"layout": LAYOUT, "base_through": dkey, "price": "不复权", "columns": COLUMNS,
                "n_stocks": n, "updated_at": S.now_cst().isoformat(timespec="seconds")})
    shutil.rmtree(base_dir() / "_backfill", ignore_errors=True)
    return {"status": "ok", "date": dkey, "dir": str(master_dir()), "prev": None, "rows": len(today_xs),
            "base_built": n, "gap_days": 0}


def _previous_day(dkey: str) -> pd.DataFrame | None:
    """dkey 之前最近一个交易日的全市场数据 (最近的日期目录, 没有则取 base 的最后一天)。"""
    prev = [d for d in daily_dates() if d < dkey]
    if prev:
        return _read(base_dir() / prev[-1] / XS_FILE)
    bt = base_through()
    return _scan_master(pd.Timestamp(bt)) if bt else None


def stale_share(xs: pd.DataFrame, prev: pd.DataFrame | None) -> float:
    """当日数据中, 收盘价、成交额、成交量与上一交易日完全相同的股票占比。
    正常交易日这个比例接近 0 (只有极少数停牌股); 接近 1 说明拿到的是旧数据。"""
    if prev is None or not len(prev) or not len(xs):
        return 0.0
    cols = ["close", "amount", "volume"]
    m = xs[["code"] + cols].merge(prev[["code"] + cols], on="code", suffixes=("", "_p"))
    if not len(m):
        return 0.0
    same = np.ones(len(m), dtype=bool)
    for c in cols:
        same &= (m[c].to_numpy() == m[f"{c}_p"].to_numpy())
    return float(same.mean())


STALE_LIMIT = 0.9     # 超过 90% 的股票与上一交易日完全相同 -> 判定为旧数据, 拒绝写入


def update(spot: pd.DataFrame, fetch_hist: Callable, trade_date=None, workers: int = 4,
           allow_intraday: bool = False, force: bool = False, spot_is_stale: bool = False) -> dict:
    """保存 trade_date (默认最近收盘交易日) 当日的交易数据到 snapshots/<YYYYMMDD>/。base 建立后不再改动。

    spot_is_stale: 调用方已知这份全市场快照不是本次拉取的 (例如拉取失败、退回了旧缓存), 此时拒绝写入。"""
    if S.is_intraday() and not allow_intraday:
        return {"status": "skip", "msg": "盘中运行 (北京时间 15:30 前), 不保存当日数据; 加 --allow-intraday 可强制"}
    if spot_is_stale:
        return {"status": "stale", "msg": "全市场实时快照本次拉取失败、用的是旧缓存, 不能当作当日数据保存; "
                                          "下次运行会自动补上这一天"}
    D = pd.Timestamp(trade_date or S.last_closed_trade_date())
    dkey = D.strftime("%Y%m%d")
    bt = base_through()
    if bt and dkey <= bt:
        return {"status": "skip", "msg": f"{dkey} 已包含在 base 中 (base 覆盖到 {bt})"}
    if bt and dkey in daily_dates() and not force:
        return {"status": "skip", "msg": f"{dkey} 已保存"}

    if "_source" in spot and len(spot) and (spot["_source"] == "xq").all():
        return {"status": "skip", "msg": "当日行情只取得部分股票 (雪球兜底), 不保存当日快照; 下次运行会按漏跑的交易日补上"}
    # 当日行情 (一次请求得到的全市场快照)
    sp = spot.copy()
    sp["code"] = sp["代码"].astype(str).str.zfill(6)
    sp = sp[sp["code"].map(S.exchange_prefix).notna()]
    sp = sp.rename(columns=SPOT_MAP)
    sp["trade_date"] = D
    traded = sp[pd.to_numeric(sp["close"], errors="coerce").notna()]
    names = dict(zip(sp["code"], sp["name"], strict=False))
    src = "sina" if ("_source" in traded and (traded["_source"] == "sina").all()) else "spot"   # 新浪备用源: 缺换手率 / PE 等
    xs = _normalize(traded, traded["code"].values, traded["name"].values, src)

    if not bt:
        return _build_base(sorted(sp["code"]), dkey, xs, fetch_hist, workers, force)

    # ---- 漏跑的交易日: 逐只补下载, 每天写入各自的日期目录 ----
    cal = S.trade_calendar()
    last = max([bt] + [d for d in daily_dates() if d < dkey])
    gap_days = cal[(cal > pd.Timestamp(last)) & (cal < D)]
    n_gap = 0
    if len(gap_days):
        g0, g1 = gap_days[0].strftime("%Y%m%d"), gap_days[-1].strftime("%Y%m%d")
        gap_dir = base_dir() / "_backfill" / f"gap_{g0}_{g1}"
        log.info(f"  · 漏跑了 {len(gap_days)} 个交易日 ({g0}–{g1}), 逐只补下载这几天的日线")
        fails = _fetch_with_retry(sorted(sp["code"]), g0, g1, fetch_hist, gap_dir, workers, "补漏跑的交易日")
        if len(fails) > MAX_MISSING * len(sp) and not force:
            return {"status": "incomplete", "fails": fails,
                    "msg": f"{len(fails)} 只下载失败 (超过 {MAX_MISSING:.0%}), 漏跑的交易日未写入, 已保存进度, "
                           f"再次运行将继续。例: {list(fails.items())[:5]}"}
        if fails:
            missing = sorted(fails)
            log.info(f"    · 仍有 {len(missing)} 只 ({len(missing) / len(sp):.1%}) 未下载到, 在允许范围内, "
                  f"这几天的截面缺这些股票: {', '.join(missing[:10])}{' …' if len(missing) > 10 else ''}")
            meta = _meta()
            meta.setdefault("gap_missing", {}).update({d.strftime("%Y%m%d"): missing for d in gap_days})
            _save_meta(meta)
        parts = [x for x in (_read(f) for f in gap_dir.glob("*.parquet")) if len(x)]
        if parts:
            g = pd.concat(parts, ignore_index=True)
            g["name"] = g["code"].map(names).astype("string")
            for day, x in g[g["trade_date"].isin(gap_days)].groupby("trade_date"):
                _write_cross_section(day.strftime("%Y%m%d"), x)
                n_gap += 1
        shutil.rmtree(gap_dir, ignore_errors=True)

    # ---- 当日数据: 先确认不是旧数据 (例如接口返回了上一交易日的快照) ----
    share = stale_share(xs, _previous_day(dkey))
    if share > STALE_LIMIT and not force:
        return {"status": "stale", "msg": f"当日快照中 {share:.0%} 的股票与上一交易日完全相同, 判定为旧数据, 未保存; "
                                          "下次运行会自动补上这一天"}
    xs_path = _write_cross_section(dkey, xs)
    shutil.rmtree(base_dir() / "_backfill", ignore_errors=True)
    in_base = {f.stem[2:] for f in master_dir().glob("*.parquet")}
    n_not_in_base = int((~xs["code"].isin(in_base)).sum())
    meta = _meta()
    meta.update(daily=daily_dates(), latest=dkey, updated_at=S.now_cst().isoformat(timespec="seconds"))
    _save_meta(meta)
    merged = [m for m in ensure_merged() if not m.startswith("-")]
    return {"status": "ok", "date": dkey, "dir": str(xs_path.parent), "prev": last, "rows": len(xs),
            "gap_days": n_gap, "not_in_base": n_not_in_base, "base_built": 0, "merged": merged}


# ---------------------------------------------------------------------------
# 按月合并缓存 (派生数据, 可随时删除重建)
# ---------------------------------------------------------------------------
# 日期目录越积越多后, 逐只读取股票要打开几百个文件 (243 天约 220ms/只)。每个月结束后把该月的日期目录
# 合并成一个按 (code, trade_date) 排序的文件 _merged/YYYYMM.parquet, 读单只股票只需打开一个文件的几个行组。
# 日期目录和 base 都不改动; _manifest.json 记录每个合并文件由哪些日期目录 (大小 + 修改时间) 生成,
# 日期目录有变化 (如事后补了漏跑的一天) 时自动重建。
MERGED_DIR = "_merged"
ROW_GROUP = 20_000            # 每个行组约 20000 行 (约 4 个交易日的全市场), 按 code 过滤时可跳过无关行组


def merged_dir() -> Path:
    return base_dir() / MERGED_DIR


def _month_days() -> dict[str, list[str]]:
    """base 之后的日期目录按月分组: {YYYYMM: [YYYYMMDD, ...]}。"""
    bt = base_through()
    out: dict[str, list[str]] = {}
    for d in daily_dates():
        if bt is None or d > bt:
            out.setdefault(d[:6], []).append(d)
    return out


def _signature(days: list[str]) -> list[list]:
    """一组日期目录的指纹: [日期, 文件大小, 修改时间]。任何一个日期目录增删或重写, 指纹就会变。"""
    sig = []
    for d in days:
        st = (base_dir() / d / XS_FILE).stat()
        sig.append([d, st.st_size, st.st_mtime_ns])
    return sig


def _manifest() -> dict:
    p = merged_dir() / "_manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_manifest(m: dict) -> None:
    merged_dir().mkdir(parents=True, exist_ok=True)
    p = merged_dir() / "_manifest.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def _complete_months(groups: dict[str, list[str]]) -> list[str]:
    """已经结束的月份: 之后已有更晚月份的日期目录。当月 (最新一个月) 还在增加, 不合并。"""
    months = sorted(groups)
    return months[:-1]


def ensure_merged() -> list[str]:
    """为每个已结束的月份建立 / 更新合并文件; 删除已无对应日期目录的合并文件。返回本次 (重)建的月份。"""
    groups = _month_days()
    done = _complete_months(groups)
    man = _manifest()
    built = []
    for mon in done:
        sig = _signature(groups[mon])
        f = merged_dir() / f"{mon}.parquet"
        if f.exists() and man.get(mon) == sig:
            continue
        df = pd.concat([_read(base_dir() / d / XS_FILE) for d in groups[mon]], ignore_index=True)
        df = df.sort_values(["code", "trade_date"]).reset_index(drop=True)
        merged_dir().mkdir(parents=True, exist_ok=True)
        out = df.copy()
        out["trade_date"] = out["trade_date"].dt.date
        tmp = f.with_suffix(".parquet.tmp")
        out[COLUMNS].to_parquet(tmp, index=False, compression="zstd", row_group_size=ROW_GROUP)
        os.replace(tmp, f)
        man[mon] = sig
        built.append(mon)
    for mon in [m for m in man if m not in done]:          # 月份变成"未结束"或日期目录被删除
        (merged_dir() / f"{mon}.parquet").unlink(missing_ok=True)
        man.pop(mon)
        built.append(f"-{mon}")
    if built:
        _save_manifest(man)
    return built


_SRC_CACHE: tuple | None = None       # (目录指纹, 文件列表): 同一进程内反复读取时不必每次核对清单


def _dir_key() -> tuple:
    """新增 / 重写日期目录都会改变 snapshots/ 目录本身的修改时间; 合并文件变化会改变清单的修改时间。"""
    man = merged_dir() / "_manifest.json"
    return (str(base_dir()), base_dir().stat().st_mtime_ns, man.stat().st_mtime_ns if man.exists() else 0)


def _daily_sources() -> list[tuple[Path, list[str]]]:
    """读取 base 之后数据的文件列表: [(文件, 包含的日期)]。已结束的月份用合并文件, 其余用日期目录。"""
    global _SRC_CACHE
    if not base_dir().exists():
        return []
    key = _dir_key()
    if _SRC_CACHE is not None and _SRC_CACHE[0] == key:
        return _SRC_CACHE[1]
    out = _build_sources()
    _SRC_CACHE = (_dir_key(), out)
    return out


def _build_sources() -> list[tuple[Path, list[str]]]:
    try:
        ensure_merged()
    except OSError as e:                     # 只读环境等: 合并缓存只是加速, 失败时直接读日期目录
        log.warning(f"  ! 合并缓存不可用, 直接读取日期目录: {e}")
    groups = _month_days()
    man = _manifest()
    out = []
    for mon, days in sorted(groups.items()):
        f = merged_dir() / f"{mon}.parquet"
        if f.exists() and man.get(mon) == _signature(days):
            out.append((f, days))
        else:
            out += [(base_dir() / d / XS_FILE, [d]) for d in days]
    return out


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
def load_daily(start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """base 之后的全部交易数据 (全市场, 按日期)。start / end 为 YYYY-MM-DD 或 YYYYMMDD, 均含。"""
    lo = pd.Timestamp(start).strftime("%Y%m%d") if start else None
    hi = pd.Timestamp(end).strftime("%Y%m%d") if end else None
    parts = []
    for f, days in _daily_sources():
        if (lo and days[-1] < lo) or (hi and days[0] > hi):
            continue
        parts.append(_read(f))
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    if lo:
        df = df[df["trade_date"] >= pd.Timestamp(lo)]
    if hi:
        df = df[df["trade_date"] <= pd.Timestamp(hi)]
    return df.sort_values(["trade_date", "code"]).reset_index(drop=True)[COLUMNS]


def load_stock(symbol: str, asof: str | None = None) -> pd.DataFrame:
    """单只股票的全部日线 = base 中的历史 + base 之后的数据 (已结束的月份读合并文件, 当月读日期目录)。
    symbol 如 'SH600519'; asof 为截止日期 (含)。"""
    symbol = symbol.upper()
    code = symbol[2:]
    p = master_dir() / f"{symbol}.parquet"
    parts = [_read(p)] if p.exists() else []
    hi = pd.Timestamp(asof).strftime("%Y%m%d") if asof else None
    for f, days in _daily_sources():
        if hi and days[0] > hi:
            continue
        x = _read(f, filters=[("code", "==", code)])
        if len(x):
            parts.append(x)
    if not parts:
        raise FileNotFoundError(f"没有 {symbol} 的快照数据")
    df = _merge(*parts)[COLUMNS]
    if asof is not None:
        df = df[df["trade_date"] <= pd.Timestamp(asof)].reset_index(drop=True)
    return df


def load_cross_section(trade_date: str, workers: int = 8) -> pd.DataFrame:
    """某一交易日的全市场截面。base 之后的日期直接读该日期目录; base 覆盖的日期从 base 逐文件抽取 (较慢)。"""
    t = pd.Timestamp(trade_date)
    p = base_dir() / t.strftime("%Y%m%d") / XS_FILE
    if p.exists():
        return _read(p)
    return _scan_master(t, workers)

