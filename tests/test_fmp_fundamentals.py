import unittest
from unittest import mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import fmp_fundamentals as ff

FETCH = "tradingagents.dataflows.vendors.fmp_fundamentals.fetch"


def _rows():
    """Three quarters, newest first as FMP sends them; the newest is filed on 2026-08-26."""
    return [
        {"date": "2026-07-26", "period": "Q2", "fiscalYear": "2027", "filingDate": "2026-08-26",
         "reportedCurrency": "USD", "revenue": 96_221_000_000, "netIncome": 59_688_000_000,
         "eps": 2.47, "weightedAverageShsOutDil": 24_285_000_000},
        {"date": "2026-04-26", "period": "Q1", "fiscalYear": "2027", "filingDate": "2026-05-20",
         "reportedCurrency": "USD", "revenue": 80_000_000_000, "netIncome": 48_000_000_000,
         "eps": 1.98, "weightedAverageShsOutDil": 24_300_000_000},
        {"date": "2026-01-25", "period": "Q4", "fiscalYear": "2026", "filingDate": "2026-02-25",
         "reportedCurrency": "USD", "revenue": 68_100_000_000, "netIncome": 40_000_000_000,
         "eps": 1.65, "weightedAverageShsOutDil": 24_400_000_000},
    ]


@pytest.mark.unit
class FmpStatementTests(unittest.TestCase):
    def test_only_periods_filed_by_the_run_date_oldest_first(self):
        with mock.patch(FETCH, return_value=_rows()):
            out = ff.get_income_statement("NVDA", "quarterly", "2026-07-02")
        header = out.splitlines()[3]
        self.assertIn("2026-01-25 Q4 FY2026 filed 2026-02-25", header)
        self.assertLess(header.index("2026-01-25"), header.index("2026-04-26"))
        self.assertNotIn("2026-07-26", out)  # filed 2026-08-26, after the run date

    def test_money_in_millions_per_share_and_shares_labelled(self):
        with mock.patch(FETCH, return_value=_rows()):
            out = ff.get_income_statement("NVDA", "quarterly", "2026-10-23")
        lines = {line.split(",")[0]: line.split(",")[1:] for line in out.splitlines()[3:]}
        self.assertEqual(lines["Revenue"], ["68100", "80000", "96221"])
        self.assertEqual(lines["EPS (USD per share)"], ["1.65", "1.98", "2.47"])
        self.assertEqual(lines["Diluted shares (millions)"], ["24400", "24300", "24285"])
        self.assertIn("USD in millions", out.splitlines()[0])
        self.assertIn("current values", out.splitlines()[1])

    def test_nothing_filed_yet_is_no_data(self):
        with mock.patch(FETCH, return_value=_rows()), self.assertRaises(NoMarketDataError):
            ff.get_balance_sheet("NVDA", "quarterly", "2025-06-30")

    def test_undated_rows_count_as_not_filed(self):
        rows = [{**_rows()[0], "filingDate": None, "acceptedDate": None}]
        with mock.patch(FETCH, return_value=rows), self.assertRaises(NoMarketDataError):
            ff.get_cashflow("NVDA", "quarterly", "2030-01-01")

    def test_requests_five_periods_of_the_asked_frequency(self):
        with mock.patch(FETCH, return_value=_rows()) as f:
            ff.get_balance_sheet("NVDA", "annual", "2026-10-23")
        endpoint, params = f.call_args.args[:2]
        self.assertEqual(endpoint, "balance-sheet-statement")
        self.assertEqual(params, {"symbol": "NVDA", "period": "annual", "limit": 5})


@pytest.mark.unit
class FmpOverviewTests(unittest.TestCase):
    def test_past_run_withholds_the_live_profile_without_a_request(self):
        with mock.patch(FETCH) as f:
            out = ff.get_fundamentals("NVDA", "2020-01-02")
        f.assert_not_called()
        self.assertIn("withheld", out)

    def test_today_serves_profile_and_ttm_and_survives_a_gated_ttm(self):
        profile = [{"companyName": "NVIDIA Corporation", "sector": "Technology", "currency": "USD",
                    "price": 210.96, "marketCap": 5_130_000_000_000}]
        ratios = [{"grossProfitMarginTTM": 0.7312, "debtToEquityRatioTTM": 0.17}]

        def fake(endpoint, *_):
            if endpoint == "profile":
                return profile
            if endpoint == "key-metrics-ttm":
                raise NoMarketDataError("NVDA", "NVDA", "not on plan")
            return ratios

        with mock.patch(FETCH, side_effect=fake):
            out = ff.get_fundamentals("NVDA")
        self.assertIn("Name: NVIDIA Corporation", out)
        self.assertIn("Market Cap: 5130000M USD", out)
        self.assertIn("Gross Margin (TTM): 73.1%", out)
        self.assertIn("Debt to Equity (TTM): 0.17x", out)
        self.assertNotIn("EV to EBITDA", out)


@pytest.mark.unit
def test_router_offers_fmp_for_every_fundamentals_tool():
    for method in ("get_fundamentals", "get_balance_sheet", "get_cashflow", "get_income_statement"):
        assert "fmp" in router.VENDOR_METHODS[method], method
