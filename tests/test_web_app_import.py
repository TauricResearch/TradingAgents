import importlib

import pytest


@pytest.mark.smoke
def test_streamlit_app_imports_without_starting_analysis():
    app = importlib.import_module("tradingagents.web.app")

    assert hasattr(app, "main")
    assert hasattr(app, "get_job_manager")


def test_provider_strength_options_are_ordered_low_to_high():
    app = importlib.import_module("tradingagents.web.app")

    assert app.GEMINI_THINKING_OPTIONS == ["minimal", "high"]
    assert app.REASONING_EFFORT_OPTIONS == ["low", "medium", "high"]
    assert app.ANTHROPIC_EFFORT_OPTIONS == ["low", "medium", "high"]
    assert app.DEEPSEEK_THINKING_OPTIONS == ["disabled", "enabled"]


def test_provider_model_options_are_provider_specific():
    app = importlib.import_module("tradingagents.web.app")

    assert app._request_model_label("deepseek", "quick", "deepseek-chat") == "DeepSeek V3.2"
    assert app._request_model_label("deepseek", "deep", "deepseek-reasoner") == "DeepSeek V3.2 (thinking)"
    assert app._request_model_label("deepseek", "quick", "gpt-5.4-mini") == "Custom model ID"
