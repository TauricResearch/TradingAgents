"""Tests for the shared structured invocation cache helper."""

import unittest
from unittest.mock import MagicMock

from tradingagents.agents.utils.structured import (
    invoke_structured_or_freetext,
)


class StructuredInvocationCacheTests(unittest.TestCase):
    def test_reuses_cached_structured_result(self):
        cache = {}
        structured = MagicMock()
        structured.invoke.return_value = {"value": "structured"}
        plain = MagicMock()
        render = MagicMock(return_value="rendered-structured")
        prompt = [{"role": "user", "content": "hello"}]

        first = invoke_structured_or_freetext(
            structured,
            plain,
            prompt,
            render,
            "Trader",
            cache=cache,
        )
        second = invoke_structured_or_freetext(
            structured,
            plain,
            prompt,
            render,
            "Trader",
            cache=cache,
        )

        self.assertEqual(first, "rendered-structured")
        self.assertEqual(second, "rendered-structured")
        self.assertEqual(structured.invoke.call_count, 1)
        self.assertEqual(plain.invoke.call_count, 0)
        self.assertEqual(render.call_count, 1)

    def test_reuses_cached_freetext_fallback(self):
        cache = {}
        structured = MagicMock()
        structured.invoke.side_effect = RuntimeError("structured failed")
        plain = MagicMock()
        plain.invoke.return_value = MagicMock(content="plain fallback")
        render = MagicMock()
        prompt = [{"role": "user", "content": "hello"}]

        first = invoke_structured_or_freetext(
            structured,
            plain,
            prompt,
            render,
            "Trader",
            cache=cache,
        )
        second = invoke_structured_or_freetext(
            structured,
            plain,
            prompt,
            render,
            "Trader",
            cache=cache,
        )

        self.assertEqual(first, "plain fallback")
        self.assertEqual(second, "plain fallback")
        self.assertEqual(structured.invoke.call_count, 1)
        self.assertEqual(plain.invoke.call_count, 1)
        self.assertEqual(render.call_count, 0)


if __name__ == "__main__":
    unittest.main()
