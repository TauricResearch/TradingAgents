"""Macro news for a stock outside the US leads with its home market.

The global queries are US-centred (the Fed, the S&P 500), and the searches stop
once the article limit is reached, so a Vietnamese stock's macro report was
filled with US headlines and never reached the State Bank of Vietnam or the dong.
"""

from datetime import datetime, timezone
from unittest import mock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

import tradingagents.dataflows.vendors.yahoo.news as ynews
from tradingagents.agents import tools
from tradingagents.default_config import DEFAULT_CONFIG

CONFIG = {
    "global_news_lookback_days": 7,
    "global_news_article_limit": 10,
    "global_news_queries": ["Federal Reserve", "S&P 500"],
    "global_news_queries_by_suffix": {".VN": ["State Bank of Vietnam", "VN-Index"]},
}


def _searched(monkeypatch, config, **kwargs):
    """The queries the vendor sent to Yahoo, in order."""
    queries = []

    class FakeSearch:
        def __init__(self, query, **_):
            queries.append(query)
            self.news = []

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    monkeypatch.setattr(ynews, "get_config", lambda: config)
    ynews.get_global_news_yfinance("2025-05-09", **kwargs)
    return queries


@pytest.mark.unit
def test_a_vietnamese_stock_searches_its_home_market_first(monkeypatch):
    assert _searched(monkeypatch, CONFIG, ticker="VCB.VN") == [
        "State Bank of Vietnam", "VN-Index", "Federal Reserve", "S&P 500",
    ]


@pytest.mark.unit
@pytest.mark.parametrize("kwargs", [{}, {"ticker": "AAPL"}, {"ticker": "7203.T"}])
def test_other_runs_search_the_global_set_only(monkeypatch, kwargs):
    assert _searched(monkeypatch, CONFIG, **kwargs) == ["Federal Reserve", "S&P 500"]


@pytest.mark.unit
def test_a_config_without_the_suffix_map_still_works(monkeypatch):
    config = {k: v for k, v in CONFIG.items() if k != "global_news_queries_by_suffix"}
    assert _searched(monkeypatch, config, ticker="VCB.VN") == ["Federal Reserve", "S&P 500"]


@pytest.mark.unit
def test_the_default_config_leads_a_vietnamese_run_with_vietnam(monkeypatch):
    queries = _searched(monkeypatch, DEFAULT_CONFIG, ticker="VCB.VN")
    assert "Vietnam" in queries[0]
    assert queries[-len(DEFAULT_CONFIG["global_news_queries"]):] == DEFAULT_CONFIG["global_news_queries"]


@pytest.mark.unit
def test_home_market_news_fills_the_limit_first(monkeypatch):
    published = int(datetime(2025, 5, 8, tzinfo=timezone.utc).timestamp())

    class FakeSearch:
        def __init__(self, query, **_):
            self.news = [{"title": f"{query} story", "publisher": "P", "link": "l",
                          "providerPublishTime": published}]

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    monkeypatch.setattr(ynews, "get_config", lambda: {**CONFIG, "global_news_article_limit": 2})

    out = ynews.get_global_news_yfinance("2025-05-09", ticker="VCB.VN")

    assert "State Bank of Vietnam story" in out and "VN-Index story" in out
    assert "Federal Reserve story" not in out


class _State(MessagesState):
    trade_date: str
    company_of_interest: str


@pytest.mark.unit
def test_the_tool_passes_the_run_ticker_to_the_vendor():
    graph = StateGraph(_State)
    graph.add_node("tools", ToolNode([tools.get_global_news]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    call = {"name": "get_global_news", "args": {"curr_date": "2026-08-14"}, "id": "1"}

    with mock.patch.object(tools, "route_to_vendor", return_value="ok") as routed:
        graph.compile().invoke({
            "messages": [AIMessage("", tool_calls=[call])],
            "trade_date": "2026-08-14",
            "company_of_interest": "VCB.VN",
        })

    assert routed.call_args.args == ("get_global_news", "2026-08-14", None, None, "VCB.VN")


@pytest.mark.unit
def test_the_ticker_is_hidden_from_the_model():
    schema = tools.get_global_news.tool_call_schema.model_json_schema()
    assert "ticker" not in schema["properties"]


@pytest.mark.unit
def test_alpha_vantage_accepts_the_ticker(monkeypatch):
    """The vendor chain passes the same arguments to every vendor in it."""
    from tradingagents.dataflows.vendors.alpha_vantage import news as av_news

    monkeypatch.setattr(av_news, "_make_api_request", lambda fn, params: "{}")
    assert av_news.get_global_news("2026-08-14", 7, 5, "VCB.VN") == "{}"
