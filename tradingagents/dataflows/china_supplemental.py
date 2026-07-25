"""A-share supplemental vendor formatting helpers.

Extracted from ``interface.py``. When yfinance returns incomplete data for an
A-share, the router supplements with a China-only vendor (tushare/akshare).
These helpers identify supplemental vendors and format the combined or
incomplete-primary result package.
"""

from __future__ import annotations

from typing import Any

from .vendor_errors import _summarize_vendor_error


def _next_china_supplemental_vendor(vendors: list[str]) -> str | None:
    for vendor in vendors:
        if _is_china_supplemental_vendor(vendor):
            return vendor
    return None


def _is_china_supplemental_vendor(vendor: str) -> bool:
    return vendor in {"tushare", "akshare"}


def _format_supplemental_result(
    *,
    method: str,
    primary_vendor: str,
    primary_result: Any,
    reason: str,
    supplemental_vendor: str,
    supplemental_result: Any,
) -> str:
    return "\n\n".join(
        [
            f"# Data Package for `{method}`",
            f"Primary source: {primary_vendor}",
            f"Supplemental source: {supplemental_vendor}",
            f"Supplement reason: {reason}",
            "## Primary Source Result",
            str(primary_result),
            "## Supplemental Source Result",
            str(supplemental_result),
        ]
    )


def _format_incomplete_primary_result(
    *,
    method: str,
    primary_vendor: str,
    primary_result: Any,
    reason: str,
    errors: list[tuple[str, Exception]],
) -> str:
    source_status = "; ".join(
        f"{vendor}: {_summarize_vendor_error(exc)}"
        for vendor, exc in errors
        if vendor != primary_vendor
    )
    sections = [
        f"# Data Package for `{method}`",
        f"Primary source: {primary_vendor}",
        "Supplemental source: unavailable",
        f"Warning: {reason}",
    ]
    if source_status:
        sections.append(f"Supplemental source status: {source_status}")
    sections.extend(["## Primary Source Result", str(primary_result)])
    return "\n\n".join(sections)
