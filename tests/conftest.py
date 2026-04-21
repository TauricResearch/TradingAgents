"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Custom markers
# ---------------------------------------------------------------------------


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


# ---------------------------------------------------------------------------
# Auto-use: placeholder API keys so LLM client init never blocks
# ---------------------------------------------------------------------------

_API_KEY_ENV_VARS = [
    "OPENAI",
    "GOOGLE",
    "ANTHROPIC",
    "XAI",
    "ALPHA_VANTAGE",
]


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for provider in _API_KEY_ENV_VARS:
        env_var = f"{provider}_API_KEY"
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


# ---------------------------------------------------------------------------
# Auto-use: safe DEFAULT_CONFIG override (no real API calls)
# ---------------------------------------------------------------------------

_SAFE_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4-mini",
    "quick_think_llm": "gpt-5.4-mini",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
}


@pytest.fixture(autouse=True)
def _safe_default_config():
    with patch.dict("tradingagents.default_config.DEFAULT_CONFIG", _SAFE_CONFIG):
        yield


# ---------------------------------------------------------------------------
# Reusable mock LLM client
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch("tradingagents.llm_clients.create_llm_client", return_value=client):
        yield client
