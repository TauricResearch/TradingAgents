import sys
import types

import pytest
import requests

from tradingagents.agents.evidence_steward import create_evidence_steward
from tradingagents.dataflows import interface
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.evidence import (
    EvidenceGateError,
    EvidenceStatus,
    evaluate_and_enrich_evidence,
    format_company_profile,
    resolve_canonical_company_profile,
)
from tradingagents.dataflows.news_advisor import NewsAdvisorResult
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


def _disable_llm_advisor(monkeypatch):
    """Make evidence-steward unit tests deterministic and key-independent.

    Neutralizes the LLM advisor so it returns no queries (forcing the mocked
    ``_run_tavily_enrichment`` multi-round path instead of the un-mocked
    ``_run_tavily_enrichment_with_queries``), and skips LLM clustering in
    ``_assess_news_items`` so the verdict is purely rule-based. Tests then pass
    regardless of whether real API keys are present locally or in CI.
    """
    monkeypatch.setattr(
        "tradingagents.dataflows.evidence.create_llm_from_config",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "tradingagents.dataflows.evidence.analyze_news_coverage",
        lambda *a, **kw: NewsAdvisorResult(should_enrich=True, queries=[]),
    )


def test_evidence_steward_fault_persists_only_exception_category(monkeypatch):
    secret = "must-not-persist"

    def fail_evaluation(_state):
        raise RuntimeError(f"https://vendor.example/api?token={secret}")

    monkeypatch.setattr(
        "tradingagents.agents.evidence_steward.evaluate_and_enrich_evidence",
        fail_evaluation,
    )

    result = create_evidence_steward()({})

    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    assert result["evidence_steward_fault"] == "RuntimeError"
    assert "Fault category: RuntimeError" in result["evidence_report"]
    assert secret not in result["evidence_report"]


def test_all_a_share_vendors_fail_hard_fails_after_all_fallbacks(monkeypatch):
    """When every A-share OHLCV vendor fails, the router raises a typed
    DataUnavailableError carrying each vendor's error so the caller can see
    why the chain exhausted.  yfinance is intentionally absent -- it is
    skipped for A-share tickers (needs VPN, poor coverage); the A-share
    chain is mootdx -> tushare -> akshare.
    """
    calls = []

    monkeypatch.setattr(interface, "get_vendor", lambda category, method=None: "mootdx,tushare,akshare")
    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {
            "mootdx": lambda *args, **kwargs: calls.append("mootdx") or (_ for _ in ()).throw(
                interface.ChinaDataUnavailableError("mootdx unreachable")
            ),
            "tushare": lambda *args, **kwargs: calls.append("tushare") or (_ for _ in ()).throw(
                interface.ChinaDataUnavailableError("tushare empty")
            ),
            "akshare": lambda *args, **kwargs: calls.append("akshare") or (_ for _ in ()).throw(
                interface.ChinaDataUnavailableError("akshare empty")
            ),
        },
    )
    set_config({"halt_on_missing_data": True})

    with pytest.raises(interface.DataUnavailableError) as exc:
        interface.route_to_vendor("get_stock_data", "002396.SZ", "2026-01-01", "2026-01-31")

    assert calls == ["mootdx", "tushare", "akshare"]
    assert "mootdx unreachable" in str(exc.value)
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
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    state = _base_state(
        news_report=(
            "### 通信设备板块市场回顾\n"
            "光迅科技、中天科技、闻泰科技等科技公司近期走势分化，通信设备行业情绪偏谨慎。\n"
            "Link: https://example.com/industry-tech\n"
        )
    )
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
        }
    )

    result = evaluate_and_enrich_evidence(state)

    # News scarcity → LOW_CONFIDENCE, not FAIL_STOP / raise.
    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    report = result["evidence_report"]
    assert "身份冲突" not in report
    assert "公司直相关新闻" in report


