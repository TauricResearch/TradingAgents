"""Stable instruments separated from their time-varying listings."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, StringConstraints, field_validator, model_validator

from tradingagents.domain.contracts import ContractModel, content_id
from tradingagents.domain.ids import InstrumentId


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    FX = "fx"
    FUTURE = "future"
    OPTION = "option"
    BOND = "bond"
    INDEX = "index"
    CASH = "cash"
    OTHER = "other"


Symbol = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=64),
]
Venue = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=32),
]
Currency = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Z]{3}$"),
]


class ListingRef(ContractModel):
    """A symbol/venue identity that may change without changing the instrument."""

    instrument_id: InstrumentId
    symbol: Symbol
    asset_class: AssetClass = AssetClass.EQUITY
    venue: Venue | None = None
    quote_currency: Currency | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    id_scheme: str

    @field_validator("valid_from", "valid_to")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None

    @field_validator("id_scheme")
    @classmethod
    def normalize_scheme(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("id_scheme must not be empty")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> ListingRef:
        if (
            self.valid_from is not None
            and self.valid_to is not None
            and self.valid_from >= self.valid_to
        ):
            raise ValueError("listing validity must satisfy valid_from < valid_to")
        return self


def provisional_listing(
    symbol: str,
    *,
    asset_class: AssetClass = AssetClass.EQUITY,
    venue: str | None = None,
    quote_currency: str | None = "USD",
) -> ListingRef:
    """Create the explicit provisional identity used by the current V2 universe.

    This is stable for compatibility but is not claimed to be a permanent
    security master identifier.  A future instrument-master migration maps it
    to a permanent opaque ID while retaining the historical listing.
    """
    normalized_symbol = symbol.strip().upper()
    normalized_venue = venue.strip().upper() if venue else None
    scheme = "provisional-v2-listing"
    instrument_id = InstrumentId(content_id(
        "instrument",
        {
            "scheme": scheme,
            "symbol": normalized_symbol,
            "asset_class": asset_class.value,
            "venue": normalized_venue,
            "quote_currency": quote_currency.strip().upper() if quote_currency else None,
        },
    ))
    return ListingRef(
        instrument_id=instrument_id,
        symbol=normalized_symbol,
        asset_class=asset_class,
        venue=normalized_venue,
        quote_currency=quote_currency,
        id_scheme=scheme,
    )
