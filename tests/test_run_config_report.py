"""Unit tests for cli.run_config_report (Issue #752)."""

from __future__ import annotations

import pytest

from cli.run_config_report import build_run_config_markdown


@pytest.mark.unit
def test_includes_version_and_ticker_header():
    selections = {
        "ticker": "NVDA",
        "analysis_date": "2026-05-04",
        "analysts": [],
        "research_depth": 1,
        "llm_provider": "openai",
        "shallow_thinker": "gpt-5.4-mini",
        "deep_thinker": "gpt-5.4",
        "backend_url": None,
        "openai_reasoning_effort": "medium",
        "google_thinking_level": None,
        "anthropic_effort": None,
        "output_language": "English",
    }
    config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}

    md = build_run_config_markdown(selections, config, version="0.2.4")

    assert "# Run Configuration" in md
    assert "NVDA" in md
    assert "2026-05-04" in md
    assert "0.2.4" in md
    assert "gpt-5.4-mini" in md
    assert "gpt-5.4" in md


@pytest.mark.unit
def test_omits_unset_provider_specific_keys():
    """When provider-specific reasoning keys are None, they should not render as 'None'."""
    selections = {
        "ticker": "AAPL",
        "analysis_date": "2026-05-04",
        "analysts": [],
        "research_depth": 1,
        "llm_provider": "ollama",
        "shallow_thinker": "qwen3:latest",
        "deep_thinker": "gpt-oss:latest",
        "backend_url": "http://localhost:11434/v1",
        "openai_reasoning_effort": None,
        "google_thinking_level": None,
        "anthropic_effort": None,
        "output_language": "English",
    }
    config = {"max_debate_rounds": 1, "max_risk_discuss_rounds": 1}

    md = build_run_config_markdown(selections, config, version="0.2.4")

    # Ollama selections shouldn't surface a "Provider-specific reasoning parameters" section
    assert "Provider-specific reasoning parameters" not in md
    assert "ollama" in md
    assert "qwen3:latest" in md
    assert "gpt-oss:latest" in md


@pytest.mark.unit
def test_includes_debate_and_risk_rounds_and_provider_specific_section():
    selections = {
        "ticker": "MSFT",
        "analysis_date": "2026-05-04",
        "analysts": [],
        "research_depth": 3,
        "llm_provider": "anthropic",
        "shallow_thinker": "claude-haiku-4",
        "deep_thinker": "claude-opus-4",
        "backend_url": None,
        "openai_reasoning_effort": None,
        "google_thinking_level": None,
        "anthropic_effort": "high",
        "output_language": "English",
    }
    config = {"max_debate_rounds": 3, "max_risk_discuss_rounds": 2}

    md = build_run_config_markdown(selections, config, version="0.2.4")

    assert "Provider-specific reasoning parameters" in md
    assert "Anthropic effort" in md
    assert "high" in md
    # research_depth and rounds should appear
    assert "| Research depth | 3 |" in md
    assert "| Max debate rounds | 3 |" in md
    assert "| Max risk discuss rounds | 2 |" in md
