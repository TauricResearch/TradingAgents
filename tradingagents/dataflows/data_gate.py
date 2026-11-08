"""Deterministic data-quality pre-check, run before the synthesis stage.

The Execution Gate at the end of a run blocks *orders*, but by then the
Research Manager and Portfolio Manager have already debated a report built
on stale filings and wrong percentages. Blocking only the order leaves the
analysis itself wrong — and an identical PM decision, run after run, is
exactly what a report built on the same wrong numbers looks like.

This module computes the same verdicts the gate will use, *before* the
synthesis stage, and returns:

- the verdicts, stored on the state so the gate reuses them instead of
  recomputing (what the agents saw and what the gate decides cannot
  diverge);
- a short, factual notice the Research Manager and Portfolio Manager are
  given, naming the stale period and the arithmetic mismatches, so they
  qualify their conclusions instead of presenting a wrong number as a
  verified fact.

The pre-check never rewrites an agent's text and never decides the rating:
it reports what the data does not support. It is pure — no network, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.dataflows.arithmetic import (
    check_price_timestamp_alignment,
    check_stated_percentage,
)
from tradingagents.dataflows.filing_freshness import check_filing_freshness


@dataclass
class DataQualityPrecheck:
    """The verdicts the synthesis stage must see before it concludes."""

    freshness: object | None = None
    arithmetic: list = field(default_factory=list)
    blocking_codes: tuple[str, ...] = ()

    @property
    def blocks_execution(self) -> bool:
        """Whether these findings must prevent an order at the end of the run."""
        return bool(self.blocking_codes)

    @property
    def is_clean(self) -> bool:
        return not self.blocking_codes and not self.arithmetic

    def notice(self) -> str:
        """The factual block injected into the managers' prompts.

        Empty when nothing is wrong: an analyst that receives no notice is
        not being told everything is verified, only that no deterministic
        check objected. The two are different claims.
        """
        lines: list[str] = []
        freshness = self.freshness
        if freshness is not None and getattr(freshness, "blocks_decision", False):
            latest = getattr(freshness, "latest_known_period", None) or "unknown"
            used = getattr(freshness, "used_period", None) or getattr(
                freshness, "used_period_end", "unknown")
            lines.append(
                f"- **Fundamentals are not current:** the report uses the "
                f"period {used}, but the latest authoritative filing known at "
                f"the analysis date is {latest}. Treat every figure from the "
                f"older period as historical, never as the current quarter, "
                f"and say so explicitly wherever it drives a conclusion."
            )
        for verdict in self.arithmetic:
            if not getattr(verdict, "blocks_decision", False):
                continue
            lines.append(
                f"- **Arithmetic does not support the report:** "
                f"{verdict.message}. Quote the computed figure "
                f"({verdict.computed_pct:+.2f}%) or omit the claim; do not "
                f"repeat the unsupported percentage."
            )
        if not lines:
            return ""
        return (
            "## Deterministic data-quality findings (binding)\n\n"
            "A validation layer checked the report against its own data and "
            "found the following. These are computed facts, not opinions: "
            "your analysis must not present the contradicted figures as "
            "verified.\n\n"
            + "\n".join(lines)
            + "\n\n"
            "No execution may rely on a fact listed above. State the "
            "limitation in your output."
        )

    def summary(self) -> dict:
        return {
            "blocks_execution": self.blocks_execution,
            "blocking_codes": list(self.blocking_codes),
            "freshness": (
                self.freshness.summary() if self.freshness is not None else None
            ),
            "arithmetic": [v.summary() for v in self.arithmetic],
        }


def precheck_data_quality(
    *,
    trade_date: str,
    filings: list | None = None,
    used_fundamentals_period_end: str | None = None,
    used_fundamentals_period: str | None = None,
    price_snapshot: dict | None = None,
    stated_percentages: dict | None = None,
) -> DataQualityPrecheck:
    """Run the freshness and arithmetic checks before synthesis.

    Exactly the checks the Execution Gate later applies, so the managers and
    the gate never disagree about what the data supports.
    """
    result = DataQualityPrecheck()
    codes: list[str] = []

    if filings is not None:
        result.freshness = check_filing_freshness(
            used_fundamentals_period_end, filings, trade_date,
            used_period=used_fundamentals_period,
        )
        if result.freshness.blocks_decision:
            codes.append(result.freshness.reason_code)

    if price_snapshot:
        alignment = check_price_timestamp_alignment(
            price_snapshot.get("price_as_of"),
            price_snapshot.get("indicator_as_of"),
            indicator=price_snapshot.get("indicator", "indicator"),
        )
        result.arithmetic.append(alignment)
        if alignment.blocks_decision:
            codes.append(alignment.reason_code)

        close = price_snapshot.get("close")
        for label, spec in (stated_percentages or {}).items():
            verdict = check_stated_percentage(
                spec.get("stated_pct"), spec.get("reference"), close,
                label=label,
            )
            result.arithmetic.append(verdict)
            if verdict.blocks_decision:
                codes.append(verdict.reason_code)

    result.blocking_codes = tuple(dict.fromkeys(codes))
    return result


def precheck_notice_from_state(state) -> str:
    """The notice for a state that already carries a pre-check result."""
    precheck = state.get("data_quality_precheck")
    if precheck is None:
        return ""
    if isinstance(precheck, dict):
        return precheck.get("notice", "")
    return precheck.notice() if hasattr(precheck, "notice") else ""
