"""Tests for the Reddit RSS fetcher: one combined request, its 429 backoff, and
chunked-transfer error handling (#1024)."""

from __future__ import annotations

import http.client
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from tradingagents.dataflows.vendors import reddit

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

        def read(self_inner, size=-1):
            data = read_fn()
            return data if size is None or size < 0 else data[:size]
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
        assert posts[0]["created_utc"] > 0
        assert "datacenter unit" in posts[0]["selftext"]
        assert posts[0]["subreddit"] == "stocks"

    def test_malformed_xml_reports_unavailable(self):
        with patch.object(reddit, "urlopen", return_value=_resp(lambda: b"<<not xml>>")):
            assert reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0) is None


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
        assert posts is None

    def test_retry_after_header_is_honoured(self):
        err = HTTPError("url", 429, "Too Many Requests", {"Retry-After": "12"}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, _atom_resp()]), \
             patch.object(reddit.time, "sleep") as slept:
            reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        slept.assert_called_once_with(12.0)

    def test_retry_after_zero_is_honoured_not_treated_as_absent(self):
        # A valid "Retry-After: 0" means retry at once; it must not fall through
        # to the fallback wait (the earlier `or 5.0` bug turned 0 into 5s).
        err = HTTPError("url", 429, "Too Many Requests", {"Retry-After": "0"}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, _atom_resp()]), \
             patch.object(reddit.time, "sleep") as slept:
            reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        slept.assert_called_once_with(0.0)

    def test_headerless_429_fallback_is_jittered(self):
        # No Retry-After -> our own ~5s fallback, jittered so concurrent runs
        # don't retry in lockstep (kept within a tight band).
        err = HTTPError("url", 429, "Too Many Requests", {}, None)
        with patch.object(reddit, "urlopen", side_effect=[err, _atom_resp()]), \
             patch.object(reddit.time, "sleep") as slept:
            reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0)
        slept.assert_called_once()
        (wait,), _ = slept.call_args
        assert 48.0 <= wait <= 72.0  # 60s +/-20% jitter


@pytest.mark.unit
class TestChunkedTransferErrorsHandled:
    """IncompleteRead/RemoteDisconnected come from http.client and are NOT
    OSErrors, so they were previously uncaught and crashed the pipeline (#1024)."""

    def test_rss_incomplete_read_reports_unavailable(self):
        with patch.object(reddit, "urlopen", return_value=_raise(http.client.IncompleteRead(b""))):
            assert reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0) is None

    def test_oversized_rss_feed_is_refused_not_parsed(self):
        # A hostile/misbehaving endpoint streaming an unbounded body must not be
        # read into memory before parsing; overflow degrades to an empty feed.
        big = _resp(lambda: b"x" * 100)
        with patch.object(reddit, "_MAX_FEED_BYTES", 10), \
             patch.object(reddit, "urlopen", return_value=big):
            assert reddit._fetch_subreddit_rss("NVDA", "stocks", 5, 5.0) is None


@pytest.mark.unit
class TestFormatterHandlesRssPosts:
    def test_rss_posts_omit_fake_counts_and_note_source(self):
        rss_posts = [{
            "title": "NVDA pops", "score": None, "num_comments": None,
            "created_utc": reddit._iso_to_timestamp("2026-05-20T14:30:00Z"),
            "selftext": "great quarter", "source": "rss",
        }]
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=rss_posts):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("stocks",))
        assert "↑" not in out  # RSS has no scores; none are invented
        assert "NVDA pops" in out
        assert "great quarter" in out


@pytest.mark.unit
class TestCryptoSearchTerm:
    """A crypto pair (BTC-USD) barely matches Reddit text; search the base (#1113)."""

    def _captured_ticker(self, ticker):
        seen = {}

        def fake_fetch(t, subs, limit, timeout, **kwargs):
            seen["ticker"] = t
            return []

        with patch.object(reddit, "_fetch_subreddit_rss", side_effect=fake_fetch):
            reddit.fetch_reddit_posts(ticker, subreddits=("stocks",))
        return seen["ticker"]

    def test_crypto_pair_searches_base(self):
        assert self._captured_ticker("BTC-USD") == "BTC"

    def test_equity_passes_through(self):
        assert self._captured_ticker("NVDA") == "NVDA"


