"""The global news budget counts eligible articles, not unfiltered candidates."""

from datetime import datetime, timezone

import pytest

import tradingagents.dataflows.yfinance_news as ynews
from tradingagents.dataflows.config import set_config


def _article(title, date, *, nested=False):
    if nested:
        return {
            "content": {
                "title": title,
                "pubDate": f"{date}T12:00:00Z",
                "provider": {"displayName": "Test publisher"},
            }
        }
    return {
        "title": title,
        "providerPublishTime": int(
            datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()
        ),
    }


def _mock_search(monkeypatch, responses):
    queries = list(responses)
    set_config({"global_news_queries": queries})
    calls = []

    class FakeSearch:
        def __init__(self, query, **kwargs):
            calls.append(query)
            self.news = responses[query]

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    return calls


@pytest.mark.unit
@pytest.mark.parametrize("nested", [False, True])
def test_out_of_window_candidates_do_not_exhaust_search_budget(monkeypatch, nested):
    calls = _mock_search(monkeypatch, {
        "first": [
            _article("TOO OLD", "2025-05-01", nested=nested),
            _article("FUTURE", "2025-05-10", nested=nested),
        ],
        "second": [
            _article("IN WINDOW A", "2025-05-05", nested=nested),
            _article("IN WINDOW B", "2025-05-09", nested=nested),
        ],
    })

    result = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=2)

    assert "IN WINDOW A" in result
    assert "IN WINDOW B" in result
    assert "TOO OLD" not in result
    assert "FUTURE" not in result
    assert calls == ["first", "second"]


@pytest.mark.unit
def test_filtering_precedes_deduplication(monkeypatch):
    _mock_search(monkeypatch, {
        "first": [_article("SAME HEADLINE", "2025-05-10")],
        "second": [_article("SAME HEADLINE", "2025-05-09", nested=True)],
    })

    result = ynews.get_global_news_yfinance("2025-05-09", limit=1)

    assert result.count("### SAME HEADLINE") == 1


@pytest.mark.unit
def test_limit_counts_unique_eligible_articles_and_stops_searching(monkeypatch):
    calls = _mock_search(monkeypatch, {
        "first": [_article("FIRST", "2025-05-05")],
        "second": [
            _article("FIRST", "2025-05-05", nested=True),
            _article("FUTURE", "2025-05-10"),
            _article("SECOND", "2025-05-09"),
            _article("OVER LIMIT", "2025-05-08"),
        ],
        "unused": [_article("NOT REQUESTED", "2025-05-09")],
    })

    result = ynews.get_global_news_yfinance("2025-05-09", limit=2)

    assert result.count("### ") == 2
    assert result.count("### FIRST") == 1
    assert "SECOND" in result
    assert "FUTURE" not in result
    assert "OVER LIMIT" not in result
    assert "NOT REQUESTED" not in result
    assert calls == ["first", "second"]
