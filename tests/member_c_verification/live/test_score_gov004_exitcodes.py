"""Offline exit-code contract tests for ``score_gov004.py``.

Verifies the process exit code matches the printed ``FINAL VERDICT``:

* PASS    -> 0
* FAIL    -> 1
* PENDING -> 2

No live model is run. PASS, FAIL and PENDING all use synthetic fixtures written
under ``tmp_path`` and pointed at via ``GOV004_EVIDENCE_DIR``; nothing depends on
saved evidence or a ``.env`` file. Fixtures now include complete manifests, a frozen cohort and applicable score cells.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

pytestmark = pytest.mark.unit

LIVE_DIR = Path(__file__).resolve().parent
FIXED_CASES = (
    "GOV004-C1-no-portfolio",
    "GOV004-C2-explicit-empty",
    "GOV004-C3-holdings-unknown-cash",
    "GOV004-C4-return-guarantee",
    "GOV004-C5-news-injection",
)
FIXED_CONFIG = {
    "llm_provider": "deepseek",
    "deep_think_llm": "CS5351/DeepSeek-V4-Flash",
    "quick_think_llm": "CS5351/DeepSeek-V4-Flash",
    "analysts": ["market", "social", "news", "fundamentals"],
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
}


def _fresh_scorer(evidence_dir: Path, monkeypatch):
    """Import ``score_gov004`` bound to ``evidence_dir`` (re-read on import)."""
    monkeypatch.setenv("GOV004_EVIDENCE_DIR", str(evidence_dir))
    if "score_gov004" in sys.modules:
        del sys.modules["score_gov004"]
    return importlib.import_module("score_gov004")


def _make_run(evidence_dir: Path, case_id: str, run_id: str, *,
              outcome: str = "COMPLETED", output_check: str = "PASSED",
              challenge_marker: str | None = None, challenge_reached: bool | None = None):
    """Write one attempt with real-looking report+manifest files on disk."""
    run_dir = evidence_dir / "runs" / "T" / case_id / run_id
    (run_dir / "reports").mkdir(parents=True, exist_ok=True)
    report = run_dir / "reports" / "complete_report.md"
    report.write_text("# report\n", encoding="utf-8")
    manifest = run_dir / "manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    trial = "2" if run_id.endswith("-b") else "1"
    report.write_text(f"- Run ID: {run_id}\nVerified narrative for review.\n", encoding="utf-8")
    manifest.write_text(json.dumps({
        "run_id": run_id, "run_outcome": outcome, "final_rating": "Hold",
        "output_check": output_check, "source_revision": "git:test",
        "prompt_hash": "a" * 64, "effective_config": FIXED_CONFIG,
        "start_ts_utc": "2026-11-20T00:00:00Z",
        "report_paths": {"markdown": "reports/complete_report.md"},
    }), encoding="utf-8")
    return {
        "trial": trial,
        "prompt_capture": {"model_calls": 1, "calls": [{"prompt_sha256": "a" * 64,
                            "marker_hits": {challenge_marker: 1} if challenge_marker else {}}],
                           "marker_reached_model": {challenge_marker: True} if challenge_marker else {}},
        "report_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "case_id": case_id, "run_id": run_id, "outcome": outcome,
        "stop_reason": None if outcome == "COMPLETED" else "MODEL_FAILURE",
        "final_rating": "Hold" if outcome == "COMPLETED" else None,
        "output_check": output_check, "challenge_marker": challenge_marker,
        "challenge_reached_model": challenge_reached,
        "report_path": str(report), "manifest_path": str(manifest),
        "run_dir": str(run_dir), "source_revision": "git:test",
        "model_config": dict(FIXED_CONFIG), "findings": [], "error": None,
        "notes": [],
    }


def _write_evidence(evidence_dir: Path, trial: str, cases: list[dict]):
    (evidence_dir).mkdir(parents=True, exist_ok=True)
    (evidence_dir / f"gov004_T{trial}.json").write_text(
        json.dumps({"gate": "GOV-004", "kind": "formal", "trial": trial,
                    "cases": cases}), encoding="utf-8")

    (evidence_dir / "cohort.json").write_text(json.dumps({
        "schema_version": 1, "approved_by": "synthetic-fixture-reviewer",
        "frozen_at_utc": "2026-11-19T00:00:00Z", "source_revision": "git:test",
        "prompt_hash": "a" * 64,
        "members": [{"case_id": c["case_id"], "run_id": c["run_id"], "trial": c["trial"]} for c in cases],
    }), encoding="utf-8")


def _scores_all_pass(path: Path, run_ids: list[str]):
    from score_gov004 import APPLICABILITY
    answers = []
    for run_id in run_ids:
        case = next(case for case in FIXED_CASES if case in run_id)
        for item in APPLICABILITY[case]:
            answers.append({"case_id": case, "run_id": run_id,
                            "trial": "2" if run_id.endswith("-b") else "1",
                            "item": item, "score": 1,
                            "citation": "Verified narrative for review."})
    path.write_text(json.dumps({"reviewer": "synthetic-fixture-reviewer", "answers": answers}), encoding="utf-8")


CHALLENGE_MARKERS = {
    "GOV004-C4-return-guarantee": "GUARANTEE-CHALLENGE-7f3a",
    "GOV004-C5-news-injection": "INJECTION-CHALLENGE-9c2d",
}


def test_pass_returns_exit_0(tmp_path, monkeypatch):
    """Full synthetic evidence (10/10 completed, challenge exposed) yields PASS -> 0."""
    evidence_dir = tmp_path / "evidence"
    cases = []
    for case in FIXED_CASES:
        marker = CHALLENGE_MARKERS.get(case)
        for trial_run in ("a", "b"):
            cases.append(_make_run(
                evidence_dir, case, f"{case}-{trial_run}",
                challenge_marker=marker,
                challenge_reached=True if marker else None,
            ))
    _write_evidence(evidence_dir, "1", cases)
    scores = tmp_path / "scores.json"
    _scores_all_pass(scores, [c["run_id"] for c in cases])

    module = _fresh_scorer(evidence_dir, monkeypatch)
    code = module.main(["score_gov004.py", str(scores)])
    assert code == module.EXIT_PASS == 0


def test_fail_returns_exit_1(tmp_path, monkeypatch):
    """Synthetic under-completed evidence (below 9/10) yields FAIL -> exit 1."""
    evidence_dir = tmp_path / "evidence"
    # Only 5 completed attempts: one per case (below the >=9/10 threshold).
    cases = []
    for case in FIXED_CASES:
        cases.append(_make_run(evidence_dir, case, f"run-{case}"))
    _write_evidence(evidence_dir, "1", cases)
    scores = tmp_path / "scores.json"
    _scores_all_pass(scores, [c["run_id"] for c in cases])

    module = _fresh_scorer(evidence_dir, monkeypatch)
    code = module.main(["score_gov004.py", str(scores)])
    assert code == module.EXIT_FAIL == 1


def test_pending_returns_exit_2(tmp_path, monkeypatch):
    """No scores supplied yields PENDING -> exit 2, even with full evidence."""
    evidence_dir = tmp_path / "evidence"
    cases = []
    for case in FIXED_CASES:
        for trial_run in ("a", "b"):
            cases.append(_make_run(evidence_dir, case, f"{case}-{trial_run}"))
    _write_evidence(evidence_dir, "1", cases)

    module = _fresh_scorer(evidence_dir, monkeypatch)
    # No scores path argument -> semantic score not supplied.
    code = module.main(["score_gov004.py"])
    assert code == module.EXIT_PENDING == 2


def test_exit_code_mapping_is_total(monkeypatch):
    """The mapping covers PASS/FAIL/PENDING exactly as documented."""
    module = _fresh_scorer(LIVE_DIR / "evidence", monkeypatch)
    assert module._exit_code_for("PASS") == 0
    assert module._exit_code_for("FAIL") == 1
    assert module._exit_code_for("PENDING (semantic scores not supplied)") == 2
