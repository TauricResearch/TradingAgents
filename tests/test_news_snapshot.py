"""Tests for Phase 0 — News snapshot persistence (T0.3).

Validates the snapshot store contract and the yfinance integration:
- Every fetch writes both raw + formatted output to disk.
- A second fetch with the same (scope, date) returns the cached formatted
  string verbatim and does NOT call the upstream API.
- ``news_force_refresh=True`` skips the cache read but still writes a new
  snapshot so each refresh leaves an auditable trail.
- Errors are never cached (re-running an error case re-attempts the fetch).
- Disabling snapshots leaves the original code path bit-for-bit unchanged.

Unit-only; no live yfinance calls anywhere.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tradingagents.dataflows import snapshots, yfinance_news
from tradingagents.dataflows.config import set_config


# -------------------------------------------------------------------- #
# Fixtures
# -------------------------------------------------------------------- #


@pytest.fixture
def snap_dir(tmp_path, monkeypatch):
    """Point news snapshots at an isolated tmp dir and reset between tests.

    Yields the directory so individual tests can inspect what landed.
    """
    set_config({
        "news_snapshot_enabled": True,
        "news_snapshot_dir": str(tmp_path),
        "news_force_refresh": False,
        # Defaults that yfinance_news functions read
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "global_news_lookback_days": 7,
        "global_news_queries": ["test query"],
    })
    yield tmp_path


@pytest.fixture
def snap_dir_disabled(tmp_path):
    """Same as snap_dir but with snapshotting turned off — to assert
    that the off-path leaves the old behavior intact."""
    set_config({
        "news_snapshot_enabled": False,
        "news_snapshot_dir": str(tmp_path),
        "news_force_refresh": False,
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "global_news_lookback_days": 7,
        "global_news_queries": ["test query"],
    })
    yield tmp_path


def _make_yfinance_article(title, summary, link, pub_date):
    """Build the nested ``content`` shape current yfinance returns (#604)."""
    return {
        "content": {
            "title": title,
            "summary": summary,
            "provider": {"displayName": "TestWire"},
            "canonicalUrl": {"url": link},
            "pubDate": pub_date.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    }


# -------------------------------------------------------------------- #
# Snapshot helper — direct contract tests
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestSnapshotHelperContract:
    def test_write_then_load_roundtrip(self, snap_dir):
        path = snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={"ticker": "AAPL"},
            raw_response=[{"title": "x"}],
            formatted_output="formatted",
        )
        assert path is not None and path.exists()
        loaded = snapshots.load_latest_snapshot(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert loaded is not None
        assert loaded["formatted_output"] == "formatted"
        assert loaded["raw_response"] == [{"title": "x"}]
        assert loaded["scope"] == "AAPL"
        assert loaded["date"] == "2026-01-15"
        assert "fetched_at" in loaded

    def test_replay_formatted_hit(self, snap_dir):
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[],
            formatted_output="the canned output",
        )
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert hit is True
        assert out == "the canned output"

    def test_replay_formatted_miss(self, snap_dir):
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert hit is False
        assert out is None

    def test_latest_snapshot_wins(self, snap_dir):
        """When >1 snapshot for same (scope, date), latest fetched_at wins.

        Microsecond filename precision lets us write back-to-back with no
        sleep, but a tiny gap guarantees the monotonic ordering even on
        clocks that occasionally jitter backwards.
        """
        import time
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="OLD",
        )
        time.sleep(0.01)
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="NEW",
        )
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert hit is True
        assert out == "NEW"

    def test_disabled_short_circuits(self, snap_dir_disabled):
        """When the flag is off, writes are no-ops and reads always miss."""
        path = snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="x",
        )
        assert path is None
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert hit is False
        assert out is None

    def test_force_refresh_bypasses_read_but_allows_write(self, snap_dir):
        # Seed a snapshot
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="seeded",
        )
        # Flip force_refresh on
        cfg = {
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(snap_dir),
            "news_force_refresh": True,
        }
        set_config(cfg)

        # Read must miss even though a snapshot exists
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-15",
        )
        assert hit is False
        # But a write still succeeds
        path = snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="fresh",
        )
        assert path is not None and path.exists()

    def test_scope_isolation(self, snap_dir):
        """A snapshot for AAPL must not satisfy a lookup for MSFT."""
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="apple",
        )
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="MSFT", date="2026-01-15",
        )
        assert hit is False
        assert out is None

    def test_date_isolation(self, snap_dir):
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="day1",
        )
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="AAPL", date="2026-01-16",
        )
        assert hit is False

    def test_kind_isolation(self, snap_dir):
        """A globalnews snapshot must not satisfy a ticker-news lookup."""
        snapshots.write_snapshot(
            kind="globalnews", source="yfinance",
            scope="_global", date="2026-01-15",
            params={}, raw_response=[], formatted_output="global",
        )
        out, hit = snapshots.replay_formatted(
            kind="news", source="yfinance", scope="_global", date="2026-01-15",
        )
        assert hit is False

    def test_unsafe_ticker_component_does_not_escape(self, snap_dir):
        """A malicious ticker like ``../../etc/passwd`` must stay scoped under snap_dir."""
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="../../etc/passwd", date="2026-01-15",
            params={}, raw_response=[], formatted_output="bad",
        )
        # nothing should have escaped
        assert not (snap_dir.parent.parent / "etc" / "passwd").exists()
        # but a sanitized snapshot should exist somewhere under snap_dir
        found = list(snap_dir.rglob("news_yfinance_*.json"))
        assert len(found) == 1
        assert str(found[0]).startswith(str(snap_dir))


