"""Persistent, conservative Yahoo resolution and normalized snapshot caching."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import yfinance as yf

from tradingagents.agents.utils.agent_utils import resolve_instrument_identity
from tradingagents.dataflows.errors import ProviderRateLimitedError, ProviderTimedOutError
from tradingagents.dataflows.fund_data import fetch_fund_snapshot
from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.dataflows.yahoo import yahoo_rate_limit_error, yahoo_timeout_error
from tradingagents.instruments import InstrumentDescriptor, resolve_instrument
from tradingagents.persistence import Repository

PROVIDER = "yahoo_finance"
IDENTITY_TTL = timedelta(days=1)
PROBE_TTL = timedelta(days=1)
SNAPSHOT_TTL = timedelta(hours=12)
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
MAX_REQUEST_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class ResolvedInstrument:
    descriptor: InstrumentDescriptor
    identity: dict[str, str]
    cache_status: str


def _utc_now() -> datetime:
    return datetime.now(UTC)


def yahoo_request_timeout_seconds() -> float:
    raw = os.getenv("TRADINGAGENTS_YAHOO_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("TRADINGAGENTS_YAHOO_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > MAX_REQUEST_TIMEOUT_SECONDS:
        raise ValueError(
            f"TRADINGAGENTS_YAHOO_TIMEOUT_SECONDS must be greater than 0 and at most {MAX_REQUEST_TIMEOUT_SECONDS:g}"
        )
    return value


def _bounded_ticker_factory(timeout_seconds: float) -> Callable[[str], Any]:
    """Use yfinance's own session while capping every transport request."""
    from yfinance.data import new_session

    session = new_session()
    original_request = session.request

    def bounded_request(method, url, *args, **kwargs):
        requested = kwargs.get("timeout")
        if not isinstance(requested, (int, float)) or requested > timeout_seconds:
            kwargs["timeout"] = timeout_seconds
        return original_request(method, url, *args, **kwargs)

    session.request = bounded_request
    return lambda symbol: yf.Ticker(symbol, session=session)


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _business_days_between(start: date, end: date) -> int:
    if end <= start:
        return 0
    return sum(
        1
        for offset in range(1, (end - start).days + 1)
        if (start.toordinal() + offset) % 7 not in {0, 6}
    )


def _snapshot_is_fresh(payload: dict[str, Any], analysis_date: str) -> bool:
    """Use the same cutoff-price freshness threshold as the trust policy."""
    try:
        cutoff = date.fromisoformat(analysis_date)
    except ValueError:
        return False
    points = [item for item in payload.get("price_series", []) if item.get("date", "") <= analysis_date]
    if not points:
        return False
    latest = max(points, key=lambda item: str(item.get("date")))
    try:
        price_date = date.fromisoformat(str(latest["date"]))
    except (KeyError, ValueError):
        return False
    instrument = payload.get("instrument") or {}
    return bool(instrument.get("canonical_symbol") and instrument.get("currency")) and _business_days_between(price_date, cutoff) <= 2


