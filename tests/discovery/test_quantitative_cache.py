import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


class TestQuantitativeCache:
    def test_cache_set_and_get(self):
        from tradingagents.agents.discovery.quantitative_cache import (
            clear_run_cache,
            get_cached_price_data,
            set_cached_price_data,
        )

        clear_run_cache()

        df = pd.DataFrame(
            {"Close": [100.0, 101.0, 102.0], "Volume": [1000, 1100, 1200]}
        )

        set_cached_price_data("AAPL", df)

        cached = get_cached_price_data("AAPL")

        assert cached is not None
        assert len(cached) == 3
        assert cached["Close"].tolist() == [100.0, 101.0, 102.0]

    def test_cache_miss_returns_none(self):
        from tradingagents.agents.discovery.quantitative_cache import (
            clear_run_cache,
            get_cached_price_data,
        )

        clear_run_cache()

        result = get_cached_price_data("NONEXISTENT")

        assert result is None

    def test_cache_clear(self):
        from tradingagents.agents.discovery.quantitative_cache import (
            clear_run_cache,
            get_cached_price_data,
            set_cached_price_data,
        )

        clear_run_cache()

        df = pd.DataFrame({"Close": [100.0]})
        set_cached_price_data("AAPL", df)

        assert get_cached_price_data("AAPL") is not None

        clear_run_cache()

        assert get_cached_price_data("AAPL") is None

    def test_cache_max_size_enforcement(self):
        from tradingagents.agents.discovery.quantitative_cache import (
            MAX_CACHE_SIZE,
            clear_run_cache,
            get_cached_price_data,
            set_cached_price_data,
        )

        clear_run_cache()

        for i in range(MAX_CACHE_SIZE + 10):
            ticker = f"TICKER{i}"
            df = pd.DataFrame({"Close": [float(i)]})
            set_cached_price_data(ticker, df)

        cached_count = 0
        for i in range(MAX_CACHE_SIZE + 10):
            ticker = f"TICKER{i}"
            if get_cached_price_data(ticker) is not None:
                cached_count += 1

        assert cached_count <= MAX_CACHE_SIZE


class TestCacheTTLConstants:
    def test_default_ttl_hours_contains_quant_entries(self):
        from tradingagents.database.services.market_data import DEFAULT_TTL_HOURS

        assert "quant_indicators" in DEFAULT_TTL_HOURS
        assert "volume_analysis" in DEFAULT_TTL_HOURS
        assert "relative_strength" in DEFAULT_TTL_HOURS
        assert "support_resistance" in DEFAULT_TTL_HOURS
        assert "risk_reward" in DEFAULT_TTL_HOURS

    def test_quant_ttl_values(self):
        from tradingagents.database.services.market_data import DEFAULT_TTL_HOURS

        assert DEFAULT_TTL_HOURS["quant_indicators"] == 1
        assert DEFAULT_TTL_HOURS["volume_analysis"] == 1
        assert DEFAULT_TTL_HOURS["relative_strength"] == 4
        assert DEFAULT_TTL_HOURS["support_resistance"] == 1
        assert DEFAULT_TTL_HOURS["risk_reward"] == 1
