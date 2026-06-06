"""Per-agent tools = the canvas "Extractors set".

The Extractors set is *every* tool that extracts / computes / writes information.
Each AI agent is given all the tools potentially useful to its task and calls
them autonomously during reasoning (or they run on events/recurrences, see the
ingestion layer). A tool **extracts** (real-time-first where a live fetcher is
available), **responds to the agent**, and **writes the relevant info to the DB**
(the single source of truth). With no live fetcher a tool falls back to reading
what the periodical extraction already stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

from langchain_core.tools import StructuredTool
from sqlalchemy.orm import Session

from ..indicators import indicator_snapshot
from ..ingestion import (
    DEFAULT_MACRO_SERIES,
    ingest_fundamentals,
    ingest_macro,
    ingest_news,
    ingest_price_bars,
    ingest_social,
)
from ..storage import repository as repo
from ..tools import get_open_positions_risk, get_realtime_quote, volume_spike
from .context import _headlines, _macro_snapshot, _social


@dataclass
class Extractors:
    """The live fetchers behind the agent tools. All optional (offline -> DB)."""

    price_fetcher: Optional[Any] = None
    news_fetcher: Optional[Any] = None
    fundamentals_fetcher: Optional[Any] = None
    macro_fetcher: Optional[Any] = None
    social_fetcher: Optional[Any] = None
    quote_fn: Optional[Callable[[str], Optional[float]]] = None
    history_start: str = "2024-01-01"


def build_desk_tools(
    session: Session, agent: str, extractors: Optional[Extractors] = None
) -> list[StructuredTool]:
    """All tools useful to ``agent``, each extract -> respond -> write-through."""
    ex = extractors or Extractors()

    def quote(symbol: str) -> str:
        """Latest price (real-time first, written through to the DB)."""
        return f"price[{symbol}] = {get_realtime_quote(session, symbol, live_fn=ex.quote_fn)}"

    def prices(symbol: str) -> str:
        """Refresh OHLCV history into the DB and report the latest bar."""
        if ex.price_fetcher is not None:
            ingest_price_bars(session, symbol, fetcher=ex.price_fetcher,
                              start=ex.history_start, end=date.today().isoformat())
        bar = repo.latest_price(session, symbol)
        return f"ohlcv[{symbol}] last_close = {bar.close if bar else None}"

    def indicators(symbol: str) -> str:
        """Technical indicators snapshot (ATR, RSI, SMA, drawdown, 52w)."""
        return f"indicators[{symbol}] = {indicator_snapshot(session, symbol)}"

    def volume(symbol: str) -> str:
        """Abnormal volume spike check (rolling z-score)."""
        return f"volume[{symbol}] = {volume_spike(session, symbol)}"

    def news(symbol: str) -> str:
        """Fetch & store recent news, then return the headlines."""
        if ex.news_fetcher is not None:
            ingest_news(session, symbol, fetcher=ex.news_fetcher)
        return f"news[{symbol}]:\n{_headlines(session, symbol)}"

    def social(symbol: str) -> str:
        """Fetch & store recent social posts, then return them."""
        if ex.social_fetcher is not None:
            ingest_social(session, symbol, fetcher=ex.social_fetcher)
        return f"social[{symbol}]:\n{_social(session, symbol)}"

    def fundamentals(symbol: str) -> str:
        """Fetch & store fundamentals, then return the metrics."""
        if ex.fundamentals_fetcher is not None:
            ingest_fundamentals(session, symbol, fetcher=ex.fundamentals_fetcher)
        snap = repo.latest_fundamentals(session, symbol)
        return f"fundamentals[{symbol}] = {snap.metrics if snap else 'n/a'}"

    def macro(symbol: str = "") -> str:
        """Refresh & return the macro snapshot (GDP, CPI, rates, unemployment, 10y)."""
        if ex.macro_fetcher is not None:
            for sid in DEFAULT_MACRO_SERIES:
                ingest_macro(session, sid, fetcher=ex.macro_fetcher)
        return f"macro:\n{_macro_snapshot(session)}"

    def portfolio_risk(symbol: str = "") -> str:
        """Current portfolio heat (aggregate open risk)."""
        return f"portfolio_risk = {get_open_positions_risk(session)}"

    # Each agent gets all tools potentially useful to its task.
    catalog: dict[str, list[Callable[..., str]]] = {
        "market": [quote, prices, news, macro, indicators, portfolio_risk],
        "sentiment": [news, social, quote, portfolio_risk],
        "technical": [prices, indicators, volume, quote],
        "fundamental": [fundamentals, prices, quote],
        "risk": [quote, indicators, news, fundamentals, portfolio_risk],
    }
    funcs = catalog.get(agent, [])
    return [
        StructuredTool.from_function(f, name=f.__name__, description=(f.__doc__ or f.__name__))
        for f in funcs
    ]
