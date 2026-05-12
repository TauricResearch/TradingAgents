from tradingagents.webapi.schemas import AnalysisRequest, SettingsPayload
from tradingagents.webapi.service import (
    build_effective_config,
    chunk_to_run_events,
    candidate_ticker_symbols,
    event_fingerprint,
    iter_mock_research_events,
    list_model_catalog,
    mask_secret,
    resolve_chinese_company_profile,
    resolve_company_name,
    summarize_run_event,
)


def test_mask_secret_preserves_only_edges():
    assert mask_secret("") == ""
    assert mask_secret("sk-1234567890") == "sk-1******890"
    assert mask_secret("short") == "*****"


def test_build_effective_config_maps_web_settings_to_tradingagents_config():
    settings = SettingsPayload(
        llm_provider="deepseek",
        deep_think_llm="deepseek-reasoner",
        quick_think_llm="deepseek-chat",
        backend_url="https://api.deepseek.com",
        max_debate_rounds=3,
        max_risk_discuss_rounds=2,
        output_language="Chinese",
        checkpoint_enabled=True,
        data_vendors={
            "core_stock_apis": "alpha_vantage",
            "technical_indicators": "yfinance",
            "fundamental_data": "alpha_vantage",
            "news_data": "yfinance",
        },
    )

    config = build_effective_config(settings)

    assert config["llm_provider"] == "deepseek"
    assert config["deep_think_llm"] == "deepseek-reasoner"
    assert config["quick_think_llm"] == "deepseek-chat"
    assert config["backend_url"] == "https://api.deepseek.com"
    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 2
    assert config["output_language"] == "Chinese"
    assert config["checkpoint_enabled"] is True
    assert config["data_vendors"]["core_stock_apis"] == "alpha_vantage"


def test_analysis_request_defaults_are_web_friendly():
    request = AnalysisRequest(ticker=" nvda ")

    assert request.ticker == "NVDA"
    assert request.analysis_date
    assert request.analysts == ["market", "news", "fundamentals"]
    assert request.research_depth == 1
    assert request.output_language == "Chinese"
    assert request.use_mock_stream is False


def test_resolve_company_name_uses_yfinance_metadata(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def get_info(self):
            return {"longName": "NVIDIA Corporation", "shortName": "NVIDIA"}

    monkeypatch.setattr("tradingagents.webapi.service.resolve_chinese_company_profile", lambda ticker: None)
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    assert resolve_company_name("nvda") == "NVIDIA Corporation"


def test_resolve_company_name_falls_back_to_ticker_on_lookup_failure(monkeypatch):
    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def get_info(self):
            raise RuntimeError("network unavailable")

    monkeypatch.setattr("tradingagents.webapi.service.resolve_chinese_company_profile", lambda ticker: None)
    monkeypatch.setattr("yfinance.Ticker", FakeTicker)

    assert resolve_company_name("688160") is None


def test_resolve_company_name_prefers_chinese_profile(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.webapi.service.resolve_chinese_company_profile",
        lambda ticker: {"ticker": "NVDA", "company_name": "英伟达", "market": "US"},
    )

    assert resolve_company_name("NVDA") == "英伟达"


def test_candidate_ticker_symbols_infers_cn_market_suffixes():
    assert candidate_ticker_symbols("688160")[:2] == ["688160.SS", "688160.SZ"]
    assert candidate_ticker_symbols("000001")[:2] == ["000001.SZ", "000001.SS"]
    assert candidate_ticker_symbols("0700")[0] == "0700.HK"


def test_model_catalog_contains_provider_modes():
    catalog = list_model_catalog()

    assert "openai" in catalog
    assert "quick" in catalog["openai"]
    assert any(model["value"] == "gpt-5.4-mini" for model in catalog["openai"]["quick"])


def test_summarize_run_event_returns_frontend_shape():
    event = summarize_run_event(
        run_id="run_1",
        event_type="agent_status",
        agent="Market Analyst",
        status="completed",
        content="Market report ready",
    )

    assert event["runId"] == "run_1"
    assert event["type"] == "agent_status"
    assert event["agent"] == "Market Analyst"
    assert event["status"] == "completed"
    assert event["content"] == "Market report ready"


def test_chunk_to_run_events_maps_trading_graph_reports():
    events = chunk_to_run_events(
        "run_1",
        {
            "market_report": "Market body",
            "investment_debate_state": {
                "bull_history": "Bull body",
                "bear_history": "",
                "judge_decision": "Manager body",
            },
            "trader_investment_plan": "Trader body",
            "risk_debate_state": {
                "aggressive_history": "Aggressive body",
                "neutral_history": "Neutral body",
                "conservative_history": "",
                "judge_decision": "Portfolio body",
            },
            "final_trade_decision": "Final body",
        },
    )

    sections = {event["section"]: event for event in events if event["type"] == "report"}

    assert sections["market_report"]["agent"] == "Market Analyst"
    assert sections["bull_researcher"]["content"] == "### 多头研究员\nBull body"
    assert sections["research_manager"]["agent"] == "Research Manager"
    assert sections["trader_investment_plan"]["content"] == "Trader body"
    assert sections["portfolio_manager"]["content"] == "### 组合经理\nPortfolio body"
    assert any(event["type"] == "decision" and event["content"] == "Final body" for event in events)


def test_chunk_to_run_events_maps_langchain_messages_and_tool_calls():
    class FakeMessage:
        content = "Thinking about market data"
        tool_calls = [{"name": "get_stock_data", "args": {"ticker": "NVDA"}}]

    events = chunk_to_run_events("run_1", {"messages": [FakeMessage()]})

    assert events[0]["type"] == "message"
    assert events[0]["content"] == "Thinking about market data"
    assert events[1]["type"] == "tool_call"
    assert events[1]["content"] == "get_stock_data"
    assert events[1]["payload"]["args"] == {"ticker": "NVDA"}


def test_mock_research_depth_controls_debate_rounds(monkeypatch):
    monkeypatch.setenv("TRADINGAGENTS_MOCK_STEP_DELAY", "0")
    request = AnalysisRequest(ticker="NVDA", analysts=["market"], research_depth=3, use_mock_stream=True)

    events = list(iter_mock_research_events("run_depth", request))
    report_sections = [event["section"] for event in events if event["type"] == "report"]

    assert "bull_researcher_round_3" in report_sections
    assert "bear_researcher_round_3" in report_sections
    assert "research_manager_round_3" in report_sections
    assert "portfolio_manager_round_3" in report_sections


def test_live_event_fingerprint_deduplicates_repeated_reports_by_content():
    first = summarize_run_event(
        run_id="run_1",
        event_type="report",
        agent="Market Analyst",
        status="completed",
        section="market_report",
        content="same report",
    )
    second = summarize_run_event(
        run_id="run_1",
        event_type="report",
        agent="Market Analyst",
        status="completed",
        section="market_report",
        content="same report",
    )
    changed = summarize_run_event(
        run_id="run_1",
        event_type="report",
        agent="Market Analyst",
        status="completed",
        section="market_report",
        content="updated report",
    )

    assert event_fingerprint(first) == event_fingerprint(second)
    assert event_fingerprint(first) != event_fingerprint(changed)
