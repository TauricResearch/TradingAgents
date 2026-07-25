"""Regression tests for optional, source-labelled A-share specialty adapters."""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from tradingagents.dataflows import china_capabilities
from tradingagents.dataflows.china_capabilities import (
    AKShareSpecialtyProvider,
    AshareCapabilityUnavailableError,
    get_cls_telegraph,
)


class _AKShare:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def stock_dzjy_mrmx(self, **kwargs):
        self.calls.append(("bulk", kwargs))
        return pd.DataFrame(
            [
                {"证券代码": "600519", "成交价": 1500},
                {"证券代码": "000001", "成交价": 10},
            ]
        )

    def stock_zh_a_gdhs_detail_em(self, **kwargs):
        self.calls.append(("holders", kwargs))
        return pd.DataFrame([{"股东户数": 123, "统计截止日": "2026-06-30"}])

    def stock_restricted_release_detail_em(self, **kwargs):
        self.calls.append(("lockups", kwargs))
        return pd.DataFrame([{"证券代码": "000001", "解禁日期": "2026-08-01"}])

    def stock_lhb_stock_detail_em(self, **kwargs):
        self.calls.append(("lhb", kwargs))
        return pd.DataFrame([{"营业部名称": "示例营业部", "买入金额": 1000000}])

    def stock_zt_pool_em(self, **kwargs):
        self.calls.append(("limitup", kwargs))
        return pd.DataFrame(
            [
                {"代码": "000001", "连板数": 2, "涨停原因类别": "银行"},
                {"代码": "600519", "连板数": 1, "涨停原因类别": "消费"},
                {"代码": "000002", "连板数": 2, "涨停原因类别": "银行"},
            ]
        )

    def stock_irm_cninfo(self, **kwargs):
        self.calls.append(("questions", kwargs))
        return pd.DataFrame([{"问题编号": "question-1", "问题": "是否回购？"}])

    def stock_irm_ans_cninfo(self, **kwargs):
        self.calls.append(("answers", kwargs))
        return pd.DataFrame([{"回答": "以公告为准"}])


def test_interactive_questions_and_answers_are_separate_capabilities():
    api = _AKShare()
    provider = AKShareSpecialtyProvider(api)

    questions = provider.interactive_questions("000001")
    answers = provider.interactive_answers("question-1")

    assert questions.ticker == "000001.SZ"
    assert answers.ticker is None
    assert api.calls == [
        ("questions", {"symbol": "000001"}),
        ("answers", {"symbol": "question-1"}),
    ]


def test_non_a_share_is_rejected_before_optional_provider_is_called():
    api = _AKShare()

    with pytest.raises(AshareCapabilityUnavailableError, match="not an A-share ticker"):
        AKShareSpecialtyProvider(api).interactive_questions("AAPL")

    assert api.calls == []


def test_iwencai_is_real_optional_client_or_a_typed_degradation(monkeypatch):
    fake_client = types.SimpleNamespace(get=lambda **kwargs: pd.DataFrame([{"query": kwargs["query"], "代码": "000001"}]))
    monkeypatch.setitem(sys.modules, "pywencai", fake_client)

    report = AKShareSpecialtyProvider().iwencai_search("沪深300 成分股")

    assert report.provider == "iwencai"
    assert report.data.iloc[0]["query"] == "沪深300 成分股"


def test_cls_telegraph_signs_and_parses_roll_data(monkeypatch):
    """CLS telegraph computes the local sign, parses roll_data, pins Beijing time."""
    from datetime import datetime, timedelta, timezone

    ts = 1753344000
    expected_bj = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _FakeResponse(
            {
                "data": {
                    "roll_data": [
                        {"ctime": ts, "title": "测试电报", "content": "详细内容"},
                        {"ctime": ts, "brief": "仅 brief 的电报"},
                    ]
                }
            }
        )

    monkeypatch.setattr(china_capabilities.requests, "get", _fake_get)

    report = get_cls_telegraph()

    # The sign is md5(sha1(sorted query)); the URL carries it as a query param.
    assert "sign=" in captured["url"]
    assert captured["headers"]["Referer"] == "https://www.cls.cn/"
    assert "Source: cls" in report
    assert "测试电报" in report
    assert "仅 brief 的电报" in report
    assert expected_bj in report


def test_cls_telegraph_raises_on_request_failure(monkeypatch):
    """A network failure surfaces as a typed CLS capability-unavailable error."""

    def _fake_get(url, headers=None, timeout=None):
        raise china_capabilities.requests.RequestException("connection refused")

    monkeypatch.setattr(china_capabilities.requests, "get", _fake_get)

    with pytest.raises(AshareCapabilityUnavailableError, match="cls_telegraph"):
        get_cls_telegraph()


def test_date_only_limit_up_capability_routes_as_a_share_without_a_ticker_argument(monkeypatch):
    from tradingagents.dataflows import interface

    monkeypatch.setattr(interface, "get_vendor", lambda _category, method=None: "akshare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_a_share_limit_up_ladder",
        {"akshare": lambda trade_date: f"limit-up pool {trade_date}"},
    )

    assert interface.route_to_vendor("get_a_share_limit_up_ladder", "2026-07-21") == "limit-up pool 2026-07-21"
    assert interface._market_for_request(("2026-07-21",), "get_a_share_limit_up_ladder") == "a_share"
