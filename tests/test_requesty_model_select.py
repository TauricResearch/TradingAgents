"""Requesty model selection mirrors OpenRouter (#1000): prompts are labeled by
mode, required prompts exit cleanly on cancel, and the model list is
newest-first with a mainstream shortlist and a Custom-ID escape hatch."""

from unittest import mock

import pytest

from cli import utils


def _asks(value):
    return mock.Mock(ask=mock.Mock(return_value=value))


@pytest.mark.unit
class TestRequestyPromptLabel:
    @pytest.mark.parametrize("mode,label", [("quick", "Quick-Thinking"), ("deep", "Deep-Thinking")])
    def test_prompt_states_the_mode(self, mode, label):
        captured = {}

        def fake_select(message, **kwargs):
            captured["message"] = message
            return _asks("openai/gpt-4o-mini")

        with mock.patch.object(utils, "_fetch_requesty_models",
                               return_value=[("openai/gpt-4o-mini", "openai/gpt-4o-mini")]), \
             mock.patch.object(utils.questionary, "select", side_effect=fake_select):
            out = utils.select_requesty_model(mode)

        assert label in captured["message"]
        assert "Requesty" in captured["message"]
        assert out == "openai/gpt-4o-mini"


@pytest.mark.unit
class TestRequestyLatestFirst:
    def test_models_sorted_newest_first(self):
        # Requesty's /v1/models is OpenAI-shaped but carries no per-model name;
        # the id doubles as the label, so only id + created are present here.
        payload = {"data": [
            {"id": "openai/old", "created": 1000},
            {"id": "openai/new", "created": 3000},
            {"id": "openai/mid", "created": 2000},
        ]}
        resp = mock.Mock()
        resp.json.return_value = payload
        resp.raise_for_status = mock.Mock()
        with mock.patch("requests.get", return_value=resp):
            out = utils._fetch_requesty_models()
        assert [mid for _, mid in out] == ["openai/new", "openai/mid", "openai/old"]


@pytest.mark.unit
class TestRequestyMainstreamFilter:
    def test_dropdown_prefers_mainstream_over_niche(self):
        models = [
            ("policy/fable", "policy/fable"),
            ("anthropic/claude-x", "anthropic/claude-x"),
            ("openai/gpt-x", "openai/gpt-x"),
        ]
        captured = {}

        def fake_select(message, **kwargs):
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("anthropic/claude-x")

        with mock.patch.object(utils, "_fetch_requesty_models", return_value=models), \
             mock.patch.object(utils.questionary, "select", side_effect=fake_select):
            utils.select_requesty_model("quick")

        assert "anthropic/claude-x" in captured["values"]
        assert "openai/gpt-x" in captured["values"]
        assert "policy/fable" not in captured["values"]
        assert "custom" in captured["values"]  # escape hatch preserved

    def test_falls_back_to_all_when_no_mainstream(self):
        models = [("policy/fable", "policy/fable"), ("vertex/x", "vertex/x")]
        captured = {}

        def fake_select(message, **kwargs):
            captured["values"] = [c.value for c in kwargs["choices"]]
            return _asks("policy/fable")

        with mock.patch.object(utils, "_fetch_requesty_models", return_value=models), \
             mock.patch.object(utils.questionary, "select", side_effect=fake_select):
            utils.select_requesty_model("deep")

        assert "policy/fable" in captured["values"]  # fallback keeps the list usable


@pytest.mark.unit
class TestRequestyCancelExitsCleanly:
    def test_dropdown_cancel_exits(self):
        with mock.patch.object(utils, "_fetch_requesty_models", return_value=[]), \
             mock.patch.object(utils.questionary, "select", return_value=_asks(None)), \
             pytest.raises(SystemExit):
            utils.select_requesty_model("quick")

    def test_custom_id_cancel_exits(self):
        with mock.patch.object(utils, "_fetch_requesty_models", return_value=[]), \
             mock.patch.object(utils.questionary, "select", return_value=_asks("custom")), \
             mock.patch.object(utils.questionary, "text", return_value=_asks(None)), \
             pytest.raises(SystemExit):
            utils.select_requesty_model("deep")