# -------------------------------------------------------------------- #
# yfinance_news integration tests
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestGetNewsYfinanceSnapshotIntegration:
    def test_first_call_hits_api_and_writes_snapshot(self, snap_dir, monkeypatch):
        article = _make_yfinance_article(
            title="Big news",
            summary="Some summary",
            link="https://example.com/a",
            pub_date=datetime(2026, 1, 15, 10, 0),
        )
        fake_ticker = MagicMock()
        fake_ticker.get_news.return_value = [article]
        monkeypatch.setattr(yfinance_news.yf, "Ticker", lambda t: fake_ticker)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")

        assert "Big news" in out
        assert "## AAPL News" in out
        # API was hit exactly once
        assert fake_ticker.get_news.call_count == 1
        # A snapshot file landed for this scope/date
        files = list((snap_dir / "AAPL" / "2026-01-15").glob("news_yfinance_*.json"))
        assert len(files) == 1
        # And the snapshot contents match what was returned
        payload = json.loads(files[0].read_text())
        assert payload["formatted_output"] == out
        assert payload["raw_response"] == [article]
        assert payload["scope"] == "AAPL"
        assert payload["date"] == "2026-01-15"

    def test_second_call_uses_cache_and_skips_api(self, snap_dir, monkeypatch):
        # Seed cache with a known canned response
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[],
            formatted_output="CACHED OUTPUT",
        )
        fake_ticker = MagicMock()
        # If the function hits the API after a cache hit, we'd see this call
        # — which would be a regression.
        fake_ticker.get_news.return_value = [_make_yfinance_article(
            "Fresh news", "x", "https://x", datetime(2026, 1, 15, 12, 0),
        )]
        monkeypatch.setattr(yfinance_news.yf, "Ticker", lambda t: fake_ticker)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")

        assert out == "CACHED OUTPUT"
        assert fake_ticker.get_news.call_count == 0  # API was not touched

    def test_force_refresh_bypasses_cache(self, snap_dir, monkeypatch):
        snapshots.write_snapshot(
            kind="news", source="yfinance",
            scope="AAPL", date="2026-01-15",
            params={}, raw_response=[], formatted_output="OLD",
        )
        # Turn on force_refresh
        set_config({
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(snap_dir),
            "news_force_refresh": True,
            "news_article_limit": 20,
        })

        article = _make_yfinance_article(
            "Fresh", "y", "https://y", datetime(2026, 1, 15, 14, 0),
        )
        fake_ticker = MagicMock()
        fake_ticker.get_news.return_value = [article]
        monkeypatch.setattr(yfinance_news.yf, "Ticker", lambda t: fake_ticker)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")

        assert "Fresh" in out
        assert "OLD" not in out
        assert fake_ticker.get_news.call_count == 1
        # A second, newer snapshot file should now exist; the old one stays
        files = list((snap_dir / "AAPL" / "2026-01-15").glob("news_yfinance_*.json"))
        assert len(files) >= 2

    def test_disabled_does_not_write_snapshots(self, snap_dir_disabled, monkeypatch):
        """When the flag is off, behavior is bit-identical to before this PR."""
        article = _make_yfinance_article(
            "Headline", "s", "https://h", datetime(2026, 1, 15, 9, 0),
        )
        fake_ticker = MagicMock()
        fake_ticker.get_news.return_value = [article]
        monkeypatch.setattr(yfinance_news.yf, "Ticker", lambda t: fake_ticker)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out1 = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")
        out2 = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")

        # Same content on both calls (deterministic mocked API)
        assert out1 == out2
        # Both calls hit the API (no caching when disabled)
        assert fake_ticker.get_news.call_count == 2
        # No snapshot directory was created
        assert not any(snap_dir_disabled.rglob("news_yfinance_*.json"))

    def test_api_error_not_cached(self, snap_dir, monkeypatch):
        """A vendor exception must not produce a snapshot — replaying a
        stale error message would be worse than re-attempting the fetch."""
        def boom(_t):
            raise RuntimeError("vendor down")
        monkeypatch.setattr(yfinance_news.yf, "Ticker", boom)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")

        assert "Error fetching news" in out
        # No snapshot landed
        files = list(snap_dir.rglob("news_yfinance_*.json"))
        assert len(files) == 0

    def test_empty_result_is_cached(self, snap_dir, monkeypatch):
        """An empty result IS cached — distinguishing 'we asked yfinance and
        got nothing' from 'we never asked' is itself audit-relevant signal."""
        fake_ticker = MagicMock()
        fake_ticker.get_news.return_value = []
        monkeypatch.setattr(yfinance_news.yf, "Ticker", lambda t: fake_ticker)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out1 = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")
        out2 = yfinance_news.get_news_yfinance("AAPL", "2026-01-15", "2026-01-15")
        assert out1 == out2 == "No news found for AAPL"
        assert fake_ticker.get_news.call_count == 1  # 2nd call from cache


