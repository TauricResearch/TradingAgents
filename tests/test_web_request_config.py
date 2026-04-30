import pytest

from tradingagents.web.models import AnalysisRequest


@pytest.mark.unit
def test_analysis_request_maps_to_tradingagents_config():
    request = AnalysisRequest(
        ticker="BTC-USD",
        analysis_date="2026-04-30",
        output_language="Chinese",
        analysts=["news", "market", "unknown"],
        research_depth=3,
        llm_provider="deepseek",
        backend_url="https://api.deepseek.com",
        quick_think_llm="deepseek-v4-flash",
        deep_think_llm="deepseek-v4-pro",
        deepseek_thinking="enabled",
        checkpoint=True,
    )

    config = request.to_config()

    assert request.normalized_analysts() == ["market", "news"]
    assert config["llm_provider"] == "deepseek"
    assert config["backend_url"] == "https://api.deepseek.com"
    assert config["quick_think_llm"] == "deepseek-v4-flash"
    assert config["deep_think_llm"] == "deepseek-v4-pro"
    assert config["deepseek_thinking"] == "enabled"
    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 3
    assert config["output_language"] == "Chinese"
    assert config["checkpoint_enabled"] is True


@pytest.mark.unit
def test_analysis_request_round_trips_cache_entry():
    request = AnalysisRequest(
        ticker="BTC-USD",
        analysis_date="2026-04-30",
        output_language="Chinese",
        analysts=["market", "news"],
        research_depth=5,
        llm_provider="deepseek",
        backend_url="https://api.deepseek.com",
        quick_think_llm="deepseek-v4-flash",
        deep_think_llm="deepseek-v4-pro",
        deepseek_thinking="disabled",
        checkpoint=True,
    )

    restored = AnalysisRequest.from_cache_entry(request.to_cache_entry())

    assert restored == request
