import importlib
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd


class YFinanceBulkIndicatorTests(unittest.TestCase):
    def test_bulk_indicator_maps_nan_to_na(self):
        fake_stockstats = types.ModuleType("stockstats")
        fake_stockstats.wrap = lambda df: df

        with patch.dict(sys.modules, {"stockstats": fake_stockstats}):
            sys.modules.pop("tradingagents.dataflows.stockstats_utils", None)
            sys.modules.pop("tradingagents.dataflows.y_finance", None)

            try:
                y_finance = importlib.import_module("tradingagents.dataflows.y_finance")
                sample_df = pd.DataFrame(
                    {
                        "Date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
                        "rsi": [float("nan"), 55.5],
                    }
                )

                with patch.object(y_finance, "load_ohlcv", return_value=sample_df):
                    result = y_finance._get_stock_stats_bulk("AAPL", "rsi", "2024-01-03")
            finally:
                sys.modules.pop("tradingagents.dataflows.stockstats_utils", None)
                sys.modules.pop("tradingagents.dataflows.y_finance", None)

        self.assertEqual(result["2024-01-02"], "N/A")
        self.assertEqual(result["2024-01-03"], "55.5")


if __name__ == "__main__":
    unittest.main()
