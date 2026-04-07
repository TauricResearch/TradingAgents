import unittest

from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.schemas import StructuredDecisionValidationError, parse_structured_decision


class StructuredDecisionTests(unittest.TestCase):
    def test_valid_schema_parses_deterministically(self):
        payload = """
        {
          "rating": "BUY",
          "confidence": 0.78,
          "time_horizon": "medium",
          "entry_logic": "Buy on pullbacks above support.",
          "exit_logic": "Exit on a break below support.",
          "position_sizing": "Half position.",
          "risk_limits": "Risk 1% of capital.",
          "catalysts": ["Earnings beat"],
          "invalidators": ["Guidance cut"]
        }
        """
        decision = parse_structured_decision(payload)
        processor = SignalProcessor(None)

        self.assertEqual(decision.rating.value, "BUY")
        self.assertEqual(processor.process_signal(payload), "BUY")

    def test_invalid_schema_raises_validation_error(self):
        payload = '{"confidence": 0.5, "time_horizon": "short"}'
        with self.assertRaises(StructuredDecisionValidationError):
            parse_structured_decision(payload)


if __name__ == "__main__":
    unittest.main()
