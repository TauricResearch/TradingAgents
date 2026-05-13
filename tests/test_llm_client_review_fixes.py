"""Regression tests for fixes applied per gemini-code-assist review on PR #746.

Covers:
- claude_code rejects non-dict payloads with a clear error.
- gemini_cli injects ``json_schema`` into the inlined system prompt when
  ``with_structured_output`` is used.
- ``_try_parse_json`` recovers a top-level JSON array from prose-wrapped text.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, Optional

import pytest

from tradingagents.llm_clients.claude_code_client import ChatClaudeCode
from tradingagents.llm_clients.gemini_cli_client import ChatGeminiCli, _try_parse_json


@pytest.mark.unit
class TestClaudeCodeNonDictPayload(unittest.TestCase):
    def test_top_level_list_payload_raises(self):
        chat = ChatClaudeCode(model="sonnet")
        with self.assertRaises(RuntimeError) as ctx:
            chat._parse_response('[{"result": "hi"}]', json_schema=None)
        self.assertIn("not an object", str(ctx.exception))
        self.assertIn("list", str(ctx.exception))

    def test_top_level_string_payload_raises(self):
        chat = ChatClaudeCode(model="sonnet")
        with self.assertRaises(RuntimeError) as ctx:
            chat._parse_response('"just a string"', json_schema=None)
        self.assertIn("not an object", str(ctx.exception))

    def test_dict_payload_still_parses(self):
        chat = ChatClaudeCode(model="sonnet")
        text, structured = chat._parse_response(
            '{"result": "hello", "is_error": false}', json_schema=None
        )
        self.assertEqual(text, "hello")
        self.assertIsNone(structured)


@pytest.mark.unit
class TestGeminiCliJsonSchemaInjection(unittest.TestCase):
    def test_schema_appended_when_bound(self):
        chat = ChatGeminiCli(model="gemini-2.5-flash")
        chat.json_schema = {
            "type": "object",
            "properties": {"verdict": {"type": "string"}},
        }
        out = chat._subprocess_input("Be concise.", "Decide on AAPL.")
        self.assertIn("Be concise.", out)
        self.assertIn("Return your response as a JSON object matching this schema", out)
        self.assertIn('"verdict"', out)
        self.assertIn("<<USER>>", out)
        self.assertIn("Decide on AAPL.", out)

    def test_schema_with_empty_system_prompt(self):
        chat = ChatGeminiCli(model="gemini-2.5-flash")
        chat.json_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        out = chat._subprocess_input("", "What is 1+1?")
        self.assertIn("Return your response as a JSON object", out)
        self.assertIn("<<USER>>", out)

    def test_no_schema_no_injection(self):
        chat = ChatGeminiCli(model="gemini-2.5-flash")
        out = chat._subprocess_input("System.", "User.")
        self.assertNotIn("matching this schema", out)
        self.assertIn("System.", out)
        self.assertIn("User.", out)


@pytest.mark.unit
class TestTryParseJsonArraySupport(unittest.TestCase):
    def test_prose_wrapped_top_level_array(self):
        text = 'Here is the data you asked for: [{"x": 1}, {"y": 2}] hope it helps.'
        out = _try_parse_json(text)
        self.assertEqual(out, [{"x": 1}, {"y": 2}])

    def test_prose_wrapped_top_level_object_still_works(self):
        text = 'Sure! {"verdict": "buy", "score": 9} done.'
        out = _try_parse_json(text)
        self.assertEqual(out, {"verdict": "buy", "score": 9})

    def test_earlier_open_char_wins(self):
        # Object opens before array → object branch should be used
        text = 'mixed {"a": 1} then [1, 2, 3] more'
        out = _try_parse_json(text)
        self.assertEqual(out, {"a": 1})

    def test_nested_array_in_object_via_fence(self):
        text = '```json\n{"items": [1, 2, 3]}\n```'
        out = _try_parse_json(text)
        self.assertEqual(out, {"items": [1, 2, 3]})

    def test_no_json_returns_none(self):
        self.assertIsNone(_try_parse_json("just prose, no braces here"))


if __name__ == "__main__":
    unittest.main()
