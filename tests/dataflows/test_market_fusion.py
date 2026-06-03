import pandas as pd

from tradingagents.dataflows.market_fusion import (
    FusedMarketBar,
    FusedMarketSnapshot,
    format_fused_market_snapshot,
    fuse_source_frames,
)


def _frame(rows):
    return pd.DataFrame(rows)


def test_fuse_source_frames_fills_missing_sessions_by_provider_order():
    expected = [
        "2026-06-01",
        "2026-06-02",
        "2026-06-03",
        "2026-06-04",
        "2026-06-05",
    ]
    yfinance = _frame(
        [
            {
                "timestamp": "2026-06-01",
                "open": 10,
                "high": 11,
                "low": 9,
                "close": 10.5,
                "volume": 100,
            },
            {
                "timestamp": "2026-06-02",
                "open": 11,
                "high": 12,
                "low": 10,
                "close": 11.5,
                "volume": 110,
            },
            {
                "timestamp": "2026-06-05",
                "open": 14,
                "high": 15,
                "low": 13,
                "close": 14.5,
                "volume": 140,
            },
        ]
    )
    akshare = _frame(
        [
            {
                "timestamp": "2026-06-03",
                "open": 12,
                "high": 13,
                "low": 11,
                "close": 12.5,
                "volume": 120,
            },
        ]
    )
    polygon = _frame(
        [
            {
                "timestamp": "2026-06-04",
                "open": 13,
                "high": 14,
                "low": 12,
                "close": 13.5,
                "volume": 130,
            },
        ]
    )

    snapshot = fuse_source_frames(
        ticker="AAPL",
        requested_date="2026-06-05",
        expected_sessions=expected,
        source_frames=[
            ("yfinance", yfinance),
            ("akshare", akshare),
            ("polygon", polygon),
        ],
    )

    assert [bar.date for bar in snapshot.bars] == expected
    assert [bar.source for bar in snapshot.bars] == [
        "yfinance",
        "yfinance",
        "akshare",
        "polygon",
        "yfinance",
    ]
    assert snapshot.missing_sessions == []
    assert snapshot.coverage_ratio == 1.0


def test_format_fused_snapshot_exposes_full_chart_and_sources():
    snapshot = FusedMarketSnapshot(
        ticker="AAPL",
        requested_date="2026-06-05",
        as_of_utc="2026-06-05T21:00:00+00:00",
        freshness="fresh",
        expected_sessions=["2026-06-05"],
        missing_sessions=[],
        allowed_missing_sessions=["2026-07-04"],
        provider_errors={"futu": "futu-api not installed"},
        bars=[
            FusedMarketBar(
                date="2026-06-05",
                timestamp="2026-06-05T00:00:00+00:00",
                open=14.0,
                high=15.0,
                low=13.0,
                close=14.5,
                volume=140.0,
                source="yfinance",
            )
        ],
    )

    text = format_fused_market_snapshot(snapshot)

    assert "# Market snapshot for AAPL" in text
    assert "Coverage: 1/1 expected sessions (100.00%)" in text
    assert "Allowed missing sessions: 2026-07-04" in text
    assert "futu-api not installed" in text
    assert "## Fused OHLCV Chart" in text
    assert "| date | open | high | low | close | volume | source |" in text
    assert "| 2026-06-05 | 14.0000 | 15.0000 | 13.0000 | 14.5000 | 140 | yfinance |" in text
