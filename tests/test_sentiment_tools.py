"""Mock-based unit tests for Reddit sentiment and Fear & Greed dataflows."""

import pytest
import requests
from unittest.mock import MagicMock, patch

from tradingagents.dataflows.reddit_sentiment import get_reddit_sentiment
from tradingagents.dataflows.fear_greed import get_fear_greed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_post(post_id, title, score=100, num_comments=50, upvote_ratio=0.9,
               flair=None, created_utc=9_999_999_999):
    return {"kind": "t3", "data": {
        "id": post_id,
        "title": title,
        "score": score,
        "num_comments": num_comments,
        "upvote_ratio": upvote_ratio,
        "link_flair_text": flair,
        "created_utc": created_utc,
    }}


def _search_response(posts):
    return {"data": {"children": posts}}


def _comment_response(comments):
    comment_items = [
        {"kind": "t1", "data": {"author": "user1", "body": c}}
        for c in comments
    ]
    return [
        {"data": {"children": []}},  # post listing (unused)
        {"data": {"children": comment_items}},
    ]


# ---------------------------------------------------------------------------
# Reddit — get_reddit_sentiment
# ---------------------------------------------------------------------------

class TestRedditSentiment:

    def _patch_search(self, posts_by_subreddit):
        """Return a mock requests.get that returns given posts per subreddit."""
        def fake_get(url, params=None, headers=None, timeout=None):
            resp = MagicMock()
            resp.ok = True
            resp.status_code = 200
            resp.encoding = "utf-8"
            subreddit = url.split("/r/")[1].split("/")[0]
            posts = posts_by_subreddit.get(subreddit, [])
            resp.json.return_value = _search_response(posts)
            return resp
        return fake_get

    def test_happy_path_returns_formatted_post(self):
        posts = {"wallstreetbets": [
            _make_post("abc1", "NVDA calls printing today", score=500, num_comments=80, upvote_ratio=0.92)
        ], "stocks": [], "options": []}

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=self._patch_search(posts)), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("NVDA", days=7)

        assert "NVDA" in result
        assert "NVDA calls printing today" in result
        assert "Score: 500" in result
        assert "Comments: 80" in result
        assert "92%" in result

    def test_no_posts_returns_informative_message(self):
        empty = {"wallstreetbets": [], "stocks": [], "options": []}

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=self._patch_search(empty)), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("XYZQ", days=7)

        assert "No Reddit posts found" in result
        assert "XYZQ" in result

    def test_429_skips_subreddit_and_returns_no_posts_message(self):
        """429 from all subreddits → no posts collected → informative message returned."""
        def rate_limited(*args, **kwargs):
            resp = MagicMock()
            resp.ok = False
            resp.status_code = 429
            return resp

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=rate_limited), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("NVDA", days=7)

        assert "No Reddit posts found" in result
        assert "NVDA" in result

    def test_network_error_skips_subreddit_and_returns_no_posts_message(self):
        """Network failure on all subreddits → no posts collected → informative message returned."""
        with patch("tradingagents.dataflows.reddit_sentiment.requests.get",
                   side_effect=requests.RequestException("connection reset")), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("NVDA", days=7)

        assert "No Reddit posts found" in result
        assert "NVDA" in result

    def test_title_filter_removes_off_topic_posts(self):
        """Posts whose title doesn't contain ticker or company name are dropped."""
        posts = {"wallstreetbets": [
            _make_post("abc1", "SanDisk joins QQQ today", score=900),   # off-topic
            _make_post("abc2", "NVDA calls printing today", score=100),  # on-topic
        ], "stocks": [], "options": []}

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=self._patch_search(posts)), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("NVDA", days=7)

        assert "SanDisk" not in result
        assert "NVDA calls printing today" in result

    def test_company_name_keyword_matches_title(self):
        """Posts containing company name but not ticker are included."""
        posts = {"wallstreetbets": [
            _make_post("abc1", "Nvidia GPU demand surging", score=200),
        ], "stocks": [], "options": []}

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=self._patch_search(posts)), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value="Nvidia Corp"):
            result = get_reddit_sentiment("NVDA", days=7)

        assert "Nvidia GPU demand surging" in result

    def test_deduplication_across_subreddits(self):
        """Same post appearing in multiple subreddit results is only shown once."""
        same_post = _make_post("dup1", "NVDA bull case", score=50)
        posts = {
            "wallstreetbets": [same_post],
            "stocks": [same_post],
            "options": [],
        }

        with patch("tradingagents.dataflows.reddit_sentiment.requests.get", side_effect=self._patch_search(posts)), \
             patch("tradingagents.dataflows.reddit_sentiment._get_company_name", return_value=""):
            result = get_reddit_sentiment("NVDA", days=7)

        assert result.count("NVDA bull case") == 1


# ---------------------------------------------------------------------------
# Fear & Greed — get_fear_greed
# ---------------------------------------------------------------------------

class TestFearGreed:

    def _fng_response(self, days):
        import time
        data = []
        for i in range(days):
            ts = int(time.time()) - i * 86400
            data.append({
                "value": str(30 + i),
                "value_classification": "Fear",
                "timestamp": str(ts),
            })
        return {"data": data}

    def test_happy_path_returns_n_entries(self):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.encoding = "utf-8"
        resp.json.return_value = self._fng_response(7)

        with patch("tradingagents.dataflows.fear_greed.requests.get", return_value=resp):
            result = get_fear_greed(7)

        lines = [l for l in result.splitlines() if "Score:" in l]
        assert len(lines) == 7
        assert "Fear" in result
        assert "/100" in result

    def test_single_day_returns_one_entry(self):
        resp = MagicMock()
        resp.ok = True
        resp.status_code = 200
        resp.encoding = "utf-8"
        resp.json.return_value = self._fng_response(1)

        with patch("tradingagents.dataflows.fear_greed.requests.get", return_value=resp):
            result = get_fear_greed(1)

        lines = [l for l in result.splitlines() if "Score:" in l]
        assert len(lines) == 1

    def test_api_failure_returns_empty_string(self):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 500

        with patch("tradingagents.dataflows.fear_greed.requests.get", return_value=resp):
            result = get_fear_greed(7)

        assert result == ""

    def test_network_error_returns_empty_string(self):
        with patch("tradingagents.dataflows.fear_greed.requests.get",
                   side_effect=requests.RequestException("timeout")):
            result = get_fear_greed(7)

        assert result == ""
