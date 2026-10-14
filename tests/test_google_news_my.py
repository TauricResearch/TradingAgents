"""Tests for the MY-localized Google News RSS vendor: ticker->name resolution,
RSS parsing, the fetch-failed vs no-results distinction, and point-in-time
window filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from tradingagents.dataflows import google_news_my as gnews

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Maybank completes acquisition of remaining interest in Maybank Ageas</title>
    <link>https://news.google.com/rss/articles/xyz?oc=5</link>
    <pubDate>Mon, 08 Sep 2026 08:00:00 GMT</pubDate>
    <source url="https://thestar.com.my">The Star</source>
  </item>
  <item>
    <title>Maybank wins Best Company at Bursa Malaysia Investor Relations Awards</title>
    <link>https://news.google.com/rss/articles/abc?oc=5</link>
    <pubDate>Tue, 20 Oct 2026 08:00:00 GMT</pubDate>
    <source url="https://maybank.com">Maybank Group</source>
  </item>
</channel></rss>
"""


def _resp(read_fn):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner, size=-1):
            data = read_fn()
            return data if size is None or size < 0 else data[:size]
    return _Resp()


def _rss_resp():
    return _resp(lambda: _SAMPLE_RSS.encode("utf-8"))


def _raise(exc):
    def _r():
        raise exc
    return _resp(_r)


@pytest.fixture(autouse=True)
def _clear_name_cache():
    gnews._name_cache.clear()
    yield
    gnews._name_cache.clear()


@pytest.mark.unit
class TestResolveQueryName:
    def test_uses_yfinance_short_name(self):
        class _FakeTicker:
            def __init__(self, symbol):
                self.info = {"shortName": "Malayan Banking Bhd", "longName": "Malayan Banking Berhad"}

        with patch("yfinance.Ticker", _FakeTicker):
            assert gnews._resolve_query_name("1155.KL") == "Malayan Banking Bhd"

    def test_falls_back_to_bare_ticker_on_failure(self):
        class _FakeTicker:
            def __init__(self, symbol):
                raise RuntimeError("network down")

        with patch("yfinance.Ticker", _FakeTicker):
            assert gnews._resolve_query_name("1155.KL") == "1155"

    def test_caches_per_ticker(self):
        calls = []

        class _FakeTicker:
            def __init__(self, symbol):
                calls.append(symbol)
                self.info = {"shortName": "Malayan Banking Bhd"}

        with patch("yfinance.Ticker", _FakeTicker):
            gnews._resolve_query_name("1155.KL")
            gnews._resolve_query_name("1155.KL")
        assert len(calls) == 1


@pytest.mark.unit
class TestParseRss:
    def test_parses_items(self):
        items = gnews._parse_rss(_SAMPLE_RSS.encode("utf-8"))
        assert len(items) == 2
        assert items[0]["title"].startswith("Maybank completes acquisition")
        assert items[0]["publisher"] == "The Star"
        assert items[0]["pub_date"] == datetime(2026, 9, 8, 8, 0, tzinfo=timezone.utc)


@pytest.mark.unit
class TestGetNews:
    def test_fetch_failure_is_reported_as_unavailable_not_no_news(self):
        # A failed fetch must not be rendered as "no news found" (matches
        # reddit.py's #1295 distinction: absence-of-data vs never-observed).
        with patch.object(gnews, "urlopen", side_effect=OSError("boom")):
            out = gnews.get_news("1155.KL", "2026-09-01", "2026-09-15")
        assert "unavailable" in out
        assert "not an absence of news" in out

    def test_window_filters_out_of_range_articles(self):
        with patch.object(gnews, "urlopen", return_value=_rss_resp()), \
             patch.object(gnews, "_resolve_query_name", return_value="Maybank"):
            out = gnews.get_news("1155.KL", "2026-09-01", "2026-09-15")
        # Sept 8 article is in-window; Oct 20 article must be filtered out.
        assert "Maybank completes acquisition" in out
        assert "Best Company at Bursa Malaysia" not in out

    def test_no_results_in_window_is_reported_distinctly(self):
        with patch.object(gnews, "urlopen", return_value=_rss_resp()), \
             patch.object(gnews, "_resolve_query_name", return_value="Maybank"):
            out = gnews.get_news("1155.KL", "2020-01-01", "2020-01-31")
        assert "No news found" in out


