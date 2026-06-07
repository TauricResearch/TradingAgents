"""Formatting helpers for Indian market reports."""

from __future__ import annotations


def format_inr(value: float | int | None, precision: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"₹{float(value):,.{precision}f}"


def format_inr_crore_lakh(value: float | int | None, precision: int = 2) -> str:
    if value is None:
        return "unavailable"
    amount = float(value)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    if amount >= 10_000_000:
        return f"{sign}₹{amount / 10_000_000:,.{precision}f} crore"
    if amount >= 100_000:
        return f"{sign}₹{amount / 100_000:,.{precision}f} lakh"
    return f"{sign}₹{amount:,.{precision}f}"


def format_bps(value: float | int | None, precision: int = 0) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):,.{precision}f} bps"


def format_percent(value: float | int | None, precision: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):,.{precision}f}%"


def fy_label(year: int) -> str:
    return f"FY{year % 100:02d}"


def quarter_fy_label(quarter: int, fiscal_year: int) -> str:
    if quarter not in {1, 2, 3, 4}:
        raise ValueError("quarter must be 1, 2, 3, or 4")
    return f"Q{quarter}{fy_label(fiscal_year)}"


def ttm_label() -> str:
    return "TTM"