def test_evidence_steward_allows_chinese_alias_when_yfinance_profile_is_english(monkeypatch):
    # Deterministic rule-based assessment: the news item is sourced from cninfo
    # (high-credibility) so a single company item clears the
    # news_min_company_items=1 threshold via credibility weight.
    _disable_llm_advisor(monkeypatch)
    state = _base_state(
        news_report=(
            "### 星网锐捷公告更新\n"
            "002396.SZ（星网锐捷）发布经营公告，公告主体为福建星网锐捷通讯股份有限公司。\n"
            "Link: https://static.cninfo.com.cn/finalpage/2026-05-07/002396-announcement.html\n"
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
    _disable_llm_advisor(monkeypatch)
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

    result = evaluate_and_enrich_evidence(_base_state(news_report="No curated news found for 'get_news'."))

    # Peer codes in industry items are not identity conflicts; overall
    # scarcity → LOW_CONFIDENCE, not FAIL_STOP / raise.
    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    report = result["evidence_report"]
    assert "身份冲突" not in report
    assert "公司直相关新闻" in report


def test_evidence_steward_enriches_empty_news_three_rounds_and_dedupes(monkeypatch):
    calls = []
    _disable_llm_advisor(monkeypatch)

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
    # High-credibility sources (cninfo.com.cn, szse.cn) get 1.5x weight,
    # so 2 company items → weighted 3.0, meeting the threshold of 3.
    assert "通过" in result["evidence_report"]


def test_evidence_steward_returns_low_confidence_when_enrichment_still_insufficient(monkeypatch):
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "evidence_max_enrichment_rounds": 3,
            "evidence_max_enrichment_seconds": 90,
        }
    )

    result = evaluate_and_enrich_evidence(_base_state(news_report="No curated news found for 'get_news'."))

    # Thin evidence after enrichment → LOW_CONFIDENCE (proceeds), not FAIL_STOP.
    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    report = result["evidence_report"]
    assert "Evidence confidence: LOW_CONFIDENCE" in report
    assert "Tavily enrichment rounds used: 3" in report


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


# --- Low-confidence verdict model ---------------------------------------------------


def test_low_confidence_default_config_thin_evidence_does_not_fail(monkeypatch):
    """With default evidence_stop_on_fail=False, thin evidence proceeds."""
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    set_config(
        {
            "evidence_gate_enabled": True,
            # evidence_stop_on_fail default is False; don't override it.
            "evidence_max_enrichment_rounds": 1,
            "evidence_max_enrichment_seconds": 10,
        }
    )

    result = evaluate_and_enrich_evidence(_base_state(news_report=""))

    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    assert "evidence_report" in result


def test_identity_conflict_still_fails_even_when_stop_on_fail_false(monkeypatch):
    """Wrong-identity detection is a hard fail regardless of stop_on_fail."""
    _disable_llm_advisor(monkeypatch)
    state = _base_state(
        news_report=(
            "### 海峡股份航运业务更新\n"
            "002320.SZ 证券代码：002320 证券简称：海峡股份，公告主体为海南海峡航运股份有限公司。\n"
            "Link: https://example.com/002320\n"
        )
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": False})

    with pytest.raises(EvidenceGateError):
        evaluate_and_enrich_evidence(state)


def test_core_data_degraded_patterns_produce_low_confidence(monkeypatch):
    """Non-fatal data warnings → LOW_CONFIDENCE, not FAIL_STOP."""
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    state = _base_state(
        news_report="### 某新闻\ncontent here\n",
        fundamentals_report="Warning: Yahoo Finance data is stale. 暂未获取完整财务数据。",
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    result = evaluate_and_enrich_evidence(state)

    # Not a hard fail; data quality downgrade contributes to LOW_CONFIDENCE.
    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    assert "数据质量降级" in result["evidence_report"]


def test_core_data_fatal_pattern_still_fails(monkeypatch):
    """'no usable financial statement' remains a hard FAIL_STOP."""
    _disable_llm_advisor(monkeypatch)
    state = _base_state(
        news_report="### 某新闻\ncontent here\n",
        fundamentals_report="Error: no usable financial statement available.",
    )
    set_config({"evidence_gate_enabled": True, "evidence_stop_on_fail": True})

    with pytest.raises(EvidenceGateError) as exc:
        evaluate_and_enrich_evidence(state)

    assert "核心财务数据缺失" in str(exc.value)


def test_unresolved_a_share_profile_produces_low_confidence(monkeypatch):
    """Unresolved A-share profile name → LOW_CONFIDENCE, not FAIL_STOP."""
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])

    def fake_complete_profile(profile, ticker):
        profile["ticker"] = "600519.SS"
        profile["symbol"] = "600519"
        profile["ts_code"] = "600519.SH"
        profile["name"] = ""
        profile["full_name"] = ""
        return profile

    monkeypatch.setattr(
        "tradingagents.dataflows.evidence._complete_profile",
        fake_complete_profile,
    )
    state = _base_state(news_report="")
    state["canonical_company_profile"] = {}
    set_config(
        {
            "evidence_gate_enabled": True,
            "evidence_stop_on_fail": True,
            "evidence_max_enrichment_rounds": 1,
        }
    )

    result = evaluate_and_enrich_evidence(state)

    assert result["evidence_status"] == EvidenceStatus.LOW_CONFIDENCE.value
    assert "身份信息不完整" in result["evidence_report"]


