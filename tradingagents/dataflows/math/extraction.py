"""Certified metric extraction (P3): what the run can compute, and from what.

Phase 1 built the registry from fields like ``state["eps_ttm"]`` — but nothing
populated them, so a real run certified nothing and blocked. This module closes
that gap by reading the figures the run *does* have:

- the verified market snapshot (price, indicators), which the graph records;
- the SEC facts the freshness gate already fetched;
- the labelled figures the analysts reported.

Two rules keep it honest:

**Only labelled figures are read.** A number without a label carries no metric
identity, so it cannot be certified. The pattern for each figure requires an
explicit name ("P/B", "EPS", "Total revenue"), which is why an unlabelled figure
is `None` rather than a guess.

**The source is recorded.** Every extracted figure names where it came from —
snapshot, SEC concept, or a report's labelled line — because the audit's whole
finding was that provenance was being discarded one layer at a time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tradingagents.dataflows.math.run_registry import RunInputs

# A labelled money figure with an optional scale. Shared by every extractor so
# the scales are read the same way.
_SCALE = {"billion": 1_000_000_000, "bn": 1_000_000_000, "b": 1_000_000_000,
          "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
          "thousand": 1_000, "k": 1_000}


@dataclass(frozen=True)
class Extracted:
    """A figure read from the run, with where it came from."""

    value: float | None
    origin: str
    label: str = ""

    def summary(self) -> dict:
        return {"value": self.value, "origin": self.origin, "label": self.label}


def _scaled(raw: str, scale: str | None) -> float | None:
    try:
        value = float(raw.replace(",", ""))
    except (TypeError, ValueError):
        return None
    factor = _SCALE.get((scale or "").strip().lower())
    return value * factor if factor else value


def _search(pattern: str, text: str | None) -> Extracted | None:
    if not text:
        return None
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    raw, scale = _groups(match)
    if raw is None:
        return None
    value = _scaled(_normalise(raw), scale)
    if value is None:
        return None
    return Extracted(value=value, origin="report", label=match.group(0)[:60])


# Each pattern demands a label. A bare number never matches, which is the
# fail-closed direction: an unlabelled figure stays uncertified.
_PATTERNS = {
    # "P/B of 1.73x", "P/B (Class B) | ~1,73x", "P/B 1.735x"
    "price_to_book": r"P/?B[^.\d\n]{0,28}?(\d+(?:[.,]\d+)?)\s*x?",
    # "EPS TTM 39.76", "EPS (TTM): 39,76", "EPS trailing 39.76"
    "eps_ttm": r"EPS[^.\d\n]{0,24}?(?:TTM|trailing)[^.\d\n]{0,12}?(\d+(?:[.,]\d+)?)",
    # "EPS forward 22.43", "EPS atteso 22,43", and the tabular "EPS TTM / Forward
    # | 39,76 / 22,43" where the forward figure is the *second* value. The
    # optional prefix handles both in a single capture group, so the caller
    # never has to know which branch matched.
    "eps_forward": (
        r"EPS[^.\d\n]{0,24}?(?:"
        r"(?:TTM|trailing)\s*(?:/|e)\s*(?:forward|fwd|atteso)"
        r"\D{0,16}?\d+(?:[.,]\d+)?\s*/\s*"
        r"|(?:forward|atteso|fwd)\D{0,16}?)"
        r"(\d+(?:[.,]\d+)?)"),
    # "Book value per share 359.56", "BVPS 359,56"
    "book_value_per_share": (
        r"(?:book\s+value\s+per\s+share|BVPS)[^.\d\n]{0,20}?(\d+(?:[.,]\d+)?)"),
    # "Total revenue 105,647 million", "Ricavi 74,3 mld"
    "revenue_consolidated": (
        r"(?:total\s+revenue|consolidated\s+revenue|ricavi\s+consolidati)"
        r"\D{0,24}?(\d[\d,\.]*)\s*(billion|million|bn|mn|b|m)?"),
}

# A decimal comma is a European convention; a comma otherwise separates
# thousands. Exactly three digits after the comma is the thousands form
# ("105,647"); one or two is the usual decimal ("39,76"), and four or more
# can only be a decimal ("359,5599") because a thousands group never has four
# digits. Reading "359,5599" as 3,595,599 inflated a per-share book value by
# four orders of magnitude.
_COMMA_DECIMAL = re.compile(r"^\d{1,3},\d{1,2}$|^\d{1,3},\d{4,}$")


def _groups(match) -> tuple[str | None, str | None]:
    """The first number a pattern captured, plus any scale word it captured.

    Patterns in this module alternate between shapes (a plain "EPS forward
    22.43" and a tabular "39,76 / 22,43"), so the value can land in any of
    several groups and the rest stay ``None``. Reading ``group(1)`` blindly is
    what made extraction raise ``TypeError`` on a ``None`` group as soon as
    the second branch matched; picking the first populated group is the shape
    -independent way to get the figure.
    """
    raw: str | None = None
    scale: str | None = None
    for value in match.groups():
        if value is None:
            continue
        if value.strip().lower() in _SCALE:
            scale = value
        elif raw is None:
            raw = value
    return raw, scale


def _normalise(value: str) -> str:
    """Read ``1,73`` as 1.73 and ``105,647`` as 105647."""
    if _COMMA_DECIMAL.match(value):
        return value.replace(",", ".")
    return value.replace(",", "")


def from_report(report: str | None, metric: str) -> Extracted | None:
    """Read one labelled figure out of a report."""
    pattern = _PATTERNS.get(metric)
    if pattern is None or not report:
        return None
    match = re.search(pattern, report, re.IGNORECASE)
    if not match:
        return None
    raw, scale = _groups(match)
    if raw is None:
        return None
    value = _scaled(_normalise(raw), scale)
    if value is None:
        return None
    return Extracted(value=value, origin="report", label=match.group(0)[:60])


@dataclass
class ExtractResult:
    """Every figure this run could certify, and what it could not."""

    inputs: RunInputs
    origins: dict[str, Extracted] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "certified": {k: v.summary() for k, v in self.origins.items()},
            "absent": sorted(set(_PATTERNS) - set(self.origins)),
        }


def extract_run_inputs(state: dict) -> ExtractResult:
    """Build ``RunInputs`` from a finished run's own artefacts.

    The snapshot supplies the price and indicators; the reports supply the
    labelled figures the analysts stated. Where a figure exists in neither, it
    stays absent — the registry then records ``NOT_COMPUTABLE`` rather than a
    value nobody can trace.
    """
    snapshot = state.get("verified_market_snapshot")
    if not isinstance(snapshot, dict):
        snapshot = {}

    def _num(*values) -> float | None:
        for value in values:
            if value is None or isinstance(value, bool):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    result = ExtractResult(inputs=RunInputs())

    price = _num(snapshot.get("close"), snapshot.get("price"),
                 state.get("price"))
    if price is not None:
        result.origins["price"] = Extracted(price, "verified_market_snapshot")

    # Reports are the only source of the labelled valuation figures until the
    # agents emit structured metrics (the §7 gap in the context-optimization
    # task). Each is read from a labelled line, never from a bare number.
    reports = {
        "fundamentals": state.get("fundamentals_report"),
        "market": state.get("market_report"),
        "decision": state.get("final_trade_decision"),
    }
    for metric in ("eps_ttm", "eps_forward", "book_value_per_share",
                   "revenue_consolidated"):
        for name, text in reports.items():
            found = from_report(text if isinstance(text, str) else None, metric)
            if found is not None:
                result.origins[metric] = Extracted(
                    found.value, f"report:{name}", found.label)
                break

    # ``RunInputs`` is frozen, so the final one is built rather than mutated.
    # Every figure recovered from report text is the model's own assertion:
    # recording it in ``claimed_inputs`` is what keeps a multiple built on it
    # out of the certified set. A figure the state supplies is left out of that
    # tuple, so a future structured-metric path is trusted without a change
    # here.
    stated = {name for name in _PATTERNS if name in result.origins
              and result.origins[name].origin.startswith("report:")}
    result.inputs = RunInputs(
        price=price,
        previous_close=_num(snapshot.get("previous_close")),
        sma50=_num(snapshot.get("sma50")),
        sma200=_num(snapshot.get("sma200")),
        period_high=_num(snapshot.get("high_52w"), snapshot.get("period_high")),
        eps_ttm=_num(result.origins["eps_ttm"].value
                     if "eps_ttm" in result.origins else None,
                     state.get("eps_ttm")),
        eps_forward=_num(result.origins["eps_forward"].value
                         if "eps_forward" in result.origins else None,
                         state.get("eps_forward")),
        book_value_per_share=_num(
            result.origins["book_value_per_share"].value
            if "book_value_per_share" in result.origins else None,
            state.get("book_value_per_share")),
        revenue_consolidated=_num(
            result.origins["revenue_consolidated"].value
            if "revenue_consolidated" in result.origins else None,
            state.get("revenue_consolidated")),
        revenue_prior=_num(state.get("revenue_prior")),
        claimed_inputs=tuple(sorted(stated)),
    )
    return result


def extraction_note(result: ExtractResult) -> dict:
    """A compact account of what was certified and from where, for the audit."""
    return result.summary()
