"""Tests for news relevance marking and company-name-anchored queries."""

import pytest

from tradingagents.dataflows.interface import (
    _is_relevant_news_item,
    _mark_news_relevance,
)
from tradingagents.dataflows.target_context import (
    clear_target_ticker,
    set_target_ticker,
)
from tradingagents.dataflows.tavily_news import _build_company_news_query
from tradingagents.default_config import DEFAULT_CONFIG


@pytest.fixture(autouse=True)
def _clean_target():
    clear_target_ticker()
    yield
    clear_target_ticker()


def _item(title="", content=""):
    return {"title": title, "content": content, "source": "tavily"}


# ---------------------------------------------------------------------------
# _is_relevant_news_item - recall-first matching
# ---------------------------------------------------------------------------


def test_relevant_by_a_share_plain_ticker():
    assert _is_relevant_news_item(
        _item("茅台业绩超预期", "代码 600519"), "600519.SH", "贵州茅台"
    )


def test_relevant_by_a_share_suffixed_ticker():
    assert _is_relevant_news_item(_item("600519.SH 涨停", ""), "600519.SH", "贵州茅台")


def test_relevant_by_company_name():
    assert _is_relevant_news_item(
        _item("贵州茅台发布年报", "白酒龙头"), "600519.SH", "贵州茅台"
    )


def test_relevant_by_us_ticker():
    assert _is_relevant_news_item(
        _item("AAPL hits new high", "Apple revenue beat"), "AAPL", "Apple Inc."
    )


def test_relevant_by_us_company_name():
    assert _is_relevant_news_item(
        _item("Apple announces buyback", "Cupertino"), "AAPL", "Apple Inc."
    )


def test_irrelevant_item_not_matched():
    assert not _is_relevant_news_item(
        _item("五粮液业绩大增", "浓香白酒龙头"), "600519.SH", "贵州茅台"
    )


def test_empty_body_treated_as_relevant():
    """Recall-first: an item with no parseable body is not penalized."""
    assert _is_relevant_news_item(_item("", ""), "600519.SH", "贵州茅台")


def test_a_share_ticker_forms_all_match():
    """600519 / 600519.SH / 600519.SS all refer to the same instrument."""
    for target in ("600519.SH", "600519.SS", "600519"):
        assert _is_relevant_news_item(_item("600519", ""), target, None)


def test_us_ticker_case_insensitive():
    assert _is_relevant_news_item(_item("aapl dividend", ""), "AAPL", None)


# ---------------------------------------------------------------------------
# _mark_news_relevance
# ---------------------------------------------------------------------------


def test_mark_relevance_no_target_is_noop():
    items = [_item("无关新闻", "")]
    assert _mark_news_relevance(items) == 0
    assert "relevance" not in items[0]


def test_mark_relevance_mixed():
    set_target_ticker("600519.SH", company_name="贵州茅台")
    items = [
        _item("茅台业绩", ""),
        _item("五粮液大涨", ""),
        _item("600519 公告", ""),
    ]
    low = _mark_news_relevance(items)
    assert low == 1
    assert items[0]["relevance"] == "high"
    assert items[1]["relevance"] == "low"
    assert items[2]["relevance"] == "high"


# ---------------------------------------------------------------------------
# _build_company_news_query - company name anchoring
# ---------------------------------------------------------------------------


def test_build_query_a_share_with_company_name():
    set_target_ticker("600519.SH", company_name="贵州茅台")
    query = _build_company_news_query("600519.SH", DEFAULT_CONFIG)
    assert "贵州茅台" in query
    assert "600519" in query


def test_build_query_us_with_company_name():
    set_target_ticker("AAPL", company_name="Apple Inc.")
    query = _build_company_news_query("AAPL", DEFAULT_CONFIG)
    assert "Apple Inc." in query
    assert "AAPL" in query


def test_build_query_without_company_name_cleans_empty_quotes():
    """When company name is unavailable, empty quoted placeholders are removed."""
    cfg = {
        "tavily_a_share_news_query_template": (
            '"{ticker}" "{plain_ticker}" "{company_name}" 股票 新闻'
        )
    }
    query = _build_company_news_query("600519.SH", cfg)
    assert '""' not in query
    assert "600519" in query
