from __future__ import annotations

import pytest


@pytest.mark.unit
def test_alpha_vantage_news_sentiment_normalized_to_markdown():
    from tradingagents.dataflows.alpha_vantage_news import _normalize_news_response

    payload = {
        "feed": [
            {
                "title": "Apple launches product",
                "source": "ExampleWire",
                "time_published": "20240102T120000",
                "summary": "A concise summary.",
                "url": "https://example.com/aapl",
                "overall_sentiment_label": "Bullish",
                "overall_sentiment_score": "0.42",
                "ticker_sentiment": [
                    {"ticker": "AAPL", "ticker_sentiment_label": "Bullish", "ticker_sentiment_score": "0.44"}
                ],
            }
        ]
    }

    out = _normalize_news_response(payload, "AAPL")

    assert out.startswith("## Alpha Vantage News Sentiment: AAPL")
    assert "### Apple launches product (source: ExampleWire)" in out
    assert "Ticker sentiment: AAPL Bullish" in out
    assert '"feed"' not in out
