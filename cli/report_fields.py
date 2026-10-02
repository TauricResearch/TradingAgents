"""Dependency-free decision fields shared by generation, reports and launchers."""

from __future__ import annotations

import math
import re


def field(text: str, name: str) -> str:
    m = re.search(
        rf"^[ \t]*(?:[-*][ \t]+|\d+[.)][ \t]+)?(?:\*\*)?{re.escape(name)}"
        rf"(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?(?:\n[ \t]*)?([^\n]+)$",
        text, flags=re.I | re.M,
    )
    if m:
        value = clean_field_value(m.group(1))
        if not re.match(r"(?:\*\*)?[A-Za-z][^\n:]*?(?:\*\*)?\s*:", value):
            return value
    m = re.search(
        rf"^\|\s*\*{{0,2}}{re.escape(name)}\*{{0,2}}\s*\|\s*(.+?)\s*\|",
        text,
        flags=re.I | re.M,
    )
    return clean_field_value(m.group(1)) if m else ""


def clean_field_value(value: str) -> str:
    return value.strip().strip("*").strip()


def parse_money(value: str) -> float | None:
    value = value.strip().replace("**", "").replace(",", "")
    m = re.match(r"^(?:[$€£¥]\s*)?([0-9]+(?:\.\d+)?(?:[eE][+-]?\d+)?)(?=$|\s|[();!?]|\.(?!\d))", value)
    if not m or re.match(
        r"\s*(?:%|(?:[-–—/]|to\b)\s*(?:[$€£¥]\s*)?\d|"
        r"(?:[-–—]\s*)?(?:(?:business|trading)\s+)?"
        r"(?:days?|weeks?|months?|quarters?|years?|hours?|minutes?|seconds?|[dwmqy]|"
        r"percent(?:age)?|basis\s+points?|bps?|times|multiple)\b)",
        value[m.end():], flags=re.I,
    ):
        return None
    number = float(m.group(1))
    return number if math.isfinite(number) and number > 0 else None


def extract_price_target(decision_text: str) -> float | None:
    for name in (
        "Price Target",
        "Target Price",
        "Near-term target",
        "Medium-term target",
        "Base-case target",
        "Fair Value",
        "Valuation Target",
    ):
        value = field(decision_text, name)
        if value:
            target = parse_money(value)
            if target is not None:
                return target
    return None


class MissingPriceTargetError(ValueError):
    """A decision cannot be completed without an absolute numeric target."""


def require_price_target(decision_text: str) -> None:
    if extract_price_target(decision_text) is None:
        raise MissingPriceTargetError(
            "Portfolio decision requires a positive numeric Price Target supported by "
            "the supplied evidence; report remains incomplete."
        )
