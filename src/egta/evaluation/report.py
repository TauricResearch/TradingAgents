"""Paired comparison report (E2).

# Implements: FR-05

``pair_report`` is a **pure delegation** to
:func:`egta.contracts.evaluation.compare_runs` (the sole authority). It never
re-implements comparison logic; when a ``manifest`` is supplied, ``compare_runs``
performs the D#1 recompute → MANIFEST_MISMATCH. An INCOMPLETE pair is never a win
(``winner``/``baseline_win``/``enhanced_win`` stay None/False via compare_runs).
"""

from __future__ import annotations

from egta.contracts.evaluation import EvaluationResult, RunSummary, compare_runs
from egta.contracts.manifest import ExperimentManifest


def pair_report(
    baseline: RunSummary,
    enhanced: RunSummary,
    rubric: dict,
    *,
    manifest: ExperimentManifest | None = None,
    run_pair_id: str | None = None,
    case_id: str | None = None,
) -> EvaluationResult:
    """Return the comparison result (delegated to ``compare_runs``)."""
    return compare_runs(
        baseline, enhanced, rubric,
        manifest=manifest, run_pair_id=run_pair_id, case_id=case_id,
    )
