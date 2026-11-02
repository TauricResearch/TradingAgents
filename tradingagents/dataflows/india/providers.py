"""Provider contract for India-market adapters; no vendor endpoints are assumed."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Protocol, runtime_checkable

from tradingagents.dataflows.india.provenance import MarketQuote, StaleMarketDataError
from tradingagents.dataflows.india.symbols import normalize_indian_symbol


@runtime_checkable
class IndianMarketDataProvider(Protocol):
    """Minimum quote interface for an explicitly selected Indian data provider."""

    provider_name: str

    def get_quote(self, symbol: str, exchange: str) -> MarketQuote:
        """Return one quote with provider and timestamp provenance attached."""
        ...


class IndiaProviderRegistry:
    """Explicit, isolated registry for India quote providers.

    This registry deliberately does not mutate the existing method-oriented
    router. Registering a provider never makes it an implicit fallback.
    """

    def __init__(self):
        self._providers: dict[str, IndianMarketDataProvider] = {}

    def register(self, provider: IndianMarketDataProvider, *, replace: bool = False) -> None:
        if not isinstance(provider, IndianMarketDataProvider):
            raise TypeError("provider must implement IndianMarketDataProvider")
        if not callable(provider.get_quote):
            raise TypeError("provider.get_quote must be callable")
        if not isinstance(replace, bool):
            raise TypeError("replace must be a bool")
        name = getattr(provider, "provider_name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("provider_name must be a non-empty string")
        key = name.strip().casefold()
        if key in self._providers and not replace:
            raise ValueError(f"India provider {name!r} is already registered")
        self._providers[key] = provider

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(sorted(provider.provider_name for provider in self._providers.values()))

    def get_quote(
        self,
        provider_name: str,
        symbol: str,
        exchange: str,
        *,
        as_of: date | datetime | str,
        max_age: timedelta,
    ) -> MarketQuote:
        """Call exactly the named provider and validate returned provenance."""
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("provider_name must explicitly select a provider")
        key = provider_name.strip().casefold()
        try:
            provider = self._providers[key]
        except KeyError as exc:
            raise LookupError(f"India provider {provider_name!r} is not registered") from exc

        canonical = normalize_indian_symbol(symbol, exchange)
        selected_exchange = exchange.strip().upper()
        quote = provider.get_quote(canonical, selected_exchange)
        if not isinstance(quote, MarketQuote):
            raise TypeError("India providers must return MarketQuote")
        provenance = quote.provenance
        if provenance.provider.casefold() != key:
            raise ValueError("quote provenance provider does not match the selected provider")
        if provenance.exchange != selected_exchange:
            raise ValueError("quote provenance exchange does not match the requested exchange")
        if normalize_indian_symbol(provenance.symbol, selected_exchange) != canonical:
            raise ValueError("quote provenance symbol does not match the requested symbol")
        quote.ensure_available_as_of(as_of)
        if quote.is_stale(max_age, as_of=as_of):
            raise StaleMarketDataError("quote is older than the requested maximum age")
        return quote