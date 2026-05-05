"""Shared pytest fixtures that prevent CI hangs when API keys are absent."""

import os
from unittest.mock import MagicMock, patch
from pathlib import Path
import json

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
    "ZHIPU_API_KEY",
    "OPENROUTER_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
)


@pytest.fixture(autouse=True)
def _dummy_api_keys(monkeypatch):
    for env_var in _API_KEY_ENV_VARS:
        monkeypatch.setenv(env_var, os.environ.get(env_var, "placeholder"))


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch("tradingagents.llm_clients.factory.create_llm_client", return_value=client), patch(
        "tradingagents.llm_clients.create_llm_client", return_value=client
    ), patch("tradingagents.graph.trading_graph.create_llm_client", return_value=client):
        yield client


@pytest.fixture()
def load_scenario():
    def _load(name: str):
        path = Path(__file__).parent / "scenarios" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


@pytest.fixture()
def scenario_llm(load_scenario):
    from tests.scenario_fakes import ScenarioChatModel, ScenarioLLMClient

    patchers = []

    def _install(name: str):
        scenario = load_scenario(name)
        model = ScenarioChatModel(scenario)
        client = ScenarioLLMClient(model)
        for target in (
            "tradingagents.llm_clients.factory.create_llm_client",
            "tradingagents.llm_clients.create_llm_client",
            "tradingagents.graph.trading_graph.create_llm_client",
        ):
            p = patch(target, return_value=client)
            p.start()
            patchers.append(p)
        return model

    try:
        yield _install
    finally:
        for p in reversed(patchers):
            p.stop()
