"""Tests for Phase 1 — Data source snapshot expansion (T1.5).

Extends T0.3's yfinance-news snapshot pattern to:
- yfinance prices (get_YFin_data_online)
- yfinance fundamentals (balance sheet, cashflow, income, overview)
- yfinance technical indicators (window + single)
- alpha_vantage news (dict return type via serialize="json")
- alpha_vantage global news (literal _global scope)

The @snapshot decorator does the work — these tests validate the
decorator's contract end-to-end against each source.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from tradingagents.dataflows import snapshots
from tradingagents.dataflows.config import set_config


# -------------------------------------------------------------------- #
# Fixture: isolated snapshot dir
# -------------------------------------------------------------------- #


@pytest.fixture
def snap_dir(tmp_path):
    """Point snapshots at a fresh tmp dir for each test."""
    set_config({
        "news_snapshot_enabled": True,
        "news_snapshot_dir": str(tmp_path),
        "news_force_refresh": False,
        # Defaults the legacy yfinance_news helpers expect
        "news_article_limit": 20,
        "global_news_article_limit": 10,
        "global_news_lookback_days": 7,
        "global_news_queries": ["test"],
    })
    yield tmp_path


# -------------------------------------------------------------------- #
# Decorator contract
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestSnapshotDecoratorContract:
    def test_first_call_miss_then_second_call_hit(self, snap_dir):
        """The decorator caches by (scope, date); a second identical call
        must not invoke the underlying function."""
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return f"data-for-{ticker}-{date}"

        r1 = fetch(ticker="AAPL", date="2026-01-15")
        r2 = fetch(ticker="AAPL", date="2026-01-15")

        assert r1 == r2 == "data-for-AAPL-2026-01-15"
        assert call_count["n"] == 1

    def test_different_scopes_dont_share_cache(self, snap_dir):
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return f"data-{ticker}"

        fetch(ticker="AAPL", date="2026-01-15")
        fetch(ticker="MSFT", date="2026-01-15")
        assert call_count["n"] == 2

    def test_different_dates_dont_share_cache(self, snap_dir):
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return "x"

        fetch(ticker="AAPL", date="2026-01-15")
        fetch(ticker="AAPL", date="2026-01-16")
        assert call_count["n"] == 2

    def test_positional_args_also_work(self, snap_dir):
        """Decorator uses inspect.signature.bind so positional args
        resolve correctly to the named scope/date params."""
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return "x"

        fetch("AAPL", "2026-01-15")  # positional
        fetch(ticker="AAPL", date="2026-01-15")  # keyword
        assert call_count["n"] == 1  # second call hit cache

    def test_error_string_not_cached(self, snap_dir):
        """Functions in this codebase signal failure by returning a string
        prefixed with 'Error...'.  Snapshotting that would replay the
        failure forever; instead the cache stays empty so a re-run
        re-attempts the fetch."""
        results = iter(["Error fetching: timeout", "real data after retry"])
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return next(results)

        r1 = fetch(ticker="AAPL", date="2026-01-15")
        r2 = fetch(ticker="AAPL", date="2026-01-15")
        assert r1 == "Error fetching: timeout"
        assert r2 == "real data after retry"  # NOT cached
        assert call_count["n"] == 2

    def test_no_data_found_not_cached(self, snap_dir):
        """Empty-data sentinels from this codebase are similarly not cached.

        Distinct from T0.3 yfinance_news behavior, which DOES cache its
        "No news found" string because "we asked and got nothing" is
        itself audit signal there.  Other sources may legitimately
        return data later in the day or after a corporate filing, so
        we err on the side of re-attempting.
        """
        results = iter(["No data found for symbol 'XYZ'", "data: 1,2,3"])
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="balancesheet", source="yfinance",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return next(results)

        fetch(ticker="XYZ", date="2026-01-15")
        fetch(ticker="XYZ", date="2026-01-15")
        assert call_count["n"] == 2

    def test_json_serialize_mode_roundtrips_dict(self, snap_dir):
        """``serialize='json'`` stores the dict result; replay returns
        the deserialized dict (not the JSON string)."""
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
            serialize="json",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return {"articles": [{"title": "hi"}], "count": 1}

        r1 = fetch(ticker="AAPL", date="2026-01-15")
        r2 = fetch(ticker="AAPL", date="2026-01-15")
        assert r1 == r2
        assert isinstance(r2, dict)
        assert r2["articles"][0]["title"] == "hi"
        assert call_count["n"] == 1

    def test_scope_literal_overrides_scope_arg(self, snap_dir):
        """``scope_literal`` is for functions that aren't ticker-specific
        (e.g. global news).  The cache key uses the literal regardless
        of what args the function takes."""
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="globalnews", source="testsrc",
            scope_literal=snapshots.GLOBAL_SCOPE,
            date_arg="curr_date",
        )
        def fetch(curr_date, limit=10):
            call_count["n"] += 1
            return f"news-{curr_date}"

        fetch(curr_date="2026-01-15")
        fetch(curr_date="2026-01-15")
        assert call_count["n"] == 1
        # And the snapshot landed under the _global scope dir
        global_dir = snap_dir / snapshots.GLOBAL_SCOPE / "2026-01-15"
        files = list(global_dir.glob("globalnews_testsrc_*.json"))
        assert len(files) == 1

    def test_decorator_requires_scope_arg_or_scope_literal(self):
        """Constructing the decorator with neither is a programming
        error — fail at decoration time, not at first call."""
        with pytest.raises(ValueError):
            snapshots.snapshot(kind="x", source="y", date_arg="date")

    def test_underscore_in_kind_rejected(self, snap_dir):
        """A kind containing underscore would collide with the filename
        separator and make load() ambiguous (the regex couldn't tell
        where kind ends and source begins). Fail loud at write time.

        This bug was discovered during T1.5 development — the original
        kind 'balance_sheet' silently round-tripped wrong; both writes
        landed (different filenames) but reads never matched.
        """
        with pytest.raises(ValueError, match="must not contain underscore"):
            snapshots.write_snapshot(
                kind="balance_sheet", source="yfinance",
                scope="AAPL", date="2026-01-15",
                params={}, raw_response=None, formatted_output="x",
            )

    def test_force_refresh_bypasses_cache(self, snap_dir):
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return f"call-{call_count['n']}"

        fetch(ticker="AAPL", date="2026-01-15")
        # Flip force_refresh on
        set_config({
            "news_snapshot_enabled": True,
            "news_snapshot_dir": str(snap_dir),
            "news_force_refresh": True,
        })
        r2 = fetch(ticker="AAPL", date="2026-01-15")
        assert r2 == "call-2"
        assert call_count["n"] == 2

    def test_disabled_short_circuits_writes_and_reads(self, snap_dir):
        set_config({
            "news_snapshot_enabled": False,
            "news_snapshot_dir": str(snap_dir),
        })
        call_count = {"n": 0}

        @snapshots.snapshot(
            kind="thing", source="testsrc",
            scope_arg="ticker", date_arg="date",
        )
        def fetch(ticker, date):
            call_count["n"] += 1
            return "x"

        fetch(ticker="AAPL", date="2026-01-15")
        fetch(ticker="AAPL", date="2026-01-15")
        # No caching — both calls hit underlying fn
        assert call_count["n"] == 2
        # No snapshot files anywhere
        assert not list(snap_dir.rglob("*.json"))

    def test_replay_raw_returns_raw_response(self, snap_dir):
        """``replay_raw`` companion to ``replay_formatted`` for json mode."""
        snapshots.write_snapshot(
            kind="x", source="y", scope="AAPL", date="2026-01-15",
            params={}, raw_response={"a": 1, "b": [2, 3]},
            formatted_output='{"a": 1, "b": [2, 3]}',
        )
        raw, hit = snapshots.replay_raw(
            kind="x", source="y", scope="AAPL", date="2026-01-15",
        )
        assert hit
        assert raw == {"a": 1, "b": [2, 3]}


# -------------------------------------------------------------------- #
# Integration with each y_finance function
# -------------------------------------------------------------------- #


def _fake_yf_history_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.5, 102.5],
            "Volume": [1000000, 1100000],
        },
        index=pd.to_datetime(["2026-01-14", "2026-01-15"]),
    )


@pytest.mark.unit
class TestYFinanceSnapshots:
    def test_get_YFin_data_online_caches(self, snap_dir, monkeypatch):
        from tradingagents.dataflows import y_finance as yfm

        fake_ticker = MagicMock()
        fake_ticker.history = MagicMock(return_value=_fake_yf_history_df())
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())

        r1 = yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")
        r2 = yfm.get_YFin_data_online("AAPL", "2026-01-14", "2026-01-15")
        assert r1 == r2
        assert "AAPL" in r1
        # Inner call happened once; second served from cache
        assert fake_ticker.history.call_count == 1
        # Snapshot file landed
        files = list((snap_dir / "AAPL" / "2026-01-15").glob("prices_yfinance_*.json"))
        assert len(files) == 1
        # Snapshot params captured the dates
        payload = json.loads(files[0].read_text())
        assert payload["params"]["start_date"] == "2026-01-14"
        assert payload["params"]["end_date"] == "2026-01-15"

    def test_get_balance_sheet_caches(self, snap_dir, monkeypatch):
        from tradingagents.dataflows import y_finance as yfm

        fake_df = pd.DataFrame({"Total Assets": [1e9]}, index=["2026-01-01"])
        fake_ticker = MagicMock()
        fake_ticker.quarterly_balance_sheet = fake_df
        fake_ticker.balance_sheet = fake_df
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())
        monkeypatch.setattr(yfm, "filter_financials_by_date", lambda df, d: df)

        r1 = yfm.get_balance_sheet("AAPL", "quarterly", "2026-01-15")
        r2 = yfm.get_balance_sheet("AAPL", "quarterly", "2026-01-15")
        assert r1 == r2
        files = list((snap_dir / "AAPL" / "2026-01-15").glob("balancesheet_yfinance_*.json"))
        assert len(files) == 1

    def test_get_fundamentals_uses_latest_when_no_date(self, snap_dir, monkeypatch):
        """get_fundamentals takes curr_date=None by default. With no date,
        we fall back to ``_latest`` sentinel."""
        from tradingagents.dataflows import y_finance as yfm

        fake_ticker = MagicMock()
        fake_ticker.info = {"longName": "Apple Inc.", "sector": "Technology"}
        monkeypatch.setattr(yfm.yf, "Ticker", lambda s: fake_ticker)
        monkeypatch.setattr(yfm, "yf_retry", lambda f: f())

        r1 = yfm.get_fundamentals("AAPL")
        r2 = yfm.get_fundamentals("AAPL")
        assert r1 == r2
        files = list((snap_dir / "AAPL" / "_latest").glob("fundamentals_yfinance_*.json"))
        assert len(files) == 1


# -------------------------------------------------------------------- #
# alpha_vantage news: dict-return path with serialize="json"
# -------------------------------------------------------------------- #


@pytest.mark.unit
class TestAlphaVantageNewsSnapshot:
    def test_get_news_caches_dict_return(self, snap_dir, monkeypatch):
        from tradingagents.dataflows import alpha_vantage_news as avm

        fake_response = {"items": "5", "feed": [{"title": "Macro update"}]}
        call_count = {"n": 0}

        def fake_request(endpoint, params):
            call_count["n"] += 1
            return fake_response

        monkeypatch.setattr(avm, "_make_api_request", fake_request)

        r1 = avm.get_news("AAPL", "2026-01-14", "2026-01-15")
        r2 = avm.get_news("AAPL", "2026-01-14", "2026-01-15")
        assert r1 == r2 == fake_response
        assert isinstance(r2, dict)
        assert call_count["n"] == 1
        files = list((snap_dir / "AAPL" / "2026-01-15").glob("news_alpha_vantage_*.json"))
        assert len(files) == 1

    def test_get_global_news_uses_global_scope(self, snap_dir, monkeypatch):
        from tradingagents.dataflows import alpha_vantage_news as avm

        call_count = {"n": 0}

        def fake_request(endpoint, params):
            call_count["n"] += 1
            return {"items": "10", "feed": []}

        monkeypatch.setattr(avm, "_make_api_request", fake_request)

        avm.get_global_news("2026-01-15", look_back_days=7, limit=50)
        avm.get_global_news("2026-01-15", look_back_days=7, limit=50)
        assert call_count["n"] == 1
        global_dir = snap_dir / snapshots.GLOBAL_SCOPE / "2026-01-15"
        files = list(global_dir.glob("globalnews_alpha_vantage_*.json"))
        assert len(files) == 1
