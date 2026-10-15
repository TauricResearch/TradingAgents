"""Additional current Yahoo profile fields must retain units and quote time."""
from unittest import TestCase, mock

from tradingagents.dataflows import date_window
from tradingagents.dataflows.vendors.yahoo import fundamentals


class YahooProfileEnrichmentTests(TestCase):
    def test_profile_reports_extra_fields_with_currency_and_market_timestamp(self):
        info = {
            "longName": "Rheinmetall AG",
            "currency": "EUR",
            "financialCurrency": "EUR",
            "regularMarketPrice": 939.1,
            "regularMarketTime": 1791560346,
            "sharesOutstanding": 46668063,
            "revenueGrowth": 0.688,
            "operatingCashflow": 1312999936,
            "totalCash": 255000000,
            "totalDebt": 2977999872,
            "targetMeanPrice": 1580.3334,
            "recommendationKey": "strong_buy",
            "numberOfAnalystOpinions": 21,
            "fullTimeEmployees": 29636,
        }
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value=info):
            output = fundamentals.get_fundamentals("RHM.DE", "2026-10-10")

        expected = (
            "Quote Currency: EUR",
            "Financial Reporting Currency: EUR",
            "Regular-Market Quote: 939.1 EUR",
            "Quote timestamp (UTC): 2026-10-09T15:39:06+00:00",
            "Shares Outstanding: 46668063",
            "Revenue Growth (YoY): 68.8%",
            "Operating Cash Flow: 1312999936 EUR",
            "Total Cash: 255000000 EUR",
            "Total Debt: 2977999872 EUR",
            "Analyst Target (Mean): 1580.3334 EUR",
            "Analyst Recommendation: strong_buy",
            "Analyst Opinions: 21",
            "Full-Time Employees: 29636",
        )
        for line in expected:
            with self.subTest(line=line):
                self.assertIn(line, output)

    def test_missing_optional_yahoo_fields_are_omitted(self):
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value={"longName": "Rheinmetall AG"}):
            output = fundamentals.get_fundamentals("RHM.DE", "2026-10-10")

        self.assertNotIn("None", output)
        self.assertNotIn("Analyst Recommendation", output)
        self.assertNotIn("Quote timestamp", output)
