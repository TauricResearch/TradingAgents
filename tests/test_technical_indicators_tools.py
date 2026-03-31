import unittest
from unittest.mock import call, patch

from tradingagents.agents.utils import technical_indicators_tools as tools


class TechnicalIndicatorsToolTests(unittest.TestCase):
    def test_get_indicators_splits_and_normalizes_indicator_names(self):
        with patch.object(
            tools,
            "route_to_vendor",
            side_effect=["rsi output", "macd output"],
        ) as mock_route:
            result = tools.get_indicators.func(
                "AAPL",
                " RSI, MACD ",
                "2026-03-31",
                30,
            )

        self.assertEqual(result, "rsi output\n\nmacd output")
        self.assertEqual(
            mock_route.call_args_list,
            [
                call("get_indicators", "AAPL", "rsi", "2026-03-31", 30),
                call("get_indicators", "AAPL", "macd", "2026-03-31", 30),
            ],
        )


if __name__ == "__main__":
    unittest.main()
