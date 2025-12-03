from unittest.mock import MagicMock, patch

import pytest


class TestCalculateReturn:
    def test_calculate_positive_return(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_return,
        )

        prices = [100.0, 102.0, 105.0, 108.0, 110.0]
        ret = calculate_return(prices, days=5)
        assert ret == pytest.approx(10.0, rel=0.01)

    def test_calculate_negative_return(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_return,
        )

        prices = [100.0, 98.0, 95.0, 92.0, 90.0]
        ret = calculate_return(prices, days=5)
        assert ret == pytest.approx(-10.0, rel=0.01)

    def test_calculate_return_insufficient_data(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_return,
        )

        prices = [100.0, 110.0]
        ret = calculate_return(prices, days=5)
        assert ret == pytest.approx(10.0, rel=0.01)

    def test_calculate_return_empty_list(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_return,
        )

        prices = []
        ret = calculate_return(prices, days=5)
        assert ret == 0.0


class TestCalculateRelativeStrength:
    def test_positive_outperformance(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_relative_strength,
        )

        rs = calculate_relative_strength(stock_return=15.0, benchmark_return=10.0)
        assert rs == 5.0

    def test_negative_outperformance(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_relative_strength,
        )

        rs = calculate_relative_strength(stock_return=5.0, benchmark_return=10.0)
        assert rs == -5.0

    def test_equal_returns(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_relative_strength,
        )

        rs = calculate_relative_strength(stock_return=10.0, benchmark_return=10.0)
        assert rs == 0.0


class TestSectorEtfMap:
    def test_sector_etf_map_contains_expected_sectors(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            SECTOR_ETF_MAP,
        )

        assert "technology" in SECTOR_ETF_MAP
        assert "finance" in SECTOR_ETF_MAP
        assert "healthcare" in SECTOR_ETF_MAP
        assert "energy" in SECTOR_ETF_MAP
        assert "consumer_goods" in SECTOR_ETF_MAP
        assert "industrials" in SECTOR_ETF_MAP
        assert "other" in SECTOR_ETF_MAP

    def test_sector_etf_map_values(self):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            SECTOR_ETF_MAP,
        )

        assert SECTOR_ETF_MAP["technology"] == "XLK"
        assert SECTOR_ETF_MAP["finance"] == "XLF"
        assert SECTOR_ETF_MAP["healthcare"] == "XLV"
        assert SECTOR_ETF_MAP["energy"] == "XLE"
        assert SECTOR_ETF_MAP["other"] == "SPY"


class TestGetSectorEtf:
    @patch(
        "tradingagents.agents.discovery.indicators.relative_strength.classify_sector"
    )
    def test_get_sector_etf_for_tech_stock(self, mock_classify):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            get_sector_etf,
        )

        mock_classify.return_value = "technology"
        etf = get_sector_etf("AAPL")
        assert etf == "XLK"

    @patch(
        "tradingagents.agents.discovery.indicators.relative_strength.classify_sector"
    )
    def test_get_sector_etf_for_finance_stock(self, mock_classify):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            get_sector_etf,
        )

        mock_classify.return_value = "finance"
        etf = get_sector_etf("JPM")
        assert etf == "XLF"

    @patch(
        "tradingagents.agents.discovery.indicators.relative_strength.classify_sector"
    )
    def test_get_sector_etf_for_unknown_sector(self, mock_classify):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            get_sector_etf,
        )

        mock_classify.return_value = "other"
        etf = get_sector_etf("XYZ")
        assert etf == "SPY"


class TestCalculateRelativeStrengthMetrics:
    @patch(
        "tradingagents.agents.discovery.indicators.relative_strength._get_price_history"
    )
    @patch("tradingagents.agents.discovery.indicators.relative_strength.get_sector_etf")
    def test_calculate_rs_metrics_returns_dict(
        self, mock_sector_etf, mock_price_history
    ):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_relative_strength_metrics,
        )

        mock_sector_etf.return_value = "XLK"

        base_prices = [100.0 + i * 0.5 for i in range(70)]
        spy_prices = [100.0 + i * 0.3 for i in range(70)]
        sector_prices = [100.0 + i * 0.4 for i in range(70)]

        def price_history_side_effect(ticker, date, days):
            if ticker == "AAPL":
                return base_prices[-days:]
            elif ticker == "SPY":
                return spy_prices[-days:]
            else:
                return sector_prices[-days:]

        mock_price_history.side_effect = price_history_side_effect

        result = calculate_relative_strength_metrics("AAPL", "2024-01-15")

        assert isinstance(result, dict)
        assert "rs_vs_spy_5d" in result
        assert "rs_vs_spy_20d" in result
        assert "rs_vs_spy_60d" in result
        assert "rs_vs_sector" in result
        assert "sector_etf" in result
        assert "relative_strength_score" in result
        assert 0.0 <= result["relative_strength_score"] <= 1.0

    @patch(
        "tradingagents.agents.discovery.indicators.relative_strength._get_price_history"
    )
    @patch("tradingagents.agents.discovery.indicators.relative_strength.get_sector_etf")
    def test_calculate_rs_metrics_handles_missing_benchmark_data(
        self, mock_sector_etf, mock_price_history
    ):
        from tradingagents.agents.discovery.indicators.relative_strength import (
            calculate_relative_strength_metrics,
        )

        mock_sector_etf.return_value = "XLK"
        mock_price_history.return_value = []

        result = calculate_relative_strength_metrics("INVALID", "2024-01-15")

        assert isinstance(result, dict)
        assert result["relative_strength_score"] == 0.5
