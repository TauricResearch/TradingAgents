"""Unit tests for the MLX and Ollama provider additions.

Covers:
- factory routing: mlx → OpenAIClient, ollama → OllamaClient
- OllamaClient construction and base_url forwarding
- OpenAIClient MLX key-handling (OMLX_API_KEY present / absent)
- model_catalog entries for mlx
- validators permissive behaviour for mlx / ollama
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Factory routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFactoryRouting(unittest.TestCase):
    def test_mlx_routes_to_openai_client(self):
        from tradingagents.llm_clients.factory import create_llm_client
        from tradingagents.llm_clients.openai_client import OpenAIClient

        with patch("tradingagents.llm_clients.openai_client.ChatOpenAI"):
            client = create_llm_client("mlx", "mlx-community/Qwen2.5-7B-4bit")

        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.provider, "mlx")

    def test_ollama_routes_to_ollama_client(self):
        from tradingagents.llm_clients.factory import create_llm_client
        from tradingagents.llm_clients.ollama_client import OllamaClient

        mock_chat_ollama = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": MagicMock(ChatOllama=mock_chat_ollama)}):
            client = create_llm_client("ollama", "llama3")

        self.assertIsInstance(client, OllamaClient)
        self.assertEqual(client.provider, "ollama")

    def test_ollama_not_routed_through_openai_client(self):
        """Ollama must NOT go through OpenAIClient after the split."""
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertNotIn("ollama", _OPENAI_COMPATIBLE)

    def test_mlx_in_openai_compatible(self):
        from tradingagents.llm_clients.factory import _OPENAI_COMPATIBLE

        self.assertIn("mlx", _OPENAI_COMPATIBLE)


# ---------------------------------------------------------------------------
# OllamaClient
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOllamaClient(unittest.TestCase):
    def _make_client(self, model="llama3", base_url=None):
        mock_chat_ollama_cls = MagicMock()
        mock_chat_ollama_cls.return_value = MagicMock()
        with patch.dict(
            "sys.modules",
            {"langchain_ollama": MagicMock(ChatOllama=mock_chat_ollama_cls)},
        ):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient(model, base_url)
            return client, mock_chat_ollama_cls

    def test_provider_is_ollama(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient("llama3")

        self.assertEqual(client.provider, "ollama")

    def test_base_url_forwarded_when_set(self):
        mock_chat_ollama_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama_cls
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient("llama3", base_url="http://myhost:11434/v1")
            client.get_llm()

        call_kwargs = mock_chat_ollama_cls.call_args[1]
        self.assertEqual(call_kwargs.get("base_url"), "http://myhost:11434/v1")

    def test_base_url_omitted_when_none(self):
        mock_chat_ollama_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama_cls
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient("llama3", base_url=None)
            client.get_llm()

        call_kwargs = mock_chat_ollama_cls.call_args[1]
        self.assertNotIn("base_url", call_kwargs)

    def test_default_url_is_forwarded(self):
        """Passing the default URL explicitly should still be forwarded (not dropped)."""
        mock_chat_ollama_cls = MagicMock()
        mock_module = MagicMock()
        mock_module.ChatOllama = mock_chat_ollama_cls
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient("llama3", base_url="http://localhost:11434/v1")
            client.get_llm()

        call_kwargs = mock_chat_ollama_cls.call_args[1]
        self.assertEqual(call_kwargs.get("base_url"), "http://localhost:11434/v1")

    def test_validate_model_always_true(self):
        mock_module = MagicMock()
        with patch.dict("sys.modules", {"langchain_ollama": mock_module}):
            from importlib import reload

            import tradingagents.llm_clients.ollama_client as mod

            reload(mod)
            client = mod.OllamaClient("anything:latest")

        self.assertTrue(client.validate_model())


# ---------------------------------------------------------------------------
# OpenAIClient — MLX key handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOpenAIClientMlxAuth(unittest.TestCase):
    """get_llm() routes through NormalizedChatOpenAI, not ChatOpenAI directly."""

    def _get_llm_kwargs(self, env: dict) -> dict:
        captured = {}

        def fake_normalized(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with patch(
            "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI",
            side_effect=fake_normalized,
        ):
            with patch.dict(os.environ, env, clear=False):
                from tradingagents.llm_clients.openai_client import OpenAIClient

                client = OpenAIClient("mlx-community/Qwen2.5-7B-4bit", provider="mlx")
                client.get_llm()

        return captured

    def test_uses_env_key_when_omlx_api_key_set(self):
        kwargs = self._get_llm_kwargs({"OMLX_API_KEY": "my-secret-key"})
        self.assertEqual(kwargs.get("api_key"), "my-secret-key")

    def test_falls_back_to_local_placeholder_when_no_key(self):
        with patch.dict(os.environ, {}, clear=True):
            kwargs = self._get_llm_kwargs({})
        self.assertEqual(kwargs.get("api_key"), "local")

    def test_default_base_url_is_localhost_8000(self):
        kwargs = self._get_llm_kwargs({})
        self.assertIn("localhost:8000", kwargs.get("base_url", ""))

    def test_custom_backend_url_overrides_default(self):
        captured = {}

        def fake_normalized(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        with patch(
            "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI",
            side_effect=fake_normalized,
        ):
            from tradingagents.llm_clients.openai_client import OpenAIClient

            client = OpenAIClient(
                "mlx-community/Qwen2.5-7B-4bit",
                base_url="http://192.168.1.5:8000/v1",
                provider="mlx",
            )
            client.get_llm()

        self.assertEqual(captured.get("base_url"), "http://192.168.1.5:8000/v1")


# ---------------------------------------------------------------------------
# model_catalog — mlx entries
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMlxModelCatalog(unittest.TestCase):
    def setUp(self):
        from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

        self.mlx_options = MODEL_OPTIONS.get("mlx", {})

    def test_mlx_has_quick_models(self):
        self.assertIn("quick", self.mlx_options)
        self.assertGreater(len(self.mlx_options["quick"]), 0)

    def test_mlx_has_deep_models(self):
        self.assertIn("deep", self.mlx_options)
        self.assertGreater(len(self.mlx_options["deep"]), 0)

    def test_mlx_quick_models_are_hf_ids(self):
        for label, model_id in self.mlx_options["quick"]:
            if model_id == "custom":
                continue
            self.assertIn("/", model_id, f"{model_id!r} does not look like an HF repo id")

    def test_mlx_both_modes_have_custom_option(self):
        for mode in ("quick", "deep"):
            ids = [mid for _, mid in self.mlx_options[mode]]
            self.assertIn("custom", ids, f"mlx {mode} missing 'custom' fallback")


# ---------------------------------------------------------------------------
# validators — permissive for mlx / ollama
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPermissiveProviders(unittest.TestCase):
    def test_mlx_accepts_arbitrary_model(self):
        from tradingagents.llm_clients.validators import validate_model

        self.assertTrue(validate_model("mlx", "mlx-community/some-new-model-8bit"))

    def test_ollama_accepts_arbitrary_model(self):
        from tradingagents.llm_clients.validators import validate_model

        self.assertTrue(validate_model("ollama", "custom-local:latest"))

    def test_mlx_in_permissive_providers(self):
        from tradingagents.llm_clients.validators import _PERMISSIVE_PROVIDERS

        self.assertIn("mlx", _PERMISSIVE_PROVIDERS)

    def test_openai_rejects_unknown_model(self):
        from tradingagents.llm_clients.validators import validate_model

        self.assertFalse(validate_model("openai", "not-a-real-gpt-model"))
