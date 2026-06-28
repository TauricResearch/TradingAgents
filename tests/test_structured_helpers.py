"""Tests for the structured output helpers (bind_structured / invoke_structured_or_freetext)."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext


class DummySchema(BaseModel):
    action: str
    reasoning: str


def _render_dummy(obj: DummySchema) -> str:
    return f"Action: {obj.action}, Reasoning: {obj.reasoning}"


# ---------------------------------------------------------------------------
# bind_structured
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBindStructured:
    def test_returns_structured_llm_when_supported(self):
        llm = MagicMock()
        structured = MagicMock()
        llm.with_structured_output.return_value = structured
        result = bind_structured(llm, DummySchema, "TestAgent")
        assert result is structured
        llm.with_structured_output.assert_called_once_with(DummySchema)

    def test_returns_none_when_not_implemented(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = NotImplementedError("no support")
        result = bind_structured(llm, DummySchema, "TestAgent")
        assert result is None

    def test_returns_none_when_attribute_error(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = AttributeError("missing method")
        result = bind_structured(llm, DummySchema, "TestAgent")
        assert result is None

    def test_propagates_unexpected_exceptions(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = RuntimeError("unexpected")
        with pytest.raises(RuntimeError, match="unexpected"):
            bind_structured(llm, DummySchema, "TestAgent")


# ---------------------------------------------------------------------------
# invoke_structured_or_freetext
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInvokeStructuredOrFreetext:
    def test_structured_path_returns_rendered_output(self):
        obj = DummySchema(action="Buy", reasoning="Strong fundamentals")
        structured_llm = MagicMock()
        structured_llm.invoke.return_value = obj
        plain_llm = MagicMock()

        result = invoke_structured_or_freetext(
            structured_llm, plain_llm, "test prompt", _render_dummy, "TestAgent"
        )
        assert result == "Action: Buy, Reasoning: Strong fundamentals"
        plain_llm.invoke.assert_not_called()

    def test_falls_back_to_freetext_when_structured_fails(self):
        structured_llm = MagicMock()
        structured_llm.invoke.side_effect = ValueError("bad JSON")
        plain_llm = MagicMock()
        plain_llm.invoke.return_value = MagicMock(content="Free text fallback.")

        result = invoke_structured_or_freetext(
            structured_llm, plain_llm, "test prompt", _render_dummy, "TestAgent"
        )
        assert result == "Free text fallback."

    def test_uses_freetext_when_structured_llm_is_none(self):
        plain_llm = MagicMock()
        plain_llm.invoke.return_value = MagicMock(content="Plain response.")

        result = invoke_structured_or_freetext(
            None, plain_llm, "test prompt", _render_dummy, "TestAgent"
        )
        assert result == "Plain response."

    def test_same_prompt_forwarded_to_both_paths(self):
        structured_llm = MagicMock()
        structured_llm.invoke.side_effect = RuntimeError("fail")
        plain_llm = MagicMock()
        plain_llm.invoke.return_value = MagicMock(content="ok")

        prompt = "Analyze NVDA"
        invoke_structured_or_freetext(
            structured_llm, plain_llm, prompt, _render_dummy, "TestAgent"
        )
        structured_llm.invoke.assert_called_once_with(prompt)
        plain_llm.invoke.assert_called_once_with(prompt)

    def test_render_function_receives_structured_result(self):
        obj = DummySchema(action="Sell", reasoning="Weak outlook")
        structured_llm = MagicMock()
        structured_llm.invoke.return_value = obj
        plain_llm = MagicMock()

        calls = []
        def tracking_render(x):
            calls.append(x)
            return "rendered"

        result = invoke_structured_or_freetext(
            structured_llm, plain_llm, "prompt", tracking_render, "TestAgent"
        )
        assert result == "rendered"
        assert calls == [obj]
