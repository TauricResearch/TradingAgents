import json
from unittest.mock import MagicMock

import pytest

import tradingagents.agents.analysts.sentiment_analyst as sentiment
import tradingagents.dataflows.alpha_vantage_fundamentals as fundamentals
import tradingagents.dataflows.alpha_vantage_news as news
from tradingagents.agents.schemas import SentimentBand, SentimentReport


@pytest.mark.unit
def test_alpha_vantage_news_filters_future_and_undated_historical_items(monkeypatch):
    payload = json.dumps({
        "feed": [
            {"title": "inside", "time_published": "20240105T120000"},
            {"title": "future", "time_published": "20240201T120000"},
            {"title": "undated"},
        ]
    })
    monkeypatch.setattr(news, "_make_api_request", lambda *args, **kwargs: payload)
    parsed = json.loads(news.get_news("AAPL", "2024-01-01", "2024-01-10"))
    assert [item["title"] for item in parsed["feed"]] == ["inside"]


@pytest.mark.unit
def test_financial_filter_uses_reported_date_and_drops_undated(monkeypatch):
    payload = json.dumps({
        "quarterlyReports": [
            {
                "fiscalDateEnding": "2023-09-30",
                "reportedDate": "2024-02-01",
                "value": "future disclosure",
            },
            {
                "fiscalDateEnding": "2023-06-30",
                "reportedDate": "2023-08-01",
                "value": "available",
            },
            {"value": "undated"},
        ]
    })
    monkeypatch.setattr(fundamentals, "_make_api_request", lambda *args, **kwargs: payload)
    parsed = json.loads(
        fundamentals.get_income_statement("AAPL", curr_date="2024-01-01")
    )
    assert [item["value"] for item in parsed["quarterlyReports"]] == ["available"]


@pytest.mark.unit
def test_historical_sentiment_does_not_fetch_live_social_sources(monkeypatch):
    monkeypatch.setattr(sentiment.get_news, "func", lambda *args: "historical news")
    stocktwits = MagicMock(side_effect=AssertionError("must not fetch live StockTwits"))
    reddit = MagicMock(side_effect=AssertionError("must not fetch live Reddit"))
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", stocktwits)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", reddit)

    structured = MagicMock()
    structured.invoke.return_value = SentimentReport(
        overall_band=SentimentBand.NEUTRAL,
        overall_score=5.0,
        confidence="low",
        narrative="Live social snapshots were excluded.",
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2020-01-10",
        "asset_type": "stock",
        "messages": [],
    }
    sentiment.create_sentiment_analyst(llm)(state)
    stocktwits.assert_not_called()
    reddit.assert_not_called()
    prompt = str(structured.invoke.call_args.args[0])
    assert "live snapshot only" in prompt
    assert "cutoff 2020-01-10" in prompt
