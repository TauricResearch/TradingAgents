"""Unit tests for polymarket_news Exa client."""

import os
from unittest.mock import patch, MagicMock
import pytest
import httpx

from tradingagents.dataflows.polymarket_news import (
    search_event_news,
    ExaAPIError,
    MIN_SOURCES_FOR_CONFIDENCE,
)


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    """Set a fake EXA_API_KEY for all tests."""
    monkeypatch.setenv("EXA_API_KEY", "test-key-do-not-use")


@pytest.mark.unit
def test_happy_path_returns_articles():
    """Exa returns 5 results, function returns 5 normalised articles."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {
                "title": f"Article {i}",
                "url": f"https://example.com/{i}",
                "publishedDate": "2026-05-01T00:00:00Z",
                "text": f"Body text for article {i}.",
            }
            for i in range(5)
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch(
        "tradingagents.dataflows.polymarket_news.httpx.post", return_value=fake_response
    ):
        articles = search_event_news("Will X happen?", limit=10)

    assert len(articles) == 5
    assert articles[0]["title"] == "Article 0"
    assert articles[0]["url"] == "https://example.com/0"
    assert "text" in articles[0]


@pytest.mark.unit
def test_insufficient_sources_returns_empty():
    """< 3 sources triggers low-confidence path: empty list returned."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "results": [
            {"title": "Only", "url": "https://x.com/1", "publishedDate": None, "text": "t"},
            {"title": "Two", "url": "https://x.com/2", "publishedDate": None, "text": "t"},
        ]
    }
    fake_response.raise_for_status = MagicMock()

    with patch(
        "tradingagents.dataflows.polymarket_news.httpx.post", return_value=fake_response
    ):
        articles = search_event_news("Will Y happen?", limit=10)

    assert articles == []


@pytest.mark.unit
def test_min_sources_threshold_is_three():
    """The threshold matches the design's < 3 rule."""
    assert MIN_SOURCES_FOR_CONFIDENCE == 3


@pytest.mark.unit
def test_zero_results_returns_empty():
    """Exa returns no results, function returns empty list."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {"results": []}
    fake_response.raise_for_status = MagicMock()

    with patch(
        "tradingagents.dataflows.polymarket_news.httpx.post", return_value=fake_response
    ):
        articles = search_event_news("No-news query", limit=10)

    assert articles == []


@pytest.mark.unit
def test_api_error_returns_empty():
    """Exa API failure degrades to empty list, loop continues."""
    fake_response = MagicMock()
    fake_response.status_code = 500
    fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=fake_response
    )

    with patch(
        "tradingagents.dataflows.polymarket_news.httpx.post", return_value=fake_response
    ):
        articles = search_event_news("Query", limit=10)

    assert articles == []


@pytest.mark.unit
def test_timeout_returns_empty():
    """Exa timeout degrades to empty list, loop continues."""
    with patch(
        "tradingagents.dataflows.polymarket_news.httpx.post",
        side_effect=httpx.ReadTimeout("timeout"),
    ):
        articles = search_event_news("Query", limit=10)

    assert articles == []


@pytest.mark.unit
def test_missing_api_key_raises():
    """No EXA_API_KEY env var raises ExaAPIError on first call."""
    if "EXA_API_KEY" in os.environ:
        os.environ.pop("EXA_API_KEY")
    with pytest.raises(ExaAPIError) as exc_info:
        search_event_news("Query", limit=10)
    assert "EXA_API_KEY" in str(exc_info.value)
