import unittest

from tradingagents.agents.utils.structured import invoke_structured_or_freetext


class _StructuredReturnsNone:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return None


class _PlainLLM:
    def __init__(self):
        self.calls = 0

    def invoke(self, prompt):
        self.calls += 1
        return type("Response", (), {"content": "fallback text"})()


class StructuredFallbackTests(unittest.TestCase):
    def test_none_structured_result_falls_back_without_rendering_none(self):
        structured = _StructuredReturnsNone()
        plain = _PlainLLM()
        render_calls = []

        def render(value):
            render_calls.append(value)
            raise AssertionError("render should not be called for a None structured result")

        result = invoke_structured_or_freetext(
            structured,
            plain,
            "prompt",
            render,
            "Test Agent",
        )

        self.assertEqual(result, "fallback text")
        self.assertEqual(structured.calls, 1)
        self.assertEqual(plain.calls, 1)
        self.assertEqual(render_calls, [])


if __name__ == "__main__":
    unittest.main()