class CachedYahooProvider:
    """One web-worker adapter for identity, price probes, and fund snapshots.

    It stores only normalized data and metadata.  Expired entries are never
    passed off as current data; their presence only improves the safe error
    detail when Yahoo is unavailable.
    """

    def __init__(
        self,
        repository: Repository,
        *,
        identity_resolver: Callable[[str], dict[str, str]] | None = None,
        ticker_factory: Callable[[str], Any] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        timeout_seconds: float | None = None,
    ):
        self.repository = repository
        self.timeout_seconds = timeout_seconds or yahoo_request_timeout_seconds()
        self.ticker_factory = ticker_factory or _bounded_ticker_factory(self.timeout_seconds)
        self.identity_resolver = identity_resolver or (
            lambda symbol: resolve_instrument_identity(
                symbol,
                raise_rate_limited=True,
                raise_timed_out=True,
                timeout_seconds=self.timeout_seconds,
                ticker_factory=self.ticker_factory,
            )
        )
        self.clock = clock

    def resolve(self, symbol: str, override: str, analysis_date: str) -> ResolvedInstrument:
        canonical = normalize_symbol(symbol)
        if canonical.endswith(("-USD", "-USDT", "-USDC", "-BTC", "-ETH")):
            descriptor = resolve_instrument(canonical, override)
            return ResolvedInstrument(descriptor, {}, "not_applicable")

        identity, identity_status = self._identity(canonical)
        if identity:
            descriptor = resolve_instrument(
                symbol,
                override,
                identity_resolver=lambda _symbol: identity,
            )
            return ResolvedInstrument(descriptor, identity, identity_status)

        available, probe_status = self._price_probe(canonical, analysis_date)
        descriptor = resolve_instrument(
            symbol,
            override,
            identity_resolver=lambda _symbol: {},
            price_probe=lambda _symbol: available,
        )
        return ResolvedInstrument(descriptor, {}, probe_status)

    def fund_snapshot(
        self,
        instrument: InstrumentDescriptor,
        analysis_date: str,
        benchmark_symbol: str,
    ) -> tuple[dict[str, Any], str]:
        params = {"analysis_date": analysis_date, "benchmark_symbol": benchmark_symbol}
        cached, cache_status = self._fresh_cache(instrument.canonical_symbol, "fund_snapshot", params)
        if cached and _snapshot_is_fresh(cached.normalized_payload, analysis_date):
            payload = dict(cached.normalized_payload)
            payload["cache_status"] = "hit"
            payload.setdefault("warnings", []).append("Using a freshness-qualified cached Yahoo fund snapshot.")
            return payload, "hit"
        if cached:
            cache_status = "expired"
        try:
            payload = fetch_fund_snapshot(
                instrument,
                analysis_date,
                benchmark_symbol,
                ticker_factory=self.ticker_factory,
                request_timeout_seconds=self.timeout_seconds,
            ).to_dict()
        except ProviderRateLimitedError as exc:
            raise exc.with_cache_status(cache_status) from exc
        except ProviderTimedOutError as exc:
            raise exc.with_cache_status(cache_status) from exc
        except Exception as exc:  # noqa: BLE001 - map only explicit provider failures
            if limited := yahoo_rate_limit_error(exc):
                raise limited.with_cache_status(cache_status) from exc
            if timed_out := yahoo_timeout_error(exc, timeout_seconds=self.timeout_seconds):
                raise timed_out.with_cache_status(cache_status) from exc
            raise
        now = self.clock()
        self.repository.put_provider_cache(
            provider=PROVIDER,
            symbol=instrument.canonical_symbol,
            capability="fund_snapshot",
            request_params=params,
            normalized_payload=payload,
            source_reference=f"Yahoo Finance normalized fund snapshot for {instrument.canonical_symbol}",
            retrieved_at=now.isoformat(),
            effective_at=analysis_date,
            expires_at=(now + SNAPSHOT_TTL).isoformat(),
        )
        payload["cache_status"] = "miss"
        return payload, "miss"

    def _identity(self, symbol: str) -> tuple[dict[str, str], str]:
        cached, status = self._fresh_cache(symbol, "identity", {})
        if cached:
            return {str(key): str(value) for key, value in cached.normalized_payload.items()}, "hit"
        try:
            identity = self.identity_resolver(symbol) or {}
        except ProviderRateLimitedError as exc:
            raise exc.with_cache_status(status) from exc
        except ProviderTimedOutError as exc:
            raise exc.with_cache_status(status) from exc
        if identity:
            now = self.clock()
            self.repository.put_provider_cache(
                provider=PROVIDER,
                symbol=symbol,
                capability="identity",
                request_params={},
                normalized_payload=identity,
                source_reference=f"Yahoo Finance identity for {symbol}",
                retrieved_at=now.isoformat(),
                effective_at=now.date().isoformat(),
                expires_at=(now + IDENTITY_TTL).isoformat(),
            )
        return dict(identity), status

    def _price_probe(self, symbol: str, analysis_date: str) -> tuple[bool, str]:
        params = {"analysis_date": analysis_date}
        cached, status = self._fresh_cache(symbol, "price_probe", params)
        if cached:
            return bool(cached.normalized_payload.get("available")), "hit"
        try:
            available = not self.ticker_factory(symbol).history(
                period="5d",
                timeout=self.timeout_seconds,
            ).empty
        except Exception as exc:  # noqa: BLE001 - only explicit Yahoo throttle has its own public state
            if limited := yahoo_rate_limit_error(exc):
                raise limited.with_cache_status(status) from exc
            if timed_out := yahoo_timeout_error(exc, timeout_seconds=self.timeout_seconds):
                raise timed_out.with_cache_status(status) from exc
            return False, status
        if available:
            now = self.clock()
            self.repository.put_provider_cache(
                provider=PROVIDER,
                symbol=symbol,
                capability="price_probe",
                request_params=params,
                normalized_payload={"available": True},
                source_reference=f"Yahoo Finance price availability probe for {symbol}",
                retrieved_at=now.isoformat(),
                effective_at=analysis_date,
                expires_at=(now + PROBE_TTL).isoformat(),
            )
        return available, status

    def _fresh_cache(self, symbol: str, capability: str, params: dict[str, Any]):
        entry = self.repository.get_provider_cache(PROVIDER, symbol, capability, params)
        if entry is None:
            return None, "miss"
        if _parse(entry.expires_at) <= self.clock():
            return None, "expired"
        return entry, "hit"
