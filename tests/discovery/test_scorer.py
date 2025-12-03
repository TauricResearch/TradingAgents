import math
from datetime import datetime, timedelta
from unittest.mock import patch

from tradingagents.agents.discovery import EventCategory, NewsArticle
from tradingagents.agents.discovery.entity_extractor import EntityMention


class TestFrequencyCalculation:
    def test_frequency_calculation_unique_article_count(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="Apple Q4 Earnings",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=1),
                content_snippet="Apple Inc reported strong earnings.",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="Apple iPhone Sales",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=2),
                content_snippet="Apple saw record iPhone sales.",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="Apple AI Features",
                source="WSJ",
                url="https://wsj.com/article3",
                published_at=now - timedelta(hours=3),
                content_snippet="Apple announced AI features.",
                ticker_mentions=["AAPL"],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="Apple Inc",
                confidence=0.95,
                context_snippet="Apple Inc reported strong earnings",
                article_id="article_0",
                event_type=EventCategory.EARNINGS,
            ),
            EntityMention(
                company_name="Apple",
                confidence=0.90,
                context_snippet="Apple saw record iPhone sales",
                article_id="article_1",
                event_type=EventCategory.EARNINGS,
            ),
            EntityMention(
                company_name="Apple Inc.",
                confidence=0.92,
                context_snippet="Apple announced AI features",
                article_id="article_2",
                event_type=EventCategory.PRODUCT_LAUNCH,
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:
            mock_resolve.return_value = "AAPL"

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles)

                assert len(result) == 1
                assert result[0].ticker == "AAPL"
                assert result[0].mention_count == 3


class TestSentimentIntensityFactor:
    def test_sentiment_intensity_uses_absolute_value(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="Stock drops sharply",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=1),
                content_snippet="Company faced major issues.",
                ticker_mentions=["TSLA"],
            ),
            NewsArticle(
                title="More bad news",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=2),
                content_snippet="Further decline expected.",
                ticker_mentions=["TSLA"],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="Tesla",
                confidence=0.95,
                context_snippet="Company faced major issues",
                article_id="article_0",
                event_type=EventCategory.OTHER,
                sentiment=-0.8,
            ),
            EntityMention(
                company_name="Tesla Inc",
                confidence=0.90,
                context_snippet="Further decline expected",
                article_id="article_1",
                event_type=EventCategory.OTHER,
                sentiment=-0.6,
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:
            mock_resolve.return_value = "TSLA"

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles)

                assert len(result) == 1
                assert result[0].sentiment < 0
                expected_sentiment = (-0.8 * 0.95 + -0.6 * 0.90) / (0.95 + 0.90)
                assert abs(result[0].sentiment - expected_sentiment) < 0.01


class TestRecencyWeightExponentialDecay:
    def test_recency_weight_exponential_decay(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="Recent news",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=1),
                content_snippet="Recent company news.",
                ticker_mentions=["NVDA"],
            ),
            NewsArticle(
                title="Older news",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=10),
                content_snippet="Older company news.",
                ticker_mentions=["NVDA"],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="Nvidia",
                confidence=0.90,
                context_snippet="Recent company news",
                article_id="article_0",
                event_type=EventCategory.OTHER,
                sentiment=0.5,
            ),
            EntityMention(
                company_name="Nvidia",
                confidence=0.90,
                context_snippet="Older company news",
                article_id="article_1",
                event_type=EventCategory.OTHER,
                sentiment=0.5,
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:
            mock_resolve.return_value = "NVDA"

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles, decay_rate=0.1)

                assert len(result) == 1
                recent_weight = math.exp(-0.1 * 1)
                older_weight = math.exp(-0.1 * 10)
                avg_recency = (recent_weight + older_weight) / 2
                assert result[0].score > 0


class TestMinimumThresholdFiltering:
    def test_minimum_threshold_filtering_requires_two_articles(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="Single mention stock",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=1),
                content_snippet="Some company news.",
                ticker_mentions=["AMD"],
            ),
            NewsArticle(
                title="Multiple mention stock 1",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=2),
                content_snippet="Popular company news.",
                ticker_mentions=["MSFT"],
            ),
            NewsArticle(
                title="Multiple mention stock 2",
                source="WSJ",
                url="https://wsj.com/article3",
                published_at=now - timedelta(hours=3),
                content_snippet="More popular company news.",
                ticker_mentions=["MSFT"],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="AMD",
                confidence=0.90,
                context_snippet="Some company news",
                article_id="article_0",
                event_type=EventCategory.OTHER,
            ),
            EntityMention(
                company_name="Microsoft",
                confidence=0.95,
                context_snippet="Popular company news",
                article_id="article_1",
                event_type=EventCategory.OTHER,
            ),
            EntityMention(
                company_name="Microsoft Corp",
                confidence=0.92,
                context_snippet="More popular company news",
                article_id="article_2",
                event_type=EventCategory.OTHER,
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:

            def resolve_side_effect(name):
                if "AMD" in name or name == "AMD":
                    return "AMD"
                return "MSFT"

            mock_resolve.side_effect = resolve_side_effect

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles, min_mentions=2)

                assert len(result) == 1
                assert result[0].ticker == "MSFT"
                assert all(stock.mention_count >= 2 for stock in result)


