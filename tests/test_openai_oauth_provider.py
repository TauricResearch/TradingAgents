import importlib
import sys
import types
import unittest
from unittest.mock import patch

import pytest


class _DummyChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def invoke(self, input, config=None, **kwargs):
        return input

    def with_structured_output(self, schema, *, method=None, **kwargs):
        return self


@pytest.mark.unit
class TestOpenAIOAuthProvider(unittest.TestCase):
    def _import_openai_client_module(self):
        sys.modules.setdefault(
            "langchain_openai",
            types.SimpleNamespace(ChatOpenAI=_DummyChatOpenAI),
        )
        sys.modules.setdefault(
            "langchain_core.messages",
            types.SimpleNamespace(AIMessage=object, BaseMessage=object),
        )
        sys.modules.setdefault(
            "langchain_core.outputs",
            types.SimpleNamespace(ChatGeneration=object, ChatResult=object),
        )
        sys.modules.setdefault(
            "langchain_openai.chat_models.base",
            types.SimpleNamespace(
                _construct_responses_api_payload=lambda messages, payload: payload,
                _convert_message_to_dict=lambda message, api=None: {"role": "user"},
            ),
        )
        return importlib.import_module("tradingagents.llm_clients.openai_client")

    def test_openai_auth_config_keys_are_mapped(self):
        auth_module = importlib.import_module("tradingagents.llm_clients.openai_auth")

        provider = lambda: "oauth-token-from-config-provider"
        kwargs = auth_module.build_openai_auth_kwargs(
            {
                "openai_api_key": "static-token",
                "openai_api_key_provider": provider,
                "openai_api_key_command": "python -c \"print('oauth-token-from-command')\"",
            }
        )

        self.assertEqual(kwargs.get("api_key"), "static-token")
        self.assertIs(kwargs.get("api_key_provider"), provider)
        self.assertEqual(
            kwargs.get("api_key_command"),
            "python -c \"print('oauth-token-from-command')\"",
        )

    def test_api_key_command_becomes_callable(self):
        auth_module = importlib.import_module("tradingagents.llm_clients.openai_auth")

        provider = auth_module.build_api_key_provider(
            api_key_command="python -c \"print('oauth-token-from-command')\""
        )

        self.assertTrue(callable(provider))
        self.assertEqual(provider(), "oauth-token-from-command")

    def test_api_key_provider_is_forwarded_to_chat_openai(self):
        openai_client_module = self._import_openai_client_module()

        with patch.object(openai_client_module, "NormalizedChatOpenAI") as mock_chat:
            client = openai_client_module.OpenAIClient(
                "gpt-5.4-mini",
                provider="openai",
                api_key_provider=lambda: "oauth-token-from-provider",
            )

            client.get_llm()

            call_kwargs = mock_chat.call_args[1]
            self.assertTrue(callable(call_kwargs.get("api_key")))
            self.assertEqual(call_kwargs["api_key"](), "oauth-token-from-provider")
            self.assertTrue(call_kwargs.get("use_responses_api"))

    def test_hermes_codex_auth_builds_provider_and_base_url(self):
        auth_module = importlib.import_module("tradingagents.llm_clients.openai_auth")

        with patch.object(
            auth_module,
            "resolve_hermes_codex_runtime_credentials",
            return_value={
                "api_key": "hermes-codex-token",
                "base_url": "https://chatgpt.com/backend-api/codex",
            },
        ):
            runtime = auth_module.build_openai_runtime_config(
                {
                    "use_hermes_codex_auth": True,
                },
                current_base_url=None,
            )
            self.assertTrue(callable(runtime["auth_kwargs"]["api_key_provider"]))
            self.assertEqual(
                runtime["auth_kwargs"]["api_key_provider"](),
                "hermes-codex-token",
            )
            self.assertEqual(runtime["base_url"], "https://chatgpt.com/backend-api/codex")


    def test_hermes_codex_does_not_override_explicit_backend_url(self):
        auth_module = importlib.import_module("tradingagents.llm_clients.openai_auth")

        with patch.object(
            auth_module,
            "resolve_hermes_codex_runtime_credentials",
            return_value={
                "api_key": "hermes-codex-token",
                "base_url": "https://chatgpt.com/backend-api/codex",
            },
        ):
            runtime = auth_module.build_openai_runtime_config(
                {
                    "use_hermes_codex_auth": True,
                },
                current_base_url="https://custom.example/v1",
            )

        self.assertEqual(runtime["base_url"], "https://custom.example/v1")

    def test_codex_backend_uses_codex_chat_openai_shim(self):
        openai_client_module = self._import_openai_client_module()

        with patch.object(openai_client_module, "CodexChatOpenAI") as mock_codex_chat, patch.object(
            openai_client_module,
            "NormalizedChatOpenAI",
        ) as mock_normalized_chat:
            client = openai_client_module.OpenAIClient(
                "gpt-5.4-mini",
                provider="openai",
                base_url="https://chatgpt.com/backend-api/codex",
                api_key_provider=lambda: "oauth-token-from-provider",
            )

            client.get_llm()

            self.assertTrue(mock_codex_chat.called)
            self.assertFalse(mock_normalized_chat.called)


if __name__ == "__main__":
    unittest.main()
