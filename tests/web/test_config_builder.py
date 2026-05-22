import pytest
from pydantic import ValidationError

from web.config_builder import build_web_config
from web.models import AnalysisRequest, StreamEvent


def test_analysis_request_normalizes_ticker():
    request = AnalysisRequest(
        ticker=" nvda ",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    assert request.ticker == "NVDA"


def test_analysis_request_rejects_invalid_date():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            ticker="NVDA",
            analysis_date="01-15-2026",
            analysts=["market"],
            research_depth=1,
            llm_provider="openai",
            quick_think_llm="gpt-5.4-mini",
            deep_think_llm="gpt-5.4",
        )


def test_analysis_request_rejects_non_padded_date():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            ticker="NVDA",
            analysis_date="2026-1-5",
            analysts=["market"],
            research_depth=1,
            llm_provider="openai",
            quick_think_llm="gpt-5.4-mini",
            deep_think_llm="gpt-5.4",
        )


def test_analysis_request_rejects_whitespace_ticker():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            ticker="   ",
            analysis_date="2026-01-15",
            analysts=["market"],
            research_depth=1,
            llm_provider="openai",
            quick_think_llm="gpt-5.4-mini",
            deep_think_llm="gpt-5.4",
        )


def test_analysis_request_rejects_unknown_analyst():
    with pytest.raises(ValidationError):
        AnalysisRequest(
            ticker="NVDA",
            analysis_date="2026-01-15",
            analysts=["macro"],
            research_depth=1,
            llm_provider="openai",
            quick_think_llm="gpt-5.4-mini",
            deep_think_llm="gpt-5.4",
        )


def test_stream_event_accepts_known_type():
    event = StreamEvent(type="run_started", payload={"ticker": "NVDA"})

    assert event.type == "run_started"
    assert event.payload == {"ticker": "NVDA"}


def test_stream_event_rejects_unknown_type():
    with pytest.raises(ValidationError):
        StreamEvent(type="unknown", payload={})


def test_build_web_config_sets_core_values():
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        output_language="English",
        analysts=["market", "news"],
        research_depth=3,
        llm_provider="openai",
        backend_url="https://api.openai.com/v1",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
        openai_reasoning_effort="medium",
        checkpoint_enabled=True,
    )

    config, analysts, asset_type = build_web_config(request)

    assert config["max_debate_rounds"] == 3
    assert config["max_risk_discuss_rounds"] == 3
    assert config["llm_provider"] == "openai"
    assert config["checkpoint_enabled"] is True
    assert analysts == ["market", "news"]
    assert asset_type == "stock"


def test_build_web_config_defaults_ollama_backend_url(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="ollama",
        quick_think_llm="qwen3:latest",
        deep_think_llm="qwen3:latest",
    )

    config, _, _ = build_web_config(request)

    assert config["llm_provider"] == "ollama"
    assert config["backend_url"] == "http://localhost:11434/v1"


def test_build_web_config_uses_ollama_base_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="ollama",
        quick_think_llm="qwen3:latest",
        deep_think_llm="qwen3:latest",
    )

    config, _, _ = build_web_config(request)

    assert config["backend_url"] == "http://remote-ollama:11434/v1"


def test_build_web_config_prefers_explicit_ollama_backend_url(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote-ollama:11434/v1")
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="ollama",
        backend_url="http://custom-ollama:11434/v1",
        quick_think_llm="qwen3:latest",
        deep_think_llm="qwen3:latest",
    )

    config, _, _ = build_web_config(request)

    assert config["backend_url"] == "http://custom-ollama:11434/v1"


def test_build_web_config_removes_fundamentals_for_crypto():
    request = AnalysisRequest(
        ticker="BTC-USD",
        analysis_date="2026-01-15",
        analysts=["fundamentals", "market"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    _, analysts, asset_type = build_web_config(request)

    assert analysts == ["market"]
    assert asset_type == "crypto"


def test_build_web_config_rejects_crypto_with_only_fundamentals():
    request = AnalysisRequest(
        ticker="BTC-USD",
        analysis_date="2026-01-15",
        analysts=["fundamentals"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    with pytest.raises(ValueError, match="At least one analyst"):
        build_web_config(request)


def test_build_web_config_does_not_share_nested_defaults():
    request = AnalysisRequest(
        ticker="NVDA",
        analysis_date="2026-01-15",
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_think_llm="gpt-5.4-mini",
        deep_think_llm="gpt-5.4",
    )

    first_config, _, _ = build_web_config(request)
    first_config["data_vendors"]["core_stock_apis"] = "changed"

    second_config, _, _ = build_web_config(request)

    assert second_config["data_vendors"]["core_stock_apis"] != "changed"
