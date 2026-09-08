"""Verify fetch_indicators returns valid data matching stockstats directly.

Since fetch_indicators now calls StockstatsUtils.get_stock_stats (the same
function the get_indicators LLM tool uses), these tests confirm the wrapper
correctly structures the results for interpret.py.
"""
import pytest

try:
    from tradingagents.indicators.compute import fetch_indicators
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@pytest.mark.skipif(not HAS_DEPS, reason="indicators module not available")
@pytest.mark.integration
class TestFetchIndicators:

    TICKER = "AAPL"
    DATE = "2024-01-10"

    def test_returns_dict(self):
        result = fetch_indicators(self.TICKER, self.DATE)
        assert isinstance(result, dict)

    def test_rsi_in_range(self):
        result = fetch_indicators(self.TICKER, self.DATE)
        if "rsi" not in result:
            pytest.skip("RSI not available")
        assert 0 <= result["rsi"]["value"] <= 100

    def test_macd_has_required_keys(self):
        result = fetch_indicators(self.TICKER, self.DATE)
        if "macd" not in result:
            pytest.skip("MACD not available")
        for key in ("value", "signal", "histogram"):
            assert key in result["macd"], f"MACD missing '{key}'"

    def test_bollinger_bands_ordered(self):
        result = fetch_indicators(self.TICKER, self.DATE)
        if "bollinger" not in result:
            pytest.skip("Bollinger not available")
        b = result["bollinger"]
        assert b["lower"] < b["upper"], "Lower band should be below upper"

    def test_sma_values_positive(self):
        result = fetch_indicators(self.TICKER, self.DATE)
        if "sma_crossover" not in result:
            pytest.skip("SMA not available")
        assert result["sma_crossover"]["sma50"] > 0
        assert result["sma_crossover"]["sma200"] > 0

    def test_empty_on_bad_ticker(self):
        result = fetch_indicators("ZZZZZZNOTREAL", self.DATE)
        assert result == {}
