import unittest

from tradingagents.dataflows.utils import normalize_date_range, normalize_iso_date


class DateNormalizationTests(unittest.TestCase):
    def test_normalize_iso_date_keeps_valid_dates(self):
        self.assertEqual(normalize_iso_date("2024-02-29"), "2024-02-29")

    def test_normalize_iso_date_clamps_invalid_month_end(self):
        self.assertEqual(normalize_iso_date("2026-02-29"), "2026-02-28")
        self.assertEqual(normalize_iso_date("2026-04-31"), "2026-04-30")

    def test_normalize_date_range_orders_dates_after_normalization(self):
        self.assertEqual(
            normalize_date_range("2026-03-29", "2026-02-29"),
            ("2026-02-28", "2026-03-29"),
        )

    def test_normalize_iso_date_rejects_bad_format(self):
        with self.assertRaises(ValueError):
            normalize_iso_date("2026/02/29")


if __name__ == "__main__":
    unittest.main()
