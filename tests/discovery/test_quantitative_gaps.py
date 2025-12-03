import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.agents.discovery.models import (
    EventCategory,
    NewsArticle,
    Sector,
    TrendingStock,
)
from tradingagents.agents.discovery.quantitative_models import QuantitativeMetrics
from tradingagents.config import QuantitativeWeightsConfig


class TestFullPipelineIntegration:
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
    def test_full_pipeline_news_to_quantitative_enhancement(
        self, mock_sr, mock_rs, mock_vol, mock_mom
    ):
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        mock_mom.return_value = {
            "rsi": 45.0,
            "macd": 0.5,
            "macd_signal": 0.4,
            "macd_histogram": 0.1,
            "price_vs_sma50": 5.0,
            "price_vs_sma200": 10.0,
            "ema10_direction": "up",
            "momentum_score": 0.7,
        }
        mock_vol.return_value = {
            "volume_ratio": 1.8,
            "volume_trend": "increasing",
            "dollar_volume": 25000000.0,
            "volume_score": 0.75,
        }
        mock_rs.return_value = {
            "rs_vs_spy_5d": 3.0,
            "rs_vs_spy_20d": 5.0,
            "rs_vs_spy_60d": 8.0,
            "rs_vs_sector": 2.5,
            "sector_etf": "XLK",
            "relative_strength_score": 0.8,
        }
        mock_sr.return_value = {
            "support_level": 145.0,
            "resistance_level": 175.0,
            "atr": 3.0,
            "suggested_stop": 140.5,
            "reward_target": 175.0,
            "risk_reward_ratio": 2.5,
            "risk_reward_score": 0.85,
        }

        articles = [
            NewsArticle(
                title="Apple Reports Strong Quarter",
                source="Reuters",
                url="http://example.com/1",
                published_at=datetime.now(),
                content_snippet="Apple beats expectations",
                ticker_mentions=["AAPL"],
            )
        ]

        stocks = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc",
                score=85.0,
                mention_count=15,
                sentiment=0.75,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Apple reports strong quarterly results",
                source_articles=articles,
            ),
            TrendingStock(
                ticker="MSFT",
                company_name="Microsoft Corp",
                score=72.0,
                mention_count=10,
                sentiment=0.6,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.PRODUCT_LAUNCH,
                news_summary="Microsoft launches new product",
                source_articles=[],
            ),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert len(result) == 2
        for stock in result:
            if stock.quantitative_metrics is not None:
                assert stock.conviction_score is not None
                assert 0.0 <= stock.conviction_score <= 1.0
                assert stock.quantitative_metrics.rsi == 45.0
                assert stock.quantitative_metrics.sector_etf == "XLK"


