"""Investable universe: catalogue + reconciliation + watchlist seeding.

Three concentric sets (wiki):
    UNIVERSE (all broker-tradable, reconciled)  ⊇  WATCHLIST (dynamic working set)  ⊇  PORTFOLIO

- ``sources``: where S&P 500 membership comes from (a shipped seed file).
- ``sync``: pull the broker's tradable assets, upsert them, mark missing ones
  inactive (reconciliation), tag S&P 500 constituents; seed the watchlist.
"""

from .sources import Sp500Source, load_sp500_seed
from .sync import SyncReport, seed_watchlist, sync_universe

__all__ = [
    "Sp500Source",
    "load_sp500_seed",
    "SyncReport",
    "sync_universe",
    "seed_watchlist",
]
