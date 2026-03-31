import json
import unittest
from unittest.mock import patch

from tradingagents.dataflows import alpha_vantage_fundamentals as fundamentals


class AlphaVantageFundamentalsTests(unittest.TestCase):
    def test_curr_date_filters_future_reports_from_json_response(self):
        payload = json.dumps(
            {
                "annualReports": [
                    {"fiscalDateEnding": "2023-12-31", "totalAssets": "100"},
                    {"fiscalDateEnding": "2024-12-31", "totalAssets": "200"},
                ],
                "quarterlyReports": [
                    {"fiscalDateEnding": "2024-03-31", "totalAssets": "110"},
                    {"fiscalDateEnding": "2024-06-30", "totalAssets": "120"},
                ],
            }
        )

        funcs = [
            fundamentals.get_balance_sheet,
            fundamentals.get_cashflow,
            fundamentals.get_income_statement,
        ]

        for func in funcs:
            with self.subTest(func=func.__name__):
                with patch.object(fundamentals, "_make_api_request", return_value=payload):
                    result = json.loads(func("AAPL", curr_date="2024-03-31"))

                self.assertEqual(
                    result["annualReports"],
                    [{"fiscalDateEnding": "2023-12-31", "totalAssets": "100"}],
                )
                self.assertEqual(
                    result["quarterlyReports"],
                    [{"fiscalDateEnding": "2024-03-31", "totalAssets": "110"}],
                )


if __name__ == "__main__":
    unittest.main()
