import sys
import types

import pytest
import requests

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.evidence import (
    EvidenceGateError,
    EvidenceStatus,
    evaluate_and_enrich_evidence,
    format_company_profile,
    resolve_canonical_company_profile,
)
from tradingagents.dataflows.ticker_utils import to_tushare_symbol
from tradingagents.graph.setup import GraphSetup


def _profile():
    return {
        "ticker": "002396.SZ",
        "symbol": "002396",
        "ts_code": "002396.SZ",
        "name": "星网锐捷",
        "full_name": "福建星网锐捷通讯股份有限公司",
        "industry": "通信设备",
        "exchange": "深圳证券交易所",
    }


def _base_state(news_report="", market_report="market ok", fundamentals_report="fundamentals ok"):
    return {
        "company_of_interest": "002396.SZ",
        "trade_date": "2026-05-07",
        "market_report": market_report,
        "sentiment_report": "",
        "news_report": news_report,
        "fundamentals_report": fundamentals_report,
        "canonical_company_profile": _profile(),
    }


def test_incomplete_primary_stock_data_hard_fails_after_all_fallbacks(monkeypatch):
    yfinance_data = (
        "# Stock data for 002396.SZ from 2026-01-01 to 2026-01-31\n"
        "# Total records: 1\n\n"
        "Date,Open,High,Low,Close,Volume\n"
        "2026-01-02,10,11,9,10.5,1000\n"
    )
    calls = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "yfinance,tushare,akshare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "yfinance": lambda *args, **kwargs: calls.append("yfinance") or yfinance_data,
            "tushare": lambda *args, **kwargs: calls.append("tushare") or (_ for _ in ()).throw(
                interface.ChinaDataUnavailableError("tushare empty")
            ),
            "akshare": lambda *args, **kwargs: calls.append("akshare") or (_ for _ in ()).throw(
                interface.ChinaDataUnavailableError("akshare empty")
            ),
        },
    )
    set_config(
        {
            "halt_on_missing_data": True,
            "a_share_yfinance_min_rows": 3,
            "a_share_yfinance_min_coverage_ratio": 0.6,
        }
    )

    with pytest.raises(interface.DataUnavailableError) as exc:
        interface.route_to_vendor("get_stock_data", "002396.SZ", "2026-01-01", "2026-01-31")

    assert calls == ["yfinance", "tushare", "akshare"]
    assert "Yahoo Finance returned only 1 OHLCV row" in str(exc.value)
    assert "tushare empty" in str(exc.value)
    assert "akshare empty" in str(exc.value)


def test_alpha_vantage_network_error_falls_back_to_next_vendor(monkeypatch):
    calls = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "alpha_vantage,yfinance")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_balance_sheet",
        {
            "alpha_vantage": lambda *args, **kwargs: calls.append("alpha_vantage") or (_ for _ in ()).throw(
                requests.exceptions.SSLError("alpha ssl failed")
            ),
            "yfinance": lambda *args, **kwargs: calls.append("yfinance") or (
                "# Balance Sheet for AAPL\n"
                "Breakdown,2025-12-31\n"
                "Cash And Cash Equivalents,100\n"
            ),
        },
    )
    set_config({"halt_on_missing_data": True})

    result = interface.route_to_vendor("get_balance_sheet", "AAPL", "quarterly", "2026-05-07")

    assert calls == ["alpha_vantage", "yfinance"]
    assert "Cash And Cash Equivalents" in result


