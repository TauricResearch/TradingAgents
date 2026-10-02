"""yfinance news must not leak future-dated (or undated, in a backtest) articles
into a historical window.

Regressions for #992 (flat articles bypassed the date filter), #1007 (global
news injected future articles), #993 (empty-after-filter returned a blank body),
and #1126 (inclusive upper bound leaked the midnight-after article; host-local
timestamp parsing made filtering machine-dependent).
"""
from datetime import UTC, datetime

import pytest

import tradingagents.dataflows.vendors.yahoo.news as ynews
from tradingagents.dataflows.date_window import in_window


def _epoch(date_str):
    """Epoch seconds for UTC midnight of ``date_str`` (host-timezone independent)."""
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


@pytest.mark.unit
def test_flat_article_publish_time_is_parsed():
    # #992: flat articles now carry a pub_date (was always None -> unfilterable).
    # #1126: parsed as UTC-aware, so the date can't shift with the host timezone.
    data = ynews._extract_article_data(
        {"title": "X", "publisher": "P", "link": "l", "providerPublishTime": _epoch("2025-05-09")}
    )
    assert data["pub_date"] is not None
    assert data["pub_date"].tzinfo is not None
    assert data["pub_date"] == datetime(2025, 5, 9, tzinfo=UTC)


@pytest.mark.unit
def test_window_excludes_future_and_undated_in_backtest():
    start = datetime(2025, 5, 1)
    end = datetime(2025, 5, 9)  # historical window (well in the past)
    inside = datetime(2025, 5, 5)
    future = datetime(2025, 6, 1)
    assert in_window(inside, start, end) is True
    assert in_window(future, start, end) is False     # look-ahead blocked
    assert in_window(None, start, end) is False        # undated -> excluded in backtest


@pytest.mark.unit
def test_window_keeps_undated_in_live_window():
    # Live window (reaches today): undated articles can't be "future", so keep them.
    now = datetime.now(UTC)
    assert in_window(None, now, now) is True


@pytest.mark.unit
def test_upper_bound_is_exclusive():
    # #1126: an article stamped exactly midnight AFTER end_date leaked in under
    # the old inclusive bound; the whole of end_date itself must still be kept.
    start = datetime(2025, 5, 1)
    end = datetime(2025, 5, 9)
    midnight_after = datetime(2025, 5, 10, 0, 0, 0, tzinfo=UTC)
    last_moment = datetime(2025, 5, 9, 23, 59, 59, tzinfo=UTC)
    assert in_window(midnight_after, start, end) is False
    assert in_window(last_moment, start, end) is True


@pytest.mark.unit
def test_offset_aware_timestamp_is_converted_not_truncated():
    # #1126: 2025-05-10T01:00+05:00 is really 2025-05-09T20:00Z -> inside the
    # window. Stripping tzinfo (old behavior) misread it as 05-10 and dropped it.
    start = datetime(2025, 5, 1)
    end = datetime(2025, 5, 9)
    aware = datetime.fromisoformat("2025-05-10T01:00:00+05:00")
    assert in_window(aware, start, end) is True


@pytest.mark.unit
def test_global_news_future_flat_article_excluded(monkeypatch):
    # #1007: a flat, future-dated global article must not appear in a historical run.
    future_article = {"title": "FUTURE EVENT", "publisher": "P", "link": "l",
                      "providerPublishTime": _epoch("2025-06-01")}
    past_article = {"title": "PAST EVENT", "publisher": "P", "link": "l",
                    "providerPublishTime": _epoch("2025-05-05")}

    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = [future_article, past_article]

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    out = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=10)
    assert "PAST EVENT" in out
    assert "FUTURE EVENT" not in out  # #1007


@pytest.mark.unit
def test_global_news_empty_after_filter_is_informative(monkeypatch):
    # #993: everything filtered out -> a clear message, not a blank-bodied report.
    only_future = {"title": "FUTURE", "publisher": "P", "link": "l",
                   "providerPublishTime": _epoch("2025-06-01")}

    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = [only_future]

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    out = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=10)
    assert "###" not in out  # no empty article body
    # Only a later article came back, so the feed does not reach this window.
    assert "unavailable" in out and "not an absence" in out


