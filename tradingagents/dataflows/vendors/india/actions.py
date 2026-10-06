"""Corporate actions: what NSE's purpose text means, and how per-share history
is adjusted for them.

NSE describes each action in a free-text PURPOSE whose spelling drifted over the
years ("FV SPLT FRM RS 10 TO RS 2" in 2015, "FVSPLT FRM RS 10 TO RS 5" in 2026).
``parse_purpose`` reads the kinds that change a share's value or count:

    dividend      amount per share in rupees (a percentage of face value when the
                  face value is known)
    split         old and new face value; consolidation is a split with factor < 1
    bonus         a new shares for every b held, as "BONUS a:b"
    rights        a new for every b held at a price (face value plus premium)
    demerger, buyback, capital_reduction   recorded, never adjusted for

A price or volume dated before an action's ex-date is adjusted by its factor:
old over new face value for a split, (a + b) / b for a bonus, and for rights the
close before the ex-date over the theoretical ex-rights price. Dividends are not
adjusted for, as in Phase 1's chart (the prices people saw, split-adjusted).
Demergers are not either: the value that left with the demerged business is not
in any of these files, and the Company page says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_AMOUNT = r"R[SE]\.?\s*([\d]+(?:\.\d+)?)"
# "FV SPLT FRM RS 10 TO RS 2", "FVSPLT FRM RS 10 TO RS 5", "FV SPL 10 TO 2", "FACE VALUE SPLIT
# (SUB-DIVISION) - FROM RS 10/- PER SHARE TO RS 2/- PER SHARE"; never "SPL DIV" (special dividend).
_FACE = r"(?:R[SE]\.?\s*)?(\d+(?:\.\d+)?)\s*(?:/-)?\s*(?:PER\s+(?:EQUITY\s+)?SHARE)?"
_SPLIT = re.compile(r"(?:SPLT|SPLIT|\bSPL\b(?!\s*DIV)|SUB-?DIVISION)[^/+]*?(?:FRM|FROM)?\s*" + _FACE
                    + r"\s*TO\s*" + _FACE)
_CONSOLIDATION = re.compile(r"CONSOLIDAT[^/+]*?(?:FRM|FROM)?\s*" + _FACE + r"\s*TO\s*" + _FACE)
_RATIO = r"(\d+)\s*:\s*(\d+)"
_BONUS = re.compile(r"BONUS[^0-9]*" + _RATIO)
_RIGHTS = re.compile(r"(?:RGHTS|RIGHTS)[^0-9]*" + _RATIO + r"(.*)")
# DIV, DIVIDEND, INTDIV, FNLDIV, SPL DIV; not the DIV of SUB-DIVISION.
_DIVIDEND = re.compile(r"\b(?:INT|FNL|SPL)?DIV(?:IDEND)?\b")
_PERCENT = re.compile(r"([\d]+(?:\.\d+)?)\s*%")


@dataclass
class Action:
    type: str
    ratio_num: float | None = None  # bonus/rights: new shares; split: old face value
    ratio_den: float | None = None  # bonus/rights: shares held; split: new face value
    amount: float | None = None     # dividend per share, or the rights issue price
    factor: float | None = None     # price adjustment factor; None when not adjustable here


def _float(text: str) -> float:
    return float(text)


def _dividend(segment: str, face_value: float | None) -> float | None:
    if (match := re.search(_AMOUNT, segment)) is not None:
        return _float(match.group(1))
    if face_value and (pct := _PERCENT.search(segment)) is not None:
        return round(_float(pct.group(1)) / 100 * face_value, 4)
    return None


def parse_purpose(purpose: str, face_value: float | None = None) -> list[Action]:
    """The actions a PURPOSE describes; one purpose can carry several
    ("AGM/DIV - RS 5 PER SH/SPL DIV - RS 2 PER SH"). Purposes that move no
    per-share figure (AGMs, interest, redemptions) give an empty list."""
    text = " ".join(purpose.upper().split())
    actions: list[Action] = []
    if (m := _SPLIT.search(text) or _CONSOLIDATION.search(text)) is not None:
        old, new = _float(m.group(1)), _float(m.group(2))
        if old > 0 and new > 0:
            actions.append(Action("split", old, new, factor=old / new))
    if (m := _BONUS.search(text)) is not None:
        a, b = _float(m.group(1)), _float(m.group(2))
        if a > 0 and b > 0:
            actions.append(Action("bonus", a, b, factor=(a + b) / b))
    if (m := _RIGHTS.search(text)) is not None:
        a, b, rest = _float(m.group(1)), _float(m.group(2)), m.group(3)
        price = None
        if (p := re.search(_AMOUNT, rest)) is not None:
            price = _float(p.group(1))
            if re.search(r"PRM|PREMIUM", rest) and face_value:
                price += face_value
        actions.append(Action("rights", a, b, amount=price))
    dividends = [d for segment in re.split(r"/|\+|\bAND\b", text)
                 if _DIVIDEND.search(segment) and (d := _dividend(segment, face_value)) is not None]
    if dividends:
        actions.append(Action("dividend", amount=round(sum(dividends), 4)))
    elif _DIVIDEND.search(text) and not actions:
        actions.append(Action("dividend"))
    if "DEMERGER" in text:
        actions.append(Action("demerger"))
    if re.search(r"BUY\s*-?\s*BACK", text):
        actions.append(Action("buyback"))
    if "CAPITAL REDUCTION" in text or "REDUCTION OF CAPITAL" in text:
        actions.append(Action("capital_reduction"))
    return actions


def rights_factor(ratio_num: float, ratio_den: float, issue_price: float | None,
                  cum_price: float | None) -> float | None:
    """Close before the ex-date over the theoretical ex-rights price, or None when
    either price is unknown or the rights were not worth taking up."""
    if not issue_price or not cum_price or ratio_num <= 0 or ratio_den <= 0 or issue_price >= cum_price:
        return None
    terp = (ratio_den * cum_price + ratio_num * issue_price) / (ratio_num + ratio_den)
    return cum_price / terp


def cumulative_factors(days: list[str], actions: list[tuple[str, float]]) -> list[float]:
    """For each day (ascending), the product of the factors of actions whose
    ex-date is after it: what that day's price is divided by."""
    events = sorted(actions)
    out, product, i = [1.0] * len(days), 1.0, len(events) - 1
    for k in range(len(days) - 1, -1, -1):
        while i >= 0 and events[i][0] > days[k]:
            product *= events[i][1]
            i -= 1
        out[k] = product
    return out
