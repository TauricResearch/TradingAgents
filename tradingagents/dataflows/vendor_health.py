"""Cheap vendor health/configuration checks for operator-visible preflight."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from tradingagents.dataflows.interface import VENDOR_METHODS, get_category_for_method, get_vendor

VendorProbe = Callable[[str, str], bool | tuple[bool, str]]

DEFAULT_CRITICAL_METHODS = (
    "get_stock_data",
    "get_news",
    "get_market_movers",
    "get_market_indices",
    "get_sector_performance",
    "get_industry_performance",
    "get_topic_news",
    "get_earnings_calendar",
)


def check_vendor_health(
    config: dict[str, Any],
    *,
    critical_methods: Iterable[str] = DEFAULT_CRITICAL_METHODS,
    probe: VendorProbe | None = None,
) -> list[dict[str, str]]:
    """Return structured degradation warnings without raising.

    The default check is intentionally cheap: validate configured vendors are
    available for critical methods and verify required vendor credentials are
    present. A caller may supply *probe* for live or mocked checks; probe
    failures are surfaced as warnings rather than graph crashes.
    """
    probe = probe or _default_probe
    warnings: list[dict[str, str]] = []
    for method in critical_methods:
        try:
            category = get_category_for_method(method)
        except ValueError as exc:
            warnings.append(_warning(method, "", "", str(exc)))
            continue

        configured = get_vendor(category, method, config=config)
        vendors = [vendor.strip() for vendor in str(configured).split(",") if vendor.strip()]
        if not vendors:
            vendors = list((VENDOR_METHODS.get(method) or {}).keys())

        available = VENDOR_METHODS.get(method) or {}
        for vendor in vendors:
            if vendor not in available:
                warnings.append(
                    _warning(
                        method,
                        category,
                        vendor,
                        "configured vendor is not available for method",
                    )
                )
                continue
            try:
                probe_result = probe(vendor, method)
                if isinstance(probe_result, tuple):
                    ok, reason = probe_result
                else:
                    ok, reason = bool(probe_result), "probe reported degraded"
            except Exception as exc:
                ok, reason = False, f"probe failed: {type(exc).__name__}: {exc}"
            if not ok:
                warnings.append(_warning(method, category, vendor, str(reason)))
    return warnings


def _default_probe(vendor: str, method: str) -> tuple[bool, str]:
    if vendor == "alpha_vantage":
        try:
            from tradingagents.dataflows.alpha_vantage_common import get_api_key

            get_api_key()
        except Exception as exc:
            return False, f"alpha_vantage credential check failed for {method}: {exc}"
    elif vendor == "finnhub":
        try:
            from tradingagents.dataflows.finnhub_common import get_api_key

            get_api_key()
        except Exception as exc:
            return False, f"finnhub credential check failed for {method}: {exc}"
    return True, "ok"


def _warning(method: str, category: str, vendor: str, reason: str) -> dict[str, str]:
    return {
        "type": "vendor_health_warning",
        "method": method,
        "category": category,
        "vendor": vendor,
        "status": "degraded",
        "reason": reason,
    }
