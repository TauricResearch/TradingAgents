import unittest

import pytest

from tradingagents.graph.signal_processing import SignalProcessor


@pytest.mark.unit
class SignalProcessorTests(unittest.TestCase):
    def test_parses_buy_rating(self):
        sp = SignalProcessor()
        result = sp.process_signal("**Rating**: Buy\nSome detail here")
        self.assertEqual(result, "Buy")

    def test_parses_sell_rating(self):
        sp = SignalProcessor()
        result = sp.process_signal("**Rating**: Sell\nExit position")
        self.assertEqual(result, "Sell")

    def test_parses_hold_rating(self):
        sp = SignalProcessor()
        result = sp.process_signal("**Rating**: Hold\nMaintain position")
        self.assertEqual(result, "Hold")

    def test_parses_overweight_rating(self):
        sp = SignalProcessor()
        result = sp.process_signal("**Rating**: Overweight\nIncrease position")
        self.assertEqual(result, "Overweight")

    def test_parses_underweight_rating(self):
        sp = SignalProcessor()
        result = sp.process_signal("**Rating**: Underweight\nReduce position")
        self.assertEqual(result, "Underweight")

    def test_accepts_llm_for_backwards_compat(self):
        sp = SignalProcessor(quick_thinking_llm="not_used")
        result = sp.process_signal("**Rating**: Buy\nGood setup")
        self.assertEqual(result, "Buy")


if __name__ == "__main__":
    unittest.main()