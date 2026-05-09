"""Tests for OpenCode Go provider wiring."""
import os
import unittest
from unittest import mock

import pytest

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.model_catalog import (
    MODEL_OPTIONS,
    get_known_models,
    get_model_options,
)
from tradingagents.llm_clients.openai_client import (
    OpenAIClient,
    DeepSeekChatOpenAI,
)
from tradingagents.llm_clients.validators import validate_model


OPENCODE_GO_MODELS = {
    "glm-5.1", "glm-5",
    "kimi-k2.5", "kimi-k2.6",
    "deepseek-v4-pro", "deepseek-v4-flash",
    "mimo-v2.5", "mimo-v2.5-pro",
    "minimax-m2.7", "minimax-m2.5",
    "qwen3.6-plus", "qwen3.5-plus",
}


@pytest.mark.unit
class OpenCodeGoFactoryWiringTests(unittest.TestCase):
    def test_factory_returns_openai_client_for_opencode_go(self):
        client = create_llm_client("opencode-go", "kimi-k2.6")
        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.provider, "opencode-go")
        self.assertEqual(client.model, "kimi-k2.6")

    def test_get_llm_uses_opencode_go_base_url_and_api_key_env(self):
        client = create_llm_client("opencode-go", "kimi-k2.6")
        with mock.patch.dict(os.environ, {"OPENCODE_GO_API_KEY": "sk-test-123"}):
            llm = client.get_llm()
        self.assertEqual(str(llm.openai_api_base), "https://opencode.ai/zen/go/v1")
        self.assertEqual(llm.openai_api_key.get_secret_value(), "sk-test-123")

    def test_get_llm_returns_reasoning_content_subclass(self):
        client = create_llm_client("opencode-go", "deepseek-v4-pro")
        with mock.patch.dict(os.environ, {"OPENCODE_GO_API_KEY": "sk-test-123"}):
            llm = client.get_llm()
        self.assertIsInstance(llm, DeepSeekChatOpenAI)

    def test_explicit_base_url_overrides_default(self):
        client = create_llm_client(
            "opencode-go", "kimi-k2.6", base_url="https://proxy.example.com/v1"
        )
        with mock.patch.dict(os.environ, {"OPENCODE_GO_API_KEY": "sk-test-123"}):
            llm = client.get_llm()
        self.assertEqual(str(llm.openai_api_base), "https://proxy.example.com/v1")


@pytest.mark.unit
class OpenCodeGoCatalogTests(unittest.TestCase):
    def test_catalog_has_opencode_go_with_quick_and_deep_modes(self):
        self.assertIn("opencode-go", MODEL_OPTIONS)
        self.assertIn("quick", MODEL_OPTIONS["opencode-go"])
        self.assertIn("deep", MODEL_OPTIONS["opencode-go"])

    def test_all_twelve_models_appear_in_catalog(self):
        catalog_models = set(get_known_models()["opencode-go"])
        self.assertEqual(catalog_models, OPENCODE_GO_MODELS)

    def test_every_opencode_go_model_passes_validator(self):
        for model in OPENCODE_GO_MODELS:
            with self.subTest(model=model):
                self.assertTrue(validate_model("opencode-go", model))

    def test_quick_and_deep_modes_each_contain_six_models(self):
        quick = {value for _, value in get_model_options("opencode-go", "quick")}
        deep = {value for _, value in get_model_options("opencode-go", "deep")}
        self.assertEqual(quick & deep, set())
        self.assertEqual(quick | deep, OPENCODE_GO_MODELS)
        self.assertEqual(len(quick), 6)
        self.assertEqual(len(deep), 6)


@pytest.mark.unit
class OpenCodeGoCLIRegistrationTests(unittest.TestCase):
    def test_cli_providers_list_includes_opencode_go(self):
        from cli.utils import select_llm_provider

        rows = [
            row
            for const in select_llm_provider.__code__.co_consts
            if isinstance(const, tuple)
            for row in const
            if isinstance(row, tuple)
            and len(row) == 3
            and row[0:2] == ("OpenCode Go", "opencode-go")
        ]
        self.assertEqual(len(rows), 1, f"expected exactly one OpenCode Go row, found {rows}")
        self.assertEqual(rows[0][2], "https://opencode.ai/zen/go/v1")
