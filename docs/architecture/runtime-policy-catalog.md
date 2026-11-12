# Runtime Policy Catalog (Member B)

Status: architecture draft. Maps each supported failure/degraded path to trigger, responsible component, fallback/action, output and diagnostic/monitor, consistent with the selected result/check contract (`SEL-TA-FR-007`, `SEL-TA-NFR-001`). Test evidence is C's; enforcement wiring is D/E's. No measured results are claimed.

## Result contract reminder
- `run_outcome = COMPLETED | INCOMPLETE`.
- `COMPLETED`: graph returned; final `rating ∈ {Buy, Overweight, Hold, Underweight, Sell, REVIEW}`.
- `INCOMPLETE`: no final rating; `stop_reason ∈ {MODEL_FAILURE, DATA_FAILURE, INTERNAL_ERROR, PERSISTENCE_ERROR, INTERRUPTED}`.
- `output_check = PASSED | NEEDS_REVIEW | NOT_RUN`; incomplete ⇒ NOT_RUN.
- Progress vocabulary (events) is separate from terminal `run_outcome`.

| # | Trigger | Responsible component | Fallback / action | Output | Diagnostic / monitor |
|---|---|---|---|---|---|
| R1 | Recoverable non-core data unavailable (upstream sentinel) | Engine/tools (baseline behaviour preserved) | Continue run with the sentinel/absent marker; **do not** classify fatal | COMPLETED (or normal) | Event notes degraded node; **not** an incomplete reason |
| R2 | Structured-output invocation fails, free text usable | `structured.py` path → PM text fallback | Use free-text; parse rating deterministically | COMPLETED; rating if readable else REVIEW | Existing structured-fallback warning retained |
| R3 | Model/provider output exhausted | `runapi/finalize.py` | Stop; no final rating | INCOMPLETE, `stop_reason=MODEL_FAILURE` | `event=run.terminal`; redacted cause |
| R4 | Raised vendor/data exception (unrecovered) | `runapi/finalize.py` | Stop; typed result | INCOMPLETE, `stop_reason=DATA_FAILURE` | Redacted data exception message |
| R5 | Ordinary internal exception | `runapi/finalize.py` | Stop; typed result, no escape past public entry | INCOMPLETE, `stop_reason=INTERNAL_ERROR` | Redacted traceback summary |
| R6 | Malformed/invalid portfolio input | `runapi/input_service.py` (precheck + upstream model) | Stop **before dispatch**; filename + bad field/path, no contents/credentials | No run (pre-run rejection) | Input diagnostic; zero LLM calls |
| R7 | As-of mismatch (`--portfolio-as-of` ≠ analysis date) | `runapi/input_service.py` | Stop before dispatch | Pre-run input error | Field-level diagnostic |
| R8 | Selected file changed after confirmation | (no reread) | **Ignore** changed bytes; use frozen snapshot | Normal run with frozen identity | (no silent change; provenance records frozen digest) |
| R9 | Output check rule broken (Q1–Q4) | `runapi/checks.py` | Do not pass; mark review needed | If graph returned: COMPLETED + NEEDS_REVIEW + blocking finding(s) | `event=output.check` findings |
| R10 | Checker raises exception | `runapi/checks.py` (fail closed) | Blocking `CHECK_ERROR` | COMPLETED retained if graph returned, but NEEDS_REVIEW | `event=output.check` `CHECK_ERROR` |
| R11 | Model text claims "OUTPUT CHECK: PASSED" but a rule fails | `runapi/checks.py` authority | Model claim ignored | NEEDS_REVIEW | Authority-source tag on check event |
| R12 | Cooperative cancellation | `runapi/execution` + CLI coordinator | Stop cooperatively (if during run) or zero-start (pre-run) | Pre-run: no completed run; during run: INCOMPLETE, `stop_reason=INTERRUPTED` | `event=input.consent`/`run.terminal` |
| R13a | Critical report/manifest staging or commit failure before rename (terminal-event append excluded) | `runapi/persist.py` + `runapi/finalize.py` | No rename; nothing visible at published path; revise logical outcome | INCOMPLETE, `stop_reason=PERSISTENCE_ERROR`, `final_rating=null`, `output_check=NOT_RUN`, `report_path=null`, `manifest_path=null` | Redacted persistence diagnostic; `_staging` not treated as published | 
| R13b | Best-effort sink failure (state JSON or message log) | `runapi/persist.py` | Continue; redacted note; does not flip a completed decision | Normal outcome unchanged | Redacted note | 
| R14 | Terminal-event JSONL append to staging fails (best-effort, non-critical) | `runapi/events.py` | Commit still publishes; logical outcome preserved (not PERSISTENCE_ERROR); manifest states non-durable terminal | Normal logical outcome; `terminal_event.durable=false` in manifest | Redacted diagnostic; later progress append never changes manifest | 
| R15 | Workflow returns unreadable final text | `runapi/finalize.py` + `runapi/checks.py` | Complete with REVIEW | COMPLETED + rating REVIEW + NEEDS_REVIEW | Q1 finding |
| R16 | Same-ticker/date second fresh run | `runapi/persist.py` / coordinator (run-ID isolation) | Write to a **new** run dir; refuse overwrite of prior artifacts | New isolated artifacts; first run unchanged | `event=output.persist` |

## Ordering and conditions
- Every incomplete result has `output_check=NOT_RUN`; every completed result has a rating (REVIEW allowed) and a check result.
- `MODEL_FAILURE` is used **only** for exhausted model/provider output failures; recoverable optional-data sentinels (R1) are never reclassified as fatal.
- Diagnostics are redacted (NFR-003) before delivery; secrets/holdings never appear.
- Durability across total disk failure/power loss is **not** promised; PERSISTENCE_ERROR is the cooperative failure contract.
