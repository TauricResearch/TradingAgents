from types import SimpleNamespace

import pandas as pd
import pytest

import tradingagents.dataflows.stockstats_utils as stockstats
import tradingagents.dataflows.y_finance as yfinance_data
from tradingagents.dataflows.symbol_utils import NoMarketDataError


def _bars(dates=("2026-08-25",), closes=(102,)):
    closes = list(closes)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates, utc=True),
            "Open": [100] * len(dates),
            "High": [max(100, close) + 1 for close in closes],
            "Low": [min(100, close) - 1 for close in closes],
            "Close": closes,
            "Volume": [1100] * len(dates),
        }
    )


def _cache_name(provider, today):
    start = (today - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    end = (today + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return f"AAPL-{provider}-data-{start}-{end}.csv"


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
def test_load_ohlcv_separates_provider_caches_and_returns_canonical_columns(
    monkeypatch, tmp_path
):
    today = pd.Timestamp("2026-08-25")
    yahoo_cache = tmp_path / _cache_name("YFin", today)
    alpaca_cache = tmp_path / _cache_name("Alpaca-IEX", today)
    _bars(closes=(11,)).to_csv(yahoo_cache, index=False)
    monkeypatch.setattr(stockstats.pd.Timestamp, "today", staticmethod(lambda: today))
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(stockstats, "_fetch_alpaca_ohlcv", lambda *_: _bars())
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: pytest.fail("Yahoo cache must not contaminate Alpaca mode"),
    )

    enabled = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert enabled.columns.tolist() == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert enabled["Close"].tolist() == [102]
    assert alpaca_cache.exists()

    alpaca_cache.write_text(yahoo_cache.read_text())
    yahoo_cache.unlink()
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": False},
    )
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: pytest.fail("Alpaca cache must not contaminate Yahoo mode"),
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: _bars(closes=(103,)).set_index("Date"),
    )

    disabled = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert disabled.columns.tolist() == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert disabled["Close"].tolist() == [103]
    assert yahoo_cache.exists()


@pytest.mark.unit
def test_enabled_mode_retries_alpaca_after_transient_yahoo_fallback(monkeypatch, tmp_path):
    today = pd.Timestamp("2026-08-25")
    alpaca_cache = tmp_path / _cache_name("Alpaca-IEX", today)
    yahoo_cache = tmp_path / _cache_name("YFin", today)
    alpaca_calls = []
    yahoo_calls = []

    monkeypatch.setattr(stockstats.pd.Timestamp, "today", staticmethod(lambda: today))
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )

    def fetch_alpaca(*_args):
        alpaca_calls.append(1)
        if len(alpaca_calls) == 1:
            raise stockstats.AlpacaMarketDataError("AAPL", detail="temporary outage")
        return _bars(closes=(150,))

    monkeypatch.setattr(stockstats, "_fetch_alpaca_ohlcv", fetch_alpaca)
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: yahoo_calls.append(1)
        or _bars(closes=(101,)).set_index("Date"),
    )

    first = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert first["Close"].tolist() == [101]
    assert yahoo_cache.exists()
    assert not alpaca_cache.exists()

    second = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert second["Close"].tolist() == [150]
    assert alpaca_calls == [1, 1]
    assert yahoo_calls == [1]
    assert alpaca_cache.exists()


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
            stockstats.AlpacaMarketDataError(
                "AAPL", detail="upstream included do-not-leak-this"
            )
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
        lambda *_: (_ for _ in ()).throw(
            stockstats.AlpacaMarketDataError("AAPL", detail="empty feed")
        ),
    )

    with pytest.raises(NoMarketDataError, match="returned no daily bars"):
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
    assert "2025-01-01" not in result


@pytest.mark.unit
def test_stock_data_falls_back_when_alpaca_rows_are_malformed(monkeypatch):
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: True)
    yahoo = _bars().set_index("Date")
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _symbol: SimpleNamespace(history=lambda **_: yahoo),
    )
    malformed = _bars()
    malformed.loc[:, "High"] = 1
    monkeypatch.setattr(yfinance_data, "_fetch_alpaca_ohlcv", lambda *_: malformed)

    result = yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")

    assert "102" in result


@pytest.mark.unit
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError])
def test_stock_data_does_not_fallback_on_programmer_errors(monkeypatch, error_type):
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: True)
    monkeypatch.setattr(
        yfinance_data,
        "_fetch_alpaca_ohlcv",
        lambda *_: (_ for _ in ()).throw(error_type("programmer defect")),
    )
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _: pytest.fail("programmer errors must not trigger Yahoo"),
    )

    with pytest.raises(error_type, match="programmer defect"):
        yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")