def test_evidence_steward_rejects_wrong_company_identity_without_passing_debate():
    state = _base_state(
        news_report=(
            "### 恒瑞医药获得药物临床试验批准\n"
            "恒瑞医药是中国创新药公司。\n"
            "Link: https://example.com/hengrui\n\n"
            "### 安洁科技消费电子订单增长\n"
            "安洁科技是苹果供应商。\n"
            "Link: https://example.com/anjie\n"
        )
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(state)

    message = str(exc.value)
    assert "身份冲突" in message
    assert "恒瑞医药" in message
    assert "安洁科技" in message


def test_evidence_steward_rejects_wrong_ticker_identity():
    state = _base_state(
        news_report=(
            "### 海峡股份航运业务更新\n"
            "002320.SZ 证券代码：002320 证券简称：海峡股份，公告主体为海南海峡航运股份有限公司。\n"
            "Link: https://example.com/002320\n"
        )
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(state)

    message = str(exc.value)
    assert "身份冲突" in message
    assert "002320.SZ" in message or "002320" in message


def test_evidence_steward_does_not_hard_fail_on_unbound_tech_company_names(monkeypatch):
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    state = _base_state(
        news_report=(
            "### 通信设备板块市场回顾\n"
            "光迅科技、中天科技、闻泰科技等科技公司近期走势分化，通信设备行业情绪偏谨慎。\n"
            "Link: https://example.com/industry-tech\n"
        )
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(state)

    assert "身份冲突" not in str(exc.value)
    assert "公司直相关新闻" in str(exc.value)


def test_evidence_steward_allows_chinese_alias_when_yfinance_profile_is_english():
    state = _base_state(
        news_report=(
            "### 星网锐捷公告更新\n"
            "002396.SZ（星网锐捷）发布经营公告，公告主体为福建星网锐捷通讯股份有限公司。\n"
            "Link: https://example.com/002396-star-net\n"
        )
    )
    state["canonical_company_profile"] = {
        "ticker": "002396.SZ",
        "symbol": "002396",
        "ts_code": "002396.SZ",
        "name": "FUJIAN STAR-NET COMMUNICATION C",
        "full_name": "Fujian Star-net Communication Co., LTD.",
        "industry": "Communication Equipment",
        "exchange": "深圳证券交易所",
        "profile_source": "yfinance",
    }
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "news_min_company_items": 1,
            "news_min_mixed_items": 1,
        }
    )

    result = evaluate_and_enrich_evidence(state)

    assert result["evidence_status"] == EvidenceStatus.PASS.value


def test_evidence_steward_does_not_hard_fail_on_peer_codes_from_enrichment(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.dataflows.evidence._run_tavily_enrichment",
        lambda *args, **kwargs: [
            {
                "title": "通信设备行业公司动态",
                "url": "https://example.com/peer-codes",
                "content": "证券代码：002110 的三钢闽光与证券代码：002217 的合力泰也出现在行业新闻中。",
                "source": "tavily_enrichment",
            }
        ],
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(_base_state(news_report="No curated news found for 'get_news'."))

    assert "身份冲突" not in str(exc.value)
    assert "公司直相关新闻" in str(exc.value)


def test_evidence_steward_enriches_empty_news_three_rounds_and_dedupes(monkeypatch):
    calls = []

    def fake_enrich(profile, trade_date, rounds, deadline):
        calls.append(rounds)
        return [
            {
                "title": "星网锐捷出售德明通讯股权进展公告",
                "url": "https://static.cninfo.com.cn/finalpage/2026-03-13/1225005995.PDF?x=1",
                "content": "证券代码：002396 证券简称：星网锐捷 公告主体为福建星网锐捷通讯股份有限公司。",
                "source": "tavily",
                "publisher": "巨潮资讯",
                "published": "2026-03-13",
            },
            {
                "title": "星网锐捷出售德明通讯股权进展公告",
                "url": "https://static.cninfo.com.cn/finalpage/2026-03-13/1225005995.PDF?x=2",
                "content": "证券代码：002396 证券简称：星网锐捷 同一公告重复结果。",
                "source": "tavily",
                "publisher": "巨潮资讯",
                "published": "2026-03-13",
            },
            {
                "title": "锐捷网络关联交易预计公告",
                "url": "https://disc.static.szse.cn/download/disc/example.PDF",
                "content": "星网锐捷为锐捷网络控股股东，通信设备行业关联交易。",
                "source": "tavily",
                "publisher": "深交所",
                "published": "2026-03-28",
            },
            {
                "title": "通信设备行业国产替代持续推进",
                "url": "https://example.com/industry",
                "content": "通信设备行业受益于国产替代和数字经济建设。",
                "source": "tavily",
                "publisher": "行业新闻",
                "published": "2026-03-30",
            },
        ]

    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", fake_enrich)
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "evidence_max_enrichment_rounds": 3,
            "evidence_max_enrichment_seconds": 90,
            "news_min_company_items": 3,
            "news_min_mixed_items": 3,
        }
    )

    result = evaluate_and_enrich_evidence(_base_state(news_report="No curated news found for 'get_news'."))

    assert calls == [3]
    assert result["evidence_status"] == EvidenceStatus.PASS.value
    assert result["news_report"].count("星网锐捷出售德明通讯股权进展公告") == 1
    assert "低覆盖通过" in result["evidence_report"]


def test_evidence_steward_stops_when_enrichment_still_insufficient(monkeypatch):
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "evidence_max_enrichment_rounds": 3,
            "evidence_max_enrichment_seconds": 90,
        }
    )

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(_base_state(news_report="No curated news found for 'get_news'."))

    assert "Tavily 补充 3 轮后仍不足" in str(exc.value)


def test_format_company_profile_keeps_a_share_identity_stable():
    profile = _profile()

    rendered = format_company_profile(profile)

    assert "002396.SZ" in rendered
    assert "星网锐捷" in rendered
    assert "福建星网锐捷通讯股份有限公司" in rendered
    assert to_tushare_symbol("002396") == "002396.SZ"


def test_canonical_profile_falls_back_to_yfinance_when_china_sources_unavailable(monkeypatch):
    from tradingagents.dataflows import china_data, evidence

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def get_info(self):
            assert self.symbol == "002396.SZ"
            return {
                "symbol": "002396.SZ",
                "shortName": "星网锐捷",
                "longName": "福建星网锐捷通讯股份有限公司",
                "industry": "通信设备",
                "fullExchangeName": "Shenzhen Stock Exchange",
            }

    resolve_canonical_company_profile.cache_clear()
    monkeypatch.setattr(
        china_data,
        "_get_tushare_pro",
        lambda: (_ for _ in ()).throw(china_data.ChinaDataUnavailableError("tushare limited")),
    )
    monkeypatch.setattr(
        evidence,
        "_apply_akshare_profile",
        lambda profile: profile.update({"akshare_resolution_error": "akshare unavailable"}),
    )
    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=FakeTicker))

    profile = resolve_canonical_company_profile("002396.SZ")

    assert profile["name"] == "星网锐捷"
    assert profile["full_name"] == "福建星网锐捷通讯股份有限公司"
    assert profile["industry"] == "通信设备"
    assert profile["profile_source"] == "yfinance"
    resolve_canonical_company_profile.cache_clear()


def test_graph_routes_last_analyst_to_evidence_steward_before_debate():
    class DummyConditional:
        def should_continue_news(self, state):
            return "Msg Clear News"

        def should_continue_debate(self, state):
            return "Research Manager"

        def should_continue_risk_analysis(self, state):
            return "Portfolio Manager"

    graph_setup = GraphSetup(
        None,
        None,
        {"news": lambda state: state},
        DummyConditional(),
    )
    workflow = graph_setup.setup_graph(["news"])

    graph = workflow.compile()

    assert "Evidence Steward" in graph.nodes
    assert "Bull Researcher" in graph.nodes
