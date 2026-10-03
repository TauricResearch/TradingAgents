"""Configurable Reddit communities for the Sentiment Analyst (#1461)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import tradingagents.agents.analysts.sentiment_analyst as sentiment
from tradingagents.dataflows.vendors import reddit
from tradingagents.dataflows.vendors.reddit import parse_subreddits, resolve_reddit_subreddits


@pytest.mark.unit
def test_parse_strips_r_prefix_and_dedupes():
    assert parse_subreddits("r/CryptoCurrency, ethtrader, CryptoCurrency") == [
        "CryptoCurrency", "ethtrader",
    ]
    assert parse_subreddits(("stocks", "r/stocks")) == ["stocks"]


@pytest.mark.unit
def test_parse_rejects_empty_and_path_characters():
    with pytest.raises(ValueError, match="empty"):
        parse_subreddits("  , ")
    with pytest.raises(ValueError, match="invalid"):
        parse_subreddits("../etc")
    with pytest.raises(ValueError, match="invalid"):
        parse_subreddits("stocks?limit=1")


@pytest.mark.unit
def test_resolve_reads_the_run_config(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.dataflows.config.get_config",
        lambda: {"reddit_subreddits": ["CryptoCurrency", "ethtrader"]},
    )
    assert resolve_reddit_subreddits() == ["CryptoCurrency", "ethtrader"]
    assert resolve_reddit_subreddits(("stocks",)) == ["stocks"]


@pytest.mark.unit
def test_fetch_without_an_explicit_list_uses_config(monkeypatch):
    monkeypatch.setattr(
        reddit, "resolve_reddit_subreddits", lambda subs=None: ["CryptoCurrency"]
    )
    seen = {}

    def record(ticker, sub, *a, **k):
        seen["sub"] = sub
        return []

    monkeypatch.setattr(reddit, "_fetch_subreddit_rss", record)
    out = reddit.fetch_reddit_posts("ETH-USD")
    assert seen["sub"] == "CryptoCurrency"
    assert "r/CryptoCurrency" in out


@pytest.mark.unit
def test_sentiment_prompt_and_fetch_use_the_same_list(monkeypatch):
    from tradingagents.agents.schemas import SentimentBand, SentimentReport

    monkeypatch.setattr(
        sentiment, "resolve_reddit_subreddits", lambda subs=None: ["CryptoCurrency", "ethtrader"]
    )
    captured_fetch = {}

    def fake_reddit(ticker, subreddits=None, **k):
        captured_fetch["subreddits"] = list(subreddits)
        return "rd"

    monkeypatch.setattr(sentiment, "fetch_reddit_posts", fake_reddit)
    monkeypatch.setattr(sentiment, "fetch_stocktwits_messages", lambda *a, **k: "st")
    monkeypatch.setattr(sentiment.get_news, "func", lambda *a, **k: "news", raising=False)

    structured = MagicMock()
    captured = {}

    def invoke(prompt):
        captured["prompt"] = prompt
        return SentimentReport(
            overall_band=SentimentBand.NEUTRAL, overall_score=5.0,
            confidence="low", narrative="n",
        )

    structured.invoke.side_effect = invoke
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    sentiment.create_sentiment_analyst(llm)({
        "company_of_interest": "ETH-USD", "trade_date": "2026-01-15",
        "asset_type": "crypto", "messages": [],
    })

    text = "\n".join(
        m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
        for m in captured["prompt"]
    )
    assert captured_fetch["subreddits"] == ["CryptoCurrency", "ethtrader"]
    assert "r/CryptoCurrency, r/ethtrader" in text
    assert "r/wallstreetbets" not in text


@pytest.mark.unit
def test_default_prompt_still_names_the_three_finance_subs():
    blurb = sentiment._reddit_source_blurb(["wallstreetbets", "stocks", "investing"])
    assert "r/wallstreetbets, r/stocks, r/investing" in blurb
    assert "contrarian/exuberant" in blurb
