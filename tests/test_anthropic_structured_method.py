"""Anthropic structured output picks json_schema when the schema tool can't be forced.

Claude 5.5-class models (and any model with thinking enabled) reject forced
``tool_choice``; LangChain's default ``function_calling`` path then only hopes
the model calls the schema tool and raises ``OutputParserException`` when it
doesn't. ``NormalizedChatAnthropic`` defaults those models to native
``output_config.format`` instead.
"""

import warnings

import pytest
from pydantic import BaseModel

from tradingagents.llm_clients.anthropic_client import NormalizedChatAnthropic


class Decision(BaseModel):
    rating: str
    price_target: float


def _bound_kwargs(runnable):
    # with_structured_output returns ``bound_llm | parser``.
    return runnable.first.kwargs


@pytest.mark.unit
@pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"])
def test_unforceable_models_default_to_json_schema(model):
    llm = NormalizedChatAnthropic(model=model, api_key="x")
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # the forced-tool warning must not fire
        runnable = llm.with_structured_output(Decision)
    kwargs = _bound_kwargs(runnable)
    assert "format" in kwargs["output_config"]
    assert "tools" not in kwargs


@pytest.mark.unit
def test_thinking_enabled_defaults_to_json_schema():
    llm = NormalizedChatAnthropic(
        model="claude-opus-4-5", api_key="x", max_tokens=4096,
        thinking={"type": "enabled", "budget_tokens": 2048},
    )
    kwargs = _bound_kwargs(llm.with_structured_output(Decision))
    assert "format" in kwargs["output_config"]


@pytest.mark.unit
def test_forceable_model_keeps_function_calling():
    llm = NormalizedChatAnthropic(model="claude-opus-4-5", api_key="x")
    kwargs = _bound_kwargs(llm.with_structured_output(Decision))
    assert kwargs["tool_choice"]["name"] == "Decision"
    assert "output_config" not in kwargs


@pytest.mark.unit
def test_explicit_method_is_respected():
    llm = NormalizedChatAnthropic(model="claude-opus-4-5", api_key="x")
    kwargs = _bound_kwargs(llm.with_structured_output(Decision, method="json_schema"))
    assert "format" in kwargs["output_config"]
