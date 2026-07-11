"""Instrument metadata: venue-reported trading facts, never hardcoded.

``VenueSpec`` stays authoritative for *policy* (which symbols we allow,
paper commission/slippage models); this service owns *venue facts* —
tick size, contract value, minimum size — fetched from the venue and
cached on the /data volume. Order construction must round/validate
against these (go-live Phase 1): a hardcoded lot size is a rejected
order at best and a 10x position at worst.

Fail-closed rule: in live mode, a missing/stale instrument cache refuses
new orders. Paper mode synthesizes facts from the static VenueSpec and
never blocks.
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class InstrumentsUnavailable(Exception):
    """Live order construction refused: no fresh venue metadata."""


@dataclass(frozen=True)
class InstrumentInfo:
    symbol: str          # canonical (XAUUSD, BTC-USD)
    venue_symbol: str    # venue convention (XAUTUSD, BTCUSD)
    product_id: int | None = None
    tick_size: float = 0.01
    contract_value: float = 1.0   # canonical units per 1 contract
    min_contracts: int = 1
    max_leverage: float = 1.0
    as_of: float = 0.0            # unix ts of the fetch

    def to_contracts(self, quantity: float) -> int:
        """Canonical quantity -> whole venue contracts (floor: never round
        a position UP with real money)."""
        if self.contract_value <= 0:
            raise ValueError(f"bad contract_value for {self.symbol}")
        return int(math.floor(quantity / self.contract_value + 1e-9))

    def to_quantity(self, contracts: float) -> float:
        return contracts * self.contract_value

    def round_price(self, price: float) -> float:
        if self.tick_size <= 0:
            return price
        return round(round(price / self.tick_size) * self.tick_size, 10)


class InstrumentService:
    """Fetch + cache instrument facts. ``fetch`` returns
    ``{canonical_symbol: InstrumentInfo}``; injectable for tests."""

    def __init__(self, fetch=None, cache_path: str | Path | None = None,
                 ttl_seconds: float = 3600.0, fail_closed: bool = True):
        self._fetch = fetch
        self._cache_path = Path(cache_path) if cache_path else None
        self._ttl = ttl_seconds
        self._fail_closed = fail_closed
        self._infos: dict[str, InstrumentInfo] = {}
        self._fetched_at: float = 0.0
        if self._cache_path is not None:
            self._load_cache()

    @classmethod
    def from_static(cls, venue_spec, quantity_precision: int | None = None):
        """Synthesize facts from a hardcoded VenueSpec — the paper-mode
        default keeps today's behavior with no venue round-trips."""
        infos = {}
        precision = (quantity_precision if quantity_precision is not None
                     else venue_spec.quantity_precision)
        for canonical, venue_symbol in venue_spec.symbol_map.items():
            step = 10 ** -precision
            infos[canonical] = InstrumentInfo(
                symbol=canonical, venue_symbol=venue_symbol,
                contract_value=step,
                min_contracts=max(1, int(round(venue_spec.min_quantity / step))),
                as_of=time.time(),
            )
        service = cls(fetch=None, fail_closed=False)
        service._infos = infos
        service._fetched_at = time.time()
        return service

    # --- cache -----------------------------------------------------------------

    def _load_cache(self) -> None:
        assert self._cache_path is not None
        try:
            raw = json.loads(self._cache_path.read_text(encoding="utf-8"))
            self._fetched_at = raw["fetched_at"]
            self._infos = {
                sym: InstrumentInfo(**data) for sym, data in raw["infos"].items()
            }
        except FileNotFoundError:
            return
        except Exception:
            logger.warning("corrupt instrument cache %s; refetching",
                           self._cache_path, exc_info=True)

    def _save_cache(self) -> None:
        if self._cache_path is None:
            return
        from tradingagents.pro.persistence import atomic_write_json

        atomic_write_json(self._cache_path, {
            "fetched_at": self._fetched_at,
            "infos": {sym: asdict(info) for sym, info in self._infos.items()},
        })

    # --- access ----------------------------------------------------------------

    @property
    def stale(self) -> bool:
        return (time.time() - self._fetched_at) > self._ttl

    def refresh(self) -> None:
        if self._fetch is None:
            return
        try:
            self._infos = dict(self._fetch())
            self._fetched_at = time.time()
            self._save_cache()
        except Exception:
            logger.warning("instrument refresh failed; cache age %.0fs",
                           time.time() - self._fetched_at, exc_info=True)

    def get(self, symbol: str) -> InstrumentInfo:
        if self.stale:
            self.refresh()
        info = self._infos.get(symbol)
        if info is None or (self.stale and self._fail_closed):
            raise InstrumentsUnavailable(
                f"no fresh instrument metadata for {symbol} "
                f"(age {time.time() - self._fetched_at:.0f}s, "
                f"fail_closed={self._fail_closed}) — refusing to construct orders"
            )
        return info
