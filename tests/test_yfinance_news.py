from types import SimpleNamespace

from tradingagents.dataflows import yfinance_news


def test_global_news_excludes_out_of_window_and_marks_undated_historical_articles(monkeypatch):
    articles = [
        {
            "content": {
                "title": "In-window macro article",
                "summary": "Relevant historical macro context.",
                "provider": {"displayName": "Source A"},
                "canonicalUrl": {"url": "https://example.com/in-window"},
                "pubDate": "2024-01-08T12:00:00Z",
            }
        },
        {
            "content": {
                "title": "Too old macro article",
                "provider": {"displayName": "Source B"},
                "pubDate": "2023-12-01T12:00:00Z",
            }
        },
        {
            "content": {
                "title": "Future macro article",
                "provider": {"displayName": "Source C"},
                "pubDate": "2024-02-01T12:00:00Z",
            }
        },
        {
            "title": "Undated macro article",
            "publisher": "Source D",
            "link": "https://example.com/undated",
        },
    ]

    monkeypatch.setattr(yfinance_news, "yf_retry", lambda func: func())
    monkeypatch.setattr(
        yfinance_news.yf,
        "Search",
        lambda **_: SimpleNamespace(news=articles),
    )

    result = yfinance_news.get_global_news_yfinance(
        curr_date="2024-01-10",
        look_back_days=7,
        limit=10,
    )

    assert "In-window macro article" in result
    assert "Too old macro article" not in result
    assert "Future macro article" not in result
    assert "Undated macro article" not in result
    assert "1 undated article excluded from historical analysis" in result


def test_global_news_applies_limit_after_historical_filtering(monkeypatch):
    articles = [
        {
            "content": {
                "title": "Too old first result",
                "provider": {"displayName": "Source A"},
                "pubDate": "2023-12-01T12:00:00Z",
            }
        },
        {
            "content": {
                "title": "Valid second result",
                "summary": "Relevant article should survive filtering.",
                "provider": {"displayName": "Source B"},
                "pubDate": "2024-01-08T12:00:00Z",
            }
        },
    ]

    monkeypatch.setattr(yfinance_news, "yf_retry", lambda func: func())
    monkeypatch.setattr(
        yfinance_news.yf,
        "Search",
        lambda **_: SimpleNamespace(news=articles),
    )

    result = yfinance_news.get_global_news_yfinance(
        curr_date="2024-01-10",
        look_back_days=7,
        limit=1,
    )

    assert "Valid second result" in result
    assert "Too old first result" not in result
