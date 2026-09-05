from datetime import date

import pytest

from tradingagents.research_platform.data_contracts import InstrumentIdentity
from tradingagents.research_platform.legacy_provider import (
    DataUnavailableError,
    LegacyDataflowProvider,
)


def test_legacy_provider_normalizes_price_bars_and_filters_as_of_date():
    raw_prices = """# Stock data for NVDA from 2026-01-02 to 2026-01-03
# Total records: 2

Date,Open,High,Low,Close,Adj Close,Volume
2026-01-02,100,105,99,104,104,1000
2026-01-03,104,106,103,105,105,2000
"""
    provider = LegacyDataflowProvider(price_fetcher=lambda *_args: raw_prices)
    identity = InstrumentIdentity(symbol="NVDA", currency="USD")

    bars = provider.get_price_bars(
        identity,
        date(2026, 1, 2),
        date(2026, 1, 3),
        as_of_date=date(2026, 1, 2),
    )

    assert len(bars) == 1
    assert bars[0].date == date(2026, 1, 2)
    assert bars[0].close == 104
    assert bars[0].volume == 1000
    assert bars[0].provenance.source == "legacy:dataflows.get_stock_data"


def test_legacy_provider_normalizes_fundamentals_snapshot():
    raw_fundamentals = """# Company Fundamentals for NVDA
# Data retrieved on: 2026-01-05 10:00:00

Name: NVIDIA Corporation
Market Cap: 3000000000000
PE Ratio (TTM): 42.5
Sector: Technology
"""
    provider = LegacyDataflowProvider(fundamentals_fetcher=lambda *_args: raw_fundamentals)
    identity = InstrumentIdentity(symbol="NVDA", currency="USD")

    snapshots = provider.get_fundamentals(identity, as_of_date=date(2026, 1, 5))

    assert len(snapshots) == 1
    assert snapshots[0].metrics["name"] == "NVIDIA Corporation"
    assert snapshots[0].metrics["market_cap"] == 3000000000000
    assert snapshots[0].metrics["pe_ratio_ttm"] == 42.5
    assert snapshots[0].period_end == date(2026, 1, 5)


def test_legacy_provider_normalizes_news_items():
    raw_news = """## NVDA News, from 2026-01-01 to 2026-01-05:

### Nvidia announces new platform (source: Example News)
Short article summary.
Link: https://example.com/nvda-platform

### Analysts raise target (source: Market Desk)
Another summary line.

"""
    provider = LegacyDataflowProvider(news_fetcher=lambda *_args: raw_news)
    identity = InstrumentIdentity(symbol="NVDA")

    items = provider.get_news(
        identity,
        date(2026, 1, 1),
        date(2026, 1, 5),
        as_of_date=date(2026, 1, 5),
    )

    assert len(items) == 2
    assert items[0].title == "Nvidia announces new platform"
    assert items[0].provider == "Example News"
    assert items[0].url == "https://example.com/nvda-platform"
    assert items[0].summary == "Short article summary."
    assert items[0].source_id.startswith("legacy-news:")


def test_legacy_provider_returns_empty_news_when_legacy_reports_none():
    provider = LegacyDataflowProvider(news_fetcher=lambda *_args: "No news found for NVDA")
    identity = InstrumentIdentity(symbol="NVDA")

    items = provider.get_news(identity, date(2026, 1, 1), date(2026, 1, 5))

    assert items == []


def test_legacy_provider_raises_on_explicit_no_data_sentinel():
    provider = LegacyDataflowProvider(
        price_fetcher=lambda *_args: "NO_DATA_AVAILABLE: No usable market data for 'BAD'"
    )
    identity = InstrumentIdentity(symbol="BAD")

    with pytest.raises(DataUnavailableError):
        provider.get_price_bars(identity, date(2026, 1, 1), date(2026, 1, 5))
