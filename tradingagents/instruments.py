"""Canonical instrument identity and classification helpers.

The current system only supports a stock deep-dive path. This module classifies
symbols up front so non-stock instruments can be kept out of that path until
dedicated ETF and crypto workflows exist.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

TRACKED_MARKET_INSTRUMENTS: dict[str, dict[str, Any]] = {
    "SPY": {"instrument_type": "broad_market_etf"},
    "QQQ": {"instrument_type": "broad_market_etf"},
    "IWM": {"instrument_type": "broad_market_etf"},
    "DIA": {"instrument_type": "broad_market_etf"},
    "XLF": {"instrument_type": "sector_etf"},
    "XLK": {"instrument_type": "sector_etf"},
    "XLV": {"instrument_type": "sector_etf"},
    "XLI": {"instrument_type": "sector_etf"},
    "XLY": {"instrument_type": "sector_etf"},
    "XLP": {"instrument_type": "sector_etf"},
    "XLU": {"instrument_type": "sector_etf"},
    "TLT": {"instrument_type": "treasury_etf"},
    "SGOV": {"instrument_type": "treasury_etf"},
    "GLD": {"instrument_type": "commodity_etf"},
    "UUP": {"instrument_type": "broad_market_etf"},
    "SH": {"instrument_type": "inverse_etf", "is_inverse": True},
    "PSQ": {"instrument_type": "inverse_etf", "is_inverse": True},
    "TQQQ": {"instrument_type": "leveraged_etf", "is_leveraged": True},
    "SQQQ": {"instrument_type": "leveraged_etf", "is_inverse": True, "is_leveraged": True},
    "TSDD": {"instrument_type": "inverse_etf", "is_inverse": True, "sector": "Inverse ETF"},
    "TSLL": {"instrument_type": "leveraged_etf", "is_leveraged": True, "sector": "Leveraged ETF"},
}

TRACKED_CRYPTO_INSTRUMENTS: dict[str, dict[str, Any]] = {
    "BTC": {},
    "ETH": {},
    "SOL": {},
    "BNB": {},
    "XRP": {},
}


@dataclass(frozen=True)
class CanonicalInstrument:
    raw_symbol: str
    canonical_symbol: str
    display_symbol: str
    instrument_key: str
    asset_class: str
    instrument_type: str
    exchange_or_market: str
    quote_currency: str
    is_etf: bool = False
    is_inverse: bool = False
    is_leveraged: bool = False
    classification_source: str = "heuristic"
    classification_confidence: float = 0.8
    source_context: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return asdict(self)


def normalize_symbol(raw_symbol: str) -> str:
    """Return the canonical uppercase symbol while preserving suffixes."""
    return str(raw_symbol or "").strip().upper()


def resolve_instrument(raw_symbol: str, *, source_context: str = "") -> CanonicalInstrument:
    symbol = normalize_symbol(raw_symbol)
    if not symbol:
        return CanonicalInstrument(
            raw_symbol="",
            canonical_symbol="",
            display_symbol="",
            instrument_key="unknown:",
            asset_class="unknown",
            instrument_type="unknown",
            exchange_or_market="",
            quote_currency="",
            classification_confidence=0.0,
            source_context=source_context,
        )

    etf_meta = TRACKED_MARKET_INSTRUMENTS.get(symbol)
    if etf_meta is not None:
        return CanonicalInstrument(
            raw_symbol=raw_symbol,
            canonical_symbol=symbol,
            display_symbol=symbol,
            instrument_key=f"etf:{symbol}",
            asset_class="etf",
            instrument_type=etf_meta["instrument_type"],
            exchange_or_market="NYSEARCA",
            quote_currency="USD",
            is_etf=True,
            is_inverse=bool(etf_meta.get("is_inverse")),
            is_leveraged=bool(etf_meta.get("is_leveraged")),
            classification_source="registry",
            classification_confidence=1.0,
            source_context=source_context,
        )

    if symbol in TRACKED_CRYPTO_INSTRUMENTS:
        return CanonicalInstrument(
            raw_symbol=raw_symbol,
            canonical_symbol=symbol,
            display_symbol=symbol,
            instrument_key=f"crypto:{symbol}",
            asset_class="crypto",
            instrument_type="coin",
            exchange_or_market="CRYPTO",
            quote_currency="USD",
            classification_source="registry",
            classification_confidence=1.0,
            source_context=source_context,
        )

    if symbol.startswith("^"):
        return CanonicalInstrument(
            raw_symbol=raw_symbol,
            canonical_symbol=symbol,
            display_symbol=symbol,
            instrument_key=f"index:{symbol}",
            asset_class="index",
            instrument_type="index",
            exchange_or_market="INDEX",
            quote_currency="USD",
            classification_source="heuristic",
            classification_confidence=0.9,
            source_context=source_context,
        )

    return CanonicalInstrument(
        raw_symbol=raw_symbol,
        canonical_symbol=symbol,
        display_symbol=symbol,
        instrument_key=f"equity:{symbol}",
        asset_class="equity",
        instrument_type="common_stock",
        exchange_or_market="",
        quote_currency="USD",
        classification_source="default_equity",
        classification_confidence=0.6,
        source_context=source_context,
    )


def instrument_metadata(raw_symbol: str, *, source_context: str = "") -> dict[str, Any]:
    return resolve_instrument(raw_symbol, source_context=source_context).to_metadata()


def is_equity_pipeline_supported(instrument: CanonicalInstrument) -> bool:
    """Return True for instruments allowed into the current stock deep-dive path."""
    return instrument.asset_class == "equity" and instrument.instrument_type == "common_stock"