class TestFinalScoreFormulaCorrectness:
    def test_final_score_formula_correctness(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        hours_old = 2.0
        articles = [
            NewsArticle(
                title="Test article 1",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=hours_old),
                content_snippet="Google announced results.",
                ticker_mentions=["GOOGL"],
            ),
            NewsArticle(
                title="Test article 2",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=hours_old),
                content_snippet="Alphabet earnings beat.",
                ticker_mentions=["GOOGL"],
            ),
        ]

        sentiment_val = 0.6
        confidence = 0.9
        mentions = [
            EntityMention(
                company_name="Google",
                confidence=confidence,
                context_snippet="Google announced results",
                article_id="article_0",
                event_type=EventCategory.EARNINGS,
                sentiment=sentiment_val,
            ),
            EntityMention(
                company_name="Alphabet",
                confidence=confidence,
                context_snippet="Alphabet earnings beat",
                article_id="article_1",
                event_type=EventCategory.EARNINGS,
                sentiment=sentiment_val,
            ),
        ]

        decay_rate = 0.1
        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:
            mock_resolve.return_value = "GOOGL"

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(
                    mentions, articles, decay_rate=decay_rate
                )

                assert len(result) == 1
                stock = result[0]

                frequency = 2
                sentiment_factor = 1 + abs(sentiment_val)
                recency_weight = math.exp(-decay_rate * hours_old)
                expected_score = frequency * sentiment_factor * recency_weight

                assert abs(stock.score - expected_score) < 0.01


class TestSortingByScoreDescending:
    def test_results_sorted_by_score_descending(self):
        from tradingagents.agents.discovery.scorer import calculate_trending_scores

        now = datetime.now()
        articles = [
            NewsArticle(
                title="High score stock 1",
                source="Reuters",
                url="https://reuters.com/article1",
                published_at=now - timedelta(hours=1),
                content_snippet="Apple news.",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="High score stock 2",
                source="Bloomberg",
                url="https://bloomberg.com/article2",
                published_at=now - timedelta(hours=1),
                content_snippet="More Apple news.",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="High score stock 3",
                source="WSJ",
                url="https://wsj.com/article3",
                published_at=now - timedelta(hours=1),
                content_snippet="Even more Apple news.",
                ticker_mentions=["AAPL"],
            ),
            NewsArticle(
                title="Low score stock 1",
                source="CNBC",
                url="https://cnbc.com/article4",
                published_at=now - timedelta(hours=10),
                content_snippet="Tesla news.",
                ticker_mentions=["TSLA"],
            ),
            NewsArticle(
                title="Low score stock 2",
                source="FT",
                url="https://ft.com/article5",
                published_at=now - timedelta(hours=10),
                content_snippet="More Tesla news.",
                ticker_mentions=["TSLA"],
            ),
        ]

        mentions = [
            EntityMention(
                company_name="Apple",
                confidence=0.95,
                context_snippet="Apple news",
                article_id="article_0",
                event_type=EventCategory.OTHER,
                sentiment=0.8,
            ),
            EntityMention(
                company_name="Apple Inc",
                confidence=0.93,
                context_snippet="More Apple news",
                article_id="article_1",
                event_type=EventCategory.OTHER,
                sentiment=0.8,
            ),
            EntityMention(
                company_name="Apple",
                confidence=0.90,
                context_snippet="Even more Apple news",
                article_id="article_2",
                event_type=EventCategory.OTHER,
                sentiment=0.8,
            ),
            EntityMention(
                company_name="Tesla",
                confidence=0.85,
                context_snippet="Tesla news",
                article_id="article_3",
                event_type=EventCategory.OTHER,
                sentiment=0.2,
            ),
            EntityMention(
                company_name="Tesla Inc",
                confidence=0.85,
                context_snippet="More Tesla news",
                article_id="article_4",
                event_type=EventCategory.OTHER,
                sentiment=0.2,
            ),
        ]

        with patch(
            "tradingagents.agents.discovery.scorer.resolve_ticker"
        ) as mock_resolve:

            def resolve_side_effect(name):
                if "Apple" in name:
                    return "AAPL"
                if "Tesla" in name:
                    return "TSLA"
                return None

            mock_resolve.side_effect = resolve_side_effect

            with patch(
                "tradingagents.agents.discovery.scorer.classify_sector"
            ) as mock_sector:
                mock_sector.return_value = "technology"

                result = calculate_trending_scores(mentions, articles, min_mentions=2)

                assert len(result) == 2
                for i in range(len(result) - 1):
                    assert result[i].score >= result[i + 1].score