class TestDelistedStockHandling:
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_momentum_score"
    )
    def test_stock_with_no_trading_data_returns_none(self, mock_mom):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_single_stock_metrics,
        )

        mock_mom.side_effect = Exception("No price data available for delisted stock")

        result = calculate_single_stock_metrics("DELIST", "2024-01-15")

        assert result is None

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
    def test_enhance_continues_after_delisted_stock_failure(
        self, mock_sr, mock_rs, mock_vol, mock_mom
    ):
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        def mom_side_effect(ticker, date):
            if ticker == "DELIST":
                raise Exception("No data for delisted stock")
            return {"momentum_score": 0.6, "rsi": 50.0}

        mock_mom.side_effect = mom_side_effect
        mock_vol.return_value = {"volume_score": 0.5}
        mock_rs.return_value = {"relative_strength_score": 0.5, "sector_etf": "SPY"}
        mock_sr.return_value = {"risk_reward_score": 0.5}

        stocks = [
            TrendingStock(
                ticker="AAPL",
                company_name="Apple Inc",
                score=90.0,
                mention_count=10,
                sentiment=0.5,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            ),
            TrendingStock(
                ticker="DELIST",
                company_name="Delisted Corp",
                score=80.0,
                mention_count=8,
                sentiment=0.4,
                sector=Sector.OTHER,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            ),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert len(result) == 2

        aapl = next((s for s in result if s.ticker == "AAPL"), None)
        delist = next((s for s in result if s.ticker == "DELIST"), None)

        assert aapl is not None
        assert aapl.quantitative_metrics is not None

        assert delist is not None
        assert delist.quantitative_metrics is None


class TestWeightConfigurationEdgeCases:
    def test_weights_near_boundary_accepted(self):
        config = QuantitativeWeightsConfig(
            news_sentiment_weight=0.501,
            quantitative_weight=0.499,
        )

        total = config.news_sentiment_weight + config.quantitative_weight
        assert abs(total - 1.0) < 0.01

    def test_sub_weights_custom_values_accepted(self):
        config = QuantitativeWeightsConfig(
            momentum_weight=0.40,
            volume_weight=0.20,
            relative_strength_weight=0.20,
            risk_reward_weight=0.20,
        )

        sub_total = (
            config.momentum_weight
            + config.volume_weight
            + config.relative_strength_weight
            + config.risk_reward_weight
        )
        assert abs(sub_total - 1.0) < 0.01


class TestCacheConcurrentAccess:
    def test_cache_thread_safety_under_concurrent_writes(self):
        from tradingagents.agents.discovery.quantitative_cache import (
            clear_run_cache,
            get_cached_price_data,
            set_cached_price_data,
        )

        clear_run_cache()

        errors = []
        results = {}

        def write_to_cache(ticker_num):
            try:
                ticker = f"TICK{ticker_num}"
                df = pd.DataFrame({"Close": [float(ticker_num)]})
                set_cached_price_data(ticker, df)
                cached = get_cached_price_data(ticker)
                if cached is not None:
                    results[ticker] = cached["Close"].iloc[0]
            except Exception as e:
                errors.append(str(e))

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(write_to_cache, i) for i in range(50)]
            for f in futures:
                f.result()

        assert len(errors) == 0

        clear_run_cache()


class TestConvictionScoreRanking:
    @patch(
        "tradingagents.agents.discovery.quantitative_scorer.calculate_single_stock_metrics"
    )
    def test_conviction_score_ranking_accuracy(self, mock_calc):
        from tradingagents.agents.discovery.quantitative_scorer import (
            enhance_with_quantitative_scores,
        )

        def side_effect(ticker, date):
            scores = {
                "HIGH_BOTH": (0.9, 0.9),
                "HIGH_NEWS_LOW_QUANT": (0.3, 0.9),
                "LOW_NEWS_HIGH_QUANT": (0.9, 0.3),
                "LOW_BOTH": (0.3, 0.3),
            }
            quant, _ = scores.get(ticker, (0.5, 0.5))
            return QuantitativeMetrics(
                momentum_score=quant,
                volume_score=quant,
                relative_strength_score=quant,
                risk_reward_score=quant,
                quantitative_score=quant,
            )

        mock_calc.side_effect = side_effect

        stocks = [
            TrendingStock(
                ticker="LOW_BOTH",
                company_name="Low Both",
                score=30.0,
                mention_count=5,
                sentiment=0.3,
                sector=Sector.OTHER,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            ),
            TrendingStock(
                ticker="HIGH_BOTH",
                company_name="High Both",
                score=90.0,
                mention_count=15,
                sentiment=0.9,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.EARNINGS,
                news_summary="Test",
                source_articles=[],
            ),
            TrendingStock(
                ticker="HIGH_NEWS_LOW_QUANT",
                company_name="High News Low Quant",
                score=90.0,
                mention_count=15,
                sentiment=0.9,
                sector=Sector.TECHNOLOGY,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            ),
            TrendingStock(
                ticker="LOW_NEWS_HIGH_QUANT",
                company_name="Low News High Quant",
                score=30.0,
                mention_count=5,
                sentiment=0.3,
                sector=Sector.OTHER,
                event_type=EventCategory.OTHER,
                news_summary="Test",
                source_articles=[],
            ),
        ]

        result = enhance_with_quantitative_scores(stocks, "2024-01-15")

        assert result[0].ticker == "HIGH_BOTH"

        high_both = next(s for s in result if s.ticker == "HIGH_BOTH")
        low_both = next(s for s in result if s.ticker == "LOW_BOTH")
        assert high_both.conviction_score > low_both.conviction_score


