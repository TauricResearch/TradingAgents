"""Tests for the RSS-first Reddit fetcher, its 429 backoff, the opt-in JSON
path's degradation (#862), and chunked-transfer error handling (#1024)."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows import reddit

_SAMPLE_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>NVDA earnings beat, stock pops</title>
    <published>2026-05-20T14:30:00+00:00</published>
    <content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;Great &lt;b&gt;quarter&lt;/b&gt; for NVDA&amp;#39;s datacenter unit.&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt;</content>
  </entry>
  <entry>
    <title>Is NVDA overvalued?</title>
    <published>2026-05-19T09:00:00Z</published>
    <content type="html">&lt;p&gt;Forward P/E discussion&lt;/p&gt;</content>
  </entry>
</feed>
"""


def _resp(read_fn):
    """A minimal context-manager response whose read() runs ``read_fn``."""
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner):
            return read_fn()
    return _Resp()


def _atom_resp():
    return _resp(lambda: _SAMPLE_ATOM.encode("utf-8"))


def _raise(exc):
    def _r():
        raise exc
    return _resp(_r)


@pytest.mark.unit
class TestIsoToTimestamp:
    def test_parses_offset_and_z(self):
        assert reddit._iso_to_timestamp("2026-05-20T14:30:00+00:00") > 0
        assert reddit._iso_to_timestamp("2026-05-19T09:00:00Z") > 0

    def test_none_and_garbage_return_none(self):
        assert reddit._iso_to_timestamp(None) is None
        assert reddit._iso_to_timestamp("not-a-date") is None


@pytest.mark.unit
class TestStripHtml:
    def test_extracts_between_sc_markers_and_unescapes(self):
        raw = "<!-- SC_OFF --><div class=\"md\"><p>Great <b>quarter</b> &amp; more</p></div><!-- SC_ON -->"
        assert reddit._strip_html(raw) == "Great quarter & more"

    def test_empty(self):
        assert reddit._strip_html("") == ""


@pytest.mark.unit
class TestRssParsing:
    def test_parses_atom_entries(self):
        with patch.object(reddit, "urlopen", return_value=_atom_resp()):
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", limit=5, timeout=5.0)
        assert len(posts) == 2
        assert posts[0]["title"] == "NVDA earnings beat, stock pops"
        assert posts[0]["source"] == "rss"
        assert posts[0]["score"] is None
        assert posts[0]["num_comments"] is None
        assert posts[0]["created_utc"] > 0
        assert "datacenter unit" in posts[0]["selftext"]

    def test_malformed_xml_fails_open(self):
        with patch.object(reddit, "urlopen", return_value=_resp(lambda: b"<<not xml>>")):
            assert reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0) == []


@pytest.mark.unit
class TestFetchSubredditIsRssFirst:
    """The default per-subreddit fetch goes straight to RSS — it must not hit
    the WAF-blocked JSON endpoint, which only burned rate-limit budget."""

    def test_delegates_to_rss_without_touching_json(self):
        sentinel = [{"title": "x", "source": "rss", "score": None,
                     "num_comments": None, "created_utc": None, "selftext": ""}]
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=sentinel) as rss, \
             patch.object(reddit, "urlopen",
                          side_effect=AssertionError("JSON endpoint must not be called")):
            out = reddit._fetch_subreddit("NVDA", "stocks", 5, 5.0)
        rss.assert_called_once()
        assert out is sentinel


@pytest.mark.unit
class TestJsonPathFallsBackToRss:
    """The opt-in JSON path still degrades to RSS on a 403 (kept for #862)."""

    def test_403_triggers_rss(self):
        err = HTTPError("url", 403, "Blocked", {}, None)
        rss_posts = [{"title": "x", "source": "rss", "score": None,
                      "num_comments": None, "created_utc": None, "selftext": ""}]
        with patch.object(reddit, "urlopen", side_effect=err), \
             patch.object(reddit, "_fetch_subreddit_rss", return_value=rss_posts) as rss:
            out = reddit._fetch_subreddit_json("NVDA", "stocks", 5, 5.0)
        rss.assert_called_once()
        assert out and out[0]["source"] == "rss"


@pytest.mark.unit
class TestRss429Backoff:
    def test_429_then_success_retries_once(self):
        err = HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, _atom_resp()]) as op, \
             patch.object(reddit.time, "sleep") as slept:
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        assert op.call_count == 2          # original + exactly one retry
        slept.assert_called_once()         # backed off before retrying
        assert len(posts) == 2

    def test_429_twice_gives_up_after_one_retry(self):
        err = HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, err]) as op, \
             patch.object(reddit.time, "sleep"):
            posts = reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        assert op.call_count == 2          # one retry, then gives up cleanly
        assert posts == []

    def test_retry_after_header_is_honoured(self):
        err = HTTPError("url", 429, "Too Many Requests", {"Retry-After": "12"}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, _atom_resp()]), \
             patch.object(reddit.time, "sleep") as slept:
            reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        slept.assert_called_once_with(12.0)


@pytest.mark.unit
class TestChunkedTransferErrorsHandled:
    """IncompleteRead/RemoteDisconnected come from http.client and are NOT
    OSErrors, so they were previously uncaught and crashed the pipeline (#1024)."""

    def test_rss_incomplete_read_degrades_to_empty(self):
        with patch.object(reddit, "urlopen", return_value=_raise(http.client.IncompleteRead(b""))):
            assert reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0) == []

    def test_json_incomplete_read_falls_back_to_rss(self):
        with patch.object(reddit, "urlopen", return_value=_raise(http.client.IncompleteRead(b""))), \
             patch.object(reddit, "_fetch_subreddit_rss", return_value=[]) as rss:
            reddit._fetch_subreddit_json("NVDA", "stocks", 5, 5.0)
        rss.assert_called_once()


