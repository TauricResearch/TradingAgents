"""Sentiment analysis must not inject current social posts into backtests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import tradingagents.agents.analysts.sentiment_analyst as sentiment
from tradingagents.agents.schemas import SentimentBand, SentimentReport


def _capturing_llm(captured: dict):
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (
        captured.__setitem__("prompt", prompt)
        or SentimentReport(
            overall_band=SentimentBand.NEUTRAL,
            overall_score=5.0,
            confidence="low",
            narrative="Historical social data is unavailable.",
        )
    )
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _run(captured: dict, trade_date: str):
    return sentiment.create_sentiment_analyst(_capturing_llm(captured))(
        {
            "company_of_interest": "NVDA",
            "trade_date": trade_date,
            "asset_type": "stock",
            "messages": [],
        }
    )


def _prompt_text(prompt) -> str:
    return "\n".join(str(getattr(message, "content", message)) for message in prompt)


@pytest.mark.unit
def test_historical_run_omits_current_social_sources(monkeypatch):
    monkeypatch.setattr(sentiment.get_news, "func", lambda *args, **kwargs: "historical news")

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("current social data must not be fetched for a historical run")

    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", unexpected_fetch)
    monkeypatch.setattr(sentiment, "fetch_reddit_posts", unexpected_fetch)

    captured = {}
    _run(captured, "2020-01-15")

    prompt = _prompt_text(captured["prompt"])
    assert "StockTwits unavailable for historical analysis ending 2020-01-15" in prompt
    assert "Reddit unavailable for historical analysis ending 2020-01-15" in prompt


@pytest.mark.unit
def test_current_run_still_fetches_social_sources(monkeypatch):
    monkeypatch.setattr(sentiment.get_news, "func", lambda *args, **kwargs: "current news")
    monkeypatch.setattr(
        sentiment,
        "fetch_stocktwits_messages",
        lambda *args, **kwargs: "current StockTwits posts",
    )
    monkeypatch.setattr(
        sentiment,
        "fetch_reddit_posts",
        lambda *args, **kwargs: "current Reddit posts",
    )

    captured = {}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _run(captured, today)

    prompt = _prompt_text(captured["prompt"])
    assert "current StockTwits posts" in prompt
    assert "current Reddit posts" in prompt
