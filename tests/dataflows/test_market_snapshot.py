from datetime import datetime, timezone

from tradingagents.dataflows.market_snapshot import (
    FreshnessStatus,
    MarketBar,
    MarketSnapshot,
    classify_freshness,
    format_market_snapshot,
)


def test_classify_freshness_for_same_day_bar():
    now = datetime(2026, 6, 3, 16, 30, tzinfo=timezone.utc)
    bar_ts = datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc)

    assert classify_freshness(
        last_bar_ts=bar_ts,
        requested_date="2026-06-03",
        now_utc=now,
        stale_after_seconds=3600,
    ) is FreshnessStatus.FRESH


def test_classify_freshness_for_old_intraday_bar():
    now = datetime(2026, 6, 3, 20, 30, tzinfo=timezone.utc)
    bar_ts = datetime(2026, 6, 3, 13, 0, tzinfo=timezone.utc)

    assert classify_freshness(
        last_bar_ts=bar_ts,
        requested_date="2026-06-03",
        now_utc=now,
        stale_after_seconds=3600,
    ) is FreshnessStatus.STALE


def test_format_market_snapshot_includes_vendor_and_warning():
    snap = MarketSnapshot(
        ticker="AAPL",
        requested_date="2026-06-03",
        source="akshare",
        as_of_utc="2026-06-03T20:30:00+00:00",
        freshness=FreshnessStatus.STALE,
        last_bar=MarketBar(
            timestamp="2026-06-02T20:00:00+00:00",
            open=195.0,
            high=198.0,
            low=194.0,
            close=197.0,
            volume=1234567,
        ),
        bars=[
            MarketBar(
                timestamp="2026-06-02T20:00:00+00:00",
                open=195.0,
                high=198.0,
                low=194.0,
                close=197.0,
                volume=1234567,
            )
        ],
        warnings=["latest bar is older than requested date"],
    )

    text = format_market_snapshot(snap)

    assert "# Market snapshot for AAPL" in text
    assert "Source: akshare" in text
    assert "Freshness: stale" in text
    assert "latest bar is older than requested date" in text
    assert "| timestamp | open | high | low | close | volume |" in text