@pytest.mark.unit
@pytest.mark.parametrize("error_type", [RuntimeError, TypeError])
def test_load_ohlcv_does_not_fallback_on_programmer_errors(
    monkeypatch, tmp_path, error_type
):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: (_ for _ in ()).throw(error_type("programmer defect")),
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: pytest.fail("programmer errors must not trigger Yahoo"),
    )

    with pytest.raises(error_type, match="programmer defect"):
        stockstats.load_ohlcv("AAPL", "2026-08-25")


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
@pytest.mark.parametrize("symbol", ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOG", "TSLA"])
def test_alpaca_market_data_allows_only_approved_symbols(monkeypatch, symbol):
    monkeypatch.setattr(stockstats, "get_config", lambda: {"use_alpaca_market_data": True})

    assert stockstats.use_alpaca_market_data(symbol) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "symbol",
    ["BTC-USD", "SHOP.TO", "VOD.L", "AAPL.US", "VTSAX", "FOOBAR", "BRK-B"],
)
def test_alpaca_market_data_rejects_every_symbol_outside_approved_universe(
    monkeypatch, symbol
):
    monkeypatch.setattr(stockstats, "get_config", lambda: {"use_alpaca_market_data": True})

    assert stockstats.use_alpaca_market_data(symbol) is False


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
def test_fetch_alpaca_ohlcv_rejects_response_with_only_future_rows(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-value")
    future = _bars(("2026-08-26",), (150,)).set_index("Date")
    future.index.name = "timestamp"
    client = SimpleNamespace(get_stock_bars=lambda _request: SimpleNamespace(df=future))

    with pytest.raises(stockstats.AlpacaMarketDataError, match="requested range"):
        stockstats._fetch_alpaca_ohlcv(
            "AAPL", "2026-08-24", "2026-08-25", client=client
        )


@pytest.mark.unit
def test_fetch_alpaca_ohlcv_keeps_only_requested_inclusive_range(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-value")
    mixed = _bars(
        ("2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26"),
        (90, 100, 110, 120),
    ).set_index("Date")
    mixed.index.name = "timestamp"
    client = SimpleNamespace(get_stock_bars=lambda _request: SimpleNamespace(df=mixed))

    result = stockstats._fetch_alpaca_ohlcv(
        "AAPL", "2026-08-24", "2026-08-25", client=client
    )

    assert result["Date"].tolist() == [pd.Timestamp("2026-08-24"), pd.Timestamp("2026-08-25")]
    assert result["Close"].tolist() == [100, 110]


@pytest.mark.unit
def test_load_ohlcv_falls_back_when_alpaca_returns_only_future_rows(
    monkeypatch, tmp_path
):
    today = pd.Timestamp("2026-08-25")
    monkeypatch.setattr(stockstats.pd.Timestamp, "today", staticmethod(lambda: today))
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: _bars(("2026-08-26",), (150,)),
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: _bars(closes=(101,)).set_index("Date"),
    )

    result = stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert result["Close"].tolist() == [101]
    assert (tmp_path / _cache_name("YFin", today)).exists()
    assert not (tmp_path / _cache_name("Alpaca-IEX", today)).exists()


@pytest.mark.unit
def test_load_ohlcv_filters_future_alpaca_rows_before_caching(monkeypatch, tmp_path):
    today = pd.Timestamp("2026-08-25")
    monkeypatch.setattr(stockstats.pd.Timestamp, "today", staticmethod(lambda: today))
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(
        stockstats,
        "_fetch_alpaca_ohlcv",
        lambda *_: _bars(
            ("2026-08-24", "2026-08-25", "2026-08-26"), (100, 110, 120)
        ),
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: pytest.fail("valid in-range Alpaca data must be used"),
    )

    result = stockstats.load_ohlcv("AAPL", "2026-08-25")
    cached = pd.read_csv(tmp_path / _cache_name("Alpaca-IEX", today))

    assert result["Close"].tolist() == [100, 110]
    assert cached["Date"].tolist() == ["2026-08-24", "2026-08-25"]


@pytest.mark.unit
def test_load_ohlcv_falls_back_when_alpaca_rows_are_after_consumer_date(
    monkeypatch, tmp_path
):
    today = pd.Timestamp.today()
    curr_date = (today - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    later_date = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    alpaca_cache = tmp_path / _cache_name("Alpaca-IEX", today)
    yahoo_calls = []

    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )
    monkeypatch.setattr(
        stockstats, "_fetch_alpaca_ohlcv", lambda *_: _bars((later_date,), (150,))
    )
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: yahoo_calls.append(1)
        or _bars((curr_date,), (101,)).set_index("Date"),
    )

    result = stockstats.load_ohlcv("AAPL", curr_date)

    assert result["Close"].tolist() == [101]
    assert yahoo_calls == [1]
    assert not alpaca_cache.exists()


