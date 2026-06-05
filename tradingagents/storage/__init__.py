"""Central persistence layer for the trading agent.

This package adds the DB-first storage the upstream TradingAgents fork lacks
(it was file/cache based). The schema mirrors the four logical areas defined in
the project wiki:

- ``portfolio_state``  -> rendicontazione (cash, positions, P/L snapshots)
- ``market_data``      -> dati live (price bars, time-series)
- ``charter``          -> costituzione / Statuto (deterministic risk rules)
- ``logs / trades``    -> esecuzione e audit

Plus two cross-cutting tables:

- ``instruments``      -> ticker registry
- ``ticker_card``      -> the persistent per-ticker "scheda" that backs the
                          screening/funnel (parallelism-design)
- ``research_states``  -> sealed research_state / investment_state (JSON)

Design notes:
- SQLite by default for zero-setup local dev; PostgreSQL + TimescaleDB in
  production (``price_bars`` becomes a hypertable).
- Time-series rows carry a double date (publication_date / reference_date) to
  guard against look-ahead bias.
"""

from .database import Base, get_engine, get_session, init_db, reset_engine
from .models import (
    CharterRule,
    Instrument,
    PortfolioSnapshot,
    PriceBar,
    ResearchState,
    TickerCard,
    Trade,
)

__all__ = [
    "Base",
    "get_engine",
    "get_session",
    "init_db",
    "reset_engine",
    "CharterRule",
    "Instrument",
    "PortfolioSnapshot",
    "PriceBar",
    "ResearchState",
    "TickerCard",
    "Trade",
]
