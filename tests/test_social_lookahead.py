"""Social-sentiment sources must not leak current posts into historical runs.

Regressions for #1220: StockTwits and Reddit fetchers accepted no date
window, so a historical analysis pulled today's posts and presented them as
covering the requested historical period. Both fetchers now filter on the
analysis window and return window-specific placeholders when nothing
survives the filter (the public APIs cannot serve true historical data).
"""

import json
from datetime import datetime, timezone

import pytest

import tradingagents.dataflows.reddit as reddit
import tradingagents.dataflows.stocktwits as stocktwits
from tradingagents.agents.analysts.sentiment_analyst import _build_system_message


def _epoch(date_str: str) -> int:
    """Epoch seconds for UTC midnight of ``date_str`` (host-timezone independent)."""
    return int(datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


class _FakeResp:
    """Minimal context-manager response whose ``read()`` returns JSON bytes."""

    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


# ---------------------------------------------------------------------------
# Window helper semantics (shared by both fetchers)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_stocktwits_in_window_boundaries():
    start, end = stocktwits._window_epochs("2025-05-01", "2025-05-09")
    assert stocktwits._in_window(_epoch("2025-05-05"), start, end) is True
    assert stocktwits._in_window(_epoch("2025-05-09"), start, end) is True  # whole end day kept
    assert stocktwits._in_window(_epoch("2025-06-01"), start, end) is False  # future blocked
    assert stocktwits._in_window(_epoch("2025-05-10"), start, end) is False  # next midnight excluded
    assert stocktwits._in_window(None, start, end) is False  # undated excluded in backtest
    assert stocktwits._in_window(_epoch("2025-05-05"), None, None) is True  # no bounds -> pass
    assert stocktwits._in_window(None, None, None) is True  # undated kept in live mode


@pytest.mark.unit
def test_reddit_in_window_boundaries():
    start, end = reddit._window_epochs("2025-05-01", "2025-05-09")
    assert reddit._in_window(_epoch("2025-05-05"), start, end) is True
    assert reddit._in_window(_epoch("2025-05-09"), start, end) is True
    assert reddit._in_window(_epoch("2025-06-01"), start, end) is False
    assert reddit._in_window(_epoch("2025-05-10"), start, end) is False
    assert reddit._in_window(None, start, end) is False
    assert reddit._in_window(_epoch("2025-05-05"), None, None) is True
    assert reddit._in_window(None, None, None) is True  # undated kept in live mode


# ---------------------------------------------------------------------------
# StockTwits end-to-end filtering
# ---------------------------------------------------------------------------


def _stocktwits_payload():
    return {
        "messages": [
            {
                "created_at": "2025-05-05T10:00:00Z",
                "user": {"username": "u1"},
                "entities": {"sentiment": {"basic": "Bullish"}},
                "body": "INSIDE POST",
            },
            {
                "created_at": "2025-06-01T10:00:00Z",
                "user": {"username": "u2"},
                "entities": {"sentiment": {"basic": "Bearish"}},
                "body": "FUTURE POST",
            },
            {
                "created_at": "2025-05-10T00:00:00Z",
                "user": {"username": "u3"},
                "entities": {},
                "body": "NEXT DAY POST",
            },
        ]
    }


@pytest.mark.unit
def test_stocktwits_filters_out_of_window_messages(monkeypatch):
    monkeypatch.setattr(
        stocktwits, "urlopen", lambda req, timeout=10.0: _FakeResp(_stocktwits_payload())
    )
    out = stocktwits.fetch_stocktwits_messages(
        "AAPL", start_date="2025-05-01", end_date="2025-05-09"
    )
    assert "INSIDE POST" in out
    assert "FUTURE POST" not in out
    assert "NEXT DAY POST" not in out


@pytest.mark.unit
def test_stocktwits_all_filtered_returns_window_placeholder(monkeypatch):
    payload = {"messages": [_stocktwits_payload()["messages"][1]]}  # future only
    monkeypatch.setattr(
        stocktwits, "urlopen", lambda req, timeout=10.0: _FakeResp(payload)
    )
    out = stocktwits.fetch_stocktwits_messages(
        "AAPL", start_date="2025-05-01", end_date="2025-05-09"
    )
    assert "no StockTwits messages found" in out
    assert "requested window" in out
    assert "FUTURE POST" not in out


@pytest.mark.unit
def test_stocktwits_live_window_keeps_recent_messages(monkeypatch):
    # No date window: current behavior must be unchanged (no filtering).
    monkeypatch.setattr(
        stocktwits, "urlopen", lambda req, timeout=10.0: _FakeResp(_stocktwits_payload())
    )
    out = stocktwits.fetch_stocktwits_messages("AAPL")
    assert "INSIDE POST" in out
    assert "FUTURE POST" in out
    assert "NEXT DAY POST" in out


# ---------------------------------------------------------------------------
# Reddit end-to-end filtering
# ---------------------------------------------------------------------------


def _reddit_posts():
    return [
        {
            "title": "INSIDE POST",
            "score": None,
            "num_comments": None,
            "created_utc": _epoch("2025-05-05"),
            "selftext": "",
            "source": "rss",
        },
        {
            "title": "FUTURE POST",
            "score": None,
            "num_comments": None,
            "created_utc": _epoch("2025-06-01"),
            "selftext": "",
            "source": "rss",
        },
        {
            "title": "UNDATED POST",
            "score": None,
            "num_comments": None,
            "created_utc": None,
            "selftext": "",
            "source": "rss",
        },
    ]


@pytest.mark.unit
def test_reddit_filters_out_of_window_posts(monkeypatch):
    monkeypatch.setattr(reddit, "_fetch_subreddit", lambda *a, **k: _reddit_posts())
    out = reddit.fetch_reddit_posts(
        "AAPL", start_date="2025-05-01", end_date="2025-05-09", inter_request_delay=0
    )
    assert "INSIDE POST" in out
    assert "FUTURE POST" not in out
    assert "UNDATED POST" not in out
    assert "2025-05-01 to 2025-05-09" in out


@pytest.mark.unit
def test_reddit_all_filtered_returns_window_placeholder(monkeypatch):
    monkeypatch.setattr(
        reddit, "_fetch_subreddit", lambda *a, **k: [_reddit_posts()[1]]
    )
    out = reddit.fetch_reddit_posts(
        "AAPL", start_date="2025-05-01", end_date="2025-05-09", inter_request_delay=0
    )
    assert "no Reddit posts found mentioning" in out
    assert "2025-05-01 to 2025-05-09" in out
    assert "FUTURE POST" not in out


@pytest.mark.unit
def test_reddit_live_window_keeps_recent_posts(monkeypatch):
    monkeypatch.setattr(reddit, "_fetch_subreddit", lambda *a, **k: _reddit_posts())
    out = reddit.fetch_reddit_posts("AAPL", inter_request_delay=0)
    assert "INSIDE POST" in out
    assert "FUTURE POST" in out
    assert "UNDATED POST" in out


# ---------------------------------------------------------------------------
# Sentiment analyst prompt labels the actual data window
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sentiment_prompt_labels_requested_window():
    msg = _build_system_message(
        ticker="AAPL",
        start_date="2025-05-01",
        end_date="2025-05-09",
        news_block="N",
        stocktwits_block="S",
        reddit_block="R",
    )
    assert "2025-05-01 to 2025-05-09" in msg
    assert "past 7 days" not in msg