def _ticker_with(articles, monkeypatch, searched=()):
    """Serve ``articles`` from the ticker feed and ``searched`` from a search;
    return the queries the search was asked."""
    queries = []

    class FakeTicker:
        def __init__(self, *a, **k):
            pass

        def get_news(self, count=20):
            return articles

    class FakeSearch:
        def __init__(self, query, **k):
            queries.append(query)
            self.news = list(searched)

    monkeypatch.setattr(ynews.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    return queries


@pytest.mark.unit
def test_ticker_news_window_before_feed_coverage_is_unavailable(monkeypatch):
    # Yahoo serves only recent articles: a historical window gets none of them,
    # which must read as "cannot answer", not "no news happened".
    recent = [{"title": "RECENT", "publisher": "P", "link": "l",
               "providerPublishTime": _epoch("2026-09-10")}]
    _ticker_with(recent, monkeypatch)
    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")
    assert "RECENT" not in out
    assert "unavailable" in out and "not an absence" in out
    assert "2026-09-10" not in out  # an article after the window


@pytest.mark.unit
def test_ticker_news_covered_but_empty_window_is_a_real_absence(monkeypatch):
    articles = [{"title": "RECENT", "publisher": "P", "link": "l",
                 "providerPublishTime": _epoch("2026-09-10")},
                {"title": "OLDER", "publisher": "P", "link": "l",
                 "providerPublishTime": _epoch("2026-07-01")}]
    _ticker_with(articles, monkeypatch)
    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")
    assert "No news found" in out
    assert "unavailable" not in out


@pytest.mark.unit
@pytest.mark.parametrize("dates, expect_gap", [
    ([], True),                                              # empty feed: covers at most now
    ([None], True),                                          # undated only: same
    ([datetime(2026, 5, 20, tzinfo=UTC)], True),    # all after the window
    ([datetime(2026, 5, 4, tzinfo=UTC)], True),     # starts mid-window: partial
    ([datetime(2026, 5, 1, 18, tzinfo=UTC)], False),  # reaches the first day
    ([datetime(2026, 5, 20, tzinfo=UTC),
      datetime(2026, 4, 1, tzinfo=UTC)], False),    # coverage reaches back
])
def test_coverage_gap_boundaries(dates, expect_gap):
    from tradingagents.dataflows.date_window import coverage_gap

    out = coverage_gap(dates, "2026-05-01", "2026-05-08", "Feed", "items")
    assert (out is not None) is expect_gap
    if expect_gap:
        assert "unavailable for 2026-05-01..2026-05-08" in out and "not an absence" in out


@pytest.mark.unit
def test_ticker_news_empty_feed_for_a_past_window_is_unavailable(monkeypatch):
    _ticker_with([], monkeypatch)
    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")
    assert "unavailable" in out and "not an absence" in out


@pytest.mark.unit
def test_ticker_news_null_feed_is_handled(monkeypatch):
    # Yahoo can return None instead of a list; that is unavailability, not an error.
    _ticker_with(None, monkeypatch)
    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")
    assert "unavailable" in out and "Error" not in out


def _tagged(title, date_str, *tickers):
    return {"title": title, "publisher": "P", "link": "l",
            "providerPublishTime": _epoch(date_str), "relatedTickers": list(tickers)}


@pytest.mark.unit
def test_an_empty_ticker_feed_falls_back_to_the_search_news_tagged_with_it(monkeypatch):
    # #1467: Ticker.get_news answers every symbol with nothing while Yahoo's
    # search still serves its articles; only those tagged with it are its news.
    searched = [_tagged("ABOUT AAPL", "2026-08-10", "MSFT", "AAPL"),
                _tagged("ABOUT MSFT", "2026-08-10", "MSFT"),
                {"title": "UNTAGGED", "publisher": "P", "link": "l",
                 "providerPublishTime": _epoch("2026-08-10")}]
    queries = _ticker_with([], monkeypatch, searched=searched)

    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")

    assert queries == ["AAPL"]
    assert "ABOUT AAPL" in out
    assert "ABOUT MSFT" not in out and "UNTAGGED" not in out


@pytest.mark.unit
def test_a_ticker_feed_with_articles_is_not_searched(monkeypatch):
    queries = _ticker_with([_tagged("FROM FEED", "2026-08-10")], monkeypatch,
                           searched=[_tagged("FROM SEARCH", "2026-08-10", "AAPL")])

    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")

    assert queries == []
    assert "FROM FEED" in out and "FROM SEARCH" not in out


@pytest.mark.unit
def test_a_failed_fallback_search_is_unavailable_not_absent(monkeypatch):
    from tradingagents.dataflows.errors import VendorUnavailableError

    _ticker_with([], monkeypatch)

    def failing_search(*a, **k):
        raise RuntimeError("yahoo hiccup")

    monkeypatch.setattr(ynews.yf, "Search", failing_search)
    with pytest.raises(VendorUnavailableError):
        ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")


@pytest.mark.unit
def test_search_hits_around_a_window_do_not_claim_it_was_covered(monkeypatch):
    # The same articles from the ticker feed would make this a real absence
    # (test_ticker_news_covered_but_empty_window_is_a_real_absence); a search
    # is ranked by relevance, so an older hit says nothing about the days after it.
    _ticker_with([], monkeypatch, searched=[_tagged("RECENT", "2026-09-10", "AAPL"),
                                            _tagged("OLDER", "2026-07-01", "AAPL")])

    out = ynews.get_news_yfinance("AAPL", "2026-08-07", "2026-08-14")

    assert "unavailable" in out and "not an absence" in out
    assert "No news found" not in out


@pytest.mark.unit
def test_global_news_empty_feed_for_a_past_window_is_unavailable(monkeypatch):
    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = []

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    out = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=10)
    assert "unavailable" in out and "not an absence" in out


