"""Unit tests for web.server.history."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import yfinance as yf

from web.server import history


_NOW = datetime(2026, 6, 7, 19, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def fixed_now(monkeypatch):
    """Pin history.now_utc() to a fixed instant so the resolver is deterministic."""
    monkeypatch.setattr(history, "now_utc", lambda: _NOW)


def test_resolve_range_1d_returns_one_day_window_at_1m(fixed_now):
    start, end, interval = history.resolve_range("1d", earliest_started_at=None)
    assert interval == "1m"
    assert end == _NOW
    assert start == _NOW - timedelta(days=1)


def test_resolve_range_5d_returns_five_day_window_at_1m(fixed_now):
    _, _, interval = history.resolve_range("5d", earliest_started_at=None)
    assert interval == "1m"


def test_resolve_range_1mo_returns_thirty_day_window_at_1h(fixed_now):
    _, _, interval = history.resolve_range("1mo", earliest_started_at=None)
    assert interval == "1h"  # 30d > 7d → 1h


def test_resolve_range_3mo_returns_ninety_day_window_at_1d(fixed_now):
    _, _, interval = history.resolve_range("3mo", earliest_started_at=None)
    assert interval == "1d"  # 90d > 60d → 1d


def test_resolve_range_all_caps_at_one_year_at_1d(fixed_now):
    _, _, interval = history.resolve_range("all", earliest_started_at=None)
    assert interval == "1d"


def test_resolve_range_auto_uses_earliest_run_started_at(fixed_now):
    earliest = _NOW - timedelta(days=12)
    start, end, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert start == earliest
    assert end == _NOW
    assert interval == "1h"  # 12d → 1h


def test_resolve_range_auto_with_no_runs_raises(fixed_now):
    with pytest.raises(ValueError, match="no runs"):
        history.resolve_range("auto", earliest_started_at=None)


def test_resolve_range_invalid_preset_raises(fixed_now):
    with pytest.raises(ValueError, match="invalid preset"):
        history.resolve_range("bogus", earliest_started_at=None)


def test_resolve_range_seven_day_span_still_picks_1m(fixed_now):
    earliest = _NOW - timedelta(days=7)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1m"


def test_resolve_range_sixty_day_span_picks_1h(fixed_now):
    earliest = _NOW - timedelta(days=60)
    _, _, interval = history.resolve_range("auto", earliest_started_at=earliest)
    assert interval == "1h"


# ---- fetch_history_bars ----


def _bar_df(start: datetime, n: int, *, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame with a tz-aware UTC DatetimeIndex."""
    idx = pd.date_range(start=start, periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "Open":  [base + i * step for i in range(n)],
            "High":  [base + i * step + 0.1 for i in range(n)],
            "Low":   [base + i * step - 0.1 for i in range(n)],
            "Close": [base + i * step for i in range(n)],
            "Volume": [1000.0 for _ in range(n)],
        },
        index=idx,
    )


class _CountingTicker:
    """Stand-in for ``yf.Ticker`` that records call count and returns a fixed DataFrame."""

    def __init__(self, df: pd.DataFrame):
        self._df = df
        self.calls = 0

    def history(self, **kwargs):
        self.calls += 1
        return self._df


@pytest.fixture
def counting_ticker(monkeypatch):
    """Patch ``yf.Ticker`` to a class that records ``.history`` invocations."""
    history._bar_cache.clear()
    df = _bar_df(_NOW - timedelta(hours=24), 24)
    ticker = _CountingTicker(df)
    monkeypatch.setattr(yf, "Ticker", lambda _t: ticker)
    return ticker


def test_fetch_history_bars_calls_yf_with_resolved_window(fixed_now, counting_ticker):
    bars = history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert isinstance(bars, list)
    assert len(bars) == 24
    assert all(set(b.keys()) == {"t", "o", "h", "l", "c", "v"} for b in bars)
    # Timestamps are ISO with Z suffix and sorted ascending.
    assert all(bars[i]["t"] < bars[i + 1]["t"] for i in range(len(bars) - 1))
    assert all(b["t"].endswith("Z") for b in bars)


def test_fetch_history_bars_cache_hit_avoids_second_yf_call(fixed_now, counting_ticker):
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 1


def test_fetch_history_bars_cache_key_includes_ticker(fixed_now, monkeypatch):
    """Two tickers with the same window must NOT share a cache entry."""
    history._bar_cache.clear()
    a = _CountingTicker(_bar_df(_NOW - timedelta(hours=2), 2))
    b = _CountingTicker(_bar_df(_NOW - timedelta(hours=2), 2))
    queue = iter([a, b])

    def _pick(_t):
        return next(queue)

    monkeypatch.setattr(yf, "Ticker", _pick)
    history.fetch_history_bars("AAA", start=None, end=None, interval="1h")
    history.fetch_history_bars("BBB", start=None, end=None, interval="1h")
    assert a.calls == 1 and b.calls == 1
    assert len(history._bar_cache) == 2


def test_fetch_history_bars_cache_respects_ttl(fixed_now, counting_ticker, monkeypatch):
    """An entry past its TTL must be re-fetched (1h resolution → 300s TTL)."""
    fake_now = [_NOW.timestamp()]
    monkeypatch.setattr(history.time, "monotonic", lambda: fake_now[0])
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 1
    fake_now[0] += 600  # past 5-min TTL
    history.fetch_history_bars("MU", start=None, end=None, interval="1h")
    assert counting_ticker.calls == 2


def test_fetch_history_bars_returns_empty_list_for_empty_dataframe(fixed_now, monkeypatch):
    empty = _CountingTicker(pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]))
    monkeypatch.setattr(yf, "Ticker", lambda _t: empty)
    bars = history.fetch_history_bars("DEAD", start=None, end=None, interval="1d")
    assert bars == []
