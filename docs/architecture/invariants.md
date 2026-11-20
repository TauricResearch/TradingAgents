# Invariants — Deterministic Safety Gate

Both invariants are non-negotiable, enforced in deterministic code, and fail closed to
`REVIEW`.

## INV-SG-01 — Selected evidence completeness
- Statement: a tradeable rating must not leave the graph unless every selected
  analyst's report and the investment plan, trader plan, and final decision are
  non-empty (a non-blank string).
- Enforcement component: `tradingagents/graph/safety_gate.py` (`evaluate_safety`).
  Required report keys derive from `build_analyst_execution_plan(selected_analysts)` —
  never a hardcoded all-four set; disabled analysts are irrelevant.
- Negative tests (`tests/test_safety_gate.py`):
  - `test_missing_or_nonstring_selected_evidence_downgrades` — empty, whitespace,
    `None`, non-string, and list reports downgrade.
  - `test_missing_plan_or_decision_downgrades` — missing plan/proposal/decision.
- Fail-closed fallback: `final_rating=REVIEW`,
  `safety_gate_status=REVIEW`, `MISSING_SELECTED_EVIDENCE` (with exact missing keys)
  and/or `MISSING_INVESTMENT_PLAN` / `MISSING_TRADER_PLAN` / `MISSING_DECISION`.

## INV-SG-02 — Monotonic downgrade only
- Statement: the gate preserves a canonical 5-tier rating or downgrades to `REVIEW`;
  it never upgrades `REVIEW` and never replaces one tradeable tier with another.
- Enforcement component: `tradingagents/graph/safety_gate.py`.
- Negative tests (`tests/test_safety_gate.py`):
  - `test_monotonic_downgrade_and_idempotence` — output is the input tier or REVIEW,
    and re-running the gate on its own output changes nothing.
  - `test_bad_or_unrecoverable_rating_fails_closed` — noncanonical/REVIEW present,
    ambiguous prose, and no-call prose all fail closed.
- Fail-closed fallback: `final_rating=REVIEW`, `UNUSABLE_RATING`.
