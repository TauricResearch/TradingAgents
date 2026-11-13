"""Tests for the Reddit RSS fetcher: one combined request for the newest posts,
filtered here by mention; its 429 backoff, and chunked-transfer error handling
(#1024)."""

from __future__ import annotations

import html
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


def _byline(user, sub):
    """What Reddit ends every entry of a combined feed with, as it serves it."""
    return (
        f' &#32; submitted by &#32; <a href="https://www.reddit.com/user/{user}"> /u/{user} </a>'
        f' &#32; to &#32; <a href="https://www.reddit.com/r/{sub}/"> r/{sub} </a> <br/>'
        ' <span><a href="https://example.com/story">[link]</a></span> &#32;'
        f' <span><a href="https://www.reddit.com/r/{sub}/comments/abc/story/">[comments]</a></span>'
    )


def _entry(sub, title, published, content):
    return (
        f'<entry><category term="{sub}" label="r/{sub}"/><title>{html.escape(title)}</title>'
        f"<published>{published}</published>"
        f'<content type="html">{html.escape(content)}</content></entry>'
    )


def _post(title, sub, body=""):
    return {"title": title, "created_utc": None, "selftext": body, "subreddit": sub}


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

    def test_a_link_posts_byline_is_not_body_text(self):
        # A link post has no text of its own: the byline is all its entry holds.
        assert reddit._strip_html(_byline("btc-maxi", "CryptoMarkets")) == ""
        thumbnail = '<table> <tr><td> <a href="https://x"> <img src="https://y" alt="t" title="t" /> </a> </td><td>'
        assert reddit._strip_html(thumbnail + _byline("someone", "Bitcoin") + " </td></tr></table>") == ""

    def test_a_byline_that_names_no_subreddit_is_dropped_too(self):
        raw = _byline("someone", "stocks").replace(
            ' &#32; to &#32; <a href="https://www.reddit.com/r/stocks/"> r/stocks </a>', "")
        assert " to " not in raw
        assert reddit._strip_html(raw) == ""


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

    def test_reads_the_listing_of_newest_posts_not_the_search(self):
        # The search feed answers anonymous clients 403; the listing is served.
        with patch.object(reddit, "urlopen", return_value=_atom_resp()) as op:
            reddit._fetch_subreddit_rss("BTC", "Bitcoin+CryptoCurrency", limit=100, timeout=5.0)
        (request,), _ = op.call_args
        assert request.full_url == "https://www.reddit.com/r/Bitcoin+CryptoCurrency/new.rss?limit=100"

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
    """A crypto pair (BTC-USD) barely matches Reddit text; match the base (#1113)."""

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
        posts = [self._post("b", "NVDA FROM B"), self._post("a", "NVDA FROM A")]
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert out.index("r/a") < out.index("FROM A") < out.index("r/b") < out.index("FROM B")

    def test_failed_request_is_unavailable_not_silence(self):
        # #1295: a throttled fetch must not read as "no posts found".
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=None):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert "Reddit unavailable" in out
        assert "no Reddit posts found" not in out

    def test_an_empty_page_is_unavailable_not_silence(self):
        # A listing of live subreddits always has posts, so an empty page was
        # not a look at them.
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=[]):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert "Reddit unavailable: the feed came back empty (r/a, r/b)" in out
        assert "not an absence" in out and "no Reddit posts found" not in out

    def test_a_page_that_never_names_the_ticker_reports_no_posts(self):
        # ...and says how far the page it read goes back.
        with patch.object(reddit, "_fetch_subreddit_rss",
                          return_value=[self._post("a", "Fed day thread")]):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert out == ("<no Reddit posts found mentioning NVDA among the newest 1 across r/a, r/b, "
                       "back to 2026-05-20>")

    def test_so_does_a_window_the_page_reaches_only_partway_into(self):
        # The 15th to the 19th were not read. That is stated, not passed off as
        # silence, and not as a feed that could not be read either.
        with patch.object(reddit, "_fetch_subreddit_rss",
                          return_value=[self._post("a", "Fed day thread")]):
            out = reddit.fetch_reddit_posts(
                "NVDA", subreddits=("a", "b"), start_date="2026-05-15", end_date="2026-05-22",
            )
        assert out == ("<no Reddit posts found mentioning NVDA within 2026-05-15..2026-05-22 "
                       "among the newest 1 across r/a, r/b, back to 2026-05-20>")

    def test_subreddit_with_no_posts_is_listed_when_others_have_some(self):
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=[self._post("a")]):
            out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
        assert ("r/b: <no posts mentioning NVDA among the newest 1 across r/a, r/b, "
                "back to 2026-05-20>") in out


