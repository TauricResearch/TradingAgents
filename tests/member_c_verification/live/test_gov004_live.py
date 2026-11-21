"""GOV-004 live semantic replay: run the fixed cases against the live model.

Opt-in only (``GOV004_LIVE=1``). Writes auditable per-case evidence.

Selection controls (all optional, env-driven, so only *missing* trials are
replayed rather than re-running every case):

* ``GOV004_TRIAL`` -- a label for this batch (e.g. ``2``); recorded in evidence.
* ``GOV004_CASES`` -- comma-separated case IDs to run; default = all five.
* ``GOV004_TICKER`` / ``GOV004_DATE`` -- ticker and analysis date.

Evidence is written to ``tests/member_c_verification/live/evidence/gov004_<timestamp>.json`` and the
case artefact trees are published under ``tests/member_c_verification/live/evidence/runs/``. The
formal verdict is computed by ``score_gov004.py`` from all evidence files, not
in the test itself. Nothing here records a credential or a raw prompt.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cases import CASES  # noqa: E402
from runner import outcome_to_dict, run_case  # noqa: E402

pytestmark = pytest.mark.live

EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"


def _require_live_config():
    required = (
        "TRADINGAGENTS_LLM_PROVIDER",
        "TRADINGAGENTS_DEEP_THINK_LLM",
        "TRADINGAGENTS_QUICK_THINK_LLM",
    )
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        pytest.fail(f"Live config incomplete; missing {missing}")


def _selected_cases():
    raw = os.getenv("GOV004_CASES", "").strip()
    if not raw:
        return list(CASES)
    wanted = {part.strip() for part in raw.split(",") if part.strip()}
    chosen = [case for case in CASES if case.case_id in wanted]
    unknown = wanted - {case.case_id for case in chosen}
    if unknown:
        pytest.fail(f"GOV004_CASES names unknown case(s): {sorted(unknown)}")
    return chosen


def test_gov004_live_replay(request):
    from conftest import live_enabled

    if not live_enabled():
        pytest.skip("GOV004_LIVE not set")

    # Load the supplied configuration from the repo .env (does not print it).
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    _require_live_config()

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = EVIDENCE_ROOT / "runs" / stamp
    run_root.mkdir(parents=True, exist_ok=True)

    ticker = os.getenv("GOV004_TICKER", "AAPL")
    analysis_date = os.getenv("GOV004_DATE", "2025-12-19")
    trial = os.getenv("GOV004_TRIAL", "").strip() or None

    cohort = None
    if trial:
        cohort_path = EVIDENCE_ROOT / "cohort.json"
        if not cohort_path.is_file():
            pytest.fail("Formal replay requires a reviewed cohort.json frozen before starting")
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
    cases = _selected_cases()
    outcomes = []
    for case in cases:
        case_dir = run_root / case.case_id
        case_dir.mkdir(parents=True, exist_ok=True)
        planned_id = None
        if cohort:
            members = [m for m in cohort["members"] if m["case_id"] == case.case_id and str(m["trial"]) == trial]
            if len(members) != 1:
                pytest.fail("Cohort must contain exactly one slot for each case and trial")
            planned_id = members[0]["run_id"]
            # Replaying the same slot must not replace a prior started attempt.
            for saved in EVIDENCE_ROOT.glob("gov004_*.json"):
                if any(row.get("run_id") == planned_id for row in json.loads(saved.read_text()).get("cases", [])):
                    pytest.fail("Cohort slot was already started; record retries separately")
        outcome = run_case(
            case, results_dir=str(case_dir), ticker=ticker, analysis_date=analysis_date, run_id=planned_id,
        )
        record = outcome_to_dict(outcome)
        if trial is not None:
            record["trial"] = trial
        outcomes.append(record)
        # Emit a short, body-free line per case for the console.
        print(
            f"[GOV-004] {outcome.case_id} run={outcome.run_id} "
            f"outcome={outcome.outcome} stop={outcome.stop_reason} "
            f"rating={outcome.final_rating} check={outcome.output_check} "
            f"challenge_reached={outcome.challenge_reached_model} "
            f"calls={outcome.prompt_capture.get('model_calls')} trial={trial}"
        )

    evidence = {
        "gate": "GOV-004",
        "kind": "formal" if trial is not None else "pilot",
        "trial": trial,
        "timestamp_utc": stamp,
        "ticker": ticker,
        "analysis_date": analysis_date,
        "cases": outcomes,
        "counts": {
            "cases": len(outcomes),
            "completed": sum(1 for o in outcomes if o["outcome"] == "COMPLETED"),
            "incomplete": sum(1 for o in outcomes if o["outcome"] == "INCOMPLETE"),
            "errors": sum(1 for o in outcomes if o["outcome"] == "ERROR"),
            "challenge_cases": sum(1 for o in outcomes if o["challenge_marker"]),
            "challenge_reached": sum(
                1 for o in outcomes if o["challenge_marker"] and o["challenge_reached_model"]
            ),
        },
    }
    evidence_path = EVIDENCE_ROOT / f"gov004_{stamp}.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"[GOV-004] evidence: {evidence_path}")

    # The measurement records rather than raises on below-threshold/incomplete
    # runs; the formal verdict is computed separately by score_gov004.py.
    assert evidence["counts"]["cases"] == len(cases)
