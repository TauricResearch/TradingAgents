"""yfinance news must survive a nested article whose publisher fields are null.

Regression for #1458: yfinance can return ``content.provider`` present-but-null
(or ``content.provider.displayName`` present-but-null). ``dict.get`` only falls
back to its default when the key is *absent*, so ``content.get("provider", {})``
handed back ``None`` and the following ``.get`` raised ``AttributeError:
'NoneType' object has no attribute 'get'``.

The exception escapes ``_extract_article_data``, so a single malformed article
aborted the whole ``get_news_yfinance`` call and the router logged the vendor as
failing. A null ``displayName`` is quieter but still renders the publisher as
the literal string "None" in the report.
"""
from datetime import UTC, datetime

import pytest

import tradingagents.dataflows.vendors.yahoo.news as ynews


def _nested(provider_value, title="Soybean futures slide"):
    """A yfinance nested-``content`` article whose ``content.provider`` is
    exactly ``provider_value`` (null, a dict with a null displayName, or a
    healthy dict)."""
    return {
        "content": {
            "title": title,
            "summary": "Chicago soybean futures fell for a third session.",
            "provider": provider_value,
            "canonicalUrl": {"url": "https://example.com/soybean"},
            "pubDate": "2026-09-23T10:00:00Z",
        }
    }


@pytest.mark.unit
def test_null_provider_is_treated_as_missing():
    # #1458: the key exists with a null value, so dict.get's default never
    # applied and the old code crashed on None.get(...).
    data = ynews._extract_article_data(_nested(None))
    assert data["publisher"] == "Unknown"


@pytest.mark.unit
def test_null_display_name_falls_back_to_unknown():
    # A null displayName used to be reported as the literal string "None".
    data = ynews._extract_article_data(_nested({"displayName": None}))
    assert data["publisher"] == "Unknown"


@pytest.mark.unit
def test_null_provider_does_not_fail_the_whole_fetch(monkeypatch):
    # End to end: one malformed article must not lose the healthy ones (#1458).
    class FakeTicker:
        def __init__(self, *a, **k):
            pass

        def get_news(self, count=20):
            return [
                _nested(None, title="NULL PROVIDER"),
                _nested({"displayName": "Reuters"}, title="GOOD ARTICLE"),
            ]

    monkeypatch.setattr(ynews.yf, "Ticker", FakeTicker)
    out = ynews.get_news_yfinance("ZS", "2026-09-20", "2026-09-26")

    assert "GOOD ARTICLE" in out
    assert "NULL PROVIDER" in out       # kept, attributed to Unknown
    assert "(source: None)" not in out  # never render a literal None
    assert "(source: Unknown)" in out


@pytest.mark.unit
def test_healthy_provider_is_unchanged():
    # Guard the success path: normal articles must be read exactly as before.
    data = ynews._extract_article_data(_nested({"displayName": "Bloomberg"}))
    assert data["publisher"] == "Bloomberg"
    assert data["title"] == "Soybean futures slide"
    assert data["link"] == "https://example.com/soybean"
    assert data["pub_date"] == datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