@pytest.mark.unit
def test_posts_from_an_unrequested_or_unnamed_subreddit_are_not_dropped():
    posts = [
        {"title": "NVDA ELSEWHERE", "created_utc": None, "selftext": "", "subreddit": "options"},
        {"title": "NVDA NO LABEL", "created_utc": None, "selftext": "", "subreddit": ""},
    ]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert "ELSEWHERE" in out and "r/options" in out
    assert "NO LABEL" in out


@pytest.mark.unit
def test_each_subreddit_keeps_its_own_quota():
    busy = [_post(f"NVDA A{i}", "a") for i in range(9)]
    quiet = [_post("NVDA B0", "b")]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=busy + quiet):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), limit_per_sub=3)
    assert "A0" in out and "A2" in out and "A3" not in out  # capped per subreddit
    assert "B0" in out                                        # not crowded out


@pytest.mark.unit
def test_an_empty_subreddit_is_reported_against_the_page_that_was_read():
    # The page holds the newest posts of all the subreddits together, so a busy
    # one can fill it: "none from r/b" is a statement about that page, not
    # about r/b's week.
    full = [_post(f"NVDA A{i}", "a") for i in range(reddit._FEED_PAGE)]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=full):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert f"r/b: <no posts mentioning NVDA among the newest {reddit._FEED_PAGE} across r/a, r/b>" in out


def _screen_out(*dropped):
    """A screen that drops posts whose text starts with one of ``dropped``."""
    def screen(texts):
        return [not t.startswith(dropped) for t in texts], "Screened: note"
    return screen


@pytest.mark.unit
def test_screened_out_posts_free_their_subreddit_slots():
    posts = [_post(t, "a", body="on NVDA") for t in ("SPAM1", "SPAM2", "A1", "A2")]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a",), limit_per_sub=2,
                                        screen=_screen_out("SPAM"))
    assert out.startswith("Screened: note")
    assert "A1" in out and "A2" in out and "SPAM" not in out


@pytest.mark.unit
def test_a_subreddit_emptied_by_screening_is_not_called_empty():
    posts = [_post("SPAM", "b", body="on NVDA"), _post("A1", "a", body="on NVDA")]
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        out = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), screen=_screen_out("SPAM"))
    assert "r/b: <no posts about NVDA after screening>" in out


@pytest.mark.unit
def test_an_unavailable_screen_keeps_every_post_and_says_so():
    posts = [_post("A1", "a", body="on NVDA")]

    def unavailable(texts):
        return [True] * len(texts), "<Jev screening unavailable (HTTP 529); posts are unscreened>"

    with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
        screened = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"), screen=unavailable)
        plain = reddit.fetch_reddit_posts("NVDA", subreddits=("a", "b"))
    assert screened == "<Jev screening unavailable (HTTP 529); posts are unscreened>\n\n" + plain


@pytest.mark.unit
@pytest.mark.parametrize("ticker, expected", [
    ("NVDA", ("wallstreetbets", "stocks", "investing")),
    ("BTC-USD", ("Bitcoin", "CryptoCurrency", "CryptoMarkets")),
    ("ETH-USD", ("ethereum", "CryptoCurrency", "CryptoMarkets")),
    ("SOL-USD", ("solana", "CryptoCurrency", "CryptoMarkets")),
    ("DOGE-USD", ("CryptoCurrency", "CryptoMarkets")),
])
def test_a_crypto_ticker_is_searched_in_crypto_communities(ticker, expected):
    assert reddit.subreddits_for(ticker) == expected


@pytest.mark.unit
def test_a_crypto_pair_is_fetched_from_its_communities_in_one_request():
    with patch.object(reddit, "_fetch_subreddit_rss", return_value=[]) as fetch:
        out = reddit.fetch_reddit_posts("ETH-USD")
    fetch.assert_called_once()
    query, subs = fetch.call_args.args[:2]
    assert (query, subs) == ("ETH", "ethereum+CryptoCurrency+CryptoMarkets")
    assert "r/wallstreetbets" not in out


