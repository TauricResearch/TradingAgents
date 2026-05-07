"""Tests for structured_output module: invoke_structured_or_freetext fallback utility.

Feature: upstream-feature-adoption, Property 14: Structured Output Fallback on Error Types
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, Field, ValidationError

from tradingagents.agents.utils.structured_output import invoke_structured_or_freetext

# ---------------------------------------------------------------------------
# Test schema and helpers
# ---------------------------------------------------------------------------


class _TestSchema(BaseModel):
    """Simple schema for testing."""

    action: str = Field(description="Test action")
    value: int = Field(description="Test value")


def _mock_fallback_extractor(text: str) -> dict[str, Any]:
    """Simple fallback extractor for testing."""
    return {"action": "Hold", "value": 0, "raw_text": text}


def _make_mock_llm(
    *,
    structured_error: Exception | None = None,
    structured_result: Any = None,
    freetext_result: Any = None,
    freetext_error: Exception | None = None,
):
    """Create a mock LLM with configurable structured/freetext behavior."""
    mock_llm = MagicMock()

    if structured_error is not None:
        mock_llm.with_structured_output.side_effect = structured_error
    else:
        structured_llm = MagicMock()
        if structured_result is not None:
            structured_llm.invoke.return_value = structured_result
        else:
            structured_llm.invoke.return_value = None
        mock_llm.with_structured_output.return_value = structured_llm

    if freetext_result is not None:
        mock_llm.invoke.return_value = freetext_result
    elif freetext_error is not None:
        mock_llm.invoke.side_effect = freetext_error
    else:
        result = MagicMock()
        result.content = "fallback text content"
        mock_llm.invoke.return_value = result

    return mock_llm


# ---------------------------------------------------------------------------
# Property 14: For NotImplementedError/ValidationError, utility invokes
#              fallback without raising
# ---------------------------------------------------------------------------


_FALLBACK_ERRORS = st.sampled_from(
    [
        NotImplementedError("Provider does not support structured output"),
        ValidationError.from_exception_data(
            title="_TestSchema",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("action",),
                    "msg": "Field required",
                    "input": {},
                }
            ],
        ),
        TypeError("unexpected keyword argument"),
        AttributeError("object has no attribute 'with_structured_output'"),
    ]
)


@settings(max_examples=100)
@given(error=_FALLBACK_ERRORS)
def test_prop14_fallback_on_error_types(error: Exception):
    """For known error types, the utility falls back without raising.

    Feature: upstream-feature-adoption, Property 14: Structured Output Fallback on Error Types
    """
    mock_llm = _make_mock_llm(structured_error=error)

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        freetext_result = MagicMock()
        freetext_result.content = "some fallback text"
        mock_invoke.return_value = (freetext_result, None)

        schema_instance, raw_text, fallback_dict = invoke_structured_or_freetext(
            llm=mock_llm,
            schema=_TestSchema,
            messages=[{"role": "user", "content": "test"}],
            fallback_extractor=_mock_fallback_extractor,
            agent_name="test_agent",
            timeout_tier="deep",
        )

    # Structured path failed, so schema_instance should be None
    assert schema_instance is None
    # Fallback dict should be populated
    assert fallback_dict is not None
    assert fallback_dict["action"] == "Hold"
    assert raw_text == "some fallback text"


# ---------------------------------------------------------------------------
# Unit: successful structured path returns schema instance
# ---------------------------------------------------------------------------


def test_structured_path_success():
    """When structured output succeeds, returns the schema instance."""
    expected = _TestSchema(action="Buy", value=42)

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        mock_invoke.return_value = (expected, None)

        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = MagicMock()

        schema_instance, raw_text, fallback_dict = invoke_structured_or_freetext(
            llm=mock_llm,
            schema=_TestSchema,
            messages=[{"role": "user", "content": "test"}],
            fallback_extractor=_mock_fallback_extractor,
            agent_name="test_agent",
        )

    assert schema_instance is not None
    assert schema_instance.action == "Buy"
    assert schema_instance.value == 42
    assert raw_text == ""
    assert fallback_dict is None


# ---------------------------------------------------------------------------
# Unit: fallback on NotImplementedError
# ---------------------------------------------------------------------------


def test_fallback_on_not_implemented_error():
    """When with_structured_output raises NotImplementedError, falls back gracefully."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = NotImplementedError("not supported")

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        freetext_result = MagicMock()
        freetext_result.content = "The recommendation is Hold with value 0"
        mock_invoke.return_value = (freetext_result, None)

        schema_instance, raw_text, fallback_dict = invoke_structured_or_freetext(
            llm=mock_llm,
            schema=_TestSchema,
            messages=[{"role": "user", "content": "test"}],
            fallback_extractor=_mock_fallback_extractor,
            agent_name="ResearchManager",
        )

    assert schema_instance is None
    assert fallback_dict is not None
    assert raw_text == "The recommendation is Hold with value 0"


