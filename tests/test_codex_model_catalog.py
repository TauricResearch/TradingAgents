import pytest

from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.validators import validate_model


@pytest.mark.unit
def test_codex_model_catalog_lists_common_codex_models():
    quick_models = [model for _, model in get_model_options("codex", "quick")]
    deep_models = [model for _, model in get_model_options("codex", "deep")]

    for model in (
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex-spark",
    ):
        assert model in quick_models
        assert model in deep_models
        assert validate_model("codex", model)

    assert "custom" in quick_models
    assert "custom" in deep_models
