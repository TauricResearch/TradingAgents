"""Unit tests for tradingagents/agents/utils/structured.py."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext

pytestmark = pytest.mark.unit


class StructuredBindEdgeTests(unittest.TestCase):
    """Lines 50-56: AttributeError handling in bind_structured."""

    def test_bind_structured_attribute_error_fallback(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = AttributeError("no tool_choice")

        class TestSchema(BaseModel):
            field: str

        result = bind_structured(llm, TestSchema, "test_agent")
        self.assertIsNone(result)
        llm.with_structured_output.assert_called_once_with(TestSchema)

    def test_bind_structured_attribute_error_logged_at_warning(self):
        llm = MagicMock()
        llm.with_structured_output.side_effect = AttributeError("no tool_choice")

        class TestSchema(BaseModel):
            field: str

        with self.assertLogs(level="WARNING") as logs:
            result = bind_structured(llm, TestSchema, "test_agent")
        self.assertIsNone(result)
        self.assertTrue(any("test_agent" in m and "does not support" in m for m in logs.output))

    def test_invoke_structured_or_freetext_structured_fails_fallback(self):
        class TestSchema(BaseModel):
            field: str

        structured_llm = MagicMock()
        structured_llm.invoke.side_effect = ValueError("structured call failed")
        plain_llm = MagicMock()
        plain_response = MagicMock()
        plain_response.content = "free text fallback"
        plain_llm.invoke.return_value = plain_response

        result = invoke_structured_or_freetext(
            structured_llm, plain_llm,
            "test prompt",
            lambda x: x.field,
            "test_agent",
        )
        self.assertEqual(result, "free text fallback")

    def test_invoke_structured_or_freetext_structured_success(self):
        class TestSchema(BaseModel):
            field: str

        structured_llm = MagicMock()
        structured_llm.invoke.return_value = TestSchema(field="structured result")
        plain_llm = MagicMock()

        result = invoke_structured_or_freetext(
            structured_llm, plain_llm,
            "test prompt",
            lambda x: x.field,
            "test_agent",
        )
        self.assertEqual(result, "structured result")

    def test_invoke_structured_or_freetext_no_structured(self):
        plain_llm = MagicMock()
        plain_response = MagicMock()
        plain_response.content = "free text"
        plain_llm.invoke.return_value = plain_response

        result = invoke_structured_or_freetext(
            None, plain_llm,
            "test prompt",
            lambda x: "should not matter",
            "test_agent",
        )
        self.assertEqual(result, "free text")


class TestStructuredFallback(unittest.TestCase):
    """Cover remaining lines in invoke_structured_or_freetext."""

    def test_structured_llm_is_none_uses_plain(self):
        plain = MagicMock()
        plain.invoke.return_value = MagicMock(content="free-text response")
        result = invoke_structured_or_freetext(
            structured_llm=None,
            plain_llm=plain,
            prompt="test",
            render=lambda x: str(x),
            agent_name="test_agent",
        )
        self.assertEqual(result, "free-text response")
        plain.invoke.assert_called_once_with("test")
