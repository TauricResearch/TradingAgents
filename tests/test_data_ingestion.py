"""Tests for the ingestion layer: OHLCV -> DB + deterministic screening."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tradingagents.ingestion import (
    YFinanceFetcher,
    compute_screening_signals,
    ingest_price_bars,
    screen_ticker,
)
from tradingagents.storage import database, init_db, reset_engine
from tradingagents.storage import repository as repo

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    init_db(f"sqlite:///{tmp_path / 'ingest.db'}")
    yield
    reset_engine()


def _bars(prices: list[float]) -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = []
    for i, p in enumerate(prices):
        out.append(
            {
                "ts": base + timedelta(days=i),
                "open": p,
                "high": p * 1.02,
                "low": p * 0.98,
                "close": p,
                "volume": 1_000 + i,
            }
        )
    return out


class FakeFetcher:
    def __init__(self, bars):
        self._bars = bars

    def fetch(self, symbol, start, end, interval):
        return list(self._bars)


def test_ingest_writes_through(db):
    fetcher = FakeFetcher(_bars([100, 101, 102, 103]))
    with database.get_session() as s:
        result = ingest_price_bars(
            s, "AAPL", fetcher=fetcher, start="2026-01-01", end="2026-02-01"
        )
        assert result.inserted == 4
        assert result.skipped == 0

    with database.get_session() as s:
        last = repo.latest_price(s, "AAPL")
        assert last is not None and last.close == 103
        assert last.vendor is None or last.reference_date is not None


def test_ingest_is_db_first_check_presence(db):
    fetcher = FakeFetcher(_bars([100, 101, 102, 103]))
    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=fetcher, start="2026-01-01", end="2026-02-01")
    # Second run on the same range inserts nothing (immutable history).
    with database.get_session() as s:
        result = ingest_price_bars(
            s, "AAPL", fetcher=fetcher, start="2026-01-01", end="2026-02-01"
        )
        assert result.inserted == 0
        assert result.skipped == 4


def test_screening_signals_bounds_and_ordering():
    up = compute_screening_signals(_bars([100, 105, 110, 120]))
    down = compute_screening_signals(_bars([120, 110, 105, 100]))
    assert 0.0 <= up["score"] <= 1.0
    assert 0.0 <= down["score"] <= 1.0
    assert up["total_return"] > 0 > down["total_return"]
    assert up["score"] > down["score"]


def test_screening_too_short():
    assert compute_screening_signals(_bars([100]))["score"] is None


def test_screen_ticker_writes_card(db):
    fetcher = FakeFetcher(_bars([100, 105, 110, 120]))
    with database.get_session() as s:
        ingest_price_bars(s, "AAPL", fetcher=fetcher, start="2026-01-01", end="2026-02-01")

    with database.get_session() as s:
        card = screen_ticker(s, "AAPL", lookback=60)
        assert card is not None
        assert card.screening_score is not None

    with database.get_session() as s:
        card = repo.get_ticker_card(s, "AAPL")
        assert card.screening_score is not None
        assert card.last_screened_at is not None
        assert card.screening_signals["n"] == 4


@pytest.mark.integration
def test_yfinance_fetcher_real_network():
    """Real yfinance call; skipped unless network + data are available."""
    fetcher = YFinanceFetcher()
    try:
        bars = fetcher.fetch("AAPL", "2026-01-02", "2026-01-10", "1d")
    except Exception as exc:  # pragma: no cover - network dependent
        pytest.skip(f"yfinance unavailable: {exc}")
    if not bars:  # pragma: no cover - network dependent
        pytest.skip("no data returned")
    assert {"ts", "open", "high", "low", "close"} <= set(bars[0])
