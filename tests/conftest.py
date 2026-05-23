"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest


def pytest_configure(config):
    for marker in ("unit", "integration", "smoke"):
        config.addinivalue_line("markers", f"{marker}: {marker}-level tests")


_API_KEY_ENV_VARS = (
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "DASHSCOPE_API_KEY",
    "DASHSCOPE_CN_API_KEY",
    "ZHIPU_API_KEY",
    "ZHIPU_CN_API_KEY",
    "MINIMAX_API_KEY",
    "MINIMAX_CN_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


@pytest.fixture()
def stub_questionary(monkeypatch):
    """Inject a questionary stub so cli.utils can be imported/reloaded in any env.

    Returns the MagicMock so tests can configure ``.select.return_value`` and
    inspect ``.select.call_args_list``.  ``questionary.Choice`` is wired up to
    record its ``(label, value)`` constructor args as plain attributes so tests
    can inspect the choices passed to the provider dropdown without depending
    on questionary's internal repr.
    """
    mock_q = MagicMock()

    class _Choice:
        """Minimal questionary.Choice stand-in that exposes .value."""
        def __init__(self, label, value=None):
            self.label = label
            self.value = value

    mock_q.Choice.side_effect = _Choice
    monkeypatch.setitem(sys.modules, "questionary", mock_q)
    return mock_q


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client
