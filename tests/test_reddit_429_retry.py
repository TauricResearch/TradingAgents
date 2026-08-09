"""Tests for multi-retry 429 handling in the Reddit RSS fetcher (issue #1193).

Reddit rate-limits the RSS fallback too (per-IP). A single retry is not
enough when several subreddits run back-to-back; the fetcher should back
off exponentially (honouring Retry-After when present) and only give up
after a bounded number of attempts, so a transient 429 burst doesn't
blank every subreddit.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tradingagents.dataflows import reddit

_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>NVDA earnings beat</title>
    <published>2026-05-20T14:30:00+00:00</published>
    <content type="html">&lt;p&gt;body&lt;/p&gt;</content>
  </entry>
</feed>
"""


def _resp(data: bytes):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return data
    return _Resp()


def _http_error(code: int, retry_after: str | None = None):
    import email
    from urllib.error import HTTPError

    msg = email.message.Message()
    if retry_after:
        msg["Retry-After"] = retry_after
    return HTTPError("https://reddit.com/r/stocks/search.rss", code, "err", msg, None)


@pytest.mark.unit
class TestMultiRetry429:
    def test_429_then_429_then_success(self):
        """Two 429s followed by a success must still deliver posts."""
        calls = {"n": 0}

        # Patch urlopen to raise 429 twice, then return the Atom feed.
        def fake_urlopen(req, timeout):
            if calls["n"] < 2:
                calls["n"] += 1
                raise _http_error(429)
            calls["n"] += 1
            return _resp(_SAMPLE_ATOM.encode("utf-8"))

        with patch.object(reddit, "urlopen", side_effect=fake_urlopen), patch.object(
            reddit.time, "sleep", return_value=None
        ) as mock_sleep:
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)

        assert len(posts) == 1
        assert posts[0]["title"] == "NVDA earnings beat"
        # Two 429s → two backoff sleeps.
        assert mock_sleep.call_count >= 2

    def test_retry_after_header_drives_first_backoff(self):
        """The first backoff must honour a Retry-After header when present."""
        calls = {"n": 0}

        def fake_urlopen(req, timeout):
            if calls["n"] == 0:
                calls["n"] += 1
                raise _http_error(429, retry_after="7")
            calls["n"] += 1
            return _resp(_SAMPLE_ATOM.encode("utf-8"))

        with patch.object(reddit, "urlopen", side_effect=fake_urlopen), patch.object(
            reddit.time, "sleep", return_value=None
        ) as mock_sleep:
            reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)

        first_sleep = mock_sleep.call_args_list[0].args[0]
        assert first_sleep == 7.0

    def test_persistent_429_gives_up_after_bounded_retries(self):
        """Three 429s must give up and return [] (never raise)."""
        def fake_urlopen(req, timeout):
            raise _http_error(429)

        with patch.object(reddit, "urlopen", side_effect=fake_urlopen), patch.object(
            reddit.time, "sleep", return_value=None
        ) as mock_sleep:
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)

        assert posts == []
        # Bounded: 1 initial attempt + 2 retries = 3 requests, 2 sleeps.
        assert mock_sleep.call_count == 2

    def test_retry_after_cap_respected(self):
        """Retry-After values above the cap must be clamped (never sleep 5 min)."""
        def fake_urlopen(req, timeout):
            raise _http_error(429, retry_after="300")

        with patch.object(reddit, "urlopen", side_effect=fake_urlopen), patch.object(
            reddit.time, "sleep", return_value=None
        ) as mock_sleep:
            reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)

        for call in mock_sleep.call_args_list:
            assert call.args[0] <= 30.0
