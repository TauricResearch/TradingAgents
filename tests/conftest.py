"""Shared pytest fixtures that isolate the suite from the developer's environment.

Two kinds of leakage are handled here. API keys are replaced with placeholders so
an absent key cannot hang CI on a real call. And the ``TRADINGAGENTS_*`` overlay
is stripped, because ``tradingagents/__init__.py`` calls ``load_dotenv`` at
package import: with a populated ``.env`` in the working tree, the developer's own
provider and model settings become what the tests read as the framework's
defaults, so assertions about those defaults fail locally while passing in CI.
"""

import copy
import importlib
import os
from unittest.mock import MagicMock, patch

import pytest


def _defaults_without_env_overlay() -> dict:
    """DEFAULT_CONFIG as the framework ships it, ignoring any .env.

    Clearing the environment from a fixture is not enough on its own:
    ``_apply_env_overrides`` runs at *import* time, so by the time any fixture
    executes the dict already holds the developer's values and the shipped ones
    are gone. Reloading the module with the overlay removed recovers them.

    The pre-reload dict object is restored as the module attribute afterwards,
    because modules that did ``from tradingagents.default_config import
    DEFAULT_CONFIG`` hold a reference to it; rebinding the name alone would
    leave them pointing at the overlaid copy.
    """
    import tradingagents.default_config as default_config

    shared = default_config.DEFAULT_CONFIG
    saved = {k: v for k, v in os.environ.items() if k.startswith("TRADINGAGENTS_")}
    for key in saved:
        del os.environ[key]
    try:
        importlib.reload(default_config)
        shipped = copy.deepcopy(default_config.DEFAULT_CONFIG)
    finally:
        os.environ.update(saved)
    default_config.DEFAULT_CONFIG = shared
    shared.clear()
    shared.update(shipped)
    return shipped


_SHIPPED_DEFAULTS = _defaults_without_env_overlay()


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
        # `or` not a .get default: an env var present but empty (e.g. a key left
        # blank in a .env copied from .env.example) must still get the placeholder.
        monkeypatch.setenv(env_var, os.environ.get(env_var) or "placeholder")


@pytest.fixture(autouse=True)
def _isolate_env_overlay(monkeypatch):
    """Keep a developer's .env out of each test, and out of DEFAULT_CONFIG.

    Tests that exercise the overlay deliberately (test_env_overrides.py) set
    their own variables and reload the module, so a clean slate is what they
    want as a starting point too.
    """
    for key in [k for k in os.environ if k.startswith("TRADINGAGENTS_")]:
        monkeypatch.delenv(key, raising=False)

    import tradingagents.default_config as default_config

    shared = default_config.DEFAULT_CONFIG
    before = copy.deepcopy(shared)
    shared.clear()
    shared.update(copy.deepcopy(_SHIPPED_DEFAULTS))
    yield
    shared.clear()
    shared.update(before)


@pytest.fixture(autouse=True)
def _isolate_config():
    """Reset the global dataflows config before and after each test.

    ``set_config`` merges (it never clears keys absent from the override), so a
    test that sets e.g. ``tool_vendors`` would otherwise leak into later tests
    and make routing behavior order-dependent. Replace the global outright so
    every test starts from a clean DEFAULT_CONFIG.
    """
    import copy

    import tradingagents.dataflows.config as config_module
    import tradingagents.default_config as default_config

    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)
    yield
    config_module._config = copy.deepcopy(default_config.DEFAULT_CONFIG)


@pytest.fixture()
def mock_llm_client():
    client = MagicMock()
    client.get_llm.return_value = MagicMock()
    with patch(
        "tradingagents.llm_clients.factory.create_llm_client",
        return_value=client,
    ):
        yield client
