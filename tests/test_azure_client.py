"""Unit tests for tradingagents/llm_clients/azure_client.py."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.llm_clients.azure_client import (
    AzureOpenAIClient,
    NormalizedAzureChatOpenAI,
)

pytestmark = pytest.mark.unit


class AzureClientEdgeTests(unittest.TestCase):
    """Lines 18, 36-48, 52."""

    def test_normalized_azure_invoke(self):
        client = NormalizedAzureChatOpenAI(
            model="gpt-4",
            azure_deployment="my-deploy",
            openai_api_key="test",
            openai_api_version="2025-03-01-preview",
            azure_endpoint="https://test.openai.azure.com",
        )
        raw_response = MagicMock()
        raw_response.content = "normalized"
        with patch.object(NormalizedAzureChatOpenAI, "invoke", wraps=client.invoke), \
             patch("langchain_openai.AzureChatOpenAI.invoke", return_value=raw_response), \
             patch("tradingagents.llm_clients.azure_client.normalize_content",
                   return_value=raw_response) as mock_norm:
            result = client.invoke("hello")
        self.assertEqual(result.content, "normalized")

    def test_get_llm_passes_kwargs(self):
        import tradingagents.llm_clients.azure_client as mod

        captured = {}
        with patch.object(mod, "NormalizedAzureChatOpenAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)), \
             patch.dict(os.environ, {"AZURE_OPENAI_DEPLOYMENT_NAME": "deploy-env"}):
            client = AzureOpenAIClient(model="gpt-4", timeout=30, max_retries=3, temperature=0.5)
            client.get_llm()
        self.assertEqual(captured["kwargs"]["model"], "gpt-4")
        self.assertEqual(captured["kwargs"]["azure_deployment"], "deploy-env")
        self.assertEqual(captured["kwargs"]["timeout"], 30)
        self.assertEqual(captured["kwargs"]["max_retries"], 3)
        self.assertEqual(captured["kwargs"]["temperature"], 0.5)

    def test_get_llm_deployment_fallback_to_model(self):
        import tradingagents.llm_clients.azure_client as mod

        captured = {}
        with patch.object(mod, "NormalizedAzureChatOpenAI", lambda **kwargs: captured.__setitem__("kwargs", kwargs)), \
             patch.dict(os.environ, {}, clear=True):
            client = AzureOpenAIClient(model="gpt-4")
            client.get_llm()
        self.assertEqual(captured["kwargs"]["azure_deployment"], "gpt-4")

    def test_get_llm_missing_model_raises(self):
        client = AzureOpenAIClient("")
        with self.assertRaises(ValueError):
            client.get_llm()

    def test_validate_model_always_true(self):
        client = AzureOpenAIClient("gpt-4")
        self.assertTrue(client.validate_model())


class TestAzureClient(unittest.TestCase):
    """NormalizedAzureChatOpenAI, get_llm, validate_model."""

    def test_normalized_azure_is_used_by_get_llm(self):
        with patch("tradingagents.llm_clients.azure_client.NormalizedAzureChatOpenAI") as mock_cls:
            client = AzureOpenAIClient("gpt-4", api_key="x")
            result = client.get_llm()
            mock_cls.assert_called_once()
            self.assertEqual(result, mock_cls.return_value)

    @patch.dict(os.environ, {"AZURE_OPENAI_DEPLOYMENT_NAME": "my-deployment"}, clear=False)
    @patch("tradingagents.llm_clients.azure_client.NormalizedAzureChatOpenAI")
    def test_get_llm_with_deployment_name(self, mock_chat):
        client = AzureOpenAIClient("gpt-4", api_key="x")
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["azure_deployment"], "my-deployment")

    @patch("tradingagents.llm_clients.azure_client.NormalizedAzureChatOpenAI")
    def test_get_llm_passthrough_kwargs(self, mock_chat):
        client = AzureOpenAIClient(
            "gpt-4",
            api_key="test-key",
            max_retries=3,
            temperature=0.5,
            timeout=60,
        )
        client.get_llm()
        call_kwargs = mock_chat.call_args[1]
        self.assertEqual(call_kwargs["api_key"], "test-key")
        self.assertEqual(call_kwargs["max_retries"], 3)
        self.assertEqual(call_kwargs["temperature"], 0.5)
        self.assertEqual(call_kwargs["timeout"], 60)
