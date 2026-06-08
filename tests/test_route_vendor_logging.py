"""route_to_vendor must log when it swallows an unexpected vendor error, so a
broken primary vendor isn't silently masked by a later succeeding fallback
(see #989)."""

import unittest
from unittest import mock

import pytest

from tradingagents.dataflows import interface


@pytest.mark.unit
class TestRouteToVendorLogging(unittest.TestCase):
    def test_primary_failure_is_logged_but_fallback_result_returned(self):
        def primary_boom(*a, **k):
            raise RuntimeError("primary vendor exploded")

        def fallback_ok(*a, **k):
            return "FALLBACK_DATA"

        patched = {"boomvendor": primary_boom, "okvendor": fallback_ok}
        with mock.patch.object(interface, "get_vendor", return_value="boomvendor,okvendor"), \
                mock.patch.dict(
                    interface.VENDOR_METHODS, {"get_stock_data": patched}, clear=False
                ):
            with self.assertLogs(interface.logger, level="WARNING") as cm:
                result = interface.route_to_vendor(
                    "get_stock_data", "AAPL", "2026-01-01", "2026-01-10"
                )

        # The fallback's data is still returned (no behavior change)...
        self.assertEqual(result, "FALLBACK_DATA")
        # ...but the masked primary failure is now visible in the logs.
        joined = "\n".join(cm.output)
        self.assertIn("boomvendor", joined)
        self.assertIn("get_stock_data", joined)
        self.assertIn("configured primary", joined)


if __name__ == "__main__":
    unittest.main()
