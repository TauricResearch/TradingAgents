"""Quote currencies: minor units (pence, fils) and the currency of an exchange suffix.

Yahoo quotes some markets in a minor unit: London in pence (GBp), Johannesburg in
cents (ZAc), Tel Aviv in agorot (ILA) and Kuwait in fils (KWF, a thousandth of a
dinar). Per-share and market-cap figures arrive in the main unit, so a price is
compared with them only after conversion.
"""

from __future__ import annotations

# quote code -> (main-unit code, how many minor units make one main unit)
MINOR_UNITS: dict[str, tuple[str, int]] = {
    "GBp": ("GBP", 100),
    "GBX": ("GBP", 100),
    "ZAc": ("ZAR", 100),
    "ILA": ("ILS", 100),
    "KWF": ("KWD", 1000),
}

# The currency of a market, for a ticker whose Yahoo profile names none (Bahrain's
# does not). A suffix not listed has no fallback: no currency is guessed.
SUFFIX_CURRENCY: dict[str, str] = {
    ".SR": "SAR",   # Saudi Tadawul
    ".AE": "AED",   # Dubai Financial Market
    ".QA": "QAR",   # Qatar Exchange
    ".KW": "KWD",   # Boursa Kuwait (Yahoo quotes the price in fils, KWF)
    ".BH": "BHD",   # Bahrain Bourse
}


def main_unit(code: str | None) -> str | None:
    """The main-unit currency for a quote code: GBp -> GBP, KWF -> KWD, anything else unchanged."""
    return MINOR_UNITS[code][0] if code in MINOR_UNITS else code


def to_main_unit(value: float, code: str | None) -> tuple[float, str | None]:
    """(value, code) converted from a minor unit to its main unit; unchanged for a main unit."""
    if code in MINOR_UNITS:
        main, divisor = MINOR_UNITS[code]
        return value / divisor, main
    return value, code


def currency_for_symbol(symbol: str) -> str | None:
    """The market currency implied by a ticker's exchange suffix, or None when it is not known."""
    upper = symbol.strip().upper()
    return next((c for suffix, c in SUFFIX_CURRENCY.items() if upper.endswith(suffix)), None)
