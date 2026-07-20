"""Shared asset-type definitions and deterministic instrument classification."""

from collections.abc import Mapping
from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"
    FUTURES = "futures"


def coerce_asset_type(asset_type: str | AssetType) -> str:
    """Return a supported wire value or reject an unknown asset mode."""
    try:
        return AssetType(asset_type).value
    except (TypeError, ValueError) as exc:
        choices = ", ".join(asset.value for asset in AssetType)
        raise ValueError(f"asset_type must be one of: {choices}") from exc


def resolve_asset_type(
    ticker: str,
    asset_type: str | AssetType = AssetType.STOCK,
    identity: Mapping[str, str] | None = None,
) -> str:
    """Promote a run to futures when deterministic instrument data proves it.

    The validated caller-provided mode remains authoritative for non-futures
    instruments. Broker aliases are normalized before checking Yahoo's native
    ``=F`` suffix.
    """
    from tradingagents.dataflows.symbol_utils import normalize_symbol

    requested_asset_type = coerce_asset_type(asset_type)
    canonical_ticker = normalize_symbol(ticker)
    quote_type = identity.get("quote_type") if identity else None
    if (isinstance(canonical_ticker, str) and canonical_ticker.upper().endswith("=F")) or (
        isinstance(quote_type, str) and quote_type.strip().upper() == "FUTURE"
    ):
        return AssetType.FUTURES.value
    return requested_asset_type
