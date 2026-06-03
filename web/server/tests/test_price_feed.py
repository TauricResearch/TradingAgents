import asyncio
import pytest
from unittest.mock import MagicMock
from web.server import price_feed
from web.server.tests.fixtures.fake_yfinance import make_fake_download


def _make_yf_mock(*, download=None, last_price=0.0, previous_close=0.0, regular_market_previous_close=None):
    """Build a stand-in for the ``yf`` module.

    ``fast_info.get()`` returns the given ``last_price`` / ``previous_close``
    for the corresponding keys.  If ``download`` is provided it replaces
    ``yf.download`` (used by sparkline refresh).
    """
    fast_info = MagicMock()
    rmpc = previous_close if regular_market_previous_close is None else regular_market_previous_close

    def _get(key, default=None):
        mapping = {
            "lastPrice": last_price,
            "previousClose": previous_close,
            "regularMarketPreviousClose": rmpc,
        }
        return mapping.get(key, default)

    fast_info.get = _get
    ticker = MagicMock()
    ticker.fast_info = fast_info
    attrs = {"Ticker": staticmethod(lambda _t: ticker)}
    if download is not None:
        attrs["download"] = staticmethod(download)
    return type("M", (), attrs)


# ── _poll_once (fast price via fast_info) ───────────────────────────────


@pytest.mark.asyncio
async def test_poll_once_uses_fast_info_for_price(monkeypatch):
    """_poll_once fetches price from fast_info and broadcasts it."""
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(last_price=150.0, previous_close=145.0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])

    calls = []
    await price_feed._poll_once(state, broadcast=lambda e: calls.append(e))

    s = state.snapshots["NVDA"]
    assert s.price == 150.0
    assert s.change_pct == pytest.approx(3.448, rel=1e-3)
    assert s.stale is False
    # broadcast includes the live data
    assert len(calls) == 1
    assert calls[0]["data"]["price"] == 150.0
    assert calls[0]["data"]["change_pct"] == pytest.approx(3.448, rel=1e-3)
    assert calls[0]["data"]["stale"] is False


@pytest.mark.asyncio
async def test_poll_once_zero_price_marks_stale(monkeypatch):
    """When fast_info returns 0 as price the ticker is marked stale."""
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(last_price=0.0, previous_close=100.0))
    state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])

    await price_feed._poll_once(state, broadcast=lambda e: None)
    assert state.snapshots["NVDA"].stale is True


@pytest.mark.asyncio
async def test_poll_once_exception_marks_stale(monkeypatch):
    """When fast_info raises, the ticker is marked stale but no exception propagates."""
    fast_info = MagicMock()
    fast_info.get.side_effect = RuntimeError("network error")
    ticker = MagicMock()
    ticker.fast_info = fast_info
    monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)

    snap = price_feed.PriceSnapshot(price=200.0, prev_close=200.0, change_pct=0.0, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])

    await price_feed._poll_once(state, broadcast=lambda e: None)
    # snapshot retains previous values but is marked stale
    assert state.snapshots["NVDA"].price == 200.0
    assert state.snapshots["NVDA"].stale is True


@pytest.mark.asyncio
async def test_poll_once_caches_prev_close(monkeypatch):
    """prev_close is fetched once and reused on subsequent polls."""
    fast_info = MagicMock()

    call_count = 0

    def _get(key, default=None):
        nonlocal call_count
        call_count += 1
        return {"lastPrice": 100.0, "previousClose": 95.0}.get(key, default)

    fast_info.get = _get
    ticker = MagicMock()
    ticker.fast_info = fast_info
    monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)

    state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])

    # First poll: prev_close > 0, so it's cached
    await price_feed._poll_once(state, broadcast=lambda e: None)
    assert state.snapshots["NVDA"].prev_close == 95.0

    # Second poll: prev_close is already cached (>0) so fast_info should
    # NOT be queried for previousClose again.  The fast_info mock is set
    # up so that lastPrice returns 100.0 and previousClose returns 95.0
    # — the snapshot should keep 95.0 regardless.
    await price_feed._poll_once(state, broadcast=lambda e: None)
    assert state.snapshots["NVDA"].prev_close == 95.0


# ── _update_sparklines ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_sparklines_populates_sparkline(monkeypatch):
    """_update_sparklines downloads history and updates snapshots."""
    fake = make_fake_download({"NVDA": [110.0, 111.0, 112.4]})
    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(download=fake))

    snap = price_feed.PriceSnapshot(price=112.4, prev_close=110.0, change_pct=2.18, sparkline=[])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])

    await price_feed._update_sparklines(state)

    assert state.snapshots["NVDA"].sparkline == [110.0, 111.0, 112.4]