class TestTrendingStockSerializationWithQuantitativeMetrics:
    def test_trending_stock_with_quantitative_metrics_roundtrip(self):
        articles = [
            NewsArticle(
                title="Test Article",
                source="Test Source",
                url="http://test.com",
                published_at=datetime(2024, 1, 15, 10, 30, 0),
                content_snippet="Test content",
                ticker_mentions=["AAPL"],
            )
        ]

        metrics = QuantitativeMetrics(
            momentum_score=0.75,
            volume_score=0.65,
            relative_strength_score=0.80,
            risk_reward_score=0.70,
            rsi=42.5,
            macd=0.35,
            macd_signal=0.28,
            macd_histogram=0.07,
            price_vs_sma50=4.5,
            price_vs_sma200=9.2,
            ema10_direction="up",
            volume_ratio=1.65,
            volume_trend="increasing",
            dollar_volume=18500000.0,
            rs_vs_spy_5d=2.8,
            rs_vs_spy_20d=4.2,
            rs_vs_spy_60d=7.5,
            rs_vs_sector=2.1,
            sector_etf="XLK",
            support_level=148.50,
            resistance_level=165.75,
            atr=2.85,
            suggested_stop=144.22,
            reward_target=165.75,
            risk_reward_ratio=2.65,
            quantitative_score=0.725,
        )

        original = TrendingStock(
            ticker="AAPL",
            company_name="Apple Inc",
            score=87.5,
            mention_count=12,
            sentiment=0.72,
            sector=Sector.TECHNOLOGY,
            event_type=EventCategory.EARNINGS,
            news_summary="Apple reports strong quarterly earnings",
            source_articles=articles,
            quantitative_metrics=metrics,
            conviction_score=0.815,
        )

        data = original.to_dict()
        restored = TrendingStock.from_dict(data)

        assert restored.ticker == original.ticker
        assert restored.score == original.score
        assert restored.conviction_score == original.conviction_score
        assert restored.quantitative_metrics is not None
        assert restored.quantitative_metrics.momentum_score == 0.75
        assert restored.quantitative_metrics.rsi == 42.5
        assert restored.quantitative_metrics.sector_etf == "XLK"
        assert restored.quantitative_metrics.quantitative_score == 0.725


class TestModuleIntegration:
    def test_unified_score_combines_all_indicators_correctly(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_unified_score,
        )

        weights = QuantitativeWeightsConfig()

        score = calculate_unified_score(
            momentum=0.8,
            volume=0.6,
            rs=0.7,
            rr=0.9,
            weights=weights,
        )

        expected = (
            0.8 * weights.momentum_weight
            + 0.6 * weights.volume_weight
            + 0.7 * weights.relative_strength_weight
            + 0.9 * weights.risk_reward_weight
        )
        assert abs(score - expected) < 0.001

    def test_unified_score_clamped_to_valid_range(self):
        from tradingagents.agents.discovery.quantitative_scorer import (
            calculate_unified_score,
        )

        weights = QuantitativeWeightsConfig()

        score = calculate_unified_score(
            momentum=1.5,
            volume=1.5,
            rs=1.5,
            rr=1.5,
            weights=weights,
        )

        assert score == 1.0

        score_low = calculate_unified_score(
            momentum=-0.5,
            volume=-0.5,
            rs=-0.5,
            rr=-0.5,
            weights=weights,
        )

        assert score_low == 0.0
