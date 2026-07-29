"""India-specific news/social routing regression tests for issue #1178."""

import pytest

import tradingagents.dataflows.reddit as reddit
from tradingagents.dataflows.stocktwits import _stocktwits_symbol
from tradingagents.dataflows.symbol_utils import build_india_search_terms

pytestmark = pytest.mark.unit


def test_stocktwits_maps_yahoo_india_suffixes():
    assert _stocktwits_symbol("SBIN.NS") == "SBIN.NSE"
    assert _stocktwits_symbol("500325.BO") == "500325.BSE"


def test_reddit_routes_nse_to_india_communities():
    assert reddit._subreddits_for_ticker("SBIN.NS") == reddit.INDIA_SUBREDDITS
    assert reddit._subreddits_for_ticker("500325.BO") == reddit.INDIA_SUBREDDITS
    assert reddit._subreddits_for_ticker("AAPL") == reddit.DEFAULT_SUBREDDITS


def test_reddit_combines_market_terms_into_one_query():
    terms = build_india_search_terms(
        "SBIN.NS",
        {"company_name": "State Bank of India"},
    )
    assert reddit._build_search_query(terms) == (
        'SBIN OR SBI OR "State Bank of India" OR "SBIN NSE"'
    )


def test_fetch_reddit_posts_uses_one_query_across_india_sources(monkeypatch):
    calls = []

    def fake_fetch(query, sub, limit, timeout):
        calls.append((query, sub, limit, timeout))
        return []

    monkeypatch.setattr(reddit, "_fetch_subreddit", fake_fetch)
    monkeypatch.setattr(reddit.time, "sleep", lambda _seconds: None)

    terms = build_india_search_terms(
        "SBIN.NS",
        {"company_name": "State Bank of India"},
    )
    result = reddit.fetch_reddit_posts(
        "SBIN.NS",
        search_terms=terms,
        inter_request_delay=0,
    )

    expected_query = 'SBIN OR SBI OR "State Bank of India" OR "SBIN NSE"'
    assert [sub for _query, sub, _limit, _timeout in calls] == list(reddit.INDIA_SUBREDDITS)
    assert all(query == expected_query for query, _sub, _limit, _timeout in calls)
    assert "State Bank of India" in result
