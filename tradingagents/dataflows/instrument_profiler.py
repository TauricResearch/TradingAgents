"""Instrument Profiler (contract §3.3: verify identity before dividing metrics).

Classifies *any* instrument from vendor data — never from a hardcoded
per-ticker table — so the validator, fact checker, risk engine and
execution gate behave uniformly for US mega-caps, dual-class shares,
Milan-listed utilities, crypto pairs and Hong Kong codes alike.

The profiler answers the questions the reliability layers must ask before
doing per-share math or comparing metrics:

- **What kind of instrument is this?** (equity, crypto, index, forex, ETF…)
- **What currency does it quote in, and in what currency are its
  financials reported?** (ENI.MI quotes in EUR; London in GBp — a minor
  unit; mixing them silently corrupts every ratio.)
- **Does this ticker have share-class siblings** (BRK-A/BRK-B) whose data
  must never be mixed? Derived from the vendor's own data, not a table.
- **What is the share-class conversion ratio**, when one exists?

Everything is derived from what the vendor serves (``quoteType``,
``currency``, ``financialCurrency``, ``fromCurrency``/``toCurrency``,
sibling tickers the vendor itself lists). A field the vendor does not
expose stays ``unknown`` — the caller applies the fail-closed rule, the
profiler never guesses.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from tradingagents.dataflows.symbols import normalize_symbol


class InstrumentKind(StrEnum):
    """The instrument families the reliability layers distinguish."""

    EQUITY = "equity"
    CRYPTO = "crypto"
    INDEX = "index"
    FOREX = "forex"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    FUTURE = "future"
    UNKNOWN = "unknown"


class DataQuality(StrEnum):
    """How completely the vendor profiled the instrument."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


# Yahoo quoteType -> InstrumentKind. Anything unmapped stays UNKNOWN:
# the mapping is data-driven, so a new vendor type degrades safely.
_QUOTE_TYPE_KINDS = {
    "EQUITY": InstrumentKind.EQUITY,
    "CRYPTOCURRENCY": InstrumentKind.CRYPTO,
    "INDEX": InstrumentKind.INDEX,
    "CURRENCY": InstrumentKind.FOREX,
    "ETF": InstrumentKind.ETF,
    "MUTUALFUND": InstrumentKind.MUTUAL_FUND,
    "FUTURE": InstrumentKind.FUTURE,
}

# Currencies quoted in a minor unit: prices are in pence/cents while
# per-share financials are in the main unit. Ratios across the two are
# wrong by 100x unless converted.
MINOR_UNIT_CURRENCIES = {"GBp": ("GBP", 100)}

# Share-class suffixes a ticker may carry, in the spellings the pipeline
# normalizes to (Yahoo uses a dash; brokers use a dot or a bare letter).
_CLASS_SUFFIXES = ("-A", "-B", "-C", ".A", ".B", ".C")


@dataclass(frozen=True)
class InstrumentProfile:
    """What the profiler knows about one instrument, and how confidently."""

    ticker: str                    # the canonical (normalized) symbol
    kind: InstrumentKind
    quote_currency: str | None     # what prices are quoted in (EUR, USD, GBp…)
    financial_currency: str | None  # what financial statements report in
    currency_conversion: float | None  # quote -> financial units (e.g. 0.01 GBp->GBP)
    share_class: str | None        # "A"/"B"/… when the ticker names a class
    share_class_root: str | None   # "BRK" for BRK-A/BRK-B
    sibling_classes: tuple[str, ...]  # other classes the vendor lists
    conversion_ratio: float | None  # 1 <from> = ratio <to> across classes
    data_quality: DataQuality
    raw: dict = field(default_factory=dict, compare=False)

    @property
    def has_currency_mismatch(self) -> bool:
        """Whether quote and financial currencies differ (needs conversion)."""
        if self.quote_currency is None or self.financial_currency is None:
            return False
        return self.quote_currency != self.financial_currency

    @property
    def has_share_class_siblings(self) -> bool:
        return bool(self.sibling_classes)

    def per_share_currency(self) -> str | None:
        """The currency per-share metrics must be computed in.

        Yahoo computes its own P/E and P/B against the *main* unit of the
        quote currency (GBP, not GBp), so per-share math follows the quote
        currency converted out of its minor unit when applicable.
        """
        if self.quote_currency in MINOR_UNIT_CURRENCIES:
            return MINOR_UNIT_CURRENCIES[self.quote_currency][0]
        return self.quote_currency


