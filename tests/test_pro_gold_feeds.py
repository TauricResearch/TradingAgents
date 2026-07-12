"""Gold feeds against injected OHLCV frames (no network, no cache)."""

import pytest

from tests.pro_fakes import make_ohlcv_frame
from tradingagents.contracts import Timeframe
from tradingagents.dataflows.errors import NoMarketDataError
from tradingagents.pro.ingestion.gold_feeds import GoldCrossAssetFeed, YFinanceDailyBarsFeed

FRAMES = {
    "GC=F": make_ohlcv_frame(n=40, start_price=2400.0),
    "SI=F": make_ohlcv_frame(n=40, start_price=29.0),
    "DX-Y.NYB": make_ohlcv_frame(n=5, start_price=104.0),
    "^TNX": make_ohlcv_frame(n=5, start_price=42.0),
    "^GVZ": make_ohlcv_frame(n=5, start_price=24.0),
}


def fake_loader(symbol, curr_date):
    if symbol not in FRAMES:
        raise NoMarketDataError(symbol, detail="unknown test symbol")
    return FRAMES[symbol]


def make_feed() -> YFinanceDailyBarsFeed:
    return YFinanceDailyBarsFeed(loader=fake_loader)


def test_frame_becomes_daily_bars():
    bars = make_feed().get_bars("GC=F", Timeframe.D1, limit=10)
    assert len(bars) == 10
    assert bars[-1].timeframe is Timeframe.D1
    assert bars[-1].start.tzinfo is not None
    assert bars[0].close < bars[-1].close


def test_intraday_timeframe_rejected():
    with pytest.raises(ValueError, match="daily bars only"):
        make_feed().get_bars("GC=F", Timeframe.H1)


def test_empty_frame_raises_no_market_data():
    import pandas as pd

    feed = YFinanceDailyBarsFeed(loader=lambda s, d: pd.DataFrame())
    with pytest.raises(NoMarketDataError):
        feed.get_bars("GC=F", Timeframe.D1)


def test_cross_asset_metrics():
    readings = {r.name: r for r in GoldCrossAssetFeed(make_feed(), correlation_window=30).get_metrics()}

    # gold and silver test frames both rise linearly -> correlation 1.0
    assert readings["XAU_XAG_CORR_30D"].value == pytest.approx(1.0)
    assert readings["DXY"].value == pytest.approx(FRAMES["DX-Y.NYB"]["Close"].iloc[-1])
    # ^TNX quotes yield*10 -> adapter divides by 10
    # fixture uses the legacy x10 convention (42.x) -> scaled down
    assert readings["US10Y"].value == pytest.approx(FRAMES["^TNX"]["Close"].iloc[-1] / 10.0)
    assert readings["US10Y"].unit == "percent"


def test_us10y_modern_percent_quotes_pass_through():
    """Yahoo now serves ^TNX in percent directly (4.57) — no /10."""
    frames = dict(FRAMES)
    frames["^TNX"] = make_ohlcv_frame(n=5, start_price=4.2)
    feed = GoldCrossAssetFeed(
        YFinanceDailyBarsFeed(loader=lambda s, d: frames[s]), correlation_window=3
    )
    readings = {r.name: r for r in feed.get_metrics()}
    # passed through untouched (no /10): equals the raw close
    assert readings["US10Y"].value == pytest.approx(
        frames["^TNX"]["Close"].iloc[-1]
    )


def test_correlation_window_lower_bound():
    with pytest.raises(ValueError, match=">= 3"):
        GoldCrossAssetFeed(make_feed(), correlation_window=2)
