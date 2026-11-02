"""Provider quote values with explicit provenance and conflict-safe selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def _utc_timestamp(value: datetime | None, field: str, *, required: bool) -> datetime | None:
    if value is None and not required:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _as_of_cutoff(value: date | datetime | str) -> datetime:
    now = datetime.now(timezone.utc)
    today_india = now.astimezone(ZoneInfo("Asia/Kolkata")).date()
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of datetime must be timezone-aware")
        cutoff = value.astimezone(timezone.utc)
        if cutoff > now:
            raise ValueError("as_of datetime cannot be in the future")
        return cutoff
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError as exc:
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("as_of must be an ISO date or timezone-aware datetime") from exc
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("as_of datetime must be timezone-aware")
            cutoff = parsed.astimezone(timezone.utc)
            if cutoff > now:
                raise ValueError("as_of datetime cannot be in the future")
            return cutoff
    if isinstance(value, date):
        if value > today_india:
            raise ValueError("as_of date cannot be in the future")
        end_of_day = datetime.combine(value, time.max, tzinfo=ZoneInfo("Asia/Kolkata"))
        return end_of_day.astimezone(timezone.utc)
    raise TypeError("as_of must be a date, datetime, or ISO string")


class LookAheadDataError(ValueError):
    """An observation cannot be proven available by the requested as-of time."""


class StaleMarketDataError(ValueError):
    """A quote is older than the caller's permitted freshness window."""


@dataclass(frozen=True)
class DataProvenance:
    provider: str
    symbol: str
    exchange: str | None
    retrieval_timestamp: datetime
    market_timestamp: datetime | None
    currency: str
    data_quality: str
    publication_timestamp: datetime | None = None

    def __post_init__(self):
        for field in ("provider", "symbol", "currency", "data_quality"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must not be empty")
            object.__setattr__(self, field, value.strip())
        if self.exchange is not None:
            if not isinstance(self.exchange, str):
                raise ValueError("exchange must be NSE, BSE, or None")
            object.__setattr__(self, "exchange", self.exchange.strip().upper())
            if self.exchange not in {"NSE", "BSE"}:
                raise ValueError("exchange must be NSE, BSE, or None")
        object.__setattr__(
            self,
            "retrieval_timestamp",
            _utc_timestamp(self.retrieval_timestamp, "retrieval_timestamp", required=True),
        )
        object.__setattr__(
            self,
            "market_timestamp",
            _utc_timestamp(self.market_timestamp, "market_timestamp", required=False),
        )
        object.__setattr__(
            self,
            "publication_timestamp",
            _utc_timestamp(self.publication_timestamp, "publication_timestamp", required=False),
        )
        now = datetime.now(timezone.utc)
        if self.retrieval_timestamp > now:
            raise ValueError("retrieval_timestamp cannot be in the future")
        if self.market_timestamp is not None and self.market_timestamp > self.retrieval_timestamp:
            raise ValueError("market_timestamp cannot be after retrieval_timestamp")
        if self.publication_timestamp is not None:
            if self.publication_timestamp > self.retrieval_timestamp:
                raise ValueError("publication_timestamp cannot be after retrieval_timestamp")
            if (
                self.market_timestamp is not None
                and self.publication_timestamp < self.market_timestamp
            ):
                raise ValueError("publication_timestamp cannot precede market_timestamp")

    def ensure_available_as_of(self, as_of: date | datetime | str) -> None:
        """Reject data that is not proven observable by an India-local as-of date.

        Date-only cutoffs mean the end of that day in Asia/Kolkata. A dated
        historical query requires a publication timestamp; market time alone
        cannot prove when the information became public.
        """
        cutoff = _as_of_cutoff(as_of)
        if self.market_timestamp is None:
            raise LookAheadDataError("market timestamp is required for historical queries")
        if self.publication_timestamp is None:
            raise LookAheadDataError("publication timestamp is required for historical queries")
        if self.publication_timestamp > cutoff:
            raise LookAheadDataError("data was published after the requested as-of time")
        if self.market_timestamp is not None and self.market_timestamp > cutoff:
            raise LookAheadDataError("market observation is after the requested as-of time")

    def is_stale(
        self,
        max_age: timedelta,
        *,
        as_of: date | datetime | str,
    ) -> bool:
        """Check historical availability and return whether data exceeds ``max_age``.

        An explicit cutoff and verifiable market/publication timestamps are
        required so callers cannot accidentally evaluate unproven historical
        data against the wall clock.
        """
        if not isinstance(max_age, timedelta) or max_age < timedelta(0):
            raise ValueError("max_age must be a non-negative timedelta")
        cutoff = _as_of_cutoff(as_of)
        self.ensure_available_as_of(as_of)
        if self.market_timestamp is None:
            return True
        age = cutoff - self.market_timestamp
        if age < timedelta(0):
            raise LookAheadDataError("market observation is after the freshness as-of time")
        return age > max_age


@dataclass(frozen=True)
class MarketQuote:
    value: Decimal
    provenance: DataProvenance

    def __post_init__(self):
        if not isinstance(self.provenance, DataProvenance):
            raise TypeError("provenance must be a DataProvenance")
        try:
            value = Decimal(str(self.value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("quote value must be a finite decimal") from exc
        if not value.is_finite():
            raise ValueError("quote value must be a finite decimal")
        object.__setattr__(self, "value", value)

    def is_stale(self, max_age: timedelta, *, as_of: date | datetime | str) -> bool:
        return self.provenance.is_stale(max_age, as_of=as_of)

    def ensure_available_as_of(self, as_of: date | datetime | str) -> None:
        self.provenance.ensure_available_as_of(as_of)


class ConflictingProviderDataError(ValueError):
    """More than one provider quote was supplied without an explicit choice."""


def select_single_provider_quote(
    quotes: tuple[MarketQuote, ...] | list[MarketQuote],
    *,
    as_of: date | datetime | str,
    max_age: timedelta,
    provider: str | None = None,
) -> MarketQuote:
    """Select one source and enforce its as-of and freshness requirements."""
    candidates = tuple(quotes)
    if provider is not None:
        candidates = tuple(
            quote for quote in candidates
            if quote.provenance.provider.casefold() == provider.casefold()
        )
    if len(candidates) != 1:
        if len(candidates) > 1:
            raise ConflictingProviderDataError(
                "multiple provider quotes require an explicit single-provider choice"
            )
        raise LookupError("no quote matched the selected provider")
    quote = candidates[0]
    quote.ensure_available_as_of(as_of)
    if quote.is_stale(max_age, as_of=as_of):
        raise StaleMarketDataError("quote is older than the requested maximum age")
    return quote