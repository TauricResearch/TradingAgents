from datetime import date, datetime, timezone

import pandas as pd
import pytest

from tradingagents.research_platform import yfinance_provider as yp
from tradingagents.research_platform.data_contracts import InstrumentIdentity
from tradingagents.research_platform.yfinance_provider import (
    YFinanceDataUnavailableError,
    YFinanceProvider,
)


class FakeTicker:
    def __init__(
        self,
        *,
        history=None,
        info=None,
        news=None,
        history_error=None,
        info_error=None,
        news_error=None,
    ):
        self._history = history if history is not None else pd.DataFrame()
        self._info = info if info is not None else {}
        self._news = news if news is not None else []
        self._history_error = history_error
        self._info_error = info_error
        self._news_error = news_error
        self.history_calls = []
        self.news_calls = []

    @property
    def info(self):
        if self._info_error is not None:
            raise self._info_error
        return self._info

    def history(self, **kwargs):
        self.history_calls.append(kwargs)
        if self._history_error is not None:
            raise self._history_error
        return self._history

    def get_news(self, **kwargs):
        self.news_calls.append(kwargs)
        if self._news_error is not None:
            raise self._news_error
        return self._news


def test_yfinance_provider_normalizes_price_bars_and_uses_inclusive_end():
    frame = pd.DataFrame(
        {
            "Open": [100.0, 104.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 103.0],
            "Close": [104.0, 105.0],
            "Adj Close": [103.5, 104.5],
            "Volume": [1000, 2000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    fake = FakeTicker(history=frame)
    provider = YFinanceProvider(ticker_factory=lambda symbol: fake)
    identity = InstrumentIdentity(symbol="NVDA", currency="USD")

    bars = provider.get_price_bars(identity, date(2026, 1, 2), date(2026, 1, 3))

    assert fake.history_calls[0]["start"] == "2026-01-02"
    assert fake.history_calls[0]["end"] == "2026-01-04"
    assert len(bars) == 2
    assert bars[0].close == 104.0
    assert bars[0].adjusted_close == 103.5
    assert bars[0].provenance.provider == "yfinance"
    assert bars[0].provenance.vendor_symbol == "NVDA"


def test_yfinance_provider_filters_price_bars_after_as_of_date():
    frame = pd.DataFrame(
        {
            "Open": [100.0, 104.0],
            "High": [105.0, 106.0],
            "Low": [99.0, 103.0],
            "Close": [104.0, 105.0],
            "Volume": [1000, 2000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    provider = YFinanceProvider(ticker_factory=lambda symbol: FakeTicker(history=frame))
    identity = InstrumentIdentity(symbol="NVDA")

    bars = provider.get_price_bars(
        identity,
        date(2026, 1, 2),
        date(2026, 1, 3),
        as_of_date=date(2026, 1, 2),
    )

    assert [bar.date for bar in bars] == [date(2026, 1, 2)]


def test_yfinance_provider_raises_when_price_data_is_empty():
    provider = YFinanceProvider(ticker_factory=lambda symbol: FakeTicker(history=pd.DataFrame()))
    identity = InstrumentIdentity(symbol="MISSING")

    with pytest.raises(YFinanceDataUnavailableError):
        provider.get_price_bars(identity, date(2026, 1, 1), date(2026, 1, 5))


def test_yfinance_provider_wraps_history_errors():
    provider = YFinanceProvider(
        ticker_factory=lambda symbol: FakeTicker(history_error=RuntimeError("rate limited"))
    )
    identity = InstrumentIdentity(symbol="NVDA")

    with pytest.raises(YFinanceDataUnavailableError, match="price data unavailable"):
        provider.get_price_bars(identity, date(2026, 1, 1), date(2026, 1, 5))


def test_yfinance_provider_normalizes_fundamentals_snapshot():
    fake = FakeTicker(
        info={
            "longName": "NVIDIA Corporation",
            "sector": "Technology",
            "marketCap": 3000000000000,
            "trailingPE": 42.5,
            "currency": "USD",
            "irrelevantNested": {"x": 1},
        }
    )
    provider = YFinanceProvider(ticker_factory=lambda symbol: fake)
    identity = InstrumentIdentity(symbol="NVDA")

    snapshots = provider.get_fundamentals(identity, as_of_date=date(2026, 1, 5))

    assert len(snapshots) == 1
    assert snapshots[0].metrics["name"] == "NVIDIA Corporation"
    assert snapshots[0].metrics["market_cap"] == 3000000000000
    assert snapshots[0].metrics["pe_ratio_ttm"] == 42.5
    assert "irrelevantNested" not in snapshots[0].metrics
    assert snapshots[0].currency == "USD"


def test_yfinance_provider_wraps_fundamental_errors():
    provider = YFinanceProvider(
        ticker_factory=lambda symbol: FakeTicker(info_error=RuntimeError("temporarily blocked"))
    )
    identity = InstrumentIdentity(symbol="NVDA")

    with pytest.raises(YFinanceDataUnavailableError, match="fundamentals unavailable"):
        provider.get_fundamentals(identity, as_of_date=date(2026, 1, 5))


def test_yfinance_provider_normalizes_nested_and_flat_news():
    nested = {
        "content": {
            "title": "Nvidia launches research platform",
            "summary": "A concise summary.",
            "provider": {"displayName": "Example News"},
            "canonicalUrl": {"url": "https://example.com/nested"},
            "pubDate": "2026-01-04T15:30:00Z",
        }
    }
    flat = {
        "title": "Analysts update targets",
        "summary": "Flat summary.",
        "publisher": "Market Desk",
        "link": "https://example.com/flat",
        "providerPublishTime": int(
            datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc).timestamp()
        ),
    }
    fake = FakeTicker(news=[nested, flat])
    provider = YFinanceProvider(ticker_factory=lambda symbol: fake, news_limit=7)
    identity = InstrumentIdentity(symbol="NVDA")

    items = provider.get_news(
        identity,
        date(2026, 1, 1),
        date(2026, 1, 5),
        as_of_date=date(2026, 1, 5),
    )

    assert fake.news_calls[0]["count"] == 7
    assert len(items) == 2
    assert items[0].title == "Nvidia launches research platform"
    assert items[0].provider == "Example News"
    assert items[0].published_at == datetime(2026, 1, 4, 15, 30, tzinfo=timezone.utc)
    assert items[1].provider == "Market Desk"
    assert items[1].source_id.startswith("yfinance-news:")


def test_yfinance_provider_wraps_news_errors():
    provider = YFinanceProvider(
        ticker_factory=lambda symbol: FakeTicker(news_error=RuntimeError("rate limited"))
    )
    identity = InstrumentIdentity(symbol="NVDA")

    with pytest.raises(YFinanceDataUnavailableError, match="news unavailable"):
        provider.get_news(identity, date(2026, 1, 1), date(2026, 1, 5))


def test_yfinance_provider_filters_future_news():
    future = {
        "content": {
            "title": "Future article",
            "provider": {"displayName": "Example News"},
            "pubDate": "2026-01-06T15:30:00Z",
        }
    }
    provider = YFinanceProvider(
        ticker_factory=lambda symbol: FakeTicker(news=[future]),
    )
    identity = InstrumentIdentity(symbol="NVDA")

    items = provider.get_news(
        identity,
        date(2026, 1, 1),
        date(2026, 1, 6),
        as_of_date=date(2026, 1, 5),
    )

    assert items == []


def test_yfinance_provider_configures_cache_for_real_factory(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(yp, "_configure_yfinance_cache", lambda cache_dir: called.setdefault("cache_dir", cache_dir))

    provider = yp.YFinanceProvider(cache_dir=tmp_path)

    assert provider.name == "yfinance"
    assert called["cache_dir"] == tmp_path
