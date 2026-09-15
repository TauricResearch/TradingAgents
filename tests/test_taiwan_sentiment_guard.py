"""Taiwan tickers must not hit the US-centric retail social feeds, and the
resulting gap must reach the LLM as missing coverage, never as a neutral read.

The behaviour is driven by ``market_profiles[...]["social_sources"]`` (Taiwan
Adapter step 3); the analyst has no market-specific branches of its own.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import pytest

from tradingagents.agents.analysts import sentiment_analyst as sentiment
from tradingagents.agents.schemas import SentimentBand, SentimentReport
from tradingagents.dataflows.market_profiles import (
    DEFAULT_SOCIAL_SOURCES,
    SOCIAL_SOURCE_REDDIT,
    SOCIAL_SOURCE_STOCKTWITS,
    resolve_social_sources,
)
from tradingagents.default_config import DEFAULT_CONFIG

TAIWAN_TICKERS = ("2330.TW", "2454.TW", "3443.TW", "6488.TWO", "5274.TWO")


# --- market config ---------------------------------------------------------

@pytest.mark.unit
class ResolveSocialSourcesTests(unittest.TestCase):
    def test_taiwan_profile_disables_every_social_feed(self):
        self.assertEqual(DEFAULT_CONFIG["market_profiles"]["taiwan"]["social_sources"], [])
        for ticker in TAIWAN_TICKERS + ("2330.tw", "6488.two"):
            with self.subTest(ticker=ticker):
                self.assertEqual(resolve_social_sources(ticker), ())

    def test_default_market_keeps_both_feeds(self):
        for ticker in ("AAPL", "NVDA", "0700.HK", "7203.T"):
            with self.subTest(ticker=ticker):
                sources = resolve_social_sources(ticker)
                self.assertEqual(sources, DEFAULT_SOCIAL_SOURCES)
                self.assertIn(SOCIAL_SOURCE_STOCKTWITS, sources)
                self.assertIn(SOCIAL_SOURCE_REDDIT, sources)

    def test_profile_without_key_keeps_default_and_explicit_list_narrows(self):
        config = {"market_profiles": {
            "tokyo": {"suffixes": [".T"]},
            "hk": {"suffixes": [".HK"], "social_sources": ["Reddit"]},
        }}
        self.assertEqual(resolve_social_sources("7203.T", config), DEFAULT_SOCIAL_SOURCES)
        self.assertEqual(resolve_social_sources("0700.HK", config), ("reddit",))


# --- analyst execution path ------------------------------------------------

def _state(ticker):
    return {"company_of_interest": ticker, "trade_date": "2026-01-15",
            "asset_type": "stock", "messages": []}


def _capturing_llm(captured):
    report = SentimentReport(
        overall_band=SentimentBand.MIXED, overall_score=5.0,
        confidence="low", narrative="n",
    )
    structured = MagicMock()
    structured.invoke.side_effect = lambda prompt: (captured.__setitem__("prompt", prompt) or report)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    return llm


def _prompt_text(messages):
    return "\n".join(str(getattr(m, "content", m)) for m in messages)


@pytest.mark.unit
class TaiwanSentimentGuardTests(unittest.TestCase):
    def setUp(self):
        self.calls = {"news": [], "stocktwits": [], "reddit": []}
        self._patches = []

    def _install(self, target, name, fn):
        self._patches.append((target, name, getattr(target, name)))
        setattr(target, name, fn)

    def tearDown(self):
        for target, name, original in reversed(self._patches):
            setattr(target, name, original)

    def _stub_sources(self):
        def news(ticker, *a, **k):
            self.calls["news"].append(ticker)
            return "news-block"

        def stocktwits(ticker, *a, **k):
            self.calls["stocktwits"].append(ticker)
            return "<no StockTwits messages found for $X>"

        def reddit(ticker, *a, **k):
            self.calls["reddit"].append(ticker)
            return "<no Reddit posts found mentioning X>"

        self._install(sentiment.get_news, "func", news)
        self._install(sentiment, "fetch_stocktwits_messages", stocktwits)
        self._install(sentiment, "fetch_reddit_posts", reddit)

    def _run(self, ticker):
        captured = {}
        sentiment.create_sentiment_analyst(_capturing_llm(captured))(_state(ticker))
        return _prompt_text(captured["prompt"])

    def test_taiwan_ticker_never_queries_social_feeds(self):
        def forbidden(*a, **k):
            pytest.fail(f"social feed queried for a Taiwan ticker: {a} {k}")

        def news(ticker, *a, **k):
            self.calls["news"].append(ticker)
            return "news-block"

        self._install(sentiment.get_news, "func", news)
        self._install(sentiment, "fetch_stocktwits_messages", forbidden)
        self._install(sentiment, "fetch_reddit_posts", forbidden)

        for ticker in ("2330.TW", "6488.TWO"):
            with self.subTest(ticker=ticker):
                self.calls["news"].clear()
                text = self._run(ticker)
                self.assertEqual(self.calls["news"], [ticker])  # Yahoo News still used
                self.assertIn("news-block", text)

    def test_taiwan_placeholder_is_not_enabled_not_empty_not_unavailable(self):
        self._stub_sources()
        for ticker in ("2330.TW", "6488.TWO"):
            with self.subTest(ticker=ticker):
                text = self._run(ticker)
                self.assertEqual(self.calls["stocktwits"], [])
                self.assertEqual(self.calls["reddit"], [])
                self.assertIn("StockTwits not enabled for the taiwan market", text)
                self.assertIn("Reddit not enabled for the taiwan market", text)
                self.assertIn(f"{ticker} was not queried", text)
                # Must not masquerade as "queried but empty" or "queried but failed".
                self.assertNotIn("no StockTwits messages", text)
                self.assertNotIn("no Reddit posts found", text)
                self.assertNotIn("<stocktwits unavailable", text)
                self.assertNotIn("fetch failed", text)

    def test_default_market_behaviour_unchanged(self):
        self._stub_sources()
        text = self._run("AAPL")
        self.assertEqual(self.calls["news"], ["AAPL"])
        self.assertEqual(self.calls["stocktwits"], ["AAPL"])
        self.assertEqual(self.calls["reddit"], ["AAPL"])
        self.assertIn("news-block", text)
        self.assertIn("<no StockTwits messages found for $X>", text)
        self.assertIn("<no Reddit posts found mentioning X>", text)
        self.assertNotIn("not enabled for the", text)  # no placeholder; the prompt rule may mention the phrase


# --- prompt rule -------------------------------------------------------------

@pytest.mark.unit
def test_prompt_rule_missing_coverage_is_not_neutral():
    text = sentiment._build_system_message(
        ticker="2330.TW", start_date="2026-01-08", end_date="2026-01-15",
        news_block="n", stocktwits_block="s", reddit_block="r",
    )
    assert "missing coverage, not a neutral sentiment observation" in text
    assert "Do not infer bullish, bearish, or neutral sentiment from its absence" in text
    assert "lower `confidence` accordingly" in text
    assert "not enabled is missing, not silent" in text


@pytest.mark.unit
def test_not_enabled_placeholder_wording():
    text = sentiment._not_enabled_placeholder("StockTwits", "2330.tw", "taiwan")
    assert text.startswith("<StockTwits not enabled for the taiwan market: 2330.TW was not queried")
    assert "not an absence of posts" in text
    assert "not a neutral signal" in text