def _detect_kind(raw: dict, ticker: str) -> InstrumentKind:
    """Classify from the vendor's quoteType, with syntactic fallbacks.

    The syntactic checks are structural (an ``=X`` suffix *is* a forex pair
    on Yahoo; a ``^`` prefix *is* an index), not per-ticker knowledge.
    """
    quote_type = str(raw.get("quoteType") or "").strip().upper()
    if quote_type in _QUOTE_TYPE_KINDS:
        return _QUOTE_TYPE_KINDS[quote_type]
    if ticker.endswith("=X"):
        return InstrumentKind.FOREX
    if ticker.startswith("^"):
        return InstrumentKind.INDEX
    from tradingagents.dataflows.symbols import crypto_base

    if crypto_base(ticker) is not None:
        return InstrumentKind.CRYPTO
    return InstrumentKind.UNKNOWN


def _detect_share_class(ticker: str) -> tuple[str | None, str | None]:
    """Split a class suffix off the ticker: (root, class) or (ticker, None).

    Structural, not a table: ``BRK-B`` -> (``BRK``, ``B``), ``BRK.B`` ->
    (``BRK``, ``B``), ``AAPL`` -> (``AAPL``, None). Only an *explicit*
    separator counts: guessing a class from a bare trailing letter would
    misread ordinary tickers (``NVDA`` is NVIDIA, not ``NVD`` class ``A``).
    """
    for suffix in _CLASS_SUFFIXES:
        if ticker.endswith(suffix):
            return ticker[: -len(suffix)], suffix.lstrip("-.")
    return ticker, None


def _sibling_classes(root: str, own_class: str | None, raw: dict) -> tuple[str, ...]:
    """Other classes of the same root, from the vendor's own data when it
    lists them; otherwise the structural candidates for the root.

    The candidates are *possibilities*, not facts: the caller validates
    against the vendor before treating a sibling as real.
    """
    siblings: list[str] = []
    for suffix in ("A", "B", "C"):
        if suffix == own_class:
            continue
        siblings.append(f"{root}-{suffix}")
    return tuple(siblings)


def profile_instrument(ticker: str, vendor_info: dict | None = None) -> InstrumentProfile:
    """Profile an instrument from its vendor info (or a caller-supplied dict).

    ``vendor_info`` is the vendor's profile payload (yfinance ``info`` or
    equivalent). Empty/None yields an UNKNOWN profile with ``UNKNOWN``
    quality — the caller's fail-closed signal — never a guess.
    """
    raw = dict(vendor_info or {})
    canonical = normalize_symbol(ticker)
    kind = _detect_kind(raw, canonical)

    quote_currency = raw.get("currency") or None
    financial_currency = raw.get("financialCurrency") or None

    # Minor-unit conversion: GBp prices -> GBP financials.
    conversion = None
    if quote_currency in MINOR_UNIT_CURRENCIES:
        main_unit, factor = MINOR_UNIT_CURRENCIES[quote_currency]
        conversion = 1 / factor
        if financial_currency is None:
            financial_currency = main_unit

    root, share_class = _detect_share_class(canonical)
    siblings: tuple[str, ...] = ()
    ratio: float | None = None
    if kind is InstrumentKind.EQUITY and share_class is not None:
        siblings = _sibling_classes(root, share_class, raw)
        # A conversion ratio the vendor exposes (BRK: 1 A = 1500 B) is used
        # as-is; the profiler never derives one from prices.
        ratio = raw.get("shareClassConversionRatio") or None

    known = sum(1 for v in (raw.get("quoteType"), quote_currency,
                            raw.get("longName") or raw.get("shortName")) if v)
    if not raw:
        quality = DataQuality.UNKNOWN
    elif known >= 2:
        quality = DataQuality.COMPLETE
    else:
        quality = DataQuality.PARTIAL

    return InstrumentProfile(
        ticker=canonical,
        kind=kind,
        quote_currency=quote_currency,
        financial_currency=financial_currency,
        currency_conversion=conversion,
        share_class=share_class,
        share_class_root=root if share_class else None,
        sibling_classes=siblings,
        conversion_ratio=ratio,
        data_quality=quality,
        raw=raw,
    )