# ---------------------------------------------------------------------------
# Unit: logging includes agent_name
# ---------------------------------------------------------------------------


def test_logging_includes_agent_name(caplog):
    """Warning log message includes the agent_name for debugging."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = NotImplementedError("nope")

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        freetext_result = MagicMock()
        freetext_result.content = "text"
        mock_invoke.return_value = (freetext_result, None)

        with caplog.at_level(
            logging.WARNING, logger="tradingagents.agents.utils.structured_output"
        ):
            invoke_structured_or_freetext(
                llm=mock_llm,
                schema=_TestSchema,
                messages=[{"role": "user", "content": "test"}],
                fallback_extractor=_mock_fallback_extractor,
                agent_name="MyCustomAgent",
            )

    assert any("MyCustomAgent" in record.message for record in caplog.records)
    assert any("NotImplementedError" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Unit: TimeoutError from fallback path is re-raised
# ---------------------------------------------------------------------------


def test_timeout_error_from_fallback_is_raised():
    """If the fallback invocation times out, TimeoutError is raised."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = NotImplementedError("nope")

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        mock_invoke.return_value = (None, TimeoutError("timed out"))

        with pytest.raises(TimeoutError):
            invoke_structured_or_freetext(
                llm=mock_llm,
                schema=_TestSchema,
                messages=[{"role": "user", "content": "test"}],
                fallback_extractor=_mock_fallback_extractor,
                agent_name="test_agent",
            )


# ---------------------------------------------------------------------------
# Unit: RuntimeError from fallback path is raised with agent_name
# ---------------------------------------------------------------------------


def test_runtime_error_from_fallback_includes_agent_name():
    """If the fallback invocation fails with a non-timeout error, RuntimeError is raised."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = NotImplementedError("nope")

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout") as mock_invoke,
    ):
        mock_invoke.return_value = (None, ValueError("bad response"))

        with pytest.raises(RuntimeError, match="MyAgent.*fallback invocation failed"):
            invoke_structured_or_freetext(
                llm=mock_llm,
                schema=_TestSchema,
                messages=[{"role": "user", "content": "test"}],
                fallback_extractor=_mock_fallback_extractor,
                agent_name="MyAgent",
            )


# ---------------------------------------------------------------------------
# Unit: Unexpected exceptions from structured path are re-raised (not swallowed)
# ---------------------------------------------------------------------------


def test_unexpected_exception_is_reraised():
    """Unexpected errors (e.g., PermissionError) must NOT be silently swallowed."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = PermissionError("auth failure")

    with (
        patch("tradingagents.agents.utils.structured_output.resolve_timeout", return_value=60.0),
        patch("tradingagents.agents.utils.structured_output.invoke_with_timeout"),
    ):
        with pytest.raises(PermissionError, match="auth failure"):
            invoke_structured_or_freetext(
                llm=mock_llm,
                schema=_TestSchema,
                messages=[{"role": "user", "content": "test"}],
                fallback_extractor=_mock_fallback_extractor,
                agent_name="test_agent",
            )