@pytest.mark.unit
class TestGetGlobalNewsYfinanceSnapshotIntegration:
    def test_global_news_uses_global_scope(self, snap_dir, monkeypatch):
        article = _make_yfinance_article(
            "Macro headline", "s", "https://m",
            pub_date=datetime(2026, 1, 14, 9, 0),
        )
        fake_search = MagicMock()
        fake_search.news = [article]
        monkeypatch.setattr(yfinance_news.yf, "Search", lambda **kw: fake_search)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_global_news_yfinance("2026-01-15")
        assert "Macro headline" in out

        # Snapshot landed under the reserved global scope, not under a ticker
        global_dir = snap_dir / snapshots.GLOBAL_SCOPE / "2026-01-15"
        files = list(global_dir.glob("globalnews_yfinance_*.json"))
        assert len(files) == 1

    def test_global_news_cache_hit_skips_search(self, snap_dir, monkeypatch):
        snapshots.write_snapshot(
            kind="globalnews", source="yfinance",
            scope=snapshots.GLOBAL_SCOPE, date="2026-01-15",
            params={}, raw_response=[],
            formatted_output="CANNED GLOBAL",
        )
        called = {"n": 0}
        def _search(**_):
            called["n"] += 1
            return MagicMock(news=[])
        monkeypatch.setattr(yfinance_news.yf, "Search", _search)
        monkeypatch.setattr(yfinance_news, "yf_retry", lambda f: f())

        out = yfinance_news.get_global_news_yfinance("2026-01-15")
        assert out == "CANNED GLOBAL"
        assert called["n"] == 0
