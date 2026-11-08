"""Shared financial fact registry (P0.2): one source of truth for agents.

Every material financial fact an agent asserts is registered with its full
scope — metric, value, unit, currency, period, segment, definition,
source — so Market, News, Sentiment, Fundamentals, Research Manager, Trader
and Portfolio Manager all read from the same certified set. When two
agents assert incompatible values for the same scoped fact, the conflict
is recorded, never silently overwritten, and an unresolved conflict over a
critical fact blocks execution.

Rules:

- **Scope before comparison.** Metric, period, definition, unit, currency
  and segment must all match for two values to be compared. Q2 equity and
  Q3 equity are different facts, not a disagreement (``PERIOD_MISMATCH``
  is a scope difference, never auto-reconciled).
- **Missing ≠ zero.** A vendor that says nothing about a fact has not
  asserted it is zero; an absence is recorded as an absence and can never
  refute a sourced amount.
- **Source priority.** A verified primary source (company release, SEC
  filing) settles a conflict; without one the conflict stays unresolved
  and blocks.
- **Definitions are not interchangeable.** GAAP EPS, operating EPS,
  adjusted EPS and consensus estimates are different metrics; a consensus
  figure compared against an actual of another definition is
  ``METRIC_DEFINITION_MISMATCH`` — no certified "beat" without a
  compatible definition and period.

Diagnostic codes (stable, machine-readable): ``FACT_CONFLICT``,
``FACT_CONFLICT_UNRESOLVED``, ``PERIOD_MISMATCH``, ``UNIT_MISMATCH``,
``METRIC_DEFINITION_MISMATCH``, ``UNVERIFIED_FINANCIAL_METRIC``,
``PRIMARY_SOURCE_WINS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Source tiers: a verified primary settles a conflict.
PRIMARY_SOURCES = frozenset({"company_release", "sec_filing"})

# Diagnostic codes, stable for the audit trail and the Execution Gate.
FACT_CONFLICT = "FACT_CONFLICT"
FACT_CONFLICT_UNRESOLVED = "FACT_CONFLICT_UNRESOLVED"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
UNIT_MISMATCH = "UNIT_MISMATCH"
METRIC_DEFINITION_MISMATCH = "METRIC_DEFINITION_MISMATCH"
UNVERIFIED_FINANCIAL_METRIC = "UNVERIFIED_FINANCIAL_METRIC"
PRIMARY_SOURCE_WINS = "PRIMARY_SOURCE_WINS"


@dataclass(frozen=True)
class AgentFact:
    """One material financial fact as one agent asserted it.

    ``value`` is the asserted amount (None when the agent only said the
    fact is absent — recorded as an absence, never converted to 0);
    ``metric_id`` names the definition (``eps_gaap`` vs ``eps_operating``);
    ``period``/``period_end`` scope the time window; ``segment`` scopes the
    entity (company vs BNSF/GEICO); ``verified`` is whether a primary
    source backs the value.
    """

    fact_key: str                     # e.g. "stockholders_equity", "buyback_amount"
    agent: str                        # "news", "sentiment", "fundamentals"…
    value: float | None
    unit: str = ""
    currency: str | None = None
    period: str | None = None
    period_end: str | None = None
    segment: str | None = None
    metric_id: str = ""               # the definition-level metric name
    metric_definition: str = ""
    source_type: str = "unknown"
    source_reference: str | None = None   # URI / accession number
    verified: bool = False
    statement: str = ""               # the agent's own wording, for the audit

    @property
    def is_primary(self) -> bool:
        return self.source_type in PRIMARY_SOURCES

    def scope_key(self) -> tuple:
        """The scope a value must match to be compared with another's."""
        return (self.fact_key, self.metric_id, self.period, self.period_end,
                self.segment, self.unit, self.currency,
                self.metric_definition)


@dataclass
class FactConflict:
    """Incompatible assertions about the same scoped fact."""

    fact_key: str
    metric_id: str
    period: str | None
    segment: str | None
    unit: str
    currency: str | None
    metric_definition: str
    assertions: list[AgentFact] = field(default_factory=list)
    resolved_by: str | None = None      # agent whose value wins
    reason_code: str = FACT_CONFLICT_UNRESOLVED

    @property
    def resolved(self) -> bool:
        return self.resolved_by is not None

    def summary(self) -> dict:
        return {
            "fact_key": self.fact_key,
            "metric_id": self.metric_id,
            "period": self.period,
            "segment": self.segment,
            "unit": self.unit,
            "currency": self.currency,
            "metric_definition": self.metric_definition,
            "assertions": [
                {
                    "agent": a.agent,
                    "value": a.value,
                    "source_type": a.source_type,
                    "verified": a.verified,
                    "statement": a.statement[:200],
                }
                for a in self.assertions
            ],
            "resolved_by": self.resolved_by,
            "reason_code": self.reason_code,
            "resolved": self.resolved,
        }