@pytest.mark.unit
def test_stale_alpaca_cache_retries_primary_without_changing_fallback_provenance(
    monkeypatch, tmp_path
):
    today = pd.Timestamp.today()
    curr_date = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    stale_date = (today - pd.Timedelta(days=30)).strftime("%Y-%m-%d")
    alpaca_cache = tmp_path / _cache_name("Alpaca-IEX", today)
    yahoo_cache = tmp_path / _cache_name("YFin", today)
    _bars((stale_date,), (80,)).to_csv(alpaca_cache, index=False)
    alpaca_calls = []
    yahoo_calls = []

    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": True},
    )

    def fetch_alpaca(*_args):
        alpaca_calls.append(1)
        if len(alpaca_calls) == 1:
            raise stockstats.AlpacaMarketDataError("AAPL", detail="temporary outage")
        return _bars((curr_date,), (150,))

    monkeypatch.setattr(stockstats, "_fetch_alpaca_ohlcv", fetch_alpaca)
    monkeypatch.setattr(
        stockstats.yf,
        "download",
        lambda *_args, **_kwargs: yahoo_calls.append(1)
        or _bars((curr_date,), (101,)).set_index("Date"),
    )

    fallback = stockstats.load_ohlcv("AAPL", curr_date)

    assert fallback["Close"].tolist() == [101]
    assert pd.read_csv(alpaca_cache)["Close"].tolist() == [80]
    assert pd.read_csv(yahoo_cache)["Close"].tolist() == [101]

    recovered = stockstats.load_ohlcv("AAPL", curr_date)

    assert recovered["Close"].tolist() == [150]
    assert alpaca_calls == [1, 1]
    assert yahoo_calls == [1]
    assert pd.read_csv(alpaca_cache)["Close"].tolist() == [150]
    assert pd.read_csv(yahoo_cache)["Close"].tolist() == [101]


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
@pytest.mark.parametrize("error_kind", ["api", "timeout", "os"])
def test_fetch_alpaca_ohlcv_translates_network_errors_without_leaking_details(
    monkeypatch, error_kind
):
    from alpaca.common.exceptions import APIError
    from requests.exceptions import Timeout

    monkeypatch.setenv("ALPACA_API_KEY", "key-value")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret-value")
    errors = {
        "api": APIError('{"code": 500, "message": "secret-value"}'),
        "timeout": Timeout("request contained secret-value"),
        "os": OSError("request contained secret-value"),
    }
    client = SimpleNamespace(
        get_stock_bars=lambda _request: (_ for _ in ()).throw(errors[error_kind])
    )

    with pytest.raises(NoMarketDataError) as caught:
        stockstats._fetch_alpaca_ohlcv(
            "AAPL", "2026-08-25", "2026-08-25", client=client
        )

    assert type(caught.value).__name__ == "AlpacaMarketDataError"
    assert "secret-value" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("Open", 0),
        ("High", 101),
        ("Low", 101),
        ("Close", float("inf")),
        ("Volume", -1),
    ],
)
def test_load_ohlcv_rejects_invalid_yahoo_rows_without_caching(
    monkeypatch, tmp_path, column, value
):
    monkeypatch.setattr(
        stockstats,
        "get_config",
        lambda: {"data_cache_dir": str(tmp_path), "use_alpaca_market_data": False},
    )
    invalid = _bars().set_index("Date").astype(float)
    invalid.loc[:, column] = value
    monkeypatch.setattr(stockstats.yf, "download", lambda *_args, **_kwargs: invalid)

    with pytest.raises(NoMarketDataError, match="malformed"):
        stockstats.load_ohlcv("AAPL", "2026-08-25")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.unit
@pytest.mark.parametrize("detail", ["unavailable", "no daily bars", "malformed daily bars"])
def test_stock_data_falls_back_once_for_typed_alpaca_error(monkeypatch, detail):
    yahoo_calls = []
    monkeypatch.setattr(yfinance_data, "use_alpaca_market_data", lambda *_: True)
    monkeypatch.setattr(
        yfinance_data,
        "_fetch_alpaca_ohlcv",
        lambda *_: (_ for _ in ()).throw(
            stockstats.AlpacaMarketDataError(
                "AAPL", detail=f"Alpaca market data is {detail}"
            )
        ),
    )
    monkeypatch.setattr(
        yfinance_data.yf,
        "Ticker",
        lambda _: SimpleNamespace(
            history=lambda **_: yahoo_calls.append(1) or _bars().set_index("Date")
        ),
    )

    result = yfinance_data.get_YFin_data_online("AAPL", "2026-08-25", "2026-08-25")

    assert "102" in result
    assert yahoo_calls == [1]


@pytest.mark.unit
def test_fetch_alpaca_ohlcv_missing_credentials_does_not_expose_values(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.setenv("ALPACA_SECRET_KEY", "do-not-leak-this")

    with pytest.raises(NoMarketDataError) as caught:
        stockstats._fetch_alpaca_ohlcv("AAPL", "2026-08-25", "2026-08-25")

    assert "do-not-leak-this" not in str(caught.value)
