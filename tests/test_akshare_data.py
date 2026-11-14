"""A 股数据层 (tradingagents.dataflows.vendors.akshare): 缓存 / 增量 / 行情 / 个股快照, 全部离线, 在临时目录中进行。"""
from __future__ import annotations

import sys
import types

import numpy as np
import pandas as pd
import pytest

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.vendors.akshare import (
    settings,
    snapshots as SN,
    spot as SP,
    store as S,
)

pytestmark = pytest.mark.unit

TODAY = "2026-11-10"
CODES = ["600000", "000001", "300750", "688981", "920001"]


@pytest.fixture
def data(tmp_path, monkeypatch):
    """临时数据目录 + 固定时钟 (最近收盘交易日 = TODAY, 非盘中) + 工作日日历。"""
    settings.set_data_dir(tmp_path / ".akshare_data")
    clock = {"day": pd.Timestamp(TODAY).date(), "intraday": False}
    monkeypatch.setattr(S, "last_closed_trade_date", lambda now=None: clock["day"])
    monkeypatch.setattr(S, "is_intraday", lambda now=None: clock["intraday"])
    monkeypatch.setattr(S, "_CAL", pd.bdate_range("2026-01-01", "2027-12-31"))
    monkeypatch.setattr(S.time, "sleep", lambda s: None)
    monkeypatch.setattr(SN, "RETRY_PAUSE", 0.0)
    monkeypatch.setattr(SP, "EM_PAUSE", (0.0, 0.0))
    S.FALLBACKS.clear()
    SP.NOTES.clear()
    SN._SRC_CACHE = None
    yield clock
    settings.set_data_dir(None)
    SN._SRC_CACHE = None


# ---------------------------------------------------------------------------
# 设置与工具
# ---------------------------------------------------------------------------
def test_data_dir_resolution(tmp_path, monkeypatch):
    settings.set_data_dir(None)
    monkeypatch.delenv(settings.DATA_DIR_ENV, raising=False)
    assert settings.data_dir() == settings.REPO_ROOT / ".akshare_data"
    monkeypatch.setenv(settings.DATA_DIR_ENV, str(tmp_path / "env"))
    assert settings.data_dir() == (tmp_path / "env").resolve()
    settings.set_data_dir(tmp_path / "explicit")
    assert settings.data_dir() == (tmp_path / "explicit").resolve()
    settings.set_data_dir(None)


def test_exchange_prefix_and_symbol():
    assert [S.exchange_prefix(c) for c in ["600519", "688981", "000001", "300750", "920001", "830799", "123456"]] \
        == ["SH", "SH", "SZ", "SZ", "BJ", "BJ", None]
    assert S.to_symbol("600519") == "SH600519" and S.to_symbol("1") == "SZ000001"


def test_missing_akshare_is_a_configuration_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "akshare", None)
    with pytest.raises(VendorNotConfiguredError, match="ashare"):
        S.ak()


