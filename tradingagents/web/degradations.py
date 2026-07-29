"""Stable run-level summaries of recoverable data-source failures.

Raw vendor error messages can contain transport details and change between
library versions.  The workbench needs a compact answer to a different
question: which research capability was affected, which vendors were tried,
and did a fallback ultimately provide usable data?
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tradingagents.observability.events import PersistedEvent

_AFFECTED_SECTIONS = {
    "get_stock_data": ("独立分析", "交易计划", "组合经理裁决"),
    "get_indicators": ("独立分析", "交易计划"),
    "get_fundamentals": ("独立分析", "组合经理裁决"),
    "get_balance_sheet": ("独立分析",),
    "get_cashflow": ("独立分析",),
    "get_income_statement": ("独立分析",),
    "get_news": ("独立分析", "多空辩论"),
    "get_global_news": ("独立分析",),
    "get_insider_transactions": ("独立分析",),
    "get_macro_indicators": ("独立分析",),
}

_CAPABILITY_BY_METHOD = {
    "get_stock_data": "price_history",
    "get_indicators": "technical_indicators",
    "get_fundamentals": "fundamentals",
    "get_balance_sheet": "fundamentals",
    "get_cashflow": "fundamentals",
    "get_income_statement": "fundamentals",
    "get_news": "company_news",
    "get_global_news": "global_news",
    "get_insider_transactions": "company_news",
    "get_macro_indicators": "macro",
}


def summarize_data_degradations(
    events: Iterable[PersistedEvent],
) -> list[dict[str, Any]]:
    """Produce deterministic terminal summaries from persisted data events.

    A method becomes visible only when at least one attempt failed.  A later
    ``data.completed`` makes it *degraded* (fallback worked); otherwise it is
    *unavailable*.  This is deliberately derived from durable events, so live
    replay, history, and resume all agree without trusting browser state.
    """
    groups: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.type not in {"data.progress", "data.failed", "data.completed"}:
            continue
        payload = event.payload
        method = payload.get("method")
        vendor = payload.get("vendor")
        if not isinstance(method, str) or not method or not isinstance(vendor, str) or not vendor:
            continue
        group = groups.setdefault(
            method,
            {
                "attempted_vendors": [],
                "selected_vendors": [],
                "reasons": [],
                "failed": False,
            },
        )
        _append_unique(group["attempted_vendors"], vendor)
        if event.type == "data.failed":
            group["failed"] = True
            code = payload.get("failure_code")
            _append_unique_pair(
                group["reasons"],
                {"vendor": vendor, "code": code if isinstance(code, str) and code else "vendor_error"},
            )
        elif event.type == "data.completed":
            _append_unique(group["selected_vendors"], vendor)

    summaries: list[dict[str, Any]] = []
    for method, group in groups.items():
        if not group["failed"]:
            continue
        selected = group["selected_vendors"]
        summaries.append(
            {
                "capability": _CAPABILITY_BY_METHOD.get(method, method),
                "status": "degraded" if selected else "unavailable",
                "attempted_vendors": group["attempted_vendors"],
                "selected_vendors": selected,
                "reasons": group["reasons"],
                "affected_sections": list(_AFFECTED_SECTIONS.get(method, ("研究结论",))),
            }
        )
    return summaries


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)


def _append_unique_pair(items: list[dict[str, str]], value: dict[str, str]) -> None:
    if value not in items:
        items.append(value)
