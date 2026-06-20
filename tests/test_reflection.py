import unittest
from unittest.mock import MagicMock

import pytest

from tradingagents.graph.reflection import Reflector


@pytest.mark.unit
class ReflectorTests(unittest.TestCase):
    def test_initializes_with_llm(self):
        llm = MagicMock()
        r = Reflector(llm)
        self.assertIs(r.quick_thinking_llm, llm)

    def test_log_reflection_prompt_is_string(self):
        llm = MagicMock()
        r = Reflector(llm)
        self.assertIsInstance(r.log_reflection_prompt, str)
        self.assertIn("trading analyst", r.log_reflection_prompt.lower())

    def test_reflect_on_final_decision_invokes_llm(self):
        llm = MagicMock()
        response = MagicMock()
        response.content = "Correct call. Thesis held."
        llm.invoke.return_value = response

        r = Reflector(llm)
        result = r.reflect_on_final_decision(
            final_decision="Buy MSFT",
            raw_return=0.05,
            alpha_return=0.02,
        )
        self.assertEqual(result, "Correct call. Thesis held.")
        llm.invoke.assert_called_once()

    def test_reflect_on_final_decision_passes_benchmark(self):
        llm = MagicMock()
        response = MagicMock()
        response.content = "reflection"
        llm.invoke.return_value = response

        r = Reflector(llm)
        r.reflect_on_final_decision(
            final_decision="Sell",
            raw_return=-0.03,
            alpha_return=0.01,
            benchmark_name="^N225",
        )
        call_args = llm.invoke.call_args[0][0]
        human_msg = [m for m in call_args if m[0] == "human"][0]
        self.assertIn("^N225", human_msg[1])
        self.assertIn("-3.0%", human_msg[1])

    def test_custom_llm_is_used(self):
        llm = MagicMock()
        response = MagicMock()
        response.content = "custom reflection"
        llm.invoke.return_value = response

        r = Reflector(llm)
        result = r.reflect_on_final_decision(
            final_decision="Hold", raw_return=0.0, alpha_return=0.0
        )
        self.assertEqual(result, "custom reflection")


if __name__ == "__main__":
    unittest.main()