@pytest.mark.unit
def test_global_news_does_not_infer_coverage_from_a_stale_search_hit(monkeypatch):
    # Global news merges fuzzy searches; one old hit before the window says
    # nothing about the days in between, so the window stays unavailable.
    stale = {"title": "STALE", "publisher": "P", "link": "l", "providerPublishTime": _epoch("2025-01-01")}
    fresh = {"title": "FRESH", "publisher": "P", "link": "l", "providerPublishTime": _epoch("2025-06-01")}

    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = [fresh, stale]

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    out = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=10)
    assert "unavailable" in out and "No global news found" not in out


@pytest.mark.unit
def test_coverage_gap_future_window_is_unavailable():
    from datetime import timedelta

    from tradingagents.dataflows.date_window import coverage_gap
    today = datetime.now(UTC).date()
    out = coverage_gap([], str(today), str(today + timedelta(days=3)), "Feed", "items")
    assert out is not None and "past today" in out


@pytest.mark.unit
def test_out_of_window_articles_do_not_consume_the_article_budget(monkeypatch):
    """The limit counts articles the run may see, not candidates fetched (#1356).

    Out-of-window items were counted first, so they filled the budget, stopped
    the remaining searches, and the in-window news was reported as absent.
    """
    stale = [{"title": f"OLD {i}", "publisher": "P", "link": "l",
              "providerPublishTime": _epoch("2025-01-01")} for i in range(2)]
    wanted = {"title": "IN WINDOW", "publisher": "P", "link": "l",
              "providerPublishTime": _epoch("2025-05-08")}
    pages = [stale, [wanted]]

    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = pages.pop(0) if pages else []

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    monkeypatch.setattr(ynews, "get_config", lambda: {
        "global_news_lookback_days": 7, "global_news_article_limit": 2,
        "global_news_queries": ["markets", "economy"],
    })

    out = ynews.get_global_news_yfinance("2025-05-09")

    assert "IN WINDOW" in out
    assert "OLD 0" not in out


@pytest.mark.unit
def test_the_article_limit_still_caps_what_is_returned(monkeypatch):
    articles = [{"title": f"NEWS {i}", "publisher": "P", "link": "l",
                 "providerPublishTime": _epoch("2025-05-08")} for i in range(5)]

    class FakeSearch:
        def __init__(self, *a, **k):
            self.news = articles

    monkeypatch.setattr(ynews.yf, "Search", FakeSearch)
    out = ynews.get_global_news_yfinance("2025-05-09", look_back_days=7, limit=3)

    assert out.count("### ") == 3