def test_evidence_report_carries_machine_readable_confidence_line(monkeypatch):
    _disable_llm_advisor(monkeypatch)
    monkeypatch.setattr("tradingagents.dataflows.evidence._run_tavily_enrichment", lambda *args, **kwargs: [])
    set_config(
        {
            "evidence_gate_enabled": True,
            "news_min_company_items": 3,
            "news_min_mixed_items": 5,
            "evidence_max_enrichment_rounds": 1,
        }
    )
    state = _base_state(news_report="")

    result = evaluate_and_enrich_evidence(state)

    report = result["evidence_report"]
    assert "Evidence confidence: LOW_CONFIDENCE" in report
    # Includes weighted counts against thresholds.
    assert "company" in report
    assert "mixed" in report


def test_unresolved_profile_does_not_flag_correct_company_as_wrong_identity(monkeypatch):
    """Regression for F7: empty profile name + correct news ≠ identity conflict."""
    from tradingagents.dataflows.evidence import _find_wrong_identity_hits

    profile = {
        "ticker": "2513.HK",
        "symbol": "2513",
        "name": "",
        "full_name": "",
    }
    items = [
        {
            "title": "智谱AI招股书更新",
            "url": "https://example.com/zhipu",
            "content": "智谱（2513.HK）发布最新招股书，智谱AI 持续投入大模型研发。",
            "source": "tavily",
        }
    ]

    hits = _find_wrong_identity_hits(items, profile)

    # With an unresolved profile, name-based checks abstain.
    assert hits == set()


def test_additional_correct_evidence_does_not_grow_conflict_when_profile_unresolved(monkeypatch):
    """More correct evidence must not deepen a false conflict when profile is empty."""
    from tradingagents.dataflows.evidence import _find_wrong_identity_hits

    profile = {
        "ticker": "2513.HK",
        "symbol": "2513",
        "name": "",
        "full_name": "",
    }
    items_round1 = [
        {
            "title": "智谱AI融资消息",
            "content": "智谱（2513.HK）完成新一轮融资。",
            "source": "tavily",
        }
    ]
    items_round2 = items_round1 + [
        {
            "title": "智谱AI产品更新",
            "content": "智谱AI（2513.HK）发布新一代大模型。",
            "source": "tavily",
        },
        {
            "title": "行业报道",
            "content": "据报道，智谱华章（2513.HK）营收增长显著。",
            "source": "tavily",
        },
    ]

    hits1 = _find_wrong_identity_hits(items_round1, profile)
    hits2 = _find_wrong_identity_hits(items_round2, profile)

    # No conflict hits in either case; additional correct evidence does not
    # create or deepen a spurious conflict.
    assert hits1 == set()
    assert hits2 == set()


def test_configured_tavily_keys_reads_both_env_vars(monkeypatch):
    """_configured_tavily_keys honors TAVILY_API_KEYS plus legacy TAVILY_API_KEY."""
    from tradingagents.dataflows.evidence import _configured_tavily_keys

    monkeypatch.setenv("TAVILY_API_KEYS", "key1,key2")
    monkeypatch.setenv("TAVILY_API_KEY", "legacy")
    assert _configured_tavily_keys() == ("key1", "key2", "legacy")

    monkeypatch.delenv("TAVILY_API_KEYS", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "only-legacy")
    assert _configured_tavily_keys() == ("only-legacy",)

    monkeypatch.setenv("TAVILY_API_KEYS", "multi-only")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert _configured_tavily_keys() == ("multi-only",)

    monkeypatch.delenv("TAVILY_API_KEYS", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert _configured_tavily_keys() == ()