def test_reading_local_data_does_not_import_akshare():
    import subprocess
    code = ("import sys; import tradingagents.dataflows.vendors.akshare as A; "
            "A.status(); print('akshare' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


# ---------------------------------------------------------------------------
# 分层缓存 / 增量序列
# ---------------------------------------------------------------------------
def test_cached_hits_rolls_over_and_falls_back(data):
    calls = []

    def fn():
        calls.append(1)
        return pd.DataFrame({"x": [len(calls)]})

    assert S.cached("m", fn)["x"].iat[0] == 1
    assert S.cached("m", fn)["x"].iat[0] == 1 and len(calls) == 1, "同一交易日命中缓存"
    data["day"] = pd.Timestamp("2026-11-11").date()
    assert S.cached("m", fn)["x"].iat[0] == 2
    assert sorted(p.name for p in S.root().glob("m__*.pkl")) == ["m__20261111.pkl"], "新键写入后删除旧键"

    data["day"] = pd.Timestamp("2026-11-12").date()
    df = S.cached("m", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    assert df["x"].iat[0] == 2 and "m" in S.FALLBACKS


def test_cached_daily_not_written_intraday(data):
    data["intraday"] = True
    S.cached("q", lambda: pd.DataFrame({"x": [1]}))
    assert not list(S.root().glob("q__*.pkl"))


def test_incremental_fetches_only_the_missing_tail(data):
    full = pd.DataFrame({"date": pd.bdate_range("2026-10-01", "2026-11-10").strftime("%Y-%m-%d")})
    full["close"] = np.arange(len(full), dtype=float)
    starts = []

    def fetch(start):
        starts.append(start)
        lo = pd.Timestamp(start).strftime("%Y-%m-%d")
        return full[(full["date"] >= lo) & (full["date"] <= str(data["day"]))]

    data["day"] = pd.Timestamp("2026-11-05").date()
    assert len(S.incremental("idx", fetch, "date", "20260101")) == len(full[full["date"] <= "2026-11-05"])
    data["day"] = pd.Timestamp("2026-11-10").date()
    df = S.incremental("idx", fetch, "date", "20260101")
    assert starts == ["20260101", "20261026"], "第二次只从最后日期回溯 10 天开始"
    assert len(df) == len(full) and df["date"].is_unique
    S.incremental("idx", fetch, "date", "20260101")
    assert len(starts) == 2, "已覆盖到最近收盘日时不再下载"


# ---------------------------------------------------------------------------
# 全市场行情
# ---------------------------------------------------------------------------
N = 450                                                   # 东财 5 页 (每页 100)


def em_rows():
    return [{"f12": f"{600000 + i:06d}", "f14": f"股{i}", "f2": 10.0, "f3": 1.0, "f4": 0.1, "f5": 1000.0,
             "f6": 1e7, "f8": 1.0, "f9": 20.0, "f18": 9.9, "f20": 2e9, "f21": 1e9, "f23": 2.0} for i in range(N)]


def sina_df(n=3500, price=11.0):
    return pd.DataFrame({"代码": [f"{600000 + i:06d}" for i in range(n)], "名称": [f"股{i}" for i in range(n)],
                         "最新价": price, "涨跌幅": 1.0, "涨跌额": 0.1, "成交量": 2000.0, "成交额": 2.2e7,
                         "最高": price, "最低": price, "今开": price, "昨收": 10.9, "_source": "sina"})


def boom(*a, **k):
    raise ConnectionError("不可用")


@pytest.fixture
def em(data, monkeypatch):
    rows = em_rows()
    state = {"fail_at": None, "calls": []}

    def page(pn):
        state["calls"].append(pn)
        if state["fail_at"] is not None and pn >= state["fail_at"]:
            raise ConnectionError("模拟限流")
        return {"total": N, "rows": rows[(pn - 1) * 100: pn * 100]}
    monkeypatch.setattr(SP, "fetch_em_page", page)
    monkeypatch.setattr(SP, "fetch_sina", lambda: sina_df())
    monkeypatch.setattr(SP, "fetch_xq", boom)
    return state


def test_spot_sina_first_and_enriched_from_em_reference(em):
    SP.update_ref(SP.fetch_em("20261109", persist=False), "20261109")
    em["calls"].clear()
    df = SP.fetch_spot()
    assert (df["_source"] == "sina").all() and em["calls"] == []
    r = df.iloc[0]
    assert r["换手率"] == pytest.approx(0.2) and r["流通市值"] == pytest.approx(1e8 * 11)
    assert r["市盈率-动态"] == pytest.approx(11 / (10 / 20)) and r["市净率"] == pytest.approx(11 / 5)
    assert (S.root() / "spot__20261110.pkl").exists()


def test_spot_falls_to_em_with_resume(em, monkeypatch):
    monkeypatch.setattr(SP, "fetch_sina", boom)
    em["fail_at"] = 3
    with pytest.raises(RuntimeError):
        SP.fetch_spot()
    assert em["calls"] == [1, 2, 3], "东财被限流后立即停止"
    em["fail_at"] = None
    em["calls"].clear()
    df = SP.fetch_spot()
    assert em["calls"] == [3, 4, 5] and len(df) == N and (df["_source"] == "eastmoney").all()
    assert SP.load_ref() is not None


def test_spot_xq_is_last_resort_and_not_cached(em, monkeypatch):
    monkeypatch.setattr(SP, "fetch_sina", boom)
    em["fail_at"] = 1
    xq = pd.DataFrame({"代码": ["600000"], "名称": ["甲"], "最新价": [10.0], "昨收": [9.9], "_source": ["xq"]})
    seen = {}
    monkeypatch.setattr(SP, "fetch_xq", lambda codes: seen.setdefault("codes", codes) and xq)
    df = SP.fetch_spot(xq_codes=["600000"])
    assert seen["codes"] == ["600000"] and (df["_source"] == "xq").all() and "spot_warn" in SP.NOTES
    assert not (S.root() / "spot__20261110.pkl").exists()


def test_spot_all_fail_uses_stale_cache(em, monkeypatch):
    monkeypatch.setattr(SP, "fetch_sina", boom)
    em["fail_at"] = 1
    pd.DataFrame({"代码": ["600000"], "最新价": [9.0]}).to_pickle(S.root() / "spot__20261106.pkl")
    df = SP.fetch_spot()
    assert df["最新价"].iat[0] == 9.0 and "spot" in S.FALLBACKS
    assert SP.NOTES["spot_failed"].startswith("当日行情数据获取失败")


def test_xq_requires_token_and_codes(monkeypatch):
    monkeypatch.delenv("XQ_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="XQ_TOKEN"):
        SP.fetch_xq(["600000"])
    with pytest.raises(RuntimeError, match="xq_codes"):
        SP.fetch_xq(None, token="t")


def test_sina_columns_and_units(monkeypatch):
    fake = types.ModuleType("akshare")
    fake.stock_zh_a_spot = lambda: pd.DataFrame({
        "代码": ["sh600000", "bj920001"] + [f"sz{i:06d}" for i in range(3200)], "名称": "x", "最新价": 10.0,
        "涨跌额": 0.1, "涨跌幅": 1.0, "昨收": 9.9, "今开": 9.9, "最高": 10.1, "最低": 9.8,
        "成交量": 123400.0, "成交额": 1.2e6})
    monkeypatch.setitem(sys.modules, "akshare", fake)
    df = SP.fetch_sina()
    assert list(df["代码"][:2]) == ["600000", "920001"] and df["成交量"].iat[0] == pytest.approx(1234.0)


# ---------------------------------------------------------------------------
# 个股快照: base + 日期目录
# ---------------------------------------------------------------------------
def fake_hist(fail=()):
    calls = []

    def hist(symbol, period="daily", start_date="19900101", end_date="20500101", adjust=""):
        calls.append((symbol, start_date, end_date))
        if symbol in fail:
            raise ConnectionError("限流")
        days = pd.bdate_range(max(pd.Timestamp(start_date), pd.Timestamp("2026-10-01")), end_date)
        px = 10.0 + int(symbol) % 7 + np.arange(len(days)) * 0.1
        return pd.DataFrame({"日期": days.strftime("%Y-%m-%d"), "开盘": px, "收盘": px, "最高": px, "最低": px,
                             "成交量": 1e4, "成交额": px * 1e6, "振幅": 0.0, "涨跌幅": 0.0, "涨跌额": 0.0,
                             "换手率": 1.0})
    hist.calls = calls
    return hist


def spot_for(day: str, bump: float = 0.0):
    i = (pd.Timestamp(day) - pd.Timestamp("2026-10-01")).days
    return pd.DataFrame({"代码": CODES, "名称": [f"股{c}" for c in CODES],
                         "最新价": [20.0 + k + i + bump for k in range(len(CODES))], "成交额": 1e8 + i,
                         "成交量": 1e5 + i, "涨跌额": 0.1, "市盈率-动态": 15.0, "_source": "eastmoney"})


def test_snapshot_builds_base_then_daily_dirs_and_backfills_gaps(data):
    hist = fake_hist()
    res = SN.update(spot_for(TODAY), hist)
    assert res["status"] == "ok" and res["base_built"] == len(CODES) and SN.base_through() == "20261110"
    moutai = SN.load_stock("SH600000")
    assert moutai["trade_date"].max() == pd.Timestamp(TODAY)
    assert moutai.iloc[-1]["source"] == "spot" and moutai.iloc[-1]["pe_dynamic"] == 15.0, "当日行用实时快照替换"

    data["day"] = pd.Timestamp("2026-11-11").date()
    res = SN.update(spot_for("2026-11-11"), hist)
    assert res["status"] == "ok" and SN.daily_dates() == ["20261111"]
    assert SN.update(spot_for("2026-11-11"), hist)["status"] == "skip", "同一天不重复保存"

    data["day"] = pd.Timestamp("2026-11-16").date()                  # 漏跑 11-12、11-13
    hist.calls.clear()
    res = SN.update(spot_for("2026-11-16"), hist)
    assert res["gap_days"] == 2 and SN.daily_dates() == ["20261111", "20261112", "20261113", "20261116"]
    assert {(s, e) for _, s, e in hist.calls} == {("20261112", "20261113")}
    assert len(SN.load_cross_section("2026-11-13")) == len(CODES)
    assert len(SN.load_stock("SH600000", asof="2026-11-12")) == len(SN.load_stock("SH600000")) - 2


def test_snapshot_rejects_stale_and_partial_spot(data):
    SN.update(spot_for(TODAY), fake_hist())
    data["day"] = pd.Timestamp("2026-11-11").date()
    same = spot_for(TODAY)                                             # 与上一交易日完全相同
    assert SN.update(same, fake_hist())["status"] == "stale"
    assert SN.update(spot_for("2026-11-11"), fake_hist(), spot_is_stale=True)["status"] == "stale"
    assert SN.update(spot_for("2026-11-11").assign(_source="xq"), fake_hist())["status"] == "skip"
    data["intraday"] = True
    assert SN.update(spot_for("2026-11-11"), fake_hist())["status"] == "skip"
    assert SN.daily_dates() == []


def test_merged_months_match_daily_dirs(data):
    SN.update(spot_for("2026-10-30"), fake_hist(), trade_date="2026-10-30")
    rng = np.random.default_rng(0)
    for d in pd.bdate_range("2026-11-02", "2027-01-08"):
        xs = pd.DataFrame({"trade_date": d, "code": CODES, "name": "x", "close": rng.uniform(5, 50, len(CODES)),
                           "amount": 1e8, "volume": 1e5})
        SN._write_cross_section(d.strftime("%Y%m%d"), SN._normalize(xs, xs["code"].values, None, "spot"))
    assert SN.ensure_merged() == ["202611", "202612"] and SN.ensure_merged() == []
    for c in CODES:
        sym = S.to_symbol(c)
        expected = SN._merge(SN._read(SN.master_dir() / f"{sym}.parquet"),
                             *[SN._read(SN.base_dir() / d / SN.XS_FILE, filters=[("code", "==", c)])
                               for d in SN.daily_dates()])[SN.COLUMNS]
        pd.testing.assert_frame_equal(SN.load_stock(sym), expected)
    assert len(SN.load_daily("2026-12-01", "2026-12-31")) == len(pd.bdate_range("2026-12-01", "2026-12-31")) * 5
