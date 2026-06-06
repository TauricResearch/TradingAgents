"""Data ingestion: vendor -> DB (the extraction layer of the wiki data-layer).

The fork's ``dataflows`` return CSV/text formatted for LLM prompts. This package
is the *structured* path that populates the DB: it fetches OHLCV bars and writes
them through to ``price_bars`` (DB-first, check-presence to avoid re-downloading
immutable history), and computes the deterministic screening score that backs
the funnel (writes ``ticker_card``).

The fetch is abstracted behind ``PriceFetcher`` so the ingestion logic is unit
tested offline; ``YFinanceFetcher`` is the real adapter.
"""

from .price_ingest import (
    IngestResult,
    PriceFetcher,
    YFinanceFetcher,
    ingest_price_bars,
)
from .news_ingest import (
    NewsFetcher,
    NewsIngestResult,
    YFinanceNewsFetcher,
    ingest_news,
)
from .fundamentals_ingest import (
    FundamentalsFetcher,
    YFinanceFundamentalsFetcher,
    ingest_fundamentals,
)
from .macro_ingest import (
    DEFAULT_MACRO_SERIES,
    FredFetcher,
    MacroFetcher,
    ingest_macro,
)
from .screening import compute_screening_signals, screen_ticker

__all__ = [
    "IngestResult",
    "PriceFetcher",
    "YFinanceFetcher",
    "ingest_price_bars",
    "NewsFetcher",
    "NewsIngestResult",
    "YFinanceNewsFetcher",
    "ingest_news",
    "FundamentalsFetcher",
    "YFinanceFundamentalsFetcher",
    "ingest_fundamentals",
    "DEFAULT_MACRO_SERIES",
    "FredFetcher",
    "MacroFetcher",
    "ingest_macro",
    "compute_screening_signals",
    "screen_ticker",
]
