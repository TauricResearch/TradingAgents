# Test Plan (Member C)

Status: **living document.** Approved in principle by the human reviewer for this
verification step. Records the independent offline acceptance tests that exist, how
they are run, and what remains undone. It does **not** claim the semantic-evaluation
gate or CI governance gates are satisfied.

Scope: the working selection `docs/req/selected-requirements.md`
(`SEL-TA-FR-001..007`, `SEL-TA-NFR-001..006`). Governance items
(`SEL-TA-GOV-001..006`) are tracked separately and are **not** yet verifiable here
(no CI/permission enforcement installed, semantic rubric/threshold not frozen).

## 1. Levels, fixtures, environment

- **Tier:** offline behavioural/structural unit tests. No network, no provider
  billing, no real holdings. Synthetic portfolio JSON in per-test `tmp_path`.
- **Engine:** a scripted engine injected through the shared boundary
  `runapi.execution.run_analysis_api(graph_factory=..., engine_runner=...)`.
  This exercises the real check/finalize/persist path with a deterministic state.
- **Location:** `tests/member_c_verification/offline/` (C-owned). It lives under
  the upstream `testpaths=["tests"]`, so the default `pytest` run collects it
  alongside the upstream suite; the offline tests keep the upstream conftest's
  no-network/scripted-model discipline. The `live/` sibling is collected too but
  skipped unless `GOV004_LIVE=1` (opt-in).
- **Helpers:** `tests/member_c_verification/offline/conftest.py` (`make_engine`, `confirmed_context`,
  `GOOD_STATE`, `holding_portfolio`).

### Commands
```
# New independent C suite (separate from upstream)
.venv/bin/python -m pytest tests/member_c_verification/offline -p no:cacheprovider

# Upstream regression baseline (unchanged by this work)
.venv/bin/python -m pytest -q -p no:cacheprovider
```

## 2. Test independence and human approval

- Tests assert observable contract behaviour through public seams; they do not
  import application internals beyond the documented design modules.
- Test files were authored by C after the plan was approved; application code was
  **not** modified for these tests.
- Approval reference: human message approving the plan for this verification work
  (recorded in the session transcript). Formal GOV-001 attributable sign-off in
  `docs/architecture/trace-matrix.md` / CI remains with E.

## 3. Entry / exit criteria

- **Entry:** selection approved as working scope; implementation present at
  `d94c9f8`; offline environment runnable.
- **Exit (per case):** test passes deterministically with no network.
- **Exit (suite):** all offline cases green and upstream suite shows no new
  regressions beyond the known environmental failure (see verification report).

## 4. Case inventory (IDs → requirement → expected)

