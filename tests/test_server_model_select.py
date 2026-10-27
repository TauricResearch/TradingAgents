"""A local server's models are offered from the server itself.

LM Studio, vLLM, llama.cpp and Ollama list what they serve at <base_url>/models.
Typing the ID instead lets a typo or an unloaded model through to the first
agent's call, mid-run. A server that cannot be asked falls back to the menu the
provider had before, so a model can still be entered.
"""

from unittest import mock

import pytest

from cli import prompts


@pytest.fixture(autouse=True)
def _fresh_listing():
    prompts._fetch_server_models.cache_clear()
    yield
    prompts._fetch_server_models.cache_clear()


def _served(*ids):
    resp = mock.Mock()
    resp.json.return_value = {"object": "list", "data": [{"id": i, "object": "model"} for i in ids]}
    resp.raise_for_status = mock.Mock()
    return resp


def _asks(value):
    return mock.Mock(ask=mock.Mock(return_value=value))


@pytest.mark.unit
class TestFetchServerModels:
    def test_the_served_models_are_listed_by_id(self):
        with mock.patch("requests.get", return_value=_served("qwen3-8b", "gemma-3-12b", "qwen3-8b")) as get:
            out = prompts._fetch_server_models("http://localhost:1234/v1/", "openai_compatible")
        assert out == (("gemma-3-12b", "gemma-3-12b"), ("qwen3-8b", "qwen3-8b"))
        assert get.call_args.args[0] == "http://localhost:1234/v1/models"

    def test_a_key_set_for_the_endpoint_is_sent(self, monkeypatch):
        monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "sk-relay")
        with mock.patch("requests.get", return_value=_served("m")) as get:
            prompts._fetch_server_models("https://relay.example/v1", "openai_compatible")
        assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer sk-relay"}

    def test_a_keyless_server_is_asked_without_one(self, monkeypatch):
        monkeypatch.delenv("OPENAI_COMPATIBLE_API_KEY", raising=False)
        with mock.patch("requests.get", return_value=_served("m")) as get:
            prompts._fetch_server_models("http://localhost:11434/v1", "ollama")
        assert get.call_args.kwargs["headers"] == {}

    def test_a_server_that_cannot_be_reached_lists_nothing(self):
        with mock.patch("requests.get", side_effect=ConnectionError("refused")):
            assert prompts._fetch_server_models("http://localhost:1234/v1", "openai_compatible") == ()

    def test_the_quick_and_deep_prompts_ask_the_server_once(self):
        with mock.patch("requests.get", return_value=_served("m")) as get:
            prompts._fetch_server_models("http://localhost:1234/v1", "openai_compatible")
            prompts._fetch_server_models("http://localhost:1234/v1", "openai_compatible")
        get.assert_called_once()


@pytest.mark.unit
class TestSelectServedModel:
    @pytest.mark.parametrize("provider", ["openai_compatible", "ollama"])
    def test_the_served_models_are_offered_with_a_custom_entry(self, provider):
        captured = {}

        def fake_select(message, **kwargs):
            captured["message"] = message
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("qwen3-8b")

        with mock.patch("requests.get", return_value=_served("qwen3-8b", "gemma-3-12b")), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            out = prompts.select_deep_thinking_agent(provider, None, "http://localhost:1234/v1")

        assert out == "qwen3-8b"
        assert captured["values"] == ["gemma-3-12b", "qwen3-8b", "custom"]
        assert "Deep-Thinking" in captured["message"]
        assert "http://localhost:1234/v1" in captured["message"]

    def test_the_remembered_model_is_preselected(self):
        captured = {}

        def fake_select(message, **kwargs):
            captured["default"] = kwargs["default"]
            return _asks("qwen3-8b")

        with mock.patch("requests.get", return_value=_served("gemma-3-12b", "qwen3-8b")), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            prompts.select_shallow_thinking_agent("openai_compatible", "qwen3-8b", "http://localhost:1234/v1")

        assert captured["default"] == "qwen3-8b"

    def test_an_unreachable_server_falls_back_to_the_providers_menu(self):
        captured = {}

        def fake_select(message, **kwargs):
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("qwen3:latest")

        with mock.patch("requests.get", side_effect=ConnectionError("refused")), \
             mock.patch.object(prompts.questionary, "select", side_effect=fake_select):
            out = prompts.select_shallow_thinking_agent("ollama", None, "http://localhost:11434/v1")

        assert out == "qwen3:latest"
        assert "qwen3:latest" in captured["values"] and "custom" in captured["values"]

    def test_a_hosted_provider_does_not_ask_the_endpoint(self):
        with mock.patch("requests.get") as get, \
             mock.patch.object(prompts.questionary, "select", return_value=_asks("gpt-5.5")):
            prompts.select_deep_thinking_agent("openai", None, "https://api.openai.com/v1")
        get.assert_not_called()
