"""Tests for the KLSE Screener comment fetcher: ticker->code mapping, HTML
parsing (top-level comments + threaded replies), the paginated fetch
(plain HTML page 1, JSON-wrapped page 2+), the fetch-failed vs
no-comments-found distinction, and point-in-time window filtering."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tradingagents.dataflows import klse_screener as ks

_TOP_LEVEL = """
<div id="comment-1001" class="cardmy panel panel-default comment  ml-1 mr-1">
<div class="comment-right inline-block">
<div class="panel-heading"><strong class="text-primary">Test User One </strong>
<a href="/v2/users/comments/1"><span class="fa fa-user-circle"></span></a>
<div class="float-right">
<span class="align-right text-muted" data-id="1001">
2 Like
</span>
</div>
</div>
<div class="panel-body">
<div class="comment-message">
<div class="message-container">This counter used to be a top pick, not anymore</div>
</div>
</div>
<div class="panel-heading">
<span class="text-muted">
<a data-datetime="2026-09-21 20:29:01 +0800" href="/v2/comment/1001" title="2026-09-21 20:29:01">4 days</a>
</span>
</div>
</div>
<div class="comment-replies">
<div class="comment-reply " id="comment-1002">
<div class="comment-right">
<div class="panel-heading"><strong class="text-primary">Test User Two </strong></div>
<div class="panel-body">
<div class="comment-message">
<div class="message-container">Service here has really improved lately</div>
</div>
</div>
<div class="panel-heading">
<div style="font-size:0.9em;">
<span><a class="alike" data-id="1002" data-type="0" data-count="3"> Like</a></span>
<span class="text-muted timestamp" data-datetime="2026-09-22 17:37:06 +0800" title="2026-09-22 17:37:06">Yesterday</span>
</div>
</div>
</div>
</div>
</div>
</div>
"""

_NO_COMMENTS = "<div class=\"comments\"></div>"


def _resp(data: bytes):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner, size=-1):
            return data if size is None or size < 0 else data[:size]
    return _Resp()


def _raise(exc):
    class _Resp:
        def __enter__(self_inner):
            return self_inner

        def __exit__(self_inner, *a):
            return False

        def read(self_inner, size=-1):
            raise exc
    return _Resp()


@pytest.mark.unit
class TestBursaCode:
    def test_extracts_code_from_kl_ticker(self):
        assert ks._bursa_code("1295.KL") == "1295"

    def test_is_case_insensitive(self):
        assert ks._bursa_code("1295.kl") == "1295"

    def test_returns_none_for_non_kl_ticker(self):
        assert ks._bursa_code("AAPL") is None

    def test_returns_none_for_bare_kl_suffix(self):
        assert ks._bursa_code(".KL") is None


@pytest.mark.unit
class TestParseComments:
    def test_parses_top_level_and_reply(self):
        comments = ks._parse_comments(_TOP_LEVEL)
        assert len(comments) == 2

        top = next(c for c in comments if not c["is_reply"])
        assert top["id"] == "comment-1001"
        assert top["user"] == "Test User One"
        assert "top pick" in top["text"]
        assert top["created"] == datetime(2026, 9, 21, 20, 29, 1, tzinfo=timezone(timedelta(hours=8)))
        assert top["likes"] == 2

        reply = next(c for c in comments if c["is_reply"])
        assert reply["id"] == "comment-1002"
        assert reply["user"] == "Test User Two"
        assert "improved lately" in reply["text"]
        assert reply["likes"] == 3

    def test_empty_thread_parses_to_no_comments(self):
        assert ks._parse_comments(_NO_COMMENTS) == []

    def test_malformed_html_does_not_raise(self):
        assert ks._parse_comments("<div><div id=\"comment-\">broken") == []


@pytest.mark.unit
class TestFetchPage:
    def test_page_one_is_plain_html_no_xhr_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            captured["url"] = req.full_url
            return _resp(_TOP_LEVEL.encode("utf-8"))

        with patch.object(ks, "urlopen", fake_urlopen):
            out = ks._fetch_page("1295", 1, 10.0)
        assert out == _TOP_LEVEL
        assert "/comments/all/stock/1295" in captured["url"]
        assert "/1" not in captured["url"].rsplit("stock/1295", 1)[-1]
        assert "X-Requested-With" not in captured["headers"]

    def test_page_two_sets_xhr_header_and_unwraps_json(self):
        captured = {}
        payload = json.dumps({"count": 10, "html": _TOP_LEVEL}).encode("utf-8")

        def fake_urlopen(req, timeout=None):
            captured["headers"] = dict(req.header_items())
            captured["url"] = req.full_url
            return _resp(payload)

        with patch.object(ks, "urlopen", fake_urlopen):
            out = ks._fetch_page("1295", 2, 10.0)
        assert out == _TOP_LEVEL
        assert captured["url"].endswith("/stock/1295/2")
        assert captured["headers"].get("X-requested-with") == "XMLHttpRequest"

    def test_non_json_page_two_response_is_treated_as_failure(self):
        with patch.object(ks, "urlopen", return_value=_resp(b"<html>not json</html>")):
            assert ks._fetch_page("1295", 2, 10.0) is None

    def test_http_error_returns_none(self):
        import urllib.error
        with patch.object(
            ks, "urlopen",
            side_effect=urllib.error.URLError("boom"),
        ):
            assert ks._fetch_page("1295", 1, 10.0) is None


@pytest.mark.unit
class TestFetchKlseScreenerComments:
    def test_non_kl_ticker_short_circuits_without_network(self):
        with patch.object(ks, "urlopen", side_effect=AssertionError("must not fetch")):
            out = ks.fetch_klse_screener_comments("AAPL")
        assert "not applicable" in out
        assert "AAPL" in out

    def test_fetch_failure_is_reported_as_unavailable_not_no_comments(self):
        # Matches google_news_my/reddit's convention: a failed fetch must not
        # be rendered as "no comments found" (#1295 distinction).
        with patch.object(ks, "urlopen", side_effect=OSError("boom")):
            out = ks.fetch_klse_screener_comments("1295.KL")
        assert "unavailable" in out
        assert "not an absence of comments" in out

    def test_genuinely_empty_thread_is_reported_as_no_comments(self):
        with patch.object(ks, "urlopen", return_value=_resp(_NO_COMMENTS.encode("utf-8"))):
            out = ks.fetch_klse_screener_comments("1295.KL")
        assert "no KLSE Screener comments found" in out

    def test_window_filters_out_of_range_comments(self):
        with patch.object(ks, "urlopen", return_value=_resp(_TOP_LEVEL.encode("utf-8"))):
            out = ks.fetch_klse_screener_comments(
                "1295.KL", max_pages=1, start_date="2026-09-21", end_date="2026-09-21"
            )
        # Only the top-level comment (9/21) is in-window; the reply (9/22) is not.
        assert "top pick" in out
        assert "improved lately" not in out

    def test_out_of_window_thread_reports_no_comments_with_dates(self):
        with patch.object(ks, "urlopen", return_value=_resp(_TOP_LEVEL.encode("utf-8"))):
            out = ks.fetch_klse_screener_comments(
                "1295.KL", max_pages=1, start_date="2020-01-01", end_date="2020-01-31"
            )
        assert "no KLSE Screener comments found" in out
        assert "2020-01-01" in out and "2020-01-31" in out

    def test_in_window_comments_are_formatted_with_metadata(self):
        with patch.object(ks, "urlopen", return_value=_resp(_TOP_LEVEL.encode("utf-8"))):
            out = ks.fetch_klse_screener_comments("1295.KL", max_pages=1)
        assert "Test User One" in out
        assert "2 likes" in out
        assert "Test User Two" in out
        assert "3 likes" in out
        assert "reply" in out

    def test_stops_at_max_pages_without_fetching_further(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            return _resp(_TOP_LEVEL.encode("utf-8"))

        with patch.object(ks, "urlopen", fake_urlopen):
            ks.fetch_klse_screener_comments("1295.KL", max_pages=1)
        assert len(calls) == 1

    def test_pagination_stops_when_a_later_page_is_empty(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            if req.full_url.endswith("/2"):
                return _resp(json.dumps({"count": 0, "html": ""}).encode("utf-8"))
            return _resp(_TOP_LEVEL.encode("utf-8"))

        with patch.object(ks, "urlopen", fake_urlopen):
            out = ks.fetch_klse_screener_comments("1295.KL", max_pages=3)
        assert len(calls) == 2  # page 3 never requested once page 2 is empty
        assert "Test User One" in out

    def test_duplicate_comments_across_pages_are_deduped(self):
        def fake_urlopen(req, timeout=None):
            if req.full_url.endswith("/2"):
                return _resp(json.dumps({"count": 10, "html": _TOP_LEVEL}).encode("utf-8"))
            return _resp(_TOP_LEVEL.encode("utf-8"))

        with patch.object(ks, "urlopen", fake_urlopen):
            out = ks.fetch_klse_screener_comments("1295.KL", max_pages=2)
        assert out.count("This counter used to be a top pick") == 1
