import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from tradingagents.agents.discovery import NewsArticle, EventCategory


class TestExtractEntitiesReturnsCompanyMentions:
    def test_extract_entities_returns_list_of_company_mentions(self):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
        )

        articles = [
            NewsArticle(
                title="Apple announces new iPhone",
                source="Reuters",
                url="https://reuters.com/apple",
                published_at=datetime.now(),
                content_snippet="Apple Inc unveiled its latest iPhone model today with advanced AI features.",
                ticker_mentions=[],
            ),
        ]

        mock_response = MagicMock()
        mock_response.entities = [
            MagicMock(
                company_name="Apple Inc",
                confidence=0.95,
                context_snippet="Apple Inc unveiled its latest iPhone",
                event_type="product_launch",
                sentiment=0.7,
            )
        ]

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.invoke.return_value = (
                mock_response
            )
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            assert isinstance(result, list)
            assert len(result) > 0
            assert all(isinstance(m, EntityMention) for m in result)
            assert result[0].company_name == "Apple Inc"


class TestConfidenceScoreRange:
    def test_confidence_score_in_valid_range(self):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
        )

        articles = [
            NewsArticle(
                title="Tesla reports earnings",
                source="Bloomberg",
                url="https://bloomberg.com/tsla",
                published_at=datetime.now(),
                content_snippet="Tesla Inc reported strong quarterly earnings beating analyst expectations.",
                ticker_mentions=[],
            ),
        ]

        mock_response = MagicMock()
        mock_response.entities = [
            MagicMock(
                company_name="Tesla Inc",
                confidence=0.88,
                context_snippet="Tesla Inc reported strong quarterly earnings",
                event_type="earnings",
                sentiment=0.5,
            )
        ]

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.invoke.return_value = (
                mock_response
            )
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            for mention in result:
                assert 0.0 <= mention.confidence <= 1.0


class TestContextSnippetExtraction:
    def test_context_snippet_extraction(self):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
        )

        articles = [
            NewsArticle(
                title="Microsoft acquires gaming company",
                source="WSJ",
                url="https://wsj.com/msft",
                published_at=datetime.now(),
                content_snippet="Microsoft Corporation announced today it will acquire a major gaming studio for $10 billion.",
                ticker_mentions=[],
            ),
        ]

        mock_response = MagicMock()
        mock_response.entities = [
            MagicMock(
                company_name="Microsoft Corporation",
                confidence=0.92,
                context_snippet="Microsoft Corporation announced today it will acquire",
                event_type="merger_acquisition",
                sentiment=0.6,
            )
        ]

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.invoke.return_value = (
                mock_response
            )
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            assert len(result) > 0
            for mention in result:
                assert mention.context_snippet is not None
                assert len(mention.context_snippet) > 0
                assert len(mention.context_snippet) <= 150


class TestBatchProcessing:
    def test_batch_processing_of_multiple_articles(self):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
            BATCH_SIZE,
        )

        articles = [
            NewsArticle(
                title=f"News article {i}",
                source="Reuters",
                url=f"https://reuters.com/article{i}",
                published_at=datetime.now(),
                content_snippet=f"Company {i} announced major developments today.",
                ticker_mentions=[],
            )
            for i in range(15)
        ]

        mock_response = MagicMock()
        mock_response.entities = [
            MagicMock(
                company_name="Test Company",
                confidence=0.85,
                context_snippet="Company announced major developments",
                event_type="other",
                sentiment=0.0,
            )
        ]

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            structured_llm = MagicMock()
            structured_llm.invoke.return_value = mock_response
            mock_llm.with_structured_output.return_value = structured_llm
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            expected_batches = (len(articles) + BATCH_SIZE - 1) // BATCH_SIZE
            assert structured_llm.invoke.call_count == expected_batches


class TestNoCompanyMentions:
    def test_handling_of_articles_with_no_company_mentions(self):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
        )

        articles = [
            NewsArticle(
                title="Weather forecast for tomorrow",
                source="Weather Channel",
                url="https://weather.com/forecast",
                published_at=datetime.now(),
                content_snippet="Tomorrow will be sunny with temperatures reaching 75 degrees.",
                ticker_mentions=[],
            ),
        ]

        mock_response = MagicMock()
        mock_response.entities = []

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.invoke.return_value = (
                mock_response
            )
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            assert isinstance(result, list)
            assert len(result) == 0


class TestEventTypeClassification:
    @pytest.mark.parametrize(
        "event_type",
        [
            "earnings",
            "merger_acquisition",
            "regulatory",
            "product_launch",
            "executive_change",
            "other",
        ],
    )
    def test_event_type_classification(self, event_type):
        from tradingagents.agents.discovery.entity_extractor import (
            extract_entities,
            EntityMention,
        )

        articles = [
            NewsArticle(
                title="Company news",
                source="Reuters",
                url="https://reuters.com/news",
                published_at=datetime.now(),
                content_snippet="A company made an announcement today.",
                ticker_mentions=[],
            ),
        ]

        mock_response = MagicMock()
        mock_response.entities = [
            MagicMock(
                company_name="Test Company",
                confidence=0.90,
                context_snippet="A company made an announcement",
                event_type=event_type,
                sentiment=0.0,
            )
        ]

        with patch(
            "tradingagents.agents.discovery.entity_extractor._get_llm"
        ) as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value.invoke.return_value = (
                mock_response
            )
            mock_get_llm.return_value = mock_llm

            result = extract_entities(articles)

            assert len(result) > 0
            assert result[0].event_type == EventCategory(event_type)
