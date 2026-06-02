import asyncio
import pytest
from unittest.mock import MagicMock
from web.server import price_feed
from web.server.tests.fixtures.fake_yfinance import make_fake_download


def _make_yf_mock(*, download=None):
    """Build a stand-in for the ``yf`` module: ``download`` plus a no-op ``Ticker``."""
    fast_info = MagicMock()
    fast_info.get.return_value = 0.0
    ticker = MagicMock()
    ticker.fast_info = fast_info
    attrs = {"Ticker": staticmethod(lambda _t: ticker)}
    if download is not None:
        attrs["download"] = staticmethod(download)
    return type("M", (), attrs)


@pytest.mark.asyncio
async def test_first_poll_updates_snapshot(monkeypatch):
    snapshot = price_feed.PriceSnapshot(price=0.0, prev_close=0.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snapshot}, tickers=lambda: ["NVDA"])
    fake = make_fake_download({"NVDA": [110.0, 111.0, 112.4]})
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(download=fake))

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
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(download=bad_download))

    await price_feed._poll_once(state, broadcast=lambda e: None)
    # on total failure, snapshots are unchanged but no exception propagates
    assert state.snapshots["NVDA"].price == 200.0
    assert state.snapshots["BAD"].price == 100.0


@pytest.mark.asyncio
async def test_missing_ticker_marks_stale(monkeypatch):
    snap = price_feed.PriceSnapshot(price=50.0, prev_close=50.0, change_pct=0.0, sparkline=[50.0])
    state = price_feed.PriceState(snapshots={"NVDA": snap, "BAD": price_feed.PriceSnapshot(0,0,0,[])}, tickers=lambda: ["NVDA", "BAD"])
    fake = make_fake_download({"NVDA": [50.0, 51.0]})  # no "BAD"
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(download=fake))

    broadcasts = []
    await price_feed._poll_once(state, broadcast=lambda e: broadcasts.append(e))
    assert state.snapshots["NVDA"].price == 51.0
    assert state.snapshots["BAD"].stale is True


"""Tests for change_pct computation added in Task 1."""
from unittest.mock import MagicMock


def _make_broadcast():
    """Returns (calls, broadcast_fn). Each call appends the event dict."""
    calls = []
    def broadcast(evt):
        calls.append(evt)
    return calls, broadcast


def _patch_yfinance(monkeypatch, *, previous_close: float, last_price: float, intraday: list[float] | None = None):
    """Patch yfinance so the poll loop sees a known state.

    - ``previous_close`` is what ``fast_info.get("previousClose")`` returns.
    - ``last_price`` is the last value of the intraday series (overrides ``intraday``).
    - ``intraday`` is the full intraday series; defaults to ``[last_price]``.
    """
    if intraday is None:
        intraday = [last_price]
    df = MagicMock()
    # df["NVDA"]["Close"] -> Series-like
    series = MagicMock()
    series.empty = False
    series.dropna.return_value.tail.return_value = intraday
    df.__getitem__.return_value.__getitem__.return_value = series

    fast_info = MagicMock()
    fast_info.get.return_value = previous_close
    ticker = MagicMock()
    ticker.fast_info = fast_info
    monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)
    monkeypatch.setattr("web.server.price_feed.yf.download", lambda **kw: df)
    return df


@pytest.mark.unit
class TestComputeChangePct:
    def test_change_pct_is_computed_from_previous_close(self, monkeypatch):
        """The regression test: change_pct must come from previousClose, not the default 0.0."""
        _patch_yfinance(monkeypatch, previous_close=100.0, last_price=103.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        assert len(calls) == 1
        assert calls[0]["data"]["change_pct"] == pytest.approx(3.0)

    def test_change_pct_is_zero_when_previous_close_is_zero(self, monkeypatch):
        _patch_yfinance(monkeypatch, previous_close=0.0, last_price=103.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_is_zero_when_price_series_is_empty(self, monkeypatch):
        df = MagicMock()
        series = MagicMock()
        series.empty = True
        df.__getitem__.return_value.__getitem__.return_value = series
        fast_info = MagicMock()
        fast_info.get.return_value = 100.0
        ticker = MagicMock()
        ticker.fast_info = fast_info
        monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)
        monkeypatch.setattr("web.server.price_feed.yf.download", lambda **kw: df)

        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["stale"] is True
        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_handles_negative_change(self, monkeypatch):
        _patch_yfinance(monkeypatch, previous_close=100.0, last_price=97.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] == pytest.approx(-3.0)

    def test_price_update_event_uses_real_change_pct_not_default(self, monkeypatch):
        """Final regression test: a positive previousClose and a positive last_price must yield a non-zero change_pct."""
        _patch_yfinance(monkeypatch, previous_close=200.0, last_price=210.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()
        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] != 0.0
        assert calls[0]["data"]["change_pct"] == pytest.approx(5.0)
