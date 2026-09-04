from types import SimpleNamespace

import pandas as pd
import pytest

import tradingagents.dataflows.stockstats_utils as stockstats
import tradingagents.dataflows.y_finance as yfinance_data
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _bars(dates=("2026-08-25",), closes=(102,)):
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates, utc=True),
            "Open": [100] * len(dates),
            "High": [103] * len(dates),
            "Low": [99] * len(dates),
            "Close": list(closes),
            "Volume": [1100] * len(dates),
        }
    )


@pytest.mark.unit
def test_load_ohlcv_does_not_try_alpaca_when_opt_in_is_false(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": False},
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("Yahoo down")),
    )
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: pytest.fail("Alpaca must remain disabled"),
    )

    with pytest.raises(OSError, match="Yahoo down"):
        stockstats.load_ohlcv("AAPL", "2026-08-25")


@pytest.mark.unit
def test_load_ohlcv_prefers_alpaca_before_yahoo(monkeypatch, tmp_path):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: pytest.fail("Yahoo fallback was not needed"),
    )
    monkeypatch.setattr(stockstats, "_fetch_alpaca_ohlcv", lambda *_: _bars())

    result = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert result["Close"].tolist() == [102]


@pytest.mark.unit
def test_load_ohlcv_falls_back_without_logging_alpaca_error_details(
    monkeypatch, tmp_path, caplog
):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    yahoo = _bars().set_index("Date")
    monkeypatch.setattr(stockstats.yf, "download", lambda *_args, **_kwargs: yahoo)
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: (_ for _ in ()).throw(
            NoMarketDataError("AAPL", detail="upstream included do-not-leak-this")
        ),
    )

    result = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert result["Close"].tolist() == [102]
    assert "do-not-leak-this" not in caplog.text


@pytest.mark.unit
def test_load_ohlcv_raises_typed_error_when_alpaca_and_yahoo_are_empty(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(stockstats.yf, "download", lambda *_args, **_kwargs: pd.DataFrame())
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: (_ for _ in ()).throw(NoMarketDataError("AAPL", detail="empty feed")),
    )

    with pytest.raises(NoMarketDataError, match="returned no rows"):
        stockstats.load_ohlcv("AAPL", "2026-08-25")


@pytest.mark.unit
def test_stock_data_falls_back_when_alpaca_bars_are_stale(monkeypatch):
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: True)
    yahoo = _bars().set_index("Date")
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _symbol: SimpleNamespace(history=lambda **_: yahoo),
    )
    monkeypatch.setattr(
        yfinance_data,
        "_fetch_alpaca_ohlcv",
        lambda *_: _bars(("2025-01-01",), (50,)),
    )

    result = yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")

    assert "102" in result
    assert "50" not in result


@pytest.mark.unit
def test_stock_data_does_not_try_alpaca_when_opt_in_is_false(monkeypatch):
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: False)
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _: SimpleNamespace(
            history=lambda **_: (_ for _ in ()).throw(OSError("Yahoo down"))
        ),
    )
    monkeypatch.setattr(
        yfinance_data,
        "_fetch_alpaca_ohlcv",
        lambda *_: pytest.fail("Alpaca must remain disabled"),
    )

    with pytest.raises(OSError, match="Yahoo down"):
        yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")


@pytest.mark.unit
def test_stock_data_prefers_alpaca_before_yahoo(monkeypatch):
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: True)
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _: pytest.fail("Yahoo fallback was not needed"),
    )
    monkeypatch.setattr(yfinance_data, "_fetch_alpaca_ohlcv", lambda *_: _bars())

    result = yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")

    assert "# Stock data for AAPL" in result
    assert "102" in result


@pytest.mark.unit
def test_stock_data_uses_yahoo_for_non_equity_symbols_even_when_enabled(monkeypatch):
    monkeypatch.setattr(stockstats, "get_config", lambda: {"use_alpaca_market_data": True})
    yahoo = _bars().set_index("Date")
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _symbol: SimpleNamespace(history=lambda **_: yahoo),
    )
    monkeypatch.setattr(
        yfinance_data,
        "_fetch_alpaca_ohlcv",
        lambda *_: pytest.fail("Yahoo-native crypto symbols are not Alpaca equities"),
    )

    result = yfinance_data.get_YFin_data_online("BTCUSD", "2026-08-25", "2026-08-25")

    assert "BTC-USD (from BTCUSD)" in result


@pytest.mark.unit
def test_fetch_alpaca_ohlcv_normalizes_inclusive_utc_bars(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-value")
    frame = _bars(("2026-08-24", "2026-08-25"), (101, 102)).set_index("Date")
    frame.index.name = "timestamp"
    captured = {}

    def get_stock_bars(request):
        captured["request"] = request
        return SimpleNamespace(df=frame)

    client = SimpleNamespace(get_stock_bars=get_stock_bars)

    result = stockstats._fetch_alpaca_ohlcv(
        "AAPL", "2026-08-24", "2026-08-25", client=client
    )

    assert result.columns.tolist() == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert result["Date"].tolist() == [pd.Timestamp("2026-08-24"), pd.Timestamp("2026-08-25")]
    assert captured["request"].symbol_or_symbols == "AAPL"
    assert captured["request"].timeframe.value == "1Day"
    assert captured["request"].feed.value == "iex"
    assert captured["request"].start == pd.Timestamp("2026-08-24")
    assert captured["request"].end == pd.Timestamp("2026-08-26")


@pytest.mark.unit
def test_fetch_alpaca_ohlcv_rejects_empty_and_malformed_frames(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-value")

    for frame, detail in (
        (pd.DataFrame(), "no daily bars"),
        (None, "malformed"),
        (pd.DataFrame({"timestamp": ["2026-08-25"], "close": [102]}), "malformed"),
    ):
        client = SimpleNamespace(
            get_stock_bars=lambda _request, frame=frame: SimpleNamespace(df=frame)
        )
        with pytest.raises(NoMarketDataError, match=detail):
            stockstats._fetch_alpaca_ohlcv(
                "AAPL", "2026-08-25", "2026-08-25", client=client
            )


@pytest.mark.unit
def test_fetch_alpaca_ohlcv_missing_credentials_does_not_expose_values(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "do-not-leak-this")

    with pytest.raises(NoMarketDataError) as caught:
        stockstats._fetch_alpaca_ohlcv("AAPL", "2026-08-25", "2026-08-25")

    assert "do-not-leak-this" not in str(caught.value)
