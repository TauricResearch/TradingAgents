from unittest.mock import patch

from tradingagents.dataflows.trending.sector_classifier import (
    TICKER_TO_SECTOR,
    VALID_SECTORS,
    _sector_cache,
    classify_sector,
)


class TestStaticSectorMapping:
    def test_static_sector_mapping_for_known_technology_tickers(self):
        assert classify_sector("AAPL") == "technology"
        assert classify_sector("MSFT") == "technology"
        assert classify_sector("GOOGL") == "technology"
        assert classify_sector("NVDA") == "technology"

    def test_static_sector_mapping_for_known_healthcare_tickers(self):
        assert classify_sector("JNJ") == "healthcare"
        assert classify_sector("PFE") == "healthcare"
        assert classify_sector("UNH") == "healthcare"

    def test_static_sector_mapping_for_known_finance_tickers(self):
        assert classify_sector("JPM") == "finance"
        assert classify_sector("BAC") == "finance"
        assert classify_sector("GS") == "finance"

    def test_static_sector_mapping_for_known_energy_tickers(self):
        assert classify_sector("XOM") == "energy"
        assert classify_sector("CVX") == "energy"
        assert classify_sector("COP") == "energy"

    def test_static_sector_mapping_case_insensitive(self):
        assert classify_sector("aapl") == "technology"
        assert classify_sector("AAPL") == "technology"
        assert classify_sector("Aapl") == "technology"


class TestLLMFallback:
    @patch("tradingagents.dataflows.trending.sector_classifier._llm_classify_sector")
    def test_llm_fallback_for_unknown_tickers(self, mock_llm_classify):
        mock_llm_classify.return_value = "technology"
        _sector_cache.clear()

        result = classify_sector("UNKNOWNTICKER123")

        mock_llm_classify.assert_called_once_with("UNKNOWNTICKER123")
        assert result == "technology"

    @patch("tradingagents.dataflows.trending.sector_classifier._llm_classify_sector")
    def test_llm_fallback_caches_results(self, mock_llm_classify):
        mock_llm_classify.return_value = "healthcare"
        _sector_cache.clear()

        result1 = classify_sector("NEWCO123")
        result2 = classify_sector("NEWCO123")

        assert mock_llm_classify.call_count == 1
        assert result1 == "healthcare"
        assert result2 == "healthcare"

    @patch("tradingagents.dataflows.trending.sector_classifier._llm_classify_sector")
    def test_llm_fallback_returns_other_on_error(self, mock_llm_classify):
        mock_llm_classify.side_effect = RuntimeError("LLM error")
        _sector_cache.clear()

        result = classify_sector("ERRORCO")

        assert result == "other"


class TestAllSectorCategories:
    def test_all_sector_categories_in_valid_sectors(self):
        expected_sectors = {
            "technology",
            "healthcare",
            "finance",
            "energy",
            "consumer_goods",
            "industrials",
            "other",
        }
        assert expected_sectors == VALID_SECTORS

    def test_static_mapping_covers_all_sector_categories(self):
        sectors_in_mapping = set(TICKER_TO_SECTOR.values())
        assert sectors_in_mapping.issubset(VALID_SECTORS)

    def test_classify_sector_always_returns_valid_sector(self):
        test_tickers = ["AAPL", "JPM", "XOM", "JNJ", "WMT", "CAT"]
        for ticker in test_tickers:
            result = classify_sector(ticker)
            assert result in VALID_SECTORS
