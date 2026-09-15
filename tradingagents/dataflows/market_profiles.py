"""Market identification from exchange suffixes.

Pure, network-free helpers that map a ticker to the market profile declared
in ``DEFAULT_CONFIG["market_profiles"]``. Callers that need market-specific
behaviour ask :func:`resolve_market` / :func:`get_market_profile` rather than
sprinkling ``ticker.endswith(".TW")`` checks across modules, so adding or
adjusting a market is a config edit, not a code hunt.

Only suffix-based detection is implemented: a ticker matches a profile when
it ends with one of the profile's ``suffixes`` and has a non-empty symbol
before it. Plain US tickers (no suffix) and unknown suffixes resolve to
:data:`MARKET_DEFAULT`.
"""

from __future__ import annotations

from collections.abc import Mapping

from tradingagents.default_config import DEFAULT_CONFIG

MARKET_DEFAULT = "default"
MARKET_TAIWAN = "taiwan"


def _profiles(config: Mapping | None) -> Mapping[str, Mapping]:
    source = config if config is not None else DEFAULT_CONFIG
    return source.get("market_profiles") or {}


def resolve_market(ticker: str, config: Mapping | None = None) -> str:
    """Return the market profile key for ``ticker`` (e.g. ``"taiwan"``).

    Matching is case-insensitive on the suffix and requires the suffix to
    terminate the symbol (``2330.TW`` matches ``.TW``; ``TW2330`` and
    ``2330.TWO`` do not). Longer suffixes are tried first so a future
    ``.T``/``.TW``-style overlap resolves to the more specific one.
    Returns :data:`MARKET_DEFAULT` when nothing matches.
    """
    if not isinstance(ticker, str):
        return MARKET_DEFAULT
    symbol = ticker.strip().upper()
    if not symbol:
        return MARKET_DEFAULT

    candidates: list[tuple[str, str]] = []
    for market, profile in _profiles(config).items():
        for suffix in profile.get("suffixes", ()):
            if suffix:
                candidates.append((suffix.upper(), market))
    candidates.sort(key=lambda item: len(item[0]), reverse=True)

    for suffix, market in candidates:
        if len(symbol) > len(suffix) and symbol.endswith(suffix):
            return market
    return MARKET_DEFAULT


def get_market_profile(ticker: str, config: Mapping | None = None) -> Mapping:
    """Return the profile mapping for ``ticker``'s market, or ``{}`` for the
    default market so callers can ``.get(...)`` without a None check."""
    market = resolve_market(ticker, config)
    if market == MARKET_DEFAULT:
        return {}
    return _profiles(config).get(market, {})
