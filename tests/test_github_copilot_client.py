"""Tests for the github_copilot provider routing.

Mirrors the structure of tests/test_deepseek_reasoning.py: provider-specific
behaviour verified without any real network call.

``GitHubCopilotClient`` is a thin subclass of ``OpenAIClient`` that pins
the provider name and injects the ``X-GitHub-Api-Version`` header. The
parent class still owns the OpenAI-wire-protocol plumbing (streaming,
tool-calling, structured output, content normalization), so the patches
below target the parent module where ``NormalizedChatOpenAI`` is actually
instantiated.
"""

from unittest.mock import patch

import pytest

from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.github_copilot_client import GitHubCopilotClient
from tradingagents.llm_clients.model_catalog import get_known_models
from tradingagents.llm_clients.openai_client import OpenAIClient
from tradingagents.llm_clients.validators import validate_model


# ---------------------------------------------------------------------------
# Catalog / validator wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGitHubCopilotCatalog:
    def test_provider_present_in_catalog(self):
        known = get_known_models()
        assert "github_copilot" in known
        assert known["github_copilot"], "catalog should not be empty"

    def test_known_models_pass_validation(self):
        for model in get_known_models()["github_copilot"]:
            assert validate_model("github_copilot", model), model


# ---------------------------------------------------------------------------
# Factory routing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGitHubCopilotFactoryRouting:
    def test_factory_returns_dedicated_client(self):
        client = create_llm_client("github_copilot", "openai/gpt-4o")
        # Dedicated subclass for forward-compatibility with the future
        # langchain-github-copilot migration; still inherits OpenAIClient.
        assert isinstance(client, GitHubCopilotClient)
        assert isinstance(client, OpenAIClient)
        assert client.provider == "github_copilot"
        assert client.get_provider_name() == "github_copilot"

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_get_llm_uses_normalized_chat_openai(self, mock_chat):
        # Confirm the OpenAI-compatible normalized class is used (so content
        # normalization and the function-calling default for
        # with_structured_output apply automatically).
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
        )
        client.get_llm()
        assert mock_chat.called

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_default_base_url_is_github_models(self, mock_chat):
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
        )
        client.get_llm()
        kwargs = mock_chat.call_args.kwargs
        assert kwargs.get("base_url") == "https://models.github.ai/inference"

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_does_not_enable_responses_api(self, mock_chat):
        # The Responses API is OpenAI-native only; GitHub Models exposes
        # standard chat completions, so use_responses_api must NOT be set.
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
        )
        client.get_llm()
        kwargs = mock_chat.call_args.kwargs
        assert "use_responses_api" not in kwargs

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_injects_github_api_version_header(self, mock_chat):
        # GitHub's Models REST API pins behaviour behind an
        # ``X-GitHub-Api-Version`` header; the client must inject it so we
        # get the documented surface rather than the silent ``2022-11-28``
        # fallback.
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
        )
        client.get_llm()
        headers = mock_chat.call_args.kwargs.get("default_headers")
        assert headers is not None
        assert "X-GitHub-Api-Version" in headers
        # Sanity-check the date format so a typo (e.g. dropped digit)
        # surfaces here rather than as a 4xx at runtime.
        assert headers["X-GitHub-Api-Version"].count("-") == 2

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_user_default_headers_override_api_version(self, mock_chat):
        # An explicit caller-supplied X-GitHub-Api-Version wins over the
        # provider default, so users can pin to a different version when
        # needed.
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
            default_headers={"X-GitHub-Api-Version": "2022-11-28"},
        )
        client.get_llm()
        headers = mock_chat.call_args.kwargs["default_headers"]
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    @patch("tradingagents.llm_clients.openai_client.NormalizedChatOpenAI")
    def test_user_default_headers_merged_with_api_version(self, mock_chat):
        # User can pass extra headers (e.g. tracing) without losing the
        # provider default.
        client = create_llm_client(
            "github_copilot",
            "openai/gpt-4o",
            api_key="placeholder",
            default_headers={"X-Trace-Id": "abc"},
        )
        client.get_llm()
        headers = mock_chat.call_args.kwargs["default_headers"]
        assert headers["X-Trace-Id"] == "abc"
        assert "X-GitHub-Api-Version" in headers


# ---------------------------------------------------------------------------
# Validation warning behaviour
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGitHubCopilotValidation:
    def test_unknown_model_emits_runtime_warning(self):
        client = create_llm_client(
            "github_copilot", "not-a-real-copilot-model", api_key="placeholder"
        )
        with patch(
            "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI"
        ):
            with pytest.warns(RuntimeWarning, match="not-a-real-copilot-model"):
                client.get_llm()

    def test_known_model_does_not_warn(self, recwarn):
        client = create_llm_client(
            "github_copilot", "gpt-4o", api_key="placeholder"
        )
        with patch(
            "tradingagents.llm_clients.openai_client.NormalizedChatOpenAI"
        ):
            client.get_llm()
        runtime_warnings = [
            w for w in recwarn.list if issubclass(w.category, RuntimeWarning)
        ]
        assert runtime_warnings == []

    def test_missing_token_raises_actionable_error(self, monkeypatch):
        # Without GITHUB_TOKEN the OpenAI SDK would otherwise emit a
        # confusing "Missing credentials ... OPENAI_API_KEY" error. The
        # client should fail fast with a Copilot-specific message instead.
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = create_llm_client("github_copilot", "openai/gpt-4o")
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            client.get_llm()
