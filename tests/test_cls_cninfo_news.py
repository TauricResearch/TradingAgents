"""Tests for CLS flash news + Cninfo disclosures + multi-source merge.

Pins:
  1. CLS filters the global flash stream by ticker / company-name match
     and applies the requested date window.
  2. CLS skips non-Asian-market tickers explicitly.
  3. Cninfo only handles SH/SZ; HK/US tickers get a labelled skip marker.
  4. Cninfo formats akshare's disclosure DataFrame into Markdown with
     filing title / date / link.
  5. Auto-router resolves SS/SZ → [eastmoney, cls, cninfo] and HK →
     [eastmoney, cls].
  6. ``route_to_vendor`` calls every vendor in the resolved list and
     concatenates non-empty results separated by ``---``.
  7. Pure skip-markers from a non-applicable vendor are dropped so the
     LLM doesn't get padded with no-op noise.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from tradingagents.dataflows import cls_news as cls
from tradingagents.dataflows import cninfo_disclosures as cninfo
from tradingagents.dataflows import interface as iface
from tradingagents.dataflows.config import set_config


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    set_config({
        "data_cache_dir": str(tmp_path),
        "data_vendors": {"news_data": "auto"},
        "tool_vendors": {},
    })
    cls._NAME_CACHE.clear()
    yield


def _cls_frame(rows):
    return pd.DataFrame(rows, columns=["标题", "内容", "发布日期", "发布时间"])


def _cninfo_frame(rows):
    return pd.DataFrame(rows, columns=["代码", "简称", "公告标题", "公告时间", "公告链接"])


# --- CLS ---------------------------------------------------------------

def test_cls_matches_ticker_and_filters_dates():
    fake = _cls_frame([
        ["腾讯控股回购股份", "腾讯今日宣布回购计划。", "2026-05-08", "09:30:00"],
        ["其他公司新闻", "与本案无关。", "2026-05-08", "10:00:00"],
        ["腾讯Q1业绩", "营收增长。", "2024-01-01", "09:00:00"],  # outside window
    ])
    with patch("akshare.stock_info_global_cls", return_value=fake), \
         patch("tradingagents.dataflows.cls_news._resolve_company_short_name", return_value="腾讯"):
        out = cls.get_news_cls("0700.HK", "2026-05-01", "2026-05-15")

    assert "腾讯控股回购股份" in out
    assert "其他公司新闻" not in out
    assert "腾讯Q1业绩" not in out  # date filter


def test_cls_skips_non_asian_market():
    out = cls.get_news_cls("AAPL", "2026-05-01", "2026-05-10")
    assert "skip" in out.lower()


def test_cls_handles_fetch_error():
    with patch("akshare.stock_info_global_cls", side_effect=RuntimeError("network")):
        out = cls.get_news_cls("0700.HK", "2026-05-01", "2026-05-10")
    assert "fetch failed" in out.lower()


# --- Cninfo ------------------------------------------------------------

def test_cninfo_formats_disclosure_frame():
    fake = _cninfo_frame([
        ["600519", "贵州茅台", "贵州茅台关于回购股份实施进展的公告", "2026-05-08", "https://cninfo.com.cn/x"],
        ["600519", "贵州茅台", "贵州茅台关于召开业绩说明会的公告", "2026-04-29", "https://cninfo.com.cn/y"],
    ])
    with patch("akshare.stock_zh_a_disclosure_report_cninfo", return_value=fake):
        out = cninfo.get_disclosures_cninfo("600519.SS", "2026-04-01", "2026-05-10")

    assert "贵州茅台关于回购股份实施进展的公告" in out
    assert "https://cninfo.com.cn/x" in out
    assert "巨潮" in out


def test_cninfo_skips_hk_and_us():
    out = cninfo.get_disclosures_cninfo("0700.HK", "2026-05-01", "2026-05-10")
    assert "skip" in out.lower()
    out = cninfo.get_disclosures_cninfo("AAPL", "2026-05-01", "2026-05-10")
    assert "skip" in out.lower()


def test_cninfo_handles_empty_result():
    with patch("akshare.stock_zh_a_disclosure_report_cninfo", return_value=pd.DataFrame()):
        out = cninfo.get_disclosures_cninfo("600519.SS", "2026-05-01", "2026-05-10")
    assert "No Cninfo filings" in out


@pytest.mark.parametrize("ann_id,org_id,ann_time", [
    ("20260508001234", "9900016138", "2026-05-08"),
    ("20260101005678", "9900019999", "2026-01-01"),
])
def test_cninfo_build_link_reconstructs_from_announcement_id(ann_id, org_id, ann_time):
    """_build_link Path B: no 公告链接 column; reconstruct URL from announcementId + orgId + 公告时间."""
    fake = pd.DataFrame([{
        "代码": "600519",
        "简称": "贵州茅台",
        "公告标题": "测试公告",
        "公告时间": ann_time,
        "announcementId": ann_id,
        "orgId": org_id,
    }])
    with patch("akshare.stock_zh_a_disclosure_report_cninfo", return_value=fake):
        out = cninfo.get_disclosures_cninfo("600519.SS", "2026-01-01", "2026-12-31")

    assert "cninfo.com.cn" in out
    assert f"announcementId={ann_id}" in out
    assert f"orgId={org_id}" in out


# --- Auto-router multi-source ----------------------------------------

def test_auto_router_returns_list_for_ss():
    vendors = iface._resolve_auto_vendors("get_news", ("600519.SS",))
    assert vendors == ["eastmoney", "cls", "cninfo"]


def test_auto_router_returns_list_for_sz():
    vendors = iface._resolve_auto_vendors("get_news", ("000001.SZ",))
    assert vendors == ["eastmoney", "cls", "cninfo"]


def test_auto_router_returns_list_for_hk():
    vendors = iface._resolve_auto_vendors("get_news", ("0700.HK",))
    assert vendors == ["eastmoney", "cls"]


def test_auto_router_us_stays_single_yfinance():
    assert iface._resolve_auto_vendors("get_news", ("AAPL",)) == ["yfinance"]


def test_auto_router_global_news_always_yfinance():
    assert iface._resolve_auto_vendors("get_global_news", ("2026-05-08", 7, 10)) == ["yfinance"]


def test_route_to_vendor_merges_multiple_sources_for_ss():
    """SS ticker fans out to eastmoney + cls + cninfo; results concatenate."""
    fake_em = _cls_frame([])  # placeholder, eastmoney mock returns string directly
    iface_orig = iface.VENDOR_METHODS["get_news"].copy()
    try:
        iface.VENDOR_METHODS["get_news"]["eastmoney"] = lambda *a, **kw: "<eastmoney body>"
        iface.VENDOR_METHODS["get_news"]["cls"] = lambda *a, **kw: "<cls body>"
        iface.VENDOR_METHODS["get_news"]["cninfo"] = lambda *a, **kw: "<cninfo body>"
        out = iface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-05-10")
    finally:
        iface.VENDOR_METHODS["get_news"] = iface_orig

    assert "<eastmoney body>" in out
    assert "<cls body>" in out
    assert "<cninfo body>" in out
    # Sources separated by --- so the LLM sees clear demarcation.
    assert "---" in out


def test_route_to_vendor_drops_pure_skip_markers():
    """If a vendor returns a [skip — ...] marker, it's omitted from the merge
    so the analyst doesn't get prompts polluted with no-op noise."""
    iface_orig = iface.VENDOR_METHODS["get_news"].copy()
    try:
        iface.VENDOR_METHODS["get_news"]["eastmoney"] = lambda *a, **kw: "real eastmoney content"
        iface.VENDOR_METHODS["get_news"]["cls"] = lambda *a, **kw: "[CLS skip — HK suffix routed elsewhere]"
        iface.VENDOR_METHODS["get_news"]["cninfo"] = lambda *a, **kw: "real cninfo content"
        out = iface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-05-10")
    finally:
        iface.VENDOR_METHODS["get_news"] = iface_orig

    assert "real eastmoney content" in out
    assert "real cninfo content" in out
    assert "CLS skip" not in out


def test_route_to_vendor_survives_per_vendor_failure():
    """One source raising must not block the others."""
    iface_orig = iface.VENDOR_METHODS["get_news"].copy()
    try:
        iface.VENDOR_METHODS["get_news"]["eastmoney"] = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network"))
        iface.VENDOR_METHODS["get_news"]["cls"] = lambda *a, **kw: "<cls body>"
        iface.VENDOR_METHODS["get_news"]["cninfo"] = lambda *a, **kw: "<cninfo body>"
        out = iface.route_to_vendor("get_news", "600519.SS", "2026-05-01", "2026-05-10")
    finally:
        iface.VENDOR_METHODS["get_news"] = iface_orig

    assert "<cls body>" in out
    assert "<cninfo body>" in out
    # No network error leaks to the analyst — failure is logged, not surfaced.


def test_auto_router_si_routes_to_yfinance():
    """SG (.SI) tickers must currently fall through to yfinance — the
    SGX vendor is held back from this PR pending more end-to-end testing."""
    assert iface._resolve_auto_vendors("get_news", ("D05.SI",)) == ["yfinance"]
