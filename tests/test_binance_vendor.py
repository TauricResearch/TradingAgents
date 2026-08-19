"""Binance vendor: native OHLCV data for crypto assets.

Covers symbol resolution, date-boundary inclusivity (#binance-pagination),
pagination past the 1000-candle-per-request cap, and the
NoMarketDataError contract for unrecognized symbols / empty responses.
"""
import pytest

import tradingagents.dataflows.binance as binance


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _kline_row(date_str, price=50000.0, volume=100.0):
    """Build one Binance-shaped kline row for a given date."""
    import pandas as pd
    open_ms = int(pd.Timestamp(date_str, tz="UTC").timestamp() * 1000)
    return [
        open_ms, str(price), str(price + 10), str(price - 10), str(price + 5),
        str(volume), open_ms + 86399999, "0", 1, "0", "0", "0",
    ]


@pytest.mark.unit
def test_unrecognized_symbol_raises_no_market_data_error():
    with pytest.raises(binance.NoMarketDataError):
        binance.get_binance_stock("NOTACOIN-USD", "2026-06-01", "2026-06-10")


@pytest.mark.unit
def test_empty_response_raises_no_market_data_error(monkeypatch):
    monkeypatch.setattr(
        binance.requests, "get",
        lambda *a, **k: _FakeResponse([]),
    )
    with pytest.raises(binance.NoMarketDataError):
        binance.get_binance_stock("BTC-USD", "2026-06-01", "2026-06-10")


@pytest.mark.unit
def test_normal_path_returns_expected_format(monkeypatch):
    rows = [_kline_row(d) for d in
            ["2026-06-01", "2026-06-02", "2026-06-03"]]
    monkeypatch.setattr(
        binance.requests, "get",
        lambda *a, **k: _FakeResponse(rows),
    )
    result = binance.get_binance_stock("BTC-USD", "2026-06-01", "2026-06-03")
    assert "Total records: 3" in result
    assert "2026-06-03" in result  # end_date must be included
    assert "BTCUSDT" in result


@pytest.mark.unit
def test_end_date_inclusive_even_at_batch_boundary(monkeypatch):
    # Simulate Binance returning one extra day past end_date (the buffered
    # request); the vendor must locally filter it out.
    rows = [_kline_row(d) for d in
            ["2026-06-01", "2026-06-02", "2026-06-03"]]  # 06-03 is the buffer day
    monkeypatch.setattr(
        binance.requests, "get",
        lambda *a, **k: _FakeResponse(rows),
    )
    result = binance.get_binance_stock("BTC-USD", "2026-06-01", "2026-06-02")
    assert "Total records: 2" in result
    assert "2026-06-03" not in result  # buffer day must be filtered out


@pytest.mark.unit
def test_pagination_stops_when_batch_smaller_than_limit(monkeypatch):
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append(params)
        # First call: full page (simulated as MAX_LIMIT rows) triggers a
        # second call; second call returns fewer rows, ending pagination.
        if len(calls) == 1:
            return _FakeResponse(
                [_kline_row(f"2020-01-{d:02d}") for d in range(1, 32)]
                * (binance._MAX_LIMIT // 31 + 1)
            )
        return _FakeResponse([_kline_row("2026-06-01")])

    monkeypatch.setattr(binance.requests, "get", fake_get)
    binance.get_binance_stock("BTC-USD", "2020-01-01", "2026-06-01")
    assert len(calls) == 2  # confirms pagination actually looped


@pytest.mark.unit
def test_symbol_resolution_uses_usdt_pair(monkeypatch):
    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured.update(params)
        return _FakeResponse([_kline_row("2026-06-01")])

    monkeypatch.setattr(binance.requests, "get", fake_get)
    binance.get_binance_stock("BTC-USD", "2026-06-01", "2026-06-01")
    assert captured["symbol"] == "BTCUSDT"