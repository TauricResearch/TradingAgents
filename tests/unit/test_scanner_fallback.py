"""Unit tests for AV failover — mocked, no network."""

import pytest
from unittest.mock import patch

from tradingagents.dataflows.alpha_vantage_common import AlphaVantageError
from tradingagents.dataflows.alpha_vantage_scanner import (
    get_sector_performance_alpha_vantage,
    get_industry_performance_alpha_vantage,
)


class TestAlphaVantageFailoverRaise:
    """Verify AV scanner functions raise when all data fails."""

    def test_sector_perf_raises_on_total_failure(self):
        with patch(
            "tradingagents.dataflows.alpha_vantage_scanner._fetch_global_quote",
            side_effect=AlphaVantageError("Rate limit exceeded — mocked"),
        ):
            with pytest.raises(AlphaVantageError, match="All .* sector queries failed"):
                get_sector_performance_alpha_vantage()

    def test_industry_perf_raises_on_total_failure(self):
        with patch(
            "tradingagents.dataflows.alpha_vantage_scanner._fetch_global_quote",
            side_effect=AlphaVantageError("Rate limit exceeded — mocked"),
        ):
            with pytest.raises(AlphaVantageError, match="All .* ticker queries failed"):
                get_industry_performance_alpha_vantage("technology")