@dataclass
class FactRegistryReport:
    """All registered facts and conflicts for one run, decision-ready."""

    facts: list[AgentFact] = field(default_factory=list)
    conflicts: list[FactConflict] = field(default_factory=list)
    not_reported: list[str] = field(default_factory=list)
    unverified_metrics: list[str] = field(default_factory=list)

    def add_fact(self, fact: AgentFact) -> None:
        self.facts.append(fact)

    def add_not_reported(self, fact_key: str) -> None:
        """Record an absence as an absence: it never becomes a zero."""
        if fact_key not in self.not_reported:
            self.not_reported.append(fact_key)

    @property
    def unresolved_conflicts(self) -> list[FactConflict]:
        return [c for c in self.conflicts if not c.resolved]

    @property
    def blocks_decision(self) -> bool:
        """An unresolved material conflict must not feed an approval."""
        return bool(self.unresolved_conflicts)

    def summary(self) -> dict:
        return {
            "total_facts": len(self.facts),
            "conflicts": [c.summary() for c in self.conflicts],
            "unresolved": [c.fact_key for c in self.unresolved_conflicts],
            "not_reported": list(self.not_reported),
            "unverified_metrics": list(self.unverified_metrics),
        }


def _agree(a: float, b: float, tolerance_pct: float) -> bool:
    if b == 0:
        return a == 0
    return abs(a - b) / abs(b) * 100 <= tolerance_pct


# Unit scales to a common base (USD million) before comparison: 9.6
# USD_billion and 9,600 USD_million are the same fact stated in different
# units, not a conflict. Keys are upper-case; the lookup normalizes. Units
# outside this table are never normalized and are only compared when
# identical.
_UNIT_TO_MILLIONS = {
    "USD": 1e-3,
    "USD_THOUSAND": 1e-6,
    "USD_MILLION": 1.0,
    "USD_BILLION": 1e3,
    "EUR": 1e-3,
    "EUR_MILLION": 1.0,
    "EUR_BILLION": 1e3,
    "GBP": 1e-3,
    "GBP_MILLION": 1.0,
    "GBP_BILLION": 1e3,
}


def _to_millions(value: float, unit: str) -> float | None:
    """The value expressed in millions, or None when the unit is unknown."""
    scale = _UNIT_TO_MILLIONS.get((unit or "").strip().upper())
    return value * scale if scale is not None else None


# EPS definition families: a consensus figure compared against an actual of
# another definition is the shape of an uncertifiable "beat".
_EPS_MARKERS = ("eps_gaap", "eps_operating", "eps_adjusted", "eps_consensus",
                "gaap_diluted", "operating_eps", "adjusted_eps",
                "consensus_eps")
# Figures that are not the company's reported GAAP number: a consensus or
# an adjusted/estimate figure is not comparable to a GAAP actual without an
# explicit reconciliation. Two GAAP-family actuals (GAAP vs operating) are
# separate facts, not a mismatch.
_ESTIMATE_MARKERS = ("consensus", "estimate", "expected", "forecast",
                     "adjusted")


def _is_eps(fact: AgentFact) -> bool:
    metric = (fact.metric_id or fact.fact_key).lower()
    definition = (fact.metric_definition or "").lower()
    if metric.startswith("eps_") or metric.endswith("_eps"):
        return True
    return any(m in definition for m in _EPS_MARKERS)


def _is_estimate(fact: AgentFact) -> bool:
    metric = (fact.metric_id or fact.fact_key).lower()
    definition = (fact.metric_definition or "").lower()
    return any(m in metric or m in definition for m in _ESTIMATE_MARKERS)


