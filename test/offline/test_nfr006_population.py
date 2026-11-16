"""SEL-TA-NFR-006 — Transparent evaluation population.

Fit: completion fraction counts started fresh runs; pre-run cancels/rejects are
counted separately; zero-completed means insufficient evidence, never passing.

Enforcing design: runapi/result.summarize_records (RunRecord aggregation).
"""

from __future__ import annotations

import pytest

from tradingagents.runapi.result import RunRecord, summarize_records

pytestmark = pytest.mark.unit


# TC-NFR006-a: six completed (two review-needed) + four incomplete + two cancels.
def test_tc_nfr006_a_population_breakdown():
    started = (
        [RunRecord(f"s{i}", "STARTED", "COMPLETED", "PASSED") for i in range(4)]
        + [RunRecord(f"r{i}", "STARTED", "COMPLETED", "NEEDS_REVIEW") for i in range(2)]
        + [RunRecord(f"i{i}", "STARTED", "INCOMPLETE", "NOT_RUN", "MODEL_FAILURE") for i in range(4)]
    )
    pre = [RunRecord("c0", "PRE_RUN_CANCELLED"), RunRecord("c1", "PRE_RUN_CANCELLED")]
    summary = summarize_records(started + pre)

    assert summary["started_count"] == 10
    assert summary["completed_count"] == 6
    assert summary["completion_fraction"] == pytest.approx(0.6)
    assert summary["needs_review_count"] == 2
    assert summary["pre_run_cancelled"] == 2
    assert summary["incomplete_reason_counts"] == {"MODEL_FAILURE": 4}


# TC-NFR006-b: zero completed samples is insufficient evidence, not a pass.
def test_tc_nfr006_b_zero_completed_is_insufficient():
    summary = summarize_records([RunRecord("i0", "STARTED", "INCOMPLETE", "NOT_RUN", "DATA_FAILURE")])
    assert summary["completed_count"] == 0
    assert summary["status"] == "INSUFFICIENT_EVIDENCE"
