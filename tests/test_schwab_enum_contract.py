"""Contract test: the real schwab-py PriceHistory enums must keep the members
and wire-values our vendor sends. ``get_schwab_stock`` requests an explicit
5-year daily window via ``PeriodType.YEAR`` / ``Period.FIVE_YEARS`` /
``FrequencyType.DAILY`` / ``Frequency.DAILY``. If a schwab-py upgrade renamed a
member or changed its wire value, the request would silently send the wrong
frequency and the vendor would return the wrong candles. This test pins those
enums against the *installed* schwab-py so drift fails loudly in CI.

Skipped automatically when schwab-py (the optional ``[schwab]`` extra) is not
installed, so it never breaks the default dev/test environment.
"""
import unittest

import pytest

schwab = pytest.importorskip("schwab", reason="schwab-py extra not installed")


@pytest.mark.unit
class SchwabEnumContractTests(unittest.TestCase):
    def setUp(self):
        # The enums live on the client's PriceHistory namespace; import the
        # module form so we assert the same objects the vendor references.
        from schwab.client.base import BaseClient

        self.ph = BaseClient.PriceHistory

    def test_period_type_year_wire_value(self):
        self.assertEqual(self.ph.PeriodType.YEAR.value, "year")

    def test_period_five_years_wire_value(self):
        self.assertEqual(self.ph.Period.FIVE_YEARS.value, 5)

    def test_frequency_type_daily_wire_value(self):
        self.assertEqual(self.ph.FrequencyType.DAILY.value, "daily")

    def test_frequency_daily_wire_value(self):
        # DAILY aliases onto 1 candle-per-day; our vendor relies on this.
        self.assertEqual(self.ph.Frequency.DAILY.value, 1)

    def test_members_still_exist(self):
        # Guard against renames even if values are unchanged.
        self.assertTrue(hasattr(self.ph.PeriodType, "YEAR"))
        self.assertTrue(hasattr(self.ph.Period, "FIVE_YEARS"))
        self.assertTrue(hasattr(self.ph.FrequencyType, "DAILY"))
        self.assertTrue(hasattr(self.ph.Frequency, "DAILY"))


if __name__ == "__main__":
    unittest.main()
