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
            "targetLowPrice": 1020.0,
            "targetHighPrice": 2380.0,
            "targetMedianPrice": 1600.0,
            "averageAnalystRating": "1.5 - Strong Buy",
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
            "Analyst Target Spread: 1020.0 EUR to 2380.0 EUR (86% band around the mean)",
            "Analyst Target (Median): 1600.0 EUR",
            "Analyst Rating (Yahoo text): 1.5 - Strong Buy",
        )
        for line in expected:
            with self.subTest(line=line):
                self.assertIn(line, output)

    def test_analyst_spread_hidden_when_bounds_absent(self):
        # Mean-only consensus (no low/high/median/rating) must not emit a
        # spread section or a bare "None"; the mean line alone suffices.
        info = {
            "longName": "Acme Corp",
            "currency": "USD",
            "regularMarketPrice": 10.0,
            "targetMeanPrice": 12.5,
        }
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value=info):
            output = fundamentals.get_fundamentals("ACME", "2026-10-10")

        self.assertIn("Analyst Target (Mean): 12.5 USD", output)
        self.assertNotIn("Analyst Target Spread", output)
        self.assertNotIn("Analyst consensus note", output)
        self.assertNotIn("None", output)

    def test_analyst_spread_bandless_when_mean_zero_or_missing(self):
        # A zero mean must not divide by zero; the band label is dropped but
        # the raw low/high stay visible.
        info = {
            "longName": "Acme Corp",
            "currency": "USD",
            "regularMarketPrice": 10.0,
            "targetMeanPrice": 0.0,
            "targetLowPrice": 9.0,
            "targetHighPrice": 11.0,
        }
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value=info):
            output = fundamentals.get_fundamentals("ACME", "2026-10-10")

        self.assertIn("Analyst Target Spread: 9.0 USD to 11.0 USD", output)
        self.assertNotIn("% band", output)

    def test_etf_profile_present_for_fund_and_absent_for_equity(self):
        # Generic ETF detection: a fund with NAV/TER/YTD gets a labelled ETF
        # block; a plain equity (those fields null) must not emit it or "None".
        etf_info = {
            "longName": "iShares Core MSCI World UCITS ETF USD (Acc)",
            "currency": "USD",
            "regularMarketPrice": 146.58,
            "navPrice": 146.582,
            "netExpenseRatio": 0.2,
            "ytdReturn": 11.7511,
            "totalAssets": 123456789012,
            "fundInceptionDate": 1690502400,
            "yield": 0.0,
            "legalType": "Exchange Traded Fund",
        }
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value=etf_info):
            output = fundamentals.get_fundamentals("IWDA.L", "2026-10-10")

        self.assertIn("ETF NAV: 146.582 USD", output)
        self.assertIn("Expense ratio (TER): 0.20%", output)
        self.assertIn("YTD return: +11.8%", output)
        self.assertIn("Total assets (approx): 123456789012", output)
        self.assertIn("Inception: 2023-07-28", output)
        self.assertIn("Legal type: Exchange Traded Fund", output)
        self.assertIn("ETF profile note", output)
        # A fund has no analyst consensus; that block stays absent.
        self.assertNotIn("Analyst Target (Mean)", output)

        equity_info = {
            "longName": "Acme Corp",
            "currency": "USD",
            "regularMarketPrice": 10.0,
            "fullTimeEmployees": 1000,
        }
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value=equity_info):
            output = fundamentals.get_fundamentals("ACME", "2026-10-10")

        self.assertNotIn("ETF NAV", output)
        self.assertNotIn("ETF profile note", output)
        self.assertNotIn("None", output)

    def test_missing_optional_yahoo_fields_are_omitted(self):
        with mock.patch.object(date_window, "get_current_date", return_value="2026-10-10"), \
             mock.patch.object(fundamentals, "yf_retry", return_value={"longName": "Rheinmetall AG"}):
            output = fundamentals.get_fundamentals("RHM.DE", "2026-10-10")

        self.assertNotIn("None", output)
        self.assertNotIn("Analyst Recommendation", output)
        self.assertNotIn("Quote timestamp", output)
