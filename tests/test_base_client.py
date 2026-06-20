import unittest
import warnings
from unittest.mock import MagicMock, patch

import pytest

from tradingagents.llm_clients.base_client import (
    BaseLLMClient,
    normalize_content,
)


class _ConcreteClient(BaseLLMClient):
    def get_llm(self):
        return MagicMock()

    def validate_model(self):
        return True


class _ConcreteClientNoProvider(BaseLLMClient):
    provider = None

    def get_llm(self):
        return MagicMock()

    def validate_model(self):
        return False


@pytest.mark.unit
class NormalizeContentTests(unittest.TestCase):
    def test_passes_through_string_content(self):
        response = MagicMock()
        response.content = "plain string"
        result = normalize_content(response)
        self.assertEqual(result.content, "plain string")

    def test_joins_text_blocks_from_list(self):
        response = MagicMock()
        response.content = [
            {"type": "text", "text": "Hello "},
            {"type": "text", "text": "World"},
        ]
        result = normalize_content(response)
        self.assertEqual(result.content, "Hello \nWorld")

    def test_skips_non_text_blocks(self):
        response = MagicMock()
        response.content = [
            {"type": "reasoning", "text": "thinking..."},
            {"type": "text", "text": "Answer"},
        ]
        result = normalize_content(response)
        self.assertEqual(result.content, "Answer")

    def test_passes_through_string_items_in_list(self):
        response = MagicMock()
        response.content = ["hello", "world"]
        result = normalize_content(response)
        self.assertEqual(result.content, "hello\nworld")


@pytest.mark.unit
class BaseLLMClientTests(unittest.TestCase):
    def test_stores_init_params(self):
        client = _ConcreteClient("gpt-4", "https://api.openai.com", temperature=0.7)
        self.assertEqual(client.model, "gpt-4")
        self.assertEqual(client.base_url, "https://api.openai.com")
        self.assertEqual(client.kwargs["temperature"], 0.7)

    def test_get_provider_name_from_attribute(self):
        client = _ConcreteClient("test")
        client.provider = "openai"
        self.assertEqual(client.get_provider_name(), "openai")

    def test_get_provider_name_falls_back_to_class_name(self):
        client = _ConcreteClientNoProvider("test")
        name = client.get_provider_name()
        self.assertIsInstance(name, str)

    def test_require_model_raises_on_empty(self):
        client = _ConcreteClient("")
        with self.assertRaises(ValueError):
            client._require_model()

    def test_require_model_passes_with_valid_model(self):
        client = _ConcreteClient("gpt-4")
        client._require_model()

    def test_warn_if_unknown_model_valid(self):
        client = _ConcreteClient("gpt-4")
        with warnings.catch_warnings(record=True) as w:
            client.warn_if_unknown_model()
            self.assertEqual(len(w), 0)

    def test_warn_if_unknown_model_invalid(self):
        client = _ConcreteClientNoProvider("unknown-model")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            client.warn_if_unknown_model()
            self.assertEqual(len(w), 1)
            self.assertIn("unknown-model", str(w[0].message))


# =========================================================================
# Tests merged from test_final_push.py and test_llm_and_minor.py
# =========================================================================


class _ClientNoAttr(BaseLLMClient):
    """Subclass without a 'provider' attribute at all."""

    def get_llm(self):
        return MagicMock()

    def validate_model(self):
        return True


class _ClientNoneProvider(BaseLLMClient):
    provider = None

    def get_llm(self):
        return MagicMock()

    def validate_model(self):
        return False


class BaseClientAbstractTests(unittest.TestCase):
    """Lines 66, 71: abstract methods cannot be instantiated without implementation."""

    def test_cannot_instantiate_abstract_class(self):
        with self.assertRaises(TypeError):
            BaseLLMClient("test")

    def test_concrete_subclass_works(self):
        class Concrete(BaseLLMClient):
            def get_llm(self):
                return "llm"
            def validate_model(self):
                return True
        client = Concrete("test")
        self.assertEqual(client.get_llm(), "llm")
        self.assertTrue(client.validate_model())


class TestBaseClientEdgeCases(unittest.TestCase):
    """Cover remaining get_provider_name and _require_model edge cases."""

    def test_get_provider_name_no_provider_attr(self):
        """Line 35–38: get_provider_name when provider attribute doesn't exist."""
        client = _ClientNoAttr("test-model")
        name = client.get_provider_name()
        self.assertIsInstance(name, str)
        self.assertIn("clientnoattr", name.lower())

    def test_get_provider_name_provider_is_none(self):
        """Line 35–38: provider = None triggers fallback."""
        client = _ClientNoneProvider("test-model")
        name = client.get_provider_name()
        self.assertIsInstance(name, str)
        self.assertIn("clientnoneprovider", name.lower())

    def test_get_provider_name_custom_provider(self):
        """Line 37: custom provider string returned."""
        client = _ClientNoneProvider("test-model")
        client.provider = "my-custom-provider"
        name = client.get_provider_name()
        self.assertEqual(name, "my-custom-provider")


if __name__ == "__main__":
    unittest.main()
