"""Claim harvesting (P0.2 wiring): facts from the agents' own reports.

The fact registry blocks on unresolved conflicts — but only when the run's
reports are turned into :class:`AgentFact` records. This module harvests
them deterministically from the analysts' own report text: labelled
metric patterns ("Stockholders Equity: 747,900 USD million", "Q3 2026
buyback of approximately $9.6 billion"), never bare numbers in prose.

Extraction is conservative on purpose:

- Only labelled metric patterns are recognized; a number without a
  recognizable metric label is not a fact and is skipped.
- Every harvested fact is ``verified=False`` with the agent's own report
  as its source: harvesting proves *what an agent asserted*, not that the
  assertion is true. Verification stays the primary sources' job.
- A report that names no metrics yields no facts — the registry then has
  nothing to compare, which is honest, and the freshness/causal gates
  still cover the temporal and filing axes.
"""

from __future__ import annotations

import re

from tradingagents.dataflows.fact_registry import AgentFact

# Labelled metric patterns: "Label: value unit" or "label of approximately
# $value unit". Structural, any ticker — the labels are the reports'
# vocabulary, not per-ticker rules. The unit alternation lists the
# multi-word units first so "USD million" is not read as "USD".
_METRIC_RE = re.compile(
    r"\b(?P<label>[A-Z][A-Za-z ]{2,40}?)\s*(?:[:=]|\bof\b)\s*"
    r"(?:approximately\s+|approx\.\s+|~)?"
    r"\$?\s*(?P<value>\d[\d.,]*)\s*"
    r"(?P<unit>USD\s+billion|USD\s+million|EUR\s+million|billion|million|"
    r"USD|EUR|GBP|%)?",
    re.IGNORECASE,
)

# Quarter labels a statement may be scoped to ("Q3 2026", "2026-Q3",
# "first half of 2026" -> H1).
_QUARTER_RE = re.compile(
    r"\b(?:(?P<q>Q[1-4])\s+(?P<yq>\d{4})|(?P<y>\d{4})-Q(?P<qn>[1-4]))\b",
    re.IGNORECASE,
)

# Metric labels the harvester recognizes, normalized to fact keys. A label
# outside this table is not a fact this system compares — skipped, never
# guessed.
_METRIC_KEYS = {
    "stockholders equity": "stockholders_equity",
    "total equity": "stockholders_equity",
    "shareholders equity": "stockholders_equity",
    "total assets": "total_assets",
    "revenue": "revenue",
    "total revenue": "revenue",
    "operating earnings": "operating_earnings",
    "net income": "net_income",
    "operating income": "operating_income",
    "buyback": "buyback_amount",
    "share repurchases": "buyback_amount",
    "repurchases": "buyback_amount",
    "free cash flow": "free_cash_flow",
    "cash flow from operations": "operating_cash_flow",
    "eps": "eps_gaap",
    "earnings per share": "eps_gaap",
    "book value": "book_value",
    "market cap": "market_cap",
}

_UNIT_SCALES = {
    "billion": "USD_billion",
    "million": "USD_million",
    "usd billion": "USD_billion",
    "usd million": "USD_million",
    "eur million": "EUR_million",
}


def _normalize_label(label: str) -> str:
    return " ".join(label.lower().split())


def _normalize_unit(unit_raw: str | None) -> str:
    """Normalize a unit token to the registry's unit vocabulary."""
    flattened = " ".join((unit_raw or "").lower().split())
    if not flattened:
        return "USD"
    return _UNIT_SCALES.get(flattened, flattened)


def _fact_key(label: str) -> str | None:
    """The normalized fact key for a report label, or None when unknown."""
    normalized = _normalize_label(label)
    if normalized in _METRIC_KEYS:
        return _METRIC_KEYS[normalized]
    # A label containing a known key ("Q3 Share Repurchases") still maps.
    for known, key in _METRIC_KEYS.items():
        if known in normalized:
            return key
    return None


def _parse_value(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _periods_in(text: str) -> list[str]:
    """The quarter labels a statement names, normalized ("2026-Q3")."""
    periods = []
    for match in _QUARTER_RE.finditer(text):
        if match.group("q"):
            periods.append(f"{match.group('yq')}-{match.group('q').upper()}")
        else:
            periods.append(f"{match.group('y')}-Q{match.group('qn')}")
    return periods


def harvest_facts(
    reports: dict[str, str],
    *,
    analysis_as_of: str | None = None,
) -> list[AgentFact]:
    """Harvest labelled metric facts from the run's own analyst reports.

    ``reports`` maps report keys ("news_report", "fundamentals_report"…)
    to the agents' text. Every harvested fact carries the agent's own
    report as its source and ``verified=False``: harvesting records what
    was asserted, never that it is true. A statement naming a quarter is
    scoped to it; an unscoped statement carries no period and is never
    compared against a scoped one.
    """
    facts: list[AgentFact] = []
    for report_key, text in (reports or {}).items():
        if not text:
            continue
        agent = report_key.removesuffix("_report") or report_key
        for match in _METRIC_RE.finditer(text):
            label = match.group("label")
            key = _fact_key(label)
            if key is None:
                continue
            value = _parse_value(match.group("value"))
            if value is None or value <= 0:
                continue
            unit = _normalize_unit(match.group("unit"))
            # Scope: the nearest quarter named in the surrounding sentence.
            sentence_end = text.find(".", match.end())
            sentence_start = text.rfind(".", 0, match.start())
            sentence = text[sentence_start + 1:sentence_end + 1 or len(text)]
            periods = _periods_in(sentence)
            period = periods[0] if periods else None
            facts.append(AgentFact(
                fact_key=key,
                agent=agent,
                value=value,
                unit=unit,
                period=period,
                segment="company",
                metric_id=key,
                metric_definition=key,
                source_type="unknown",
                source_reference=report_key,
                verified=False,
                statement=" ".join(match.group(0).split())[:200],
            ))
    return facts