@pytest.mark.unit
class TestFormatterHandlesRssPosts:
    def test_rss_posts_omit_fake_counts_and_note_source(self):
        rss_posts = [{
            "title": "NVDA pops", "score": None, "num_comments": None,
            "created_utc": reddit._iso_to_timestamp("2026-05-20T14:30:00Z"),
            "selftext": "great quarter", "source": "rss",
        }]
        with patch.object(reddit, "_fetch_subreddit", return_value=rss_posts):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("stocks",), inter_request_delay=0)
        assert "via RSS feed" in out
        assert "↑" not in out  # no fake score arrow
        assert "NVDA pops" in out
        assert "great quarter" in out

    def test_json_posts_still_show_counts(self):
        json_posts = [{
            "title": "NVDA pops", "score": 1234, "num_comments": 56,
            "created_utc": reddit._iso_to_timestamp("2026-05-20T14:30:00Z"),
            "selftext": "",
        }]
        with patch.object(reddit, "_fetch_subreddit", return_value=json_posts):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("stocks",), inter_request_delay=0)
        assert "1234↑" in out
        assert "56c" in out
        assert "via RSS" not in out


# =========================================================================
# Edge cases imported from test_final_push.py
# =========================================================================


@pytest.mark.unit
class RedditFetchSubredditTests(unittest.TestCase):
    """JSON success path, empty children, and RSS fallback."""

    def test_json_success_path_returns_formatted_posts(self):
        from tradingagents.dataflows.reddit import fetch_reddit_posts

        payload = json.dumps({
            "data": {
                "children": [
                    {"data": {"title": "AAPL is great", "score": 100, "num_comments": 20,
                              "created_utc": 1700000000, "selftext": "Really good quarter"}},
                    {"data": {"title": "Bearish on AAPL", "score": 50, "num_comments": 10,
                              "created_utc": 1700000000, "selftext": ""}},
                ]
            }
        }).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = payload

        with patch("tradingagents.dataflows.reddit.urlopen", return_value=mock_resp), \
             patch("tradingagents.dataflows.reddit.time.gmtime", return_value=(2024, 11, 14, 16, 53, 20, 3, 319, 0)), \
             patch("tradingagents.dataflows.reddit.time.sleep"):
            result = fetch_reddit_posts("AAPL", subreddits=("stocks",), limit_per_sub=5,
                                        inter_request_delay=0)
        self.assertIn("AAPL is great", result)
        self.assertIn("Bearish on AAPL", result)

    def test_json_empty_children_returns_no_posts_message(self):
        from tradingagents.dataflows.reddit import fetch_reddit_posts

        payload = json.dumps({"data": {"children": []}}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.read.return_value = payload

        with patch("tradingagents.dataflows.reddit.urlopen", return_value=mock_resp), \
             patch("tradingagents.dataflows.reddit.time.sleep"):
            result = fetch_reddit_posts("UNKNOWN", subreddits=("stocks",), limit_per_sub=5,
                                        inter_request_delay=0)
        self.assertIn("no Reddit posts found", result)

    def test_json_fallback_to_rss_on_failure(self):
        from tradingagents.dataflows.reddit import fetch_reddit_posts

        with patch("tradingagents.dataflows.reddit._fetch_subreddit_rss") as mock_rss, \
             patch("tradingagents.dataflows.reddit.urlopen") as mock_urlopen, \
             patch("tradingagents.dataflows.reddit.time.sleep"):
            mock_urlopen.side_effect = HTTPError("url", 429, "Too Many Requests", {}, None)
            mock_rss.return_value = [{"title": "From RSS", "score": None, "num_comments": None,
                                        "created_utc": 1700000000, "selftext": "", "source": "rss"}]
            result = fetch_reddit_posts("AAPL", subreddits=("stocks",), limit_per_sub=5,
                                        inter_request_delay=0)
        self.assertIn("From RSS", result)


# =========================================================================
# Reddit edge cases imported from test_llm_and_minor.py
# =========================================================================


@pytest.mark.unit
class TestRedditEdgeCases(unittest.TestCase):

    def test_search_qs(self):
        from tradingagents.dataflows.reddit import _search_qs
        qs = _search_qs("AAPL", 5)
        self.assertIn("q=AAPL", qs)
        self.assertIn("limit=5", qs)
        self.assertIn("sort=new", qs)
        self.assertIn("t=week", qs)

    def test_strip_html_no_sc_markers(self):
        from tradingagents.dataflows.reddit import _strip_html
        raw = "<p>Simple <b>HTML</b> without markers</p>"
        result = _strip_html(raw)
        self.assertEqual(result, "Simple HTML without markers")

    def test_total_posts_zero(self):
        from tradingagents.dataflows.reddit import fetch_reddit_posts
        with patch("tradingagents.dataflows.reddit._fetch_subreddit", return_value=[]):
            result = fetch_reddit_posts("UNKNOWN", subreddits=("stocks",), inter_request_delay=0)
        self.assertIn("no Reddit posts found", result)
        self.assertIn("UNKNOWN", result)

    def test_single_empty_subreddit_returns_total_message(self):
        from tradingagents.dataflows.reddit import fetch_reddit_posts
        with patch("tradingagents.dataflows.reddit._fetch_subreddit", return_value=[]):
            result = fetch_reddit_posts("NVDA", subreddits=("stocks",), inter_request_delay=0, limit_per_sub=5)
        self.assertIn("<no Reddit posts found", result)