@pytest.mark.unit
class TestOneRequestForAllSubreddits:
    """Reddit's anonymous RSS allows about one request per minute per IP, so a
    request per subreddit spent a back-off on nearly every run. One combined
    feed (``r/a+b+c``) carries each entry's subreddit, so nothing is lost."""

    def _post(self, sub, title="NVDA pops"):
        return {"title": title, "score": None, "num_comments": None,
                "created_utc": reddit._iso_to_timestamp("2026-05-20T14:30:00Z"),
                "selftext": "", "source": "rss", "subreddit": sub}

    def test_all_subreddits_share_one_request(self):
        calls = []

        def record(t, subs, limit, timeout):
            calls.append((subs, limit))
            return []

        with patch.object(reddit, "_fetch_subreddit_rss", side_effect=record):
            reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b", "c"), limit_per_sub=5)
        # One full page, so a busy subreddit cannot crowd the others out.
        assert calls == [("a+b+c", reddit._FEED_PAGE)]

    def test_posts_are_grouped_back_by_subreddit(self):
        posts = [self._post("b", "FROM B"), self._post("a", "FROM A")]
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert out.index("r/a") < out.index("FROM A") < out.index("r/b") < out.index("FROM B")

    def test_failed_request_is_unavailable_not_silence(self):
        # #1295: a throttled fetch must not read as "no posts found".
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=None):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert "Reddit unavailable" in out
        assert "no Reddit posts found" not in out

    def test_genuine_empty_still_reports_no_posts(self):
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=[]):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert "no Reddit posts found" in out
        assert "unavailable" not in out

    def test_subreddit_with_no_posts_is_listed_when_others_have_some(self):
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=[self._post("a")]):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert "r/b: <no posts found" in out


@pytest.mark.unit
def test_posts_from_an_unrequested_or_unnamed_subreddit_are_not_dropped():
    posts = [
        {"title": "ELSEWHERE", "created_utc": None, "selftext": "", "subreddit": "options"},
        {"title": "NO LABEL", "created_utc": None, "selftext": "", "subreddit": ""},
    ]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert "ELSEWHERE" in out and "r/options" in out
    assert "NO LABEL" in out


@pytest.mark.unit
def test_each_subreddit_keeps_its_own_quota():
    busy = [{"title": f"A{i}", "created_utc": None, "selftext": "", "subreddit": "a"} for i in range(9)]
    quiet = [{"title": "B0", "created_utc": None, "selftext": "", "subreddit": "b"}]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=busy + quiet):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), limit_per_sub=3)
    assert "A0" in out and "A2" in out and "A3" not in out  # capped per subreddit
    assert "B0" in out                                        # not crowded out


@pytest.mark.unit
def test_empty_subreddit_on_a_full_page_is_not_called_empty():
    # A full page may have cut a quieter subreddit's posts off, so its absence
    # from the page is not evidence of no posts.
    full = [{"title": f"A{i}", "created_utc": None, "selftext": "", "subreddit": "a"}
            for i in range(reddit._FEED_PAGE)]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=full):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert "r/b: <no posts found" not in out
    assert f"newest {reddit._FEED_PAGE}" in out


def _screen_out(*dropped):
    """A screen that drops posts whose text starts with one of ``dropped``."""
    def screen(texts):
        return [not t.startswith(dropped) for t in texts], "Screened: note"
    return screen


@pytest.mark.unit
def test_screened_out_posts_free_their_subreddit_slots():
    posts = [{"title": t, "created_utc": None, "selftext": "", "subreddit": "a"}
             for t in ("SPAM1", "SPAM2", "A1", "A2")]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a",), limit_per_sub=2,
                                        screen=_screen_out("SPAM"))
    assert out.startswith("Screened: note")
    assert "A1" in out and "A2" in out and "SPAM" not in out


@pytest.mark.unit
def test_a_subreddit_emptied_by_screening_is_not_called_empty():
    posts = [{"title": "SPAM", "created_utc": None, "selftext": "", "subreddit": "b"},
             {"title": "A1", "created_utc": None, "selftext": "", "subreddit": "a"}]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), screen=_screen_out("SPAM"))
    assert "r/b: <no posts about NVDA after screening>" in out


@pytest.mark.unit
def test_an_unavailable_screen_keeps_every_post_and_says_so():
    posts = [{"title": "A1", "created_utc": None, "selftext": "", "subreddit": "a"}]

    def unavailable(texts):
        return [True] * len(texts), "<Jev screening unavailable (HTTP 529); posts are unscreened>"

    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        screened = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), screen=unavailable)
        plain = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert screened == "<Jev screening unavailable (HTTP 529); posts are unscreened>\n\n" + plain
