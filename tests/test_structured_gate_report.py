"""Tests for scripts/structured_gate_report.py (TradingAgents#19 step 4).

The report's job is to tell "correctly abstaining" apart from "too
conservative" -- identical from the rating alone, opposite fixes. What matters
is that each gate is distinguishable and that rows it cannot attribute are
reported as unknown rather than folded into a bucket.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load():
    path = Path(__file__).parent.parent / "scripts" / "structured_gate_report.py"
    spec = importlib.util.spec_from_file_location("structured_gate_report_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["structured_gate_report_under_test"] = module
    spec.loader.exec_module(module)
    return module


def _row(rating="Hold", score=0.0, catalyst=True, hours=3.0, flags=(), reason="", **over):
    row = {
        "ticker": "KOTAKBANK.NS",
        "trade_date": "2026-07-17",
        "structured_rating": rating,
        "structured_score": score,
        "structured_reason": reason,
        "structured_factors": {
            "dated_catalyst_present": catalyst,
            "catalyst_hours_to_resolution": hours,
            "technical_direction": 0.35, "technical_confidence": 0.55,
            "sentiment_direction": 0.45, "sentiment_confidence": 0.60,
            "risk_flags": list(flags),
        },
    }
    row.update(over)
    return row


@pytest.mark.unit
class TestClassify:
    def test_directional_rating_is_its_own_gate(self):
        mod = _load()
        assert mod.classify(_row(rating="Overweight", score=0.39))["gate"] == "directional"

    def test_no_catalyst_is_not_a_threshold_problem(self):
        """Re-tuning thresholds cannot move these, so they must not be
        counted alongside the score-band cases."""
        mod = _load()
        c = mod.classify(_row(catalyst=False, hours=None, score=0.0))
        assert c["gate"] == "catalyst_absent"
        assert c["gap"] is None

    def test_catalyst_outside_the_window_is_distinguished_from_the_score_band(self):
        mod = _load()
        c = mod.classify(_row(
            hours=48.0, score=0.0,
            reason="Catalyst identified but resolves in 48.0h, beyond the 24h window ..."))
        assert c["gate"] == "catalyst_too_far"

    def test_score_band_case_reports_how_far_it_missed(self):
        """The KOTAKBANK shape: both hard gates passed, Hold on the score
        alone. This is the only bucket threshold calibration can act on."""
        mod = _load()
        c = mod.classify(_row(score=0.185, flags=["a", "b", "c", "d"]))
        assert c["gate"] == "score_below_band"
        assert c["gap"] == pytest.approx(0.015, abs=1e-4)
        assert c["flags"] == 4

    def test_negative_score_gap_measures_toward_underweight(self):
        mod = _load()
        c = mod.classify(_row(score=-0.18))
        assert c["gate"] == "score_below_band"
        assert c["gap"] == pytest.approx(0.02, abs=1e-4)

    def test_row_without_a_persisted_score_is_unrecoverable_not_guessed(self):
        """Pre-persistence rows must not be silently attributed -- assuming a
        gate for them is exactly the guess this report replaces."""
        mod = _load()
        legacy = {"ticker": "HCLTECH.NS", "trade_date": "2026-07-10", "rating": "Hold"}
        c = mod.classify(legacy)
        assert c["gate"] == "unrecoverable"
        assert c["score"] is None


@pytest.mark.unit
class TestUndamped:
    def test_inverts_the_risk_flag_damping(self):
        mod = _load()
        assert mod.undamped(0.185, 4) == pytest.approx(0.4625, abs=1e-3)

    def test_returns_none_when_damping_zeroed_the_score(self):
        """>= 7 flags multiplies by <= 0 -- not invertible, so don't invent
        a number."""
        mod = _load()
        assert mod.undamped(0.0, 7) is None

    def test_no_flags_is_the_identity(self):
        mod = _load()
        assert mod.undamped(0.3, 0) == pytest.approx(0.3)


@pytest.mark.unit
class TestReport:
    def test_counts_each_gate(self):
        mod = _load()
        report = mod.build_report([
            _row(rating="Overweight", score=0.39),
            _row(catalyst=False, hours=None),
            _row(hours=48.0, reason="resolves in 48.0h, beyond the 24h window"),
            _row(score=0.185, flags=["a", "b", "c", "d"]),
        ])
        assert report["counts"] == {
            "directional": 1, "catalyst_absent": 1,
            "catalyst_too_far": 1, "score_below_band": 1,
        }

    def test_error_rows_are_skipped(self):
        mod = _load()
        report = mod.build_report([{"ticker": "X", "error": "LLM timeout"}, _row()])
        assert len(report["rows"]) == 1

    def test_near_misses_sorted_closest_first(self):
        mod = _load()
        report = mod.build_report([_row(score=0.05), _row(score=0.185), _row(score=0.12)])
        assert [c["score"] for c in report["near_misses"]] == [0.185, 0.12, 0.05]

    def test_output_flags_a_damped_near_miss_that_would_have_fired(self, capsys):
        """The actionable finding: 4 flags cut a 0.46 score to 0.185, i.e. the
        damping rather than the threshold is what held it."""
        mod = _load()
        mod.print_report(mod.build_report([_row(score=0.185, flags=["a", "b", "c", "d"])]))
        out = capsys.readouterr().out
        assert "missed by 0.015" in out
        assert "would have fired undamped" in out

    def test_all_unrecoverable_batch_says_nothing_is_known(self, capsys):
        """Must not read as 'no calibration cases exist' when the truth is
        'no data' -- those imply opposite next steps."""
        mod = _load()
        mod.print_report(mod.build_report([{"ticker": "X", "trade_date": "d", "rating": "Hold"}]))
        out = capsys.readouterr().out
        assert "Nothing here is attributable" in out
        assert "predates score persistence" in out

    def test_attributable_batch_with_no_near_misses_says_the_constraint_is_upstream(self, capsys):
        mod = _load()
        mod.print_report(mod.build_report([_row(catalyst=False, hours=None)]))
        out = capsys.readouterr().out
        assert "binding constraint is upstream" in out
