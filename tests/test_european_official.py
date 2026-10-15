import unittest
from unittest.mock import Mock, patch

from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.dataflows.vendors import european_official


class EurostatParsingTests(unittest.TestCase):
    def test_quarter_period_uses_quarter_end_date(self):
        self.assertEqual(european_official._period_end("2026-Q2").isoformat(), "2026-06-30")

    def test_extracts_sparse_json_stat_observations_by_period(self):
        payload = {
            "class": "dataset",
            "label": "German HICP",
            "updated": "2026-10-02T11:00:00+0200",
            "id": ["freq", "unit", "geo", "time"],
            "size": [1, 1, 1, 3],
            "dimension": {
                "freq": {"category": {"index": {"M": 0}}},
                "unit": {"category": {"index": {"RCH_A": 0}}},
                "geo": {"category": {"index": {"DE": 0}}},
                "time": {"category": {"index": {"2026-07": 0, "2026-08": 1, "2026-09": 2}}},
            },
            "value": {"0": 1.8, "2": 2.0},
        }
        self.assertEqual(
            european_official.parse_eurostat_observations(payload),
            [("2026-07", 1.8), ("2026-09", 2.0)],
        )


class EuropeanMacroTests(unittest.TestCase):
    @patch.object(european_official, "get_scrubbed")
    def test_germany_hicp_is_filtered_at_analysis_date_and_identifies_source(self, get):
        payload = {
            "class": "dataset",
            "label": "German HICP",
            "updated": "2026-10-02T11:00:00+0200",
            "id": ["freq", "unit", "geo", "time"],
            "size": [1, 1, 1, 3],
            "dimension": {
                "freq": {"category": {"index": {"M": 0}}},
                "unit": {"category": {"index": {"RCH_A": 0}}},
                "geo": {"category": {"index": {"DE": 0}}},
                "time": {"category": {"index": {"2026-07": 0, "2026-08": 1, "2026-09": 2}}},
            },
            "value": {"0": 1.8, "1": 1.9, "2": 2.0},
        }
        response = Mock()
        response.json.return_value = payload
        get.return_value = response

        result = european_official.get_macro_data("germany_hicp", "2026-08-31", 90)

        self.assertIn("Eurostat", result)
        self.assertIn("API endpoint: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr", result)
        self.assertIn("Retrieved at (UTC):", result)
        self.assertIn("2026-08", result)
        self.assertNotIn("2026-09", result)
        self.assertEqual(get.call_args.kwargs["params"]["sinceTimePeriod"], "2026-06")
        self.assertEqual(get.call_args.kwargs["params"]["untilTimePeriod"], "2026-08")

    @patch.object(european_official, "get_scrubbed")
    def test_germany_unemployment_uses_official_monthly_series(self, get):
        payload = {
            "class": "dataset",
            "label": "German unemployment rate",
            "id": ["freq", "s_adj", "age", "unit", "sex", "geo", "time"],
            "size": [1, 1, 1, 1, 1, 1, 2],
            "dimension": {
                "freq": {"category": {"index": {"M": 0}}},
                "s_adj": {"category": {"index": {"SA": 0}}},
                "age": {"category": {"index": {"TOTAL": 0}}},
                "unit": {"category": {"index": {"PC_ACT": 0}}},
                "sex": {"category": {"index": {"T": 0}}},
                "geo": {"category": {"index": {"DE": 0}}},
                "time": {"category": {"index": {"2026-07": 0, "2026-08": 1}}},
            },
            "value": {"0": 3.9, "1": 4.0},
        }
        response = Mock()
        response.json.return_value = payload
        get.return_value = response

        result = european_official.get_macro_data("germany_unemployment", "2026-08-31", 90)

        self.assertIn("Eurostat", result)
        self.assertIn("2026-08", result)
        self.assertIn("4", result)
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["s_adj"], "SA")
        self.assertEqual(params["age"], "TOTAL")

    @patch.object(european_official, "get_scrubbed")
    def test_ecb_deposit_rate_reports_only_observations_not_after_as_of_date(self, get):
        response = Mock()
        response.text = (
            "TIME_PERIOD,OBS_VALUE,TITLE\n"
            "2026-06-17,2.25,Deposit facility\n"
            "2026-09-16,2.50,Deposit facility\n"
        )
        get.return_value = response

        result = european_official.get_macro_data("ecb_deposit_rate", "2026-08-31", 365)

        self.assertIn("European Central Bank", result)
        self.assertIn("2026-06-17", result)
        self.assertNotIn("2026-09-16", result)
        self.assertIn("2.25", result)

    @patch.object(european_official, "get_scrubbed")
    def test_germany_10y_uses_monthly_convergence_series_with_cutoff(self, get):
        get.return_value.json.return_value = {
            "class": "dataset", "id": ["freq", "int_rt", "geo", "time"],
            "size": [1, 1, 1, 3],
            "dimension": {
                "freq": {"category": {"index": {"M": 0}}},
                "int_rt": {"category": {"index": {"MCBY": 0}}},
                "geo": {"category": {"index": {"DE": 0}}},
                "time": {"category": {"index": {"2026-07": 0, "2026-08": 1, "2026-09": 2}}},
            },
            "value": {"0": 3.07, "1": 3.185, "2": 3.5},
        }
        from tradingagents.dataflows.router import route_to_vendor
        result = route_to_vendor("get_macro_indicators", "germany_10y", "2026-08-31", 365)
        self.assertIn("3.185", result)
        self.assertIn("monthly", result)
        self.assertIn("not a daily", result)
        self.assertNotIn("2026-09", result)
        self.assertIn("irt_lt_mcby_m", get.call_args.args[0])
        self.assertEqual(get.call_args.kwargs["params"]["int_rt"], "MCBY")
        self.assertEqual(get.call_args.kwargs["params"]["geo"], "DE")

    def test_unknown_indicator_is_reported_as_not_covered_for_fallback(self):
        with self.assertRaises(NoMarketDataError):
            european_official.get_macro_data("unsupported_macro", "2026-10-09", 365)


if __name__ == "__main__":
    unittest.main()