@pytest.mark.unit
class TestListingIsFilteredByMention:
    """A listing returns the newest posts whatever they are about, so which of
    them concern the ticker is decided here and no longer by Reddit's search."""

    def _fetch(self, ticker, posts, **kwargs):
        with patch.object(reddit, "_fetch_subreddit_rss", return_value=posts):
            return reddit.fetch_reddit_posts(ticker, **kwargs)

    def test_a_coins_own_subreddit_is_kept_whole(self):
        out = self._fetch("BTC-USD", [_post("Down 30% and still stacking", "Bitcoin"),
                                      _post("Daily General Discussion", "CryptoCurrency")])
        assert "r/Bitcoin — 1 recent posts:\n" in out and "still stacking" in out
        assert "Daily General Discussion" not in out
        assert ("r/CryptoCurrency: <no posts mentioning BTC among the newest 2 across "
                "r/Bitcoin, r/CryptoCurrency, r/CryptoMarkets>") in out

    def test_another_coins_subreddit_is_not(self):
        # Only the subreddit named after the coin speaks for it unasked.
        out = self._fetch("ETH-USD", [_post("Down 30% and still stacking", "Bitcoin")],
                          subreddits=("Bitcoin", "ethereum"))
        assert out.startswith("<no Reddit posts found mentioning ETH")

    @pytest.mark.parametrize("title", [
        "BTC at 66k", "btc dumping again", "Is $btc done?", "ETH/BTC ratio at lows",
        "Bitcoin under $70K", "bitcoiners, how are we feeling", "BITCOIN!!!",
    ])
    def test_elsewhere_a_coin_is_matched_by_symbol_or_name_in_any_case(self, title):
        out = self._fetch("BTC-USD", [_post(title, "CryptoMarkets")])
        assert f"r/CryptoMarkets — 1 recent posts mentioning BTC:\n  [?] {title}" in out

    @pytest.mark.parametrize("title", [
        "WBTC depeg worries", "Ethereum merge anniversary", "ETF flows turn negative",
        "A take from btc_whale", "Subtle signs of a bottom",
    ])
    def test_elsewhere_a_post_that_does_not_name_the_coin_is_left_out(self, title):
        out = self._fetch("BTC-USD", [_post(title, "CryptoMarkets")])
        assert title not in out
        assert out.startswith("<no Reddit posts found mentioning BTC among the newest 1 across")

    def test_a_mention_in_the_body_counts(self):
        out = self._fetch("SOL-USD", [_post("Why I sold everything", "CryptoCurrency",
                                            body="Rotated it all into solana last night.")])
        assert "Why I sold everything" in out

    @pytest.mark.parametrize("title, kept", [
        ("NOW beats on earnings", True),
        ("$now calls printing", True),
        ("Buy now, think later", False),
        ("SNOW and NOWL both down", False),
    ])
    def test_a_symbol_that_is_also_a_word_is_matched_only_as_written(self, title, kept):
        out = self._fetch("NOW", [_post(title, "stocks")], subreddits=("stocks",))
        assert (title in out) is kept

    def test_a_coin_without_its_own_subreddit_is_matched_as_written(self):
        out = self._fetch("DOGE-USD", [_post("DOGE to a dollar?", "CryptoCurrency"),
                                       _post("such doge, much wow", "CryptoMarkets")])
        assert "DOGE to a dollar?" in out and "such doge" not in out


@pytest.mark.unit
def test_a_combined_listing_from_feed_to_block():
    # As Reddit serves it: a link post in the coin's subreddit, a link post
    # elsewhere whose only "mention" is its author's name, and a text post.
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
        + _entry("Bitcoin", "The time of the year again", "2026-11-13T11:54:00+00:00",
                 _byline("someone", "Bitcoin"))
        + _entry("CryptoCurrency", "Altseason when?", "2026-11-13T10:00:00+00:00",
                 _byline("bitcoin-fan", "CryptoCurrency"))
        + _entry("CryptoMarkets", "Liquidations top $1.3B", "2026-11-12T09:00:00+00:00",
                 '<!-- SC_OFF --><div class="md"><p>BTC low $67,555.</p> </div><!-- SC_ON -->'
                 + _byline("someone-else", "CryptoMarkets"))
        + "</feed>"
    )
    with patch.object(reddit, "urlopen", return_value=_resp(lambda: feed.encode("utf-8"))):
        out = reddit.fetch_reddit_posts("BTC-USD", start_date="2026-11-06", end_date="2026-11-13")
    assert out == (
        "r/Bitcoin — 1 recent posts:\n"
        "  [2026-11-13] The time of the year again\n"
        "\n"
        "r/CryptoCurrency: <no posts mentioning BTC within 2026-11-06..2026-11-13 among the newest 3"
        " across r/Bitcoin, r/CryptoCurrency, r/CryptoMarkets, back to 2026-11-12>\n"
        "\n"
        "r/CryptoMarkets — 1 recent posts mentioning BTC:\n"
        "  [2026-11-12] Liquidations top $1.3B\n"
        "    body excerpt: BTC low $67,555."
    )