@pytest.mark.unit
class TestGetGlobalNews:
    def test_fetch_failure_is_reported_as_unavailable(self):
        with patch.object(gnews, "urlopen", side_effect=OSError("boom")):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=5)
        assert "unavailable" in out

    def test_dedupes_and_bounds_results(self):
        with patch.object(gnews, "urlopen", return_value=_rss_resp()):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=5)
        assert out.count("Maybank completes acquisition") == 1


def _item(title, publisher, day=10):
    return {
        "title": title,
        "link": "",
        "publisher": publisher,
        "pub_date": datetime(2026, 9, day, 8, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def news_config():
    from tradingagents.dataflows.config import get_config, set_config

    keys = ("trusted_news_only", "trusted_news_sources", "my_news_queries")
    original = {k: get_config().get(k) for k in keys}
    set_config({"trusted_news_only": True, "trusted_news_sources": None, "my_news_queries": None})
    yield set_config
    set_config(original)


@pytest.mark.unit
class TestTrustedSources:
    def test_ticker_news_drops_untrusted_publishers(self, news_config):
        items = [_item("Maybank Q2 profit rises", "The Edge Malaysia"),
                 _item("MAYBANK stock jumps 3%", "AD HOC NEWS")]
        with patch.object(gnews, "_fetch", return_value=items), \
             patch.object(gnews, "_resolve_query_name", return_value="Maybank"):
            out = gnews.get_news("1155.KL", "2026-09-01", "2026-09-15")
        assert "Maybank Q2 profit rises" in out
        assert "AD HOC NEWS" not in out
        assert "unverified" not in out

    def test_ticker_news_with_only_untrusted_sources_is_flagged_not_hidden(self, news_config):
        # A small company may only be covered by minor sites: show them, flagged.
        items = [_item("Small cap wins contract", "Some Blog")]
        with patch.object(gnews, "_fetch", return_value=items), \
             patch.object(gnews, "_resolve_query_name", return_value="SmallCo"):
            out = gnews.get_news("0001.KL", "2026-09-01", "2026-09-15")
        assert "Small cap wins contract" in out
        assert "unverified" in out

    def test_publisher_match_is_case_insensitive(self, news_config):
        items = [_item("Ringgit firms", "bernama")]
        with patch.object(gnews, "_fetch", return_value=items):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=5)
        assert "Ringgit firms" in out
        assert "unverified" not in out

    def test_filter_can_be_disabled(self, news_config):
        news_config({"trusted_news_only": False})
        items = [_item("Anything goes", "Some Blog")]
        with patch.object(gnews, "_fetch", return_value=items), \
             patch.object(gnews, "_resolve_query_name", return_value="X"):
            out = gnews.get_news("0001.KL", "2026-09-01", "2026-09-15")
        assert "Anything goes" in out and "unverified" not in out


@pytest.mark.unit
class TestGlobalNewsTopicShare:
    def test_first_broad_query_cannot_starve_later_topics(self, news_config):
        # Previously the loop stopped once `limit` articles were collected, so
        # a broad first query (100 results) meant later topics never ran.
        news_config({"my_news_queries": ["KLCI", "OPR", "ringgit"]})

        def fake_fetch(query, timeout):
            topic = query.split(" after:")[0]
            return [_item(f"{topic} story {i}", "The Star") for i in range(50)]

        with patch.object(gnews, "_fetch", side_effect=fake_fetch):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=6)
        for topic in ("KLCI", "OPR", "ringgit"):
            assert out.count(f"### {topic} story") == 2

    def test_unused_share_is_filled_from_other_topics(self, news_config):
        news_config({"my_news_queries": ["busy", "quiet"]})

        def fake_fetch(query, timeout):
            if query.startswith("quiet"):
                return []
            return [_item(f"busy story {i}", "The Star") for i in range(10)]

        with patch.object(gnews, "_fetch", side_effect=fake_fetch):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=4)
        assert out.count("### busy story") == 4

    def test_untrusted_macro_results_are_dropped(self, news_config):
        news_config({"my_news_queries": ["KLCI"]})
        items = [_item("KLCI up", "The Star"), _item("KLCI crypto tip", "CoinGecko")]
        with patch.object(gnews, "_fetch", return_value=items):
            out = gnews.get_global_news("2026-09-15", look_back_days=7, limit=5)
        assert "KLCI up" in out and "crypto tip" not in out

    def test_default_topics_cover_dividend_holder_drivers(self):
        topics = " ".join(gnews.DEFAULT_MY_QUERIES).lower()
        for word in ("klci", "foreign funds", "opr", "ringgit", "bond yields",
                     "palm oil", "budget", "federal reserve"):
            assert word in topics
