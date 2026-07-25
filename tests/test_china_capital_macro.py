"""Contract tests for optional China capital-flow and macro source adapters."""

from __future__ import annotations

import pandas as pd
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.china_capabilities import AshareCapabilityUnavailableError
from tradingagents.dataflows.china_capital_flow import ChinaCapitalFlowProvider
from tradingagents.dataflows.china_macro import ChinaMacroProvider


class _CapitalApi:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_hsgt_hist_em(self, **kwargs):
        self.calls.append(("flow", kwargs))
        return pd.DataFrame(
            [
                {"日期": "2026-07-01", "北向资金": 10},
                {"日期": "2026-07-02", "北向资金": -5},
            ]
        )

    def stock_hsgt_hold_stock_em(self, **kwargs):
        self.calls.append(("holdings", kwargs))
        return pd.DataFrame(
            [
                {"代码": "600519", "名称": "贵州茅台", "持股市值": 100},
                {"代码": "000001", "名称": "平安银行", "持股市值": 10},
            ]
        )

    def stock_ggcg_em(self, **kwargs):
        self.calls.append(("insider", kwargs))
        return pd.DataFrame(
            [
                {"证券代码": "600519", "变动日期": "2026-07-01", "变动人": "示例高管"},
                {"证券代码": "000001", "变动日期": "2026-07-01", "变动人": "他人"},
            ]
        )


class _MacroApi:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def macro_china_gdp(self):
        self.calls.append("gdp")
        return pd.DataFrame([{"季度": "2026Q1", "国内生产总值": 1.0}])

    def macro_china_cpi(self):
        self.calls.append("cpi")
        return pd.DataFrame([{"月份": "2026-06", "同比": 0.1}])


def test_northbound_flow_honours_source_date_window_and_keeps_scope_explicit():
    api = _CapitalApi()

    report = ChinaCapitalFlowProvider(api).northbound_flow("2026-07-02", "2026-07-02")

    assert report.ticker is None
    assert report.data["日期"].tolist() == ["2026-07-02"]
    assert api.calls == [("flow", {"symbol": "北向资金"})]
    assert "not an attribution" in report.render()


def test_northbound_and_insider_reports_filter_market_wide_rows_to_requested_ticker():
    api = _CapitalApi()
    provider = ChinaCapitalFlowProvider(api)

    holdings = provider.northbound_holdings("600519", "3日排行")
    insider = provider.insider_trades("600519", "2026-07-01", "2026-07-01")

    assert holdings.ticker == "600519.SS"
    assert holdings.data["代码"].tolist() == ["600519"]
    assert insider.data["证券代码"].tolist() == ["600519"]
    assert "not a complete beneficial-ownership register" in holdings.render()
    assert "must be verified against the source filing" in insider.render()
    assert api.calls == [
        ("holdings", {"market": "北向", "indicator": "3日排行"}),
        ("insider", {"symbol": "全部"}),
    ]


def test_capital_adapters_fail_closed_for_non_a_share_or_unrecognized_schema():
    api = _CapitalApi()
    provider = ChinaCapitalFlowProvider(api)

    with pytest.raises(AshareCapabilityUnavailableError, match="not an A-share ticker"):
        provider.insider_trades("AAPL")

    with pytest.raises(AshareCapabilityUnavailableError, match="unsupported indicator"):
        provider.northbound_holdings("600519", "任意排行")

    assert api.calls == []


def test_china_macro_series_are_explicitly_labelled_and_partial_unavailability_is_visible():
    api = _MacroApi()

    report = ChinaMacroProvider(api).indicators("gdp,cpi,pmi")

    assert api.calls == ["gdp", "cpi"]
    assert set(report.data["indicator"]) == {"gdp", "cpi"}
    rendered = report.render()
    assert "Source: akshare" in rendered
    assert "no cycle stage is inferred" in rendered
    assert "Unavailable requested series: pmi:" in rendered


def test_china_macro_unknown_indicator_and_empty_provider_fail_closed():
    with pytest.raises(AshareCapabilityUnavailableError, match="unsupported indicator"):
        ChinaMacroProvider(_MacroApi()).indicators("gdp,imaginary")

    with pytest.raises(AshareCapabilityUnavailableError, match="has no macro_china_gdp adapter"):
        ChinaMacroProvider(object()).indicators("gdp")


def test_new_optional_capabilities_route_with_a_share_market_scope(monkeypatch):
    calls: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "akshare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_a_share_northbound_holdings",
        {"akshare": lambda *args: calls.append(("northbound", args)) or "holding rows"},
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_china_macro_indicators",
        {"akshare": lambda *args: calls.append(("macro", args)) or "macro rows"},
    )

    assert interface.route_to_vendor("get_a_share_northbound_holdings", "600519") == "holding rows"
    assert interface.route_to_vendor("get_china_macro_indicators", "gdp,cpi") == "macro rows"
    assert interface._market_for_request(("gdp,cpi",), "get_china_macro_indicators") == "a_share"
    assert calls == [("northbound", ("600519",)), ("macro", ("gdp,cpi",))]
