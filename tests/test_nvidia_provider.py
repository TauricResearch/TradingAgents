"""Tests for NVIDIA provider support."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.validators import validate_model


@pytest.mark.unit
class NVIDIAProviderTests(unittest.TestCase):
    """Test NVIDIA provider integration and model filtering."""

    def test_nvidia_provider_routes_to_openai_compatible_client(self):
        """NVIDIA should use OpenAI-compatible client path."""
        with patch(
            "tradingagents.llm_clients.openai_client.OpenAIClient"
        ) as mock_openai_client:
            mock_openai_client.return_value = MagicMock()
            create_llm_client("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1")
            mock_openai_client.assert_called_once()

    def test_nvidia_accepts_arbitrary_model_ids(self):
        """NVIDIA should accept any model ID without validation warnings."""
        # Test standard NVIDIA models
        self.assertTrue(validate_model("nvidia", "nvidia/llama-3.3-nemotron-super-49b-v1"))
        self.assertTrue(validate_model("nvidia", "google/gemma-3-27b-it"))
        self.assertTrue(validate_model("nvidia", "mistralai/mixtral-8x7b-instruct-v0.1"))
        
        # Test arbitrary custom NVIDIA models
        self.assertTrue(validate_model("nvidia", "custom-model-id"))
        self.assertTrue(validate_model("nvidia", "vendor/any-model-v99"))

    def test_nvidia_model_filter_excludes_vision_models(self):
        """Model filter should exclude vision-related models."""
        from cli.utils import _fetch_nvidia_models
        
        # Mock the API response with mixed model types
        mock_response_data = [
            {"id": "nvidia/llama-3.3-nemotron-super-49b-v1"},  # Include
            {"id": "google/gemma-3-27b-it"},  # Include
            {"id": "nvidia/nv-vision-language-v1"},  # Exclude (vision)
            {"id": "nvidia/vlm-multimodal-v1"},  # Exclude (vlm/multimodal)
        ]
        
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": mock_response_data}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
                models = _fetch_nvidia_models()
                model_ids = [mid for _, mid in models]
                
                # Vision models should be filtered out
                self.assertNotIn("nvidia/nv-vision-language-v1", model_ids)
                self.assertNotIn("nvidia/vlm-multimodal-v1", model_ids)
                
                # LLM models should be included
                self.assertIn("nvidia/llama-3.3-nemotron-super-49b-v1", model_ids)
                self.assertIn("google/gemma-3-27b-it", model_ids)

    def test_nvidia_model_filter_excludes_embedding_models(self):
        """Model filter should exclude embedding models."""
        from cli.utils import _fetch_nvidia_models
        
        mock_response_data = [
            {"id": "nvidia/llama-3.3-nemotron-super-49b-v1"},  # Include
            {"id": "nvidia/nv-embed-qa-4"},  # Exclude (embed)
            {"id": "nvidia/nv-embeddings-v1"},  # Exclude (embedding)
        ]
        
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": mock_response_data}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
                models = _fetch_nvidia_models()
                model_ids = [mid for _, mid in models]
                
                # Embedding models should be filtered
                self.assertNotIn("nvidia/nv-embed-qa-4", model_ids)
                self.assertNotIn("nvidia/nv-embeddings-v1", model_ids)
                
                # LLM models should be included
                self.assertIn("nvidia/llama-3.3-nemotron-super-49b-v1", model_ids)

    def test_nvidia_model_filter_excludes_coding_models(self):
        """Model filter should exclude coding-specific models."""
        from cli.utils import _fetch_nvidia_models
        
        mock_response_data = [
            {"id": "nvidia/llama-3.3-nemotron-super-49b-v1"},  # Include
            {"id": "nvidia/stable-code-3b"},  # Exclude (stable-code)
            {"id": "starcoder/starcoder2-15b"},  # Exclude (starcoder/code)
        ]
        
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": mock_response_data}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
                models = _fetch_nvidia_models()
                model_ids = [mid for _, mid in models]
                
                # Coding models should be filtered
                self.assertNotIn("nvidia/stable-code-3b", model_ids)
                self.assertNotIn("starcoder/starcoder2-15b", model_ids)
                
                # LLM models should be included
                self.assertIn("nvidia/llama-3.3-nemotron-super-49b-v1", model_ids)

    def test_nvidia_model_filter_handles_missing_api_key(self):
        """Model fetch should gracefully handle missing API key."""
        from cli.utils import _fetch_nvidia_models
        
        with patch.dict("os.environ", {}, clear=False):
            # Ensure NVIDIA_API_KEY is not set
            import os
            os.environ.pop("NVIDIA_API_KEY", None)
            
            models = _fetch_nvidia_models()
            self.assertEqual(models, [])

    def test_nvidia_model_filter_handles_api_error(self):
        """Model fetch should gracefully handle API errors."""
        from cli.utils import _fetch_nvidia_models
        
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("API Error")
            
            with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
                models = _fetch_nvidia_models()
                self.assertEqual(models, [])

    def test_nvidia_model_filter_returns_sorted_models(self):
        """Model filter should return models in sorted order."""
        from cli.utils import _fetch_nvidia_models
        
        mock_response_data = [
            {"id": "zebra-model"},
            {"id": "alpha-model"},
            {"id": "beta-model"},
        ]
        
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"data": mock_response_data}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response
            
            with patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
                models = _fetch_nvidia_models()
                model_ids = [mid for _, mid in models]
                
                # Should be sorted
                self.assertEqual(model_ids, sorted(model_ids))
                self.assertEqual(model_ids, ["alpha-model", "beta-model", "zebra-model"])

    def test_nvidia_model_endpoints_configured(self):
        """NVIDIA endpoint and auth should be properly configured."""
        from tradingagents.llm_clients.openai_client import _PROVIDER_CONFIG
        
        # Check NVIDIA is in provider config
        self.assertIn("nvidia", _PROVIDER_CONFIG)
        
        # Check endpoint and auth var are correct
        endpoint, auth_key = _PROVIDER_CONFIG["nvidia"]
        self.assertEqual(endpoint, "https://integrate.api.nvidia.com/v1")
        self.assertEqual(auth_key, "NVIDIA_API_KEY")

    def test_nvidia_in_model_catalog(self):
        """NVIDIA should be in model catalog with presets."""
        from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
        
        self.assertIn("nvidia", MODEL_OPTIONS)
        
        # Check quick mode models
        self.assertIn("quick", MODEL_OPTIONS["nvidia"])
        quick_models = MODEL_OPTIONS["nvidia"]["quick"]
        self.assertTrue(len(quick_models) > 0)
        
        # Check deep mode models
        self.assertIn("deep", MODEL_OPTIONS["nvidia"])
        deep_models = MODEL_OPTIONS["nvidia"]["deep"]
        self.assertTrue(len(deep_models) > 0)

    def test_nvidia_factory_integration(self):
        """Factory should correctly instantiate NVIDIA client."""
        with patch("tradingagents.llm_clients.openai_client.ChatOpenAI"):
            client = create_llm_client(
                "nvidia",
                "nvidia/llama-3.3-nemotron-super-49b-v1",
                base_url="https://integrate.api.nvidia.com/v1"
            )
            
            # Should be an OpenAIClient instance
            from tradingagents.llm_clients.openai_client import OpenAIClient
            self.assertIsInstance(client, OpenAIClient)