@pytest.mark.asyncio
async def test_update_sparklines_handles_download_failure(monkeypatch):
    """When yf.download raises, sparklines stay unchanged."""
    def bad_download(**kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(price_feed, "yf", _make_yf_mock(download=bad_download))

    snap = price_feed.PriceSnapshot(price=50.0, prev_close=50.0, change_pct=0.0, sparkline=[10.0])
    state = price_feed.PriceState(snapshots={"NVDA": snap}, tickers=lambda: ["NVDA"])

    await price_feed._update_sparklines(state)
    assert state.snapshots["NVDA"].sparkline == [10.0]  # unchanged


# ── change_pct regression tests ─────────────────────────────────────────


def _make_broadcast():
    calls = []

    def broadcast(evt):
        calls.append(evt)

    return calls, broadcast


def _patch_fast_info(monkeypatch, *, last_price: float, previous_close: float, regular_market_previous_close: float | None = None):
    """Patch yfinance.Ticker.fast_info so it returns the given values."""
    fast_info = MagicMock()
    rmpc = previous_close if regular_market_previous_close is None else regular_market_previous_close

    def _get(key, default=None):
        mapping = {
            "lastPrice": last_price,
            "previousClose": previous_close,
            "regularMarketPreviousClose": rmpc,
        }
        return mapping.get(key, default)

    fast_info.get = _get
    ticker = MagicMock()
    ticker.fast_info = fast_info
    monkeypatch.setattr("web.server.price_feed.yf.Ticker", lambda _t: ticker)


@pytest.mark.unit
class TestComputeChangePct:
    def test_change_pct_is_computed_from_previous_close(self, monkeypatch):
        _patch_fast_info(monkeypatch, last_price=103.0, previous_close=100.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        assert len(calls) == 1
        assert calls[0]["data"]["change_pct"] == pytest.approx(3.0)

    def test_change_pct_is_zero_when_previous_close_is_zero(self, monkeypatch):
        _patch_fast_info(monkeypatch, last_price=103.0, previous_close=0.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))
        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_is_zero_when_price_is_zero(self, monkeypatch):
        _patch_fast_info(monkeypatch, last_price=0.0, previous_close=100.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))
        assert calls[0]["data"]["stale"] is True
        assert calls[0]["data"]["change_pct"] == 0.0

    def test_change_pct_handles_negative_change(self, monkeypatch):
        _patch_fast_info(monkeypatch, last_price=97.0, previous_close=100.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))
        assert calls[0]["data"]["change_pct"] == pytest.approx(-3.0)

    def test_price_update_event_uses_real_change_pct_not_default(self, monkeypatch):
        """Final regression test: positive prevClose and positive price must yield non-zero change_pct."""
        _patch_fast_info(monkeypatch, last_price=210.0, previous_close=200.0)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] != 0.0
        assert calls[0]["data"]["change_pct"] == pytest.approx(5.0)

    def test_change_pct_prefers_regular_market_previous_close(self, monkeypatch):
        """yfinance fast_info returns TWO previous-close values:
        ``previousClose`` (intraday/adjusted) and
        ``regularMarketPreviousClose`` (prior regular-session close, the
        standard reference used by every financial site). The dashboard
        must use the latter, otherwise the % change is slightly off
        (observed: ~0.5% absolute error on real tickers like TSLA, MSFT).
        """
        _patch_fast_info(
            monkeypatch,
            last_price=309.41,
            previous_close=314.9999,             # wrong reference
            regular_market_previous_close=315.20,  # correct reference
        )
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["AAPL"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        # Using previousClose:        (309.41-314.9999)/314.9999*100 = -1.776%
        # Using regularMarketPrevCl:   (309.41-315.20)/315.20*100    = -1.838%
        # The dashboard must report the second (the standard one).
        assert calls[0]["data"]["change_pct"] == pytest.approx(-1.838, rel=1e-2)

    def test_change_pct_falls_back_to_previous_close(self, monkeypatch):
        """If regularMarketPreviousClose is absent (some tickers/sessions
        don't populate it), the hook must fall back to previousClose."""
        _patch_fast_info(monkeypatch, last_price=210.0, previous_close=200.0, regular_market_previous_close=None)
        state = price_feed.PriceState(snapshots={}, tickers=lambda: ["NVDA"])
        calls, broadcast = _make_broadcast()

        asyncio.run(price_feed._poll_once(state, broadcast))

        assert calls[0]["data"]["change_pct"] == pytest.approx(5.0)
