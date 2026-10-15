"""Data-quality regressions identified by the RHM end-to-end audit."""
from unittest.mock import Mock, patch

import pandas as pd

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.dataflows.vendors.yahoo import fundamentals


def test_empty_insider_feed_names_the_source_and_unverified_coverage():
    ticker = Mock(insider_transactions=pd.DataFrame())
    with patch.object(fundamentals.yf, "Ticker", return_value=ticker), \
         patch.object(fundamentals, "vendor_reachable", return_value=True):
        result = fundamentals.get_insider_transactions("RHM.DE", get_current_date())
    assert "Yahoo Finance" in result
    assert "coverage is unverified" in result
    assert "does not establish that no transactions occurred" in result
