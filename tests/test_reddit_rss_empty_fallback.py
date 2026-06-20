from __future__ import annotations

import tradingagents.dataflows.reddit as reddit


def test_fetch_reddit_posts_returns_message_when_all_sources_empty(monkeypatch):
    def fake_fetch_subreddit(ticker, sub, limit, timeout):
        return []

    monkeypatch.setattr(reddit, "_fetch_subreddit", fake_fetch_subreddit)
    monkeypatch.setattr(reddit.time, "sleep", lambda *_args, **_kwargs: None)

    result = reddit.fetch_reddit_posts(
        "ULVR.L",
        subreddits=("stocks", "investing"),
        limit_per_sub=5,
        timeout=1.0,
        inter_request_delay=0.0,
    )

    assert result.strip()
    assert "No Reddit discussion posts were available for ULVR.L" in result
    assert "rate-limited" in result
    assert "temporarily unavailable" in result


def test_fetch_reddit_posts_marks_empty_subreddit_blocks(monkeypatch):
    calls = []

    def fake_fetch_subreddit(ticker, sub, limit, timeout):
        calls.append(sub)
        if sub == "stocks":
            return []
        return [
            {
                "title": "ULVR discussion",
                "score": None,
                "num_comments": None,
                "created_utc": None,
                "selftext": "Some discussion body",
                "source": "rss",
            }
        ]

    monkeypatch.setattr(reddit, "_fetch_subreddit", fake_fetch_subreddit)
    monkeypatch.setattr(reddit.time, "sleep", lambda *_args, **_kwargs: None)

    result = reddit.fetch_reddit_posts(
        "ULVR.L",
        subreddits=("stocks", "investing"),
        limit_per_sub=5,
        timeout=1.0,
        inter_request_delay=0.0,
    )

    assert "r/stocks: no Reddit posts returned for ULVR.L" in result
    assert "r/investing — 1 recent posts mentioning ULVR.L" in result
    assert calls == ["stocks", "investing"]