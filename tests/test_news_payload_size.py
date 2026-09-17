"""News payload size and shape.

Regressions for #291: the Alpha Vantage vendor returned the raw
``NEWS_SENTIMENT`` document — banner images, author lists, topic arrays and a
sentiment entry per mentioned ticker — straight into an analyst's context, and
no vendor bounded an article summary. Also covers the ``None`` arguments the
``get_global_news`` tool wrapper forwards when the agent omits them, which used
to reach ``timedelta`` and raise.
"""
import json

import pytest

import tradingagents.dataflows.alpha_vantage_news as avn
import tradingagents.dataflows.yfinance_news as ynews
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.news_format import trim_summary


def _article(**overrides):
    """A NEWS_SENTIMENT entry with the fields the endpoint really sends."""
    article = {
        "title": "Chipmaker beats on data-center revenue",
        "url": "https://example.com/story",
        "time_published": "20250115T093000",
        "authors": ["A. Reporter", "B. Byline"],
        "summary": "Revenue rose sharply. " * 100,
        "banner_image": "https://example.com/huge-banner.png",
        "source": "Example Wire",
        "category_within_source": "n/a",
        "source_domain": "example.com",
        "topics": [
            {"topic": "Technology", "relevance_score": "0.5"},
            {"topic": "Earnings", "relevance_score": "0.9"},
        ],
        "overall_sentiment_score": 0.31,
        "overall_sentiment_label": "Somewhat-Bullish",
        "ticker_sentiment": [
            {
                "ticker": "NVDA",
                "relevance_score": "0.92",
                "ticker_sentiment_score": "0.44",
                "ticker_sentiment_label": "Bullish",
            },
            {
                "ticker": "AMD",
                "relevance_score": "0.11",
                "ticker_sentiment_score": "0.02",
                "ticker_sentiment_label": "Neutral",
            },
        ],
    }
    article.update(overrides)
    return article


def _feed(count=1, **overrides):
    return json.dumps({"items": str(count), "feed": [_article(**overrides) for _ in range(count)]})


def _patch_request(monkeypatch, body, capture=None):
    def fake_request(function_name, params):
        if capture is not None:
            capture.update(params)
        return body
    monkeypatch.setattr(avn, "_make_api_request", fake_request)


@pytest.mark.unit
def test_av_news_drops_the_fields_no_agent_reads(monkeypatch):
    _patch_request(monkeypatch, _feed())
    out = avn.get_news("NVDA", "2025-01-10", "2025-01-16")

    assert "Chipmaker beats on data-center revenue" in out
    assert "Example Wire" in out
    assert "2025-01-15" in out
    assert "https://example.com/story" in out
    # The bulk that made a single call dominate the context (#291).
    for noise in ("banner_image", "huge-banner", "A. Reporter", "category_within_source",
                  "source_domain", "relevance_score", "overall_sentiment_score"):
        assert noise not in out


@pytest.mark.unit
def test_av_news_keeps_only_the_requested_ticker_sentiment(monkeypatch):
    _patch_request(monkeypatch, _feed())
    out = avn.get_news("NVDA", "2025-01-10", "2025-01-16")

    assert "overall Somewhat-Bullish" in out
    assert "NVDA Bullish" in out
    # A market-wide story scores every ticker it mentions; the others are noise.
    assert "AMD" not in out


@pytest.mark.unit
def test_av_news_is_smaller_than_the_raw_payload(monkeypatch):
    raw = _feed(count=5)
    _patch_request(monkeypatch, raw)
    out = avn.get_news("NVDA", "2025-01-10", "2025-01-16")
    assert len(out) < len(raw) / 2


@pytest.mark.unit
def test_av_news_honours_the_article_limit(monkeypatch):
    captured = {}
    _patch_request(monkeypatch, _feed(count=30), captured)
    set_config({"news_article_limit": 3})

    out = avn.get_news("NVDA", "2025-01-10", "2025-01-16")

    # Requested from the endpoint rather than downloaded and discarded...
    assert captured["limit"] == "3"
    # ...and enforced locally, since the endpoint's count is advisory.
    assert out.count("### ") == 3


@pytest.mark.unit
def test_av_news_empty_feed_is_informative(monkeypatch):
    _patch_request(monkeypatch, json.dumps({"items": "0", "feed": []}))
    out = avn.get_news("NVDA", "2025-01-10", "2025-01-16")
    assert out == "No news found for NVDA between 2025-01-10 and 2025-01-16"


@pytest.mark.unit
def test_av_news_passes_unrecognised_bodies_through(monkeypatch):
    """A notice or an unknown shape must not be flattened into an empty report."""
    notice = '{"Information": "Thank you for using Alpha Vantage!"}'
    _patch_request(monkeypatch, notice)
    assert avn.get_news("NVDA", "2025-01-10", "2025-01-16") == notice

    _patch_request(monkeypatch, "not json at all")
    assert avn.get_news("NVDA", "2025-01-10", "2025-01-16") == "not json at all"


@pytest.mark.unit
def test_av_global_news_accepts_the_omitted_arguments(monkeypatch):
    """The tool wrapper forwards omitted arguments as None (used to raise)."""
    captured = {}
    _patch_request(monkeypatch, _feed(count=2), captured)
    set_config({"global_news_lookback_days": 5, "global_news_article_limit": 2})

    out = avn.get_global_news("2025-05-09", None, None)

    assert "Global Market News, from 2025-05-04 to 2025-05-09" in out
    assert captured["limit"] == "2"


@pytest.mark.unit
def test_av_global_news_explicit_arguments_still_win(monkeypatch):
    captured = {}
    _patch_request(monkeypatch, _feed(count=2), captured)
    set_config({"global_news_lookback_days": 5, "global_news_article_limit": 2})

    out = avn.get_global_news("2025-05-09", look_back_days=1, limit=1)

    assert "from 2025-05-08 to 2025-05-09" in out
    assert captured["limit"] == "1"
    assert out.count("### ") == 1


@pytest.mark.unit
def test_summary_is_trimmed_on_a_word_boundary():
    set_config({"news_article_max_chars": 40})
    trimmed = trim_summary("Revenue rose sharply across every reporting segment this quarter")

    assert trimmed.endswith("...")
    assert len(trimmed) <= 43
    # Cut between words, never mid-word.
    assert not trimmed.removesuffix("...").endswith(" ")
    assert "segmen..." not in trimmed


@pytest.mark.unit
def test_summary_trim_collapses_whitespace_and_can_be_disabled():
    set_config({"news_article_max_chars": 0})
    assert trim_summary("one\n\n  two   three") == "one two three"

    set_config({"news_article_max_chars": 5000})
    long_text = "word " * 400
    assert trim_summary(long_text) == long_text.strip()


@pytest.mark.unit
def test_yfinance_news_trims_article_summaries(monkeypatch):
    set_config({"news_article_max_chars": 50, "news_article_limit": 5})

    class _FakeTicker:
        def __init__(self, symbol):
            pass

        def get_news(self, count):
            return [{
                "title": "Headline",
                "summary": "Sentence about the quarter. " * 50,
                "publisher": "Example Wire",
                "link": "https://example.com/story",
                "providerPublishTime": 1736899200,  # 2025-01-15 UTC
            }]

    monkeypatch.setattr(ynews.yf, "Ticker", _FakeTicker)
    out = ynews.get_news_yfinance("NVDA", "2025-01-10", "2025-01-16")

    assert "Headline" in out
    assert "..." in out
    assert len(out) < 400
