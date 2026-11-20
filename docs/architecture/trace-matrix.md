# Trace matrix — Deterministic Safety Gate

| Requirement / Invariant | Component | Test / evidence | Runtime state / log evidence |
|---|---|---|---|
| REQ-SG-01 gate + reason codes | `graph/safety_gate.py` `evaluate_safety`, `create_safety_gate` | `test_complete_evidence_passes_through_and_decision_text_is_unchanged`, `test_all_violations_are_collected_in_deterministic_order_with_exact_keys` | state keys `safety_gate_status`, `safety_gate_reason_codes`, `safety_gate_missing_evidence` |
| REQ-SG-02 no LLM/tool/vendor | `graph/safety_gate.py` (pure) | `test_gate_source_imports_no_llm_tool_or_vendor_layer` | no provider client constructed in node |
| REQ-SG-03 latency | `graph/safety_gate.py` | manual perf measurement (this phase) | +1 graph step, in-memory |
| REQ-SG-04 compatibility | `graph/setup.py`, `agents/state.py` (additive) | baseline regression: `test_graph_end_to_end.py`, `test_rating_integrity.py` | `final_trade_decision` unchanged; rating preserved |
| REQ-SG-05 traceability | `graph/trading_graph.py` `_log_state` | save-reports/state-log check | gate fields persisted in `full_states_log_*.json` |
| REQ-SG-06 test-first negatives | `tests/test_safety_gate.py` | every invariant has a failing-when-broken test | n/a |
| INV-SG-01 selected evidence | `graph/safety_gate.py` | `test_missing_or_nonstring_selected_evidence_downgrades`, `test_missing_plan_or_decision_downgrades`, `test_only_selected_reports_are_required` | REVIEW + `MISSING_SELECTED_EVIDENCE`/`MISSING_*` |
| INV-SG-02 monotonic | `graph/safety_gate.py` | `test_monotonic_downgrade_and_idempotence`, `test_bad_or_unrecoverable_rating_fails_closed`, `test_tradeable_rating_is_only_kept_or_downgraded` | REVIEW + `UNUSABLE_RATING` |
| Wiring (REQ-SG-01/06) | `graph/setup.py` | `test_safety_gate_wiring.py::test_gate_between_pm_and_end_without_bypass` | graph edges PM→Safety Gate→END |
| Checkpoint safety | `graph/trading_graph.py` `_run_signature` | pre-change checkpoint cannot resume past the gate | signature token `safety=gate` |