def register_facts(
    facts: list[AgentFact],
    *,
    tolerance_pct: float = 1.0,
) -> FactRegistryReport:
    """Register every agent's facts and detect the conflicts among them.

    Facts with different scopes (period, segment, unit, currency,
    definition) are never compared — a scope difference is recorded as
    ``PERIOD_MISMATCH``/``UNIT_MISMATCH`` context, not as a conflict.
    Same-scope values agreeing within tolerance corroborate; disagreeing
    ones conflict. A conflict is resolved only by a verified primary
    source; without one it stays unresolved and the caller must block.
    """
    report = FactRegistryReport()
    report.facts.extend(facts)

    # Unverified metrics: recorded so the audit can show what was used
    # without a primary source behind it.
    for fact in facts:
        if not fact.verified and fact.fact_key not in report.unverified_metrics:
            report.unverified_metrics.append(fact.fact_key)

    # Group by comparable scope. Units are normalized to a common base
    # (millions) before comparison: 9.6 USD_billion and 9,600 USD_million
    # are the same fact stated differently. The comparison key keeps the
    # normalized value's unit so a normalized group is compared on one
    # base; the original unit difference is recorded on the conflict.
    groups: dict[tuple, list[AgentFact]] = {}
    for fact in facts:
        if fact.value is None:
            continue
        normalized = _to_millions(fact.value, fact.unit)
        if normalized is not None:
            key = (fact.fact_key, fact.metric_id, fact.period,
                   fact.period_end, fact.segment, "USD_million_base",
                   fact.currency, fact.metric_definition)
        else:
            key = fact.scope_key()
        groups.setdefault(key, []).append(fact)

    for key, group in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(group) < 2:
            continue
        reference = _to_millions(group[0].value, group[0].unit)
        if reference is None:
            reference = group[0].value
        if all(
            _agree(
                (_to_millions(f.value, f.unit) if _to_millions(f.value, f.unit)
                 is not None else f.value),
                reference, tolerance_pct,
            )
            for f in group[1:]
        ):
            continue
        conflict = FactConflict(
            fact_key=key[0], metric_id=key[1], period=key[2], segment=key[4],
            unit=group[0].unit, currency=key[6], metric_definition=key[7],
            assertions=list(group),
        )
        if len({f.unit for f in group}) > 1:
            # The values were only comparable after normalization: record
            # the unit difference on the conflict for the audit trail.
            conflict.reason_code = UNIT_MISMATCH
        primaries = [f for f in group if f.verified and f.is_primary]
        if primaries and not _is_eps(group[0]):
            # A verified primary settles the value — except for the EPS
            # family: a per-share figure feeds sizing and "beat" claims, so
            # a disagreement there stays unresolved until the definitions
            # are reconciled, whatever the sources rank.
            conflict.resolved_by = primaries[0].agent
            conflict.reason_code = PRIMARY_SOURCE_WINS
        report.conflicts.append(conflict)

    # Absences: an absence never refutes a sourced value.
    for fact in facts:
        if fact.value is not None:
            continue
        contradicting = [
            o for o in facts
            if o is not fact and o.value is not None
            and o.fact_key == fact.fact_key and o.period == fact.period
            and o.segment == fact.segment
        ]
        if contradicting:
            report.conflicts.append(FactConflict(
                fact_key=fact.fact_key, metric_id=fact.metric_id,
                period=fact.period, segment=fact.segment,
                unit=contradicting[0].unit,
                currency=contradicting[0].currency,
                metric_definition=contradicting[0].metric_definition,
                assertions=[*contradicting, fact],
            ))
        elif fact.fact_key not in report.not_reported:
            report.not_reported.append(fact.fact_key)

    # EPS definition mismatches: a consensus/estimate compared against an
    # actual of another definition for the same period.
    report.conflicts.extend(_eps_definition_conflicts(facts))
    return report


def _eps_definition_conflicts(facts: list[AgentFact]) -> list[FactConflict]:
    """Flag a consensus/estimate EPS compared against an actual of another
    definition for the same period.

    Two company-reported actuals of different definitions (GAAP vs
    operating) are separate facts, not a comparison, and are not flagged.
    """
    eps_facts = [f for f in facts if f.value is not None and _is_eps(f)]
    if len(eps_facts) < 2:
        return []
    conflicts: list[FactConflict] = []
    seen: set[tuple] = set()
    for i, a in enumerate(eps_facts):
        for b in eps_facts[i + 1:]:
            if (a.metric_id, a.metric_definition) == (b.metric_id, b.metric_definition):
                continue
            if (a.period, a.segment) != (b.period, b.segment):
                continue   # different periods: separate facts
            if _is_estimate(a) == _is_estimate(b):
                continue   # two actuals or two estimates: not a beat claim
            pair = tuple(sorted((a.agent, b.agent)))
            key = (a.period, a.segment, pair)
            if key in seen:
                continue
            seen.add(key)
            conflicts.append(FactConflict(
                fact_key="eps", metric_id="eps", period=a.period,
                segment=a.segment, unit=a.unit or b.unit,
                currency=a.currency or b.currency,
                metric_definition=(
                    f"{a.metric_definition or a.metric_id} vs "
                    f"{b.metric_definition or b.metric_id}"
                ),
                assertions=[a, b],
                reason_code=METRIC_DEFINITION_MISMATCH,
            ))
    return conflicts


def check_negation_against_registry(
    fact_key: str,
    negating_agent: str,
    registry: FactRegistryReport,
    *,
    period: str | None = None,
    segment: str | None = None,
) -> FactConflict | None:
    """Whether a "no X reported" claim contradicts another agent's sourced X.

    Absence of information does not authorize a negation: when another
    agent asserted a value for the same scoped fact, the negation is a
    conflict that no absence can resolve. Returns the conflict, or None
    when nothing contradicts.
    """
    contradicting = [
        f for f in registry.facts
        if f.fact_key == fact_key and f.agent != negating_agent
        and f.value is not None and f.period == period and f.segment == segment
    ]
    if not contradicting:
        return None
    conflict = FactConflict(
        fact_key=fact_key, metric_id=contradicting[0].metric_id,
        period=period, segment=segment,
        unit=contradicting[0].unit, currency=contradicting[0].currency,
        metric_definition=contradicting[0].metric_definition,
        assertions=[
            *contradicting,
            AgentFact(
                fact_key=fact_key, agent=negating_agent, value=None,
                period=period, segment=segment, verified=False,
                statement="no value reported",
            ),
        ],
    )
    # An absence is never a verified primary: the negation cannot win.
    return conflict
