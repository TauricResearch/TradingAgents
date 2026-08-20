"""Typed, fail-safe access to KAP disclosures for BIST instruments."""

from .models import KapDisclosure, KapDisclosureResult
from .service import KapService, is_bist_ticker, normalize_bist_ticker_for_kap

__all__ = [
    "KapDisclosure",
    "KapDisclosureResult",
    "KapService",
    "is_bist_ticker",
    "normalize_bist_ticker_for_kap",
]