| Test ID | Requirement | Scenario | Expected result |
|---|---|---|---|
| TC-FR001-a | SEL-TA-FR-001 | a/b + nested + symlink + .txt present | only `a.json,b.json`, sorted |
| TC-FR001-b | SEL-TA-FR-001 | missing dir | empty list, not error |
| TC-FR001-c | SEL-TA-FR-001 | empty dir | empty list |
| TC-FR001-d | SEL-TA-FR-001 | directory read error | `DirectoryReadError` (not "empty") |
| TC-FR001-e | SEL-TA-FR-001 | select b | only b validated; basename `b.json` |
| TC-FR002-a | SEL-TA-FR-002 | FROZEN context to entry | `ValueError` (consent required) |
| TC-FR002-b | SEL-TA-FR-002 | CONFIRMED context | runs once, COMPLETED |
| TC-FR002-c | SEL-TA-FR-002 | both flags / no as-of | `FLAG_CONFLICT` / `AS_OF_MISMATCH` |
| TC-FR002-d | SEL-TA-FR-002 | `--without-portfolio` | one run with `portfolio is None` |
| TC-FR003-a | SEL-TA-FR-003 | valid populated | loads; provenance fields set |
| TC-FR003-b | SEL-TA-FR-003 | explicit empty `positions` | valid flat snapshot |
| TC-FR003-c | SEL-TA-FR-003 | `cash:null` | cash preserved as `None` |
| TC-FR003-d | SEL-TA-FR-003 | 5 invalid classes (param) | typed `InputError` w/ kind+field |
| TC-FR003-e | SEL-TA-FR-003 | unreadable path | `UNREADABLE_PATH` |
| TC-FR003-f | SEL-TA-FR-003 | as-of != analysis date | `AS_OF_MISMATCH` |
| TC-FR003-g | SEL-TA-FR-003 | edit file after freeze | frozen rows/digest unchanged |
| TC-FR004-a | SEL-TA-FR-004 | no portfolio | frozen notice, no "current position" |
| TC-FR004-b | SEL-TA-FR-004 | explicit flat | "No current position in AAPL" |
| TC-FR004-c | SEL-TA-FR-004 | held + missing cash | holding shown; no invented cash |
| TC-FR004-d | SEL-TA-FR-004 | broker alias | alias matched to instrument |
| TC-FR004-e | SEL-TA-FR-004 | two selections | no cross-selection holding leak |
| TC-FR005-a | SEL-TA-FR-005 | 5 ratings + REVIEW (param) | each parsed as itself |
| TC-FR005-b | SEL-TA-FR-005 | unreadable text | `REVIEW`, never Hold |
| TC-FR005-c | SEL-TA-FR-005 | completed RunResult | one rating enforced |
| TC-FR005-d | SEL-TA-FR-005 | report w/ differing RM/Trader/PM judgments | 3 labelled stages; exactly one PM-sourced final rating |
| TC-FR006-a | SEL-TA-FR-006 | documented Reason-E book | fingerprint = `45f07d9e…cef72`, 64 hex |
| TC-FR006-b | SEL-TA-FR-006 | reorder / 1 vs 1.0 / null price | equal digests |
| TC-FR006-c | SEL-TA-FR-006 | none vs explicit empty | distinct mode/fingerprint |
| TC-FR006-d | SEL-TA-FR-006 | select b | b fingerprint, != a |
| TC-FR006-e | SEL-TA-FR-006 | 2 runs, same contents/date, fresh IDs, different text | both texts published; provenance identical (minus run ID/ts) |
| TC-FR007-a | SEL-TA-FR-007 | all rules hold | PASSED, no findings |
| TC-FR007-b | SEL-TA-FR-007 | each Q1/Q2/Q3/Q4 break | matching finding, NEEDS_REVIEW |
| TC-FR007-c | SEL-TA-FR-007 | body claims "OUTPUT CHECK: PASSED" | ignored; NEEDS_REVIEW |
| TC-FR007-d | SEL-TA-FR-007 | `evaluate` raises inside `run_analysis_api` | called; COMPLETED + NEEDS_REVIEW + one CHECK_ERROR |
| TC-FR007-e | SEL-TA-FR-007 | check under blocked sockets | PASSED (no provider) |
| TC-NFR001-a | SEL-TA-NFR-001 | unreadable final text | COMPLETED + REVIEW + NEEDS_REVIEW |
| TC-NFR001-b | SEL-TA-NFR-001 | internal exception | INCOMPLETE / INTERNAL_ERROR |
| TC-NFR001-c | SEL-TA-NFR-001 | vendor exception | DATA_FAILURE |
| TC-NFR001-d | SEL-TA-NFR-001 | provider lib / timeout | MODEL_FAILURE |
| TC-NFR001-d2 | SEL-TA-NFR-001 | bare ConnectionError | INTERNAL_ERROR (guard) |
| TC-NFR001-e | SEL-TA-NFR-001 | raised engine error | no exception escapes |
| TC-NFR002-a | SEL-TA-NFR-002 | completed run events | all parse, fields non-null, elapsed≥0, 1 terminal |
| TC-NFR002-b | SEL-TA-NFR-002 | second terminal | rejected |
| TC-NFR002-c | SEL-TA-NFR-002 | secret in event | redacted |
| TC-NFR003-a | SEL-TA-NFR-003 | 4 secret types (param) | each scrubbed |
| TC-NFR003-b | SEL-TA-NFR-003 | secret-keyed mapping | values redacted |
| TC-NFR003-c | SEL-TA-NFR-003 | diagnostic w/ secret | type kept, secret hidden |
| TC-NFR003-d | SEL-TA-NFR-003 | model error + synthetic portfolio via API | no secret/unrelated-holding leak in result/report/manifest/events; source unchanged |
| TC-NFR003-e | SEL-TA-NFR-003 | CLI pre-run portfolio input error | no secret/unrelated-holding in CLI output; source unchanged |
| TC-NFR003-f | SEL-TA-NFR-003 | mid-run vendor exception via API | INCOMPLETE/DATA_FAILURE/NOT_RUN; no secret/unrelated-holding in result/report(.md/.html)/manifest/events; vendor stub reached; source unchanged |
| TC-NFR003-g | SEL-TA-NFR-003 | completed narrative with planted credential (md+html) | COMPLETED; benign sentence retained; credential omitted in both reports; [REDACTED] present |
| TC-NFR004-a | SEL-TA-NFR-004 | two same-ticker/date runs | isolated dirs; first bytes unchanged |
| TC-NFR004-b | SEL-TA-NFR-004 | portfolio provided | manifest omits payload/cash |
| TC-NFR004-c | SEL-TA-NFR-004 | completed manifest | conditional fields correct (rating present, stop_reason null) |
| TC-NFR004-d | SEL-TA-NFR-004 | one config value changed | only that key differs in `effective_config`; run IDs differ |
| TC-NFR004-e | SEL-TA-NFR-004 | prompt-template file edited (simulated) | `prompt_hash` changes; `effective_config` unchanged |
| TC-NFR004-f | SEL-TA-NFR-004 | engine error → published INCOMPLETE | manifest has `final_rating=null`, `output_check=NOT_RUN`, a `stop_reason` |
| TC-NFR004-g | SEL-TA-NFR-004 | R13a commit failure (rename fails) | INCOMPLETE/PERSISTENCE_ERROR/NOT_RUN; no rating; nothing published; no `_staging` left |
| TC-NFR004-h | SEL-TA-NFR-004 | R13b best-effort state.json write fails | COMPLETED outcome preserved; `BEST_EFFORT_FAILED:state.json` in events |
| TC-NFR004-i | SEL-TA-NFR-004 | R14 terminal-event append fails | COMPLETED preserved; manifest `terminal_event.durable=false` |
| TC-NFR005-a | SEL-TA-NFR-005 | scan runapi/agents/graph | no terminal-prompt imports |
| TC-NFR005-b | SEL-TA-NFR-005 | scan runapi imports | no `cli` import |
| TC-NFR006-a | SEL-TA-NFR-006 | 6 complete/4 incomplete/2 cancel | 6/10, review 2, cancel 2 |
| TC-NFR006-b | SEL-TA-NFR-006 | zero completed | INSUFFICIENT_EVIDENCE |

