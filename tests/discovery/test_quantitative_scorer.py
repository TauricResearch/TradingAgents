from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


class TestCalculateSingleStockMetrics:
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_momentum_score"
    )
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_volume_metrics"
    )
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_relative_strength_metrics"
    )
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_support_resistance_metrics"
    )
    def test_calculate_single_stock_metrics_success(
        self, mock_sr, mock_rs, mock_vol, mock_mom
    ):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_single_stock_metrics,
        )

        mock_mom.return_value = {
            "rsi": 45.0,
            "macd": 0.5,
            "macd_signal": 0.4,
            "macd_histogram": 0.1,
            "price_vs_sma50": 2.5,
            "price_vs_sma200": 5.0,
            "ema10_direction": "up",
            "momentum_score": 0.65,
        }
        mock_vol.return_value = {
            "volume_ratio": 1.5,
            "volume_trend": "increasing",
            "dollar_volume": 5000000.0,
            "volume_score": 0.7,
        }
        mock_rs.return_value = {
            "rs_vs_spy_5d": 2.0,
            "rs_vs_spy_20d": 3.5,
            "rs_vs_spy_60d": 5.0,
            "rs_vs_sector": 2.5,
            "sector_etf": "XLK",
            "relative_strength_score": 0.6,
        }
        mock_sr.return_value = {
            "support_level": 150.0,
            "resistance_level": 180.0,
            "atr": 3.5,
            "suggested_stop": 145.0,
            "reward_target": 180.0,
            "risk_reward_ratio": 2.5,
            "risk_reward_score": 0.75,
        }

        result = calculate_single_stock_metrics("AAPL", "2024-01-15")

        assert result is not None
        assert result.momentum_score == 0.65
        assert result.volume_score == 0.7
        assert result.relative_strength_score == 0.6
        assert result.risk_reward_score == 0.75
        assert 0.0 <= result.quantitative_score <= 1.0

    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_momentum_score"
    )
    def test_calculate_single_stock_metrics_failure(self, mock_mom):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_single_stock_metrics,
        )

        mock_mom.side_effect = Exception("API failure")

        result = calculate_single_stock_metrics("INVALID", "2024-01-15")

        assert result is None


class TestCalculateUnifiedScore:
    def test_unified_score_basic(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_unified_score,
        )
        from tradingagents.config import QuantitativeWeightsConfig

        weights = QuantitativeWeightsConfig()

        score = calculate_unified_score(
            momentum=0.8,
            volume=0.6,
            rs=0.7,
            rr=0.5,
            weights=weights,
        )

        expected = 0.8 * 0.30 + 0.6 * 0.25 + 0.7 * 0.25 + 0.5 * 0.20
        assert abs(score - expected) < 0.001

    def test_unified_score_all_ones(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_unified_score,
        )
        from tradingagents.config import QuantitativeWeightsConfig

        weights = QuantitativeWeightsConfig()

        score = calculate_unified_score(
            momentum=1.0,
            volume=1.0,
            rs=1.0,
            rr=1.0,
            weights=weights,
        )

        assert abs(score - 1.0) < 0.001

    def test_unified_score_all_zeros(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_unified_score,
        )
        from tradingagents.config import QuantitativeWeightsConfig

        weights = QuantitativeWeightsConfig()

        score = calculate_unified_score(
            momentum=0.0,
            volume=0.0,
            rs=0.0,
            rr=0.0,
            weights=weights,
        )

        assert abs(score - 0.0) < 0.001


class TestEnhanceWithQuantitativeScores:
    def _create_mock_trending_stock(self, ticker: str, score: float):
        from tradingagents.agents.discovery.models import (
            EventCategory,
            NewsArticle,
            Sector,
            TrendingStock,
        )

        return TrendingStock(
            ticker=ticker,
            company_name=f"{ticker} Inc",
            score=score,
            mention_count=10,
            sentiment=0.5,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Test summary",
            source_articles=[],
        )

    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_single_stock_metrics"
    )
    def test_enhance_with_quantitative_scores_basic(self, mock_calc):
        from tradingagents.agents.discovery.quantitative_models import (
            QuantitativeMetrics,
        )
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        mock_calc.return_value = QuantitativeMetrics(
            momentum_score=0.7,
            volume_score=0.6,
            relative_strength_score=0.65,
            risk_reward_score=0.7,
            quantitative_score=0.66,
        )

        stocks = [
            self._create_mock_trending_stock("AAPL", 90.0),
            self._create_mock_trending_stock("MSFT", 80.0),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert len(result) == 2
        for stock in result:
            assert stock.quantitative_metrics is not None
            assert stock.conviction_score is not None

    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_single_stock_metrics"
    )
    def test_enhance_caps_at_max_stocks(self, mock_calc):
        from tradingagents.agents.discovery.quantitative_models import (
            QuantitativeMetrics,
        )
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        mock_calc.return_value = QuantitativeMetrics(
            momentum_score=0.5,
            volume_score=0.5,
            relative_strength_score=0.5,
            risk_reward_score=0.5,
            quantitative_score=0.5,
        )

        stocks = [
            self._create_mock_trending_stock(f"TICK{i}", 100.0 - i) for i in range(60)
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15", max_stocks=10)

        assert mock_calc.call_count == 10

    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_single_stock_metrics"
    )
    def test_enhance_handles_partial_failures(self, mock_calc):
        from tradingagents.agents.discovery.quantitative_models import (
            QuantitativeMetrics,
        )
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        def side_effect(ticker, date):
            if ticker == "FAIL":
                return None
            return QuantitativeMetrics(
                momentum_score=0.5,
                volume_score=0.5,
                relative_strength_score=0.5,
                risk_reward_score=0.5,
                quantitative_score=0.5,
            )

        mock_calc.side_effect = side_effect

        stocks = [
            self._create_mock_trending_stock("AAPL", 90.0),
            self._create_mock_trending_stock("FAIL", 85.0),
            self._create_mock_trending_stock("MSFT", 80.0),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert len(result) == 3

        successful = [s for s in result if s.quantitative_metrics is not None]
        assert len(successful) == 2

    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_single_stock_metrics"
    )
    def test_enhance_sorts_by_conviction_score(self, mock_calc):
        from tradingagents.agents.discovery.quantitative_models import (
            QuantitativeMetrics,
        )
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        def side_effect(ticker, date):
            scores = {
                "LOW": 0.3,
                "MED": 0.5,
                "HIGH": 0.9,
            }
            quant_score = scores.get(ticker, 0.5)
            return QuantitativeMetrics(
                momentum_score=quant_score,
                volume_score=quant_score,
                relative_strength_score=quant_score,
                risk_reward_score=quant_score,
                quantitative_score=quant_score,
            )

        mock_calc.side_effect = side_effect

        stocks = [
            self._create_mock_trending_stock("LOW", 60.0),
            self._create_mock_trending_stock("HIGH", 40.0),
            self._create_mock_trending_stock("MED", 50.0),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert (
            result[0].quantitative_metrics.quantitative_score
            >= result[1].quantitative_metrics.quantitative_score
        )
        assert (
            result[1].quantitative_metrics.quantitative_score
            >= result[2].quantitative_metrics.quantitative_score
        )


class TestErrorHandling:
    def test_empty_stock_list(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        result = enhance_with_quantitative_scores([], "2024-01-15")

        assert result == []
