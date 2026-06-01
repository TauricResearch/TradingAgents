import asyncio
import pytest
from web.server import price_feed
from web.server.tests.fixtures.fake_yfinance import make_fake_download


@pytest.mark.asyncio
async def test_first_poll_updates_snapshot(monkeypatch):
    snapshot = price_feed.PriceSnapshot(price=0.0, prev_close=0.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snapshot}, tickers=lambda: ["NVDA"])
    fake = make_fake_download({"NVDA": [110.0, 111.0, 112.4]})
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(fake)}))

    await price_feed._poll_once(state, broadcast=lambda e: None)
    s = state.snapshots["NVDA"]
    assert s.price == 112.4
    assert s.sparkline == [110.0, 111.0, 112.4]
    assert s.stale is False


@pytest.mark.asyncio
async def test_partial_failure_marks_stale(monkeypatch):
    snap_ok = price_feed.PriceSnapshot(price=200.0, prev_close=200.0, change_pct=0.0, sparkline=[])
    snap_bad = price_feed.PriceSnapshot(price=100.0, prev_close=100.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap_ok, "BAD": snap_bad}, tickers=lambda: ["NVDA", "BAD"])

    def bad_download(*args, **kwargs):
        raise RuntimeError("network down")
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(bad_download)}))

    await price_feed._poll_once(state, broadcast=lambda e: None)
    # on total failure, snapshots are unchanged but no exception propagates
    assert state.snapshots["NVDA"].price == 200.0
    assert state.snapshots["BAD"].price == 100.0


@pytest.mark.asyncio
async def test_missing_ticker_marks_stale(monkeypatch):
    snap = price_feed.PriceSnapshot(price=50.0, prev_close=50.0, change_pct=0.0, sparkline=[50.0])
    state = price_feed.PriceState(snapshots={"NVDA": snap, "BAD": price_feed.PriceSnapshot(0,0,0,[])}, tickers=lambda: ["NVDA", "BAD"])
    fake = make_fake_download({"NVDA": [50.0, 51.0]})  # no "BAD"
    monkeypatch.setattr(price_feed, "yf", type("M", (), {"download": staticmethod(fake)}))

    broadcasts = []
    await price_feed._poll_once(state, broadcast=lambda e: broadcasts.append(e))
    assert state.snapshots["NVDA"].price == 51.0
    assert state.snapshots["BAD"].stale is True
