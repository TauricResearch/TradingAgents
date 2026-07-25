"""Unit tests for the mootdx (TDX TCP 7709) A-share OHLCV provider."""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from tradingagents.dataflows import mootdx_provider
from tradingagents.dataflows.china_data import ChinaDataUnavailableError


def _make_bars(n: int, start: str = "2026-06-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": [10.0] * n,
            "close": [10.5] * n,
            "high": [11.0] * n,
            "low": [9.5] * n,
            "vol": [1000.0] * n,
            "amount": [10000.0] * n,
            "volume": [1000.0] * n,
            "datetime": [d.strftime("%Y-%m-%d 15:00") for d in dates],
        }
    )


class _FakeClient:
    """Mimics mootdx StdQuotes.bars with pagination semantics."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars
        self.calls: list[tuple[int, int]] = []

    def bars(self, symbol="000001", frequency=9, start=0, offset=800, **kwargs):
        self.calls.append((start, offset))
        if start >= len(self._bars):
            return pd.DataFrame()
        return self._bars.iloc[start : start + offset].copy()


def _install_fake_mootdx(monkeypatch, clients: list) -> None:
    """Make Quotes.factory return the given clients in order."""
    clients_iter = iter(clients)

    class _FakeQuotes:
        def factory(self, market="std", **kwargs):
            return next(clients_iter)

    fake_quotes = types.SimpleNamespace(Quotes=_FakeQuotes())
    fake_mootdx = types.SimpleNamespace(quotes=fake_quotes)
    monkeypatch.setitem(sys.modules, "mootdx", fake_mootdx)
    monkeypatch.setitem(sys.modules, "mootdx.quotes", fake_quotes)


def _patch_tcp_ok(monkeypatch) -> None:
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

    monkeypatch.setattr(mootdx_provider.socket, "create_connection", lambda *a, **kw: _Ctx())


@pytest.fixture(autouse=True)
def _reset_cache():
    mootdx_provider._reset_tdx_client_cache()
    yield
    mootdx_provider._reset_tdx_client_cache()


def test_format_mootdx_daily_maps_columns_and_truncates_time():
    raw = _make_bars(3, "2026-07-20")
    formatted = mootdx_provider._format_mootdx_daily(raw)

    assert list(formatted.columns) == ["Date", "Open", "High", "Low", "Close", "Volume", "Amount"]
    assert formatted["Date"].iloc[0] == "2026-07-20"
    assert formatted["Date"].iloc[1] == "2026-07-21"
    # The raw 'volume' column must not leak through alongside renamed 'vol'.
    assert "volume" not in formatted.columns


def test_fetch_all_bars_paginates_until_enough():
    bars = _make_bars(1000)  # > 800, needs 2 pages
    client = _FakeClient(bars)

    result = mootdx_provider._fetch_all_bars(client, "000001")

    assert client.calls == [(0, 800), (800, 800)]
    assert len(result) == 1000


def test_fetch_all_bars_stops_when_page_is_short():
    bars = _make_bars(500)  # < 800, single page, stop
    client = _FakeClient(bars)

    result = mootdx_provider._fetch_all_bars(client, "000001")

    assert client.calls == [(0, 800)]
    assert len(result) == 500


def test_get_stock_mootdx_df_filters_date_window(monkeypatch):
    bars = _make_bars(60, "2026-05-01")  # 2026-05-01 .. 2026-06-29
    _install_fake_mootdx(monkeypatch, [_FakeClient(bars)])
    _patch_tcp_ok(monkeypatch)

    df = mootdx_provider.get_stock_mootdx_df("000001", "2026-05-10", "2026-05-20")

    assert df["Date"].iloc[0] >= "2026-05-10"
    assert df["Date"].iloc[-1] <= "2026-05-20"


def test_get_stock_mootdx_df_rejects_non_a_share():
    with pytest.raises(ChinaDataUnavailableError, match="not recognized as an A-share"):
        mootdx_provider.get_stock_mootdx_df("AAPL", "2026-01-01", "2026-07-01")


def test_get_stock_mootdx_df_raises_when_no_bars(monkeypatch):
    _install_fake_mootdx(monkeypatch, [_FakeClient(pd.DataFrame())])
    _patch_tcp_ok(monkeypatch)

    # The empty client is skipped by tdx_client (validation fails), so all
    # servers are exhausted and the vendor is unavailable.
    with pytest.raises(ChinaDataUnavailableError, match="No mootdx/TDX server"):
        mootdx_provider.get_stock_mootdx_df("000001", "2026-01-01", "2026-07-01")


def test_tdx_client_skips_false_positive_server(monkeypatch):
    """A server that handshakes but returns empty bars is skipped for the next."""
    bars = _make_bars(5)
    # First client: empty bars (false-positive handshake). Second: real bars.
    empty_client = _FakeClient(pd.DataFrame())
    good_client = _FakeClient(bars)
    _install_fake_mootdx(monkeypatch, [empty_client, good_client] + [_FakeClient(bars)] * 8)
    _patch_tcp_ok(monkeypatch)

    client = mootdx_provider.tdx_client()

    assert client is good_client
    # The empty server's validation fetch happened, then the good server won.
    assert empty_client.calls == [(0, 1)]
    assert good_client.calls == [(0, 1)]


def test_tdx_client_caches_valid_client(monkeypatch):
    bars = _make_bars(5)
    factory_calls = []

    class _FakeQuotes:
        def factory(self, market="std", **kwargs):
            factory_calls.append(kwargs)
            return _FakeClient(bars)

    fake_quotes = types.SimpleNamespace(Quotes=_FakeQuotes())
    monkeypatch.setitem(sys.modules, "mootdx", types.SimpleNamespace(quotes=fake_quotes))
    monkeypatch.setitem(sys.modules, "mootdx.quotes", fake_quotes)
    _patch_tcp_ok(monkeypatch)

    first = mootdx_provider.tdx_client()
    second = mootdx_provider.tdx_client()

    assert first is second
    assert len(factory_calls) == 1  # cached, not re-probed


def test_tdx_client_raises_when_all_servers_empty(monkeypatch):
    _install_fake_mootdx(monkeypatch, [_FakeClient(pd.DataFrame())] * 10)
    _patch_tcp_ok(monkeypatch)

    with pytest.raises(ChinaDataUnavailableError, match="No mootdx/TDX server"):
        mootdx_provider.tdx_client()
