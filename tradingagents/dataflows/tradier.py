"""Tradier vendor module: typed dataclasses and options chain retrieval with Greeks and IV.

Provides OptionsContract and OptionsChain dataclasses as the canonical typed structures
for options data throughout the system. Retrieves options chains from the Tradier API
with 1st-order Greeks (via ORATS), IV fields, DTE filtering, and session caching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date

import pandas as pd

from .tradier_common import make_tradier_request_with_retry, TradierRateLimitError


# ---------------------------------------------------------------------------
# Typed dataclasses
# ---------------------------------------------------------------------------


@dataclass
class OptionsContract:
    """A single options contract with Greeks and IV from Tradier/ORATS.

    Fields map directly to the Tradier ``/v1/markets/options/chains`` response
    with ``greeks=true``.
    """

    symbol: str  # OCC symbol e.g. AAPL220617C00270000
    underlying: str  # e.g. AAPL
    option_type: str  # "call" or "put"
    strike: float
    expiration_date: str  # YYYY-MM-DD
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    # Greeks (from ORATS via Tradier)
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None
    phi: float | None = None
    # IV
    bid_iv: float | None = None
    mid_iv: float | None = None
    ask_iv: float | None = None
    smv_vol: float | None = None
    greeks_updated_at: str | None = None


@dataclass
class OptionsChain:
    """A collection of options contracts for a single underlying.

    Provides convenience methods for DataFrame conversion and DTE-based filtering.
    """

    underlying: str
    fetch_timestamp: str
    expirations: list[str]
    contracts: list[OptionsContract] = field(default_factory=list)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all contracts to a pandas DataFrame."""
        return pd.DataFrame([vars(c) for c in self.contracts])

    def filter_by_dte(self, min_dte: int = 0, max_dte: int = 50) -> OptionsChain:
        """Return a new OptionsChain containing only contracts within the DTE range.

        Args:
            min_dte: Minimum days to expiration (inclusive).
            max_dte: Maximum days to expiration (inclusive).

        Returns:
            A new OptionsChain with filtered contracts and updated expirations list.
        """
        today = date.today()
        filtered: list[OptionsContract] = []
        for contract in self.contracts:
            exp = datetime.strptime(contract.expiration_date, "%Y-%m-%d").date()
            dte = (exp - today).days
            if min_dte <= dte <= max_dte:
                filtered.append(contract)

        # Derive unique sorted expirations from filtered contracts
        unique_exps = sorted({c.expiration_date for c in filtered})
        return OptionsChain(
            underlying=self.underlying,
            fetch_timestamp=self.fetch_timestamp,
            expirations=unique_exps,
            contracts=filtered,
        )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_contract(raw: dict) -> OptionsContract:
    """Parse a single contract dict from the Tradier API response.

    Handles missing Greeks gracefully (sandbox has no Greeks -- Pitfall 1).
    """
    greeks = raw.get("greeks") or {}
    return OptionsContract(
        symbol=raw.get("symbol", ""),
        underlying=raw.get("underlying", ""),
        option_type=raw.get("option_type", ""),
        strike=float(raw.get("strike", 0) or 0),
        expiration_date=raw.get("expiration_date", ""),
        bid=float(raw.get("bid", 0) or 0),
        ask=float(raw.get("ask", 0) or 0),
        last=float(raw.get("last", 0) or 0),
        volume=int(raw.get("volume", 0) or 0),
        open_interest=int(raw.get("open_interest", 0) or 0),
        delta=greeks.get("delta"),
        gamma=greeks.get("gamma"),
        theta=greeks.get("theta"),
        vega=greeks.get("vega"),
        rho=greeks.get("rho"),
        phi=greeks.get("phi"),
        bid_iv=greeks.get("bid_iv"),
        mid_iv=greeks.get("mid_iv"),
        ask_iv=greeks.get("ask_iv"),
        smv_vol=greeks.get("smv_vol"),
        greeks_updated_at=greeks.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# API retrieval functions
# ---------------------------------------------------------------------------


def get_options_expirations(
    symbol: str, min_dte: int = 0, max_dte: int = 50
) -> list[str]:
    """Retrieve available option expiration dates for a symbol, filtered by DTE range.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL').
        min_dte: Minimum days to expiration (inclusive).
        max_dte: Maximum days to expiration (inclusive).

    Returns:
        Sorted list of expiration date strings in YYYY-MM-DD format.
    """
    data = make_tradier_request_with_retry(
        "/v1/markets/options/expirations",
        {
            "symbol": symbol.upper(),
            "includeAllRoots": "false",
            "strikes": "false",
        },
    )

    dates = data.get("expirations", {}).get("date", [])

    # Pitfall 5: single-item response comes as a string, not a list
    if isinstance(dates, str):
        dates = [dates]

    today = date.today()
    qualifying: list[str] = []
    for d in dates:
        exp = datetime.strptime(d, "%Y-%m-%d").date()
        dte = (exp - today).days
        if min_dte <= dte <= max_dte:
            qualifying.append(d)

    return sorted(qualifying)


def _fetch_chain_for_expiration(
    symbol: str, expiration: str
) -> list[OptionsContract]:
    """Fetch the options chain for a single expiration date.

    Args:
        symbol: Ticker symbol.
        expiration: Expiration date in YYYY-MM-DD format.

    Returns:
        List of parsed OptionsContract instances.
    """
    data = make_tradier_request_with_retry(
        "/v1/markets/options/chains",
        {
            "symbol": symbol.upper(),
            "expiration": expiration,
            "greeks": "true",
        },
    )

    options = data.get("options", {}).get("option", [])

    # Pitfall 2: single contract comes as a dict, not a list
    if isinstance(options, dict):
        options = [options]

    return [_parse_contract(opt) for opt in options]


# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------

_options_cache: dict[str, OptionsChain] = {}


def clear_options_cache() -> None:
    """Clear the in-memory options chain cache."""
    _options_cache.clear()


# ---------------------------------------------------------------------------
# Public retrieval functions
# ---------------------------------------------------------------------------


def get_options_chain(symbol: str, min_dte: int = 0, max_dte: int = 50) -> str:
    """Retrieve the full options chain as a string (for LLM tool consumption).

    Pre-fetches all expirations within the DTE range (D-03), always requests
    greeks=true (D-05). Results are cached per (symbol, min_dte, max_dte) key.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL').
        min_dte: Minimum days to expiration (inclusive).
        max_dte: Maximum days to expiration (inclusive).

    Returns:
        String representation of the options chain DataFrame.
    """
    cache_key = f"{symbol.upper()}:{min_dte}:{max_dte}"

    if cache_key in _options_cache:
        return _options_cache[cache_key].to_dataframe().to_string()

    expirations = get_options_expirations(symbol, min_dte, max_dte)
    all_contracts: list[OptionsContract] = []
    for exp in expirations:
        all_contracts.extend(_fetch_chain_for_expiration(symbol, exp))

    chain = OptionsChain(
        underlying=symbol.upper(),
        fetch_timestamp=datetime.now().isoformat(),
        expirations=expirations,
        contracts=all_contracts,
    )
    _options_cache[cache_key] = chain

    return chain.to_dataframe().to_string()


def get_options_chain_structured(
    symbol: str, min_dte: int = 0, max_dte: int = 50
) -> OptionsChain:
    """Retrieve the full options chain as a typed OptionsChain dataclass.

    Same behavior as get_options_chain() but returns the OptionsChain directly
    for programmatic access by downstream computation modules.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL').
        min_dte: Minimum days to expiration (inclusive).
        max_dte: Maximum days to expiration (inclusive).

    Returns:
        OptionsChain dataclass with all contracts, Greeks, and IV.
    """
    cache_key = f"{symbol.upper()}:{min_dte}:{max_dte}"

    if cache_key in _options_cache:
        return _options_cache[cache_key]

    expirations = get_options_expirations(symbol, min_dte, max_dte)
    all_contracts: list[OptionsContract] = []
    for exp in expirations:
        all_contracts.extend(_fetch_chain_for_expiration(symbol, exp))

    chain = OptionsChain(
        underlying=symbol.upper(),
        fetch_timestamp=datetime.now().isoformat(),
        expirations=expirations,
        contracts=all_contracts,
    )
    _options_cache[cache_key] = chain

    return chain
