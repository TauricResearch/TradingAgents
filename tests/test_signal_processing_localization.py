import unittest

from tradingagents.graph.signal_processing import SignalProcessor


class _UnusedLLM:
    def invoke(self, _messages):
        raise AssertionError("LLM fallback should not be used for normalized ratings")


class SignalProcessingLocalizationTests(unittest.TestCase):
    def test_normalizes_chinese_final_proposal_markers(self):
        processor = SignalProcessor(_UnusedLLM())

        self.assertEqual(processor.process_signal("最终交易建议: **买入**"), "BUY")
        self.assertEqual(processor.process_signal("最终交易建议: **增持**"), "OVERWEIGHT")
        self.assertEqual(processor.process_signal("最终交易建议: **持有**"), "HOLD")
        self.assertEqual(processor.process_signal("最终交易建议: **减持**"), "UNDERWEIGHT")
        self.assertEqual(processor.process_signal("最终交易建议: **卖出**"), "SELL")

    def test_normalizes_english_internal_markers(self):
        processor = SignalProcessor(_UnusedLLM())

        self.assertEqual(
            processor.process_signal("FINAL TRANSACTION PROPOSAL: **BUY**"),
            "BUY",
        )


if __name__ == "__main__":
    unittest.main()