Parametrised cases expand to 80 collected test items.

## 5. Plan changes made during implementation (with reasons)

1. **FR-002-c boundary retargeted.** The as-of/flag guards are enforced in
   `cli/input_ui.resolve_run_context` (returns typed `InputError`), not in
   `cli/main.py`. Test now targets the enforcing guard rather than the wiring.
2. **NFR-001-d expectation corrected.** `classify_exception` maps by exception
   name/module; a bare `ConnectionError` is genuinely `INTERNAL_ERROR`. The
   MODEL_FAILURE case now uses a provider-library exception + `TimeoutError`, and
   a separate case pins `ConnectionError → INTERNAL_ERROR`.
3. **FR-003 calls fixed** to use an instance (`PortfolioInputService(dir)`), since
   `freeze_path`/`freeze_loaded` are instance methods.
4. **NFR-005 tests are structural** (AST import scan), matching INV-10's
   "testability: structural" note.
5. **TC-FR006-e / TC-FR007-d strengthened** to run through the full
   `run_analysis_api` publish path (two-run provenance identity with differing
   model text; checker raising during the run into the fail-closed branch) rather
   than exercising isolated seams. Both pass.
6. **FR-005 / NFR-003 end-to-end cases added** (existing a–c retained unchanged):
   TC-FR005-d asserts labelled RM/Trader/PM stages and one PM-sourced rating;
   TC-NFR003-d asserts no secret/unrelated-holding leak across result/report/
   manifest/events on a model-error path; TC-NFR003-e asserts the same for a CLI
   pre-run input error. All pass.
7. **TC-NFR003-f added** to close the mid-run data-error gap: a reached vendor
   stub raises an unrecovered `NoMarketDataError` through `run_analysis_api`;
   asserts INCOMPLETE/DATA_FAILURE/NOT_RUN and leak-free result/report(.md/.html)/
   manifest/events with an unchanged source file. Passes.
8. **TC-NFR003-g added**: a completed run whose scripted narrative embeds a fake
   credential publishes Markdown + HTML that retain the benign sentence and omit
   the credential (with `[REDACTED]`). Passes.

## 6. Deferred / not yet covered

- **GOV-001..006** CI and permission-gate tests — blocked on E enforcement and a
  frozen semantic rubric.
- **Semantic evaluation (GOV-004)** — see §7.
- **Persistence-failure walkthroughs** (R13a/R13b/R14): **covered offline** by
  TC-NFR004-g/h/i (injected commit failure, best-effort sink failure, terminal
  event append failure). See `verification-report.md` §3.5.
- **Corrupt-checkpoint / interrupted-run** (R12 INTERRUPTED) behavioural tests.
- `tests/member_c_verification/offline` vs `tests/member_c_verification/live` full course layout split; both exist under `tests/member_c_verification/`.
