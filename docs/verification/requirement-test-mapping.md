# Requirement → Test Mapping (for Member E)

Status: C's current verification roll-up for E's shared `docs/architecture/trace-matrix.md`.
Test IDs and evidence are C-owned and real; **implementation links are D's** and
left as the existing `runapi/*` module references. Governance rows are marked by
status, not faked.

Legend for **Status**:
- `PASS (offline)` — covered by a passing synthetic offline test now.
- `PARTIAL` — some aspects covered; noted gaps remain.
- `NOT VERIFIED` — no passing evidence; reason given.
- `OWNED ELSEWHERE` — not a C test artifact (A/E/human).

Evidence root: `test/offline/` (run: `.venv/bin/python -m pytest test/offline -p no:cacheprovider`).
Suite result at time of writing: **74 passed, 0 failed**.

## Functional requirements

| Req ID | Test IDs | Status | Evidence location | Notes / gap |
|---|---|---|---|---|
| SEL-TA-FR-001 | TC-FR001-a..e | PASS (offline) | `test/offline/test_fr001_discovery.py` | Interactive picker UI flow itself mocked at service layer |
| SEL-TA-FR-002 | TC-FR002-a..d | PASS (offline) | `test/offline/test_fr002_consent.py` | Consent gate + flag rules; EOF prompt path not driven via tty |
| SEL-TA-FR-003 | TC-FR003-a..g | PASS (offline) | `test/offline/test_fr003_validation_freeze.py` | 5 of 6 invalid classes param'd + unreadable as TC-e |
| SEL-TA-FR-004 | TC-FR004-a..e | PASS (offline) | `test/offline/test_fr004_propagation.py` | Asserted at render/context seam, not live LLM prompt |
| SEL-TA-FR-005 | TC-FR005-a..d | PASS (offline) | `test/offline/test_fr005_ratings.py` | TC-d end-to-end: 3 labelled stages (RM/Trader/PM) + exactly one PM-sourced final rating |
| SEL-TA-FR-006 | TC-FR006-a..e | PASS (offline) | `test/offline/test_fr006_provenance.py` | TC-e now end-to-end: two full runs, both texts published, provenance identical minus run ID/timestamp |
| SEL-TA-FR-007 | TC-FR007-a..e | PASS (offline) | `test/offline/test_fr007_output_check.py` | TC-d now drives `run_analysis_api`; checker raising ⇒ COMPLETED + NEEDS_REVIEW + one CHECK_ERROR |

## Non-functional requirements

| Req ID | Test IDs | Status | Evidence location | Notes / gap |
|---|---|---|---|---|
| SEL-TA-NFR-001 | TC-NFR001-a..e,d2 | PASS (offline) | `test/offline/test_nfr001_failures.py` | Typed outcomes; no escape; INTERRUPTED (R12) not yet tested |
| SEL-TA-NFR-002 | TC-NFR002-a..c | PASS (offline) | `test/offline/test_nfr002_events.py` | Sink-level; full-run JSONL parse via completed run |
| SEL-TA-NFR-003 | TC-NFR003-a..g | PASS (offline) | `test/offline/test_nfr003_privacy.py` | TC-d model-error, TC-e CLI input-error, TC-f mid-run vendor/data-error, TC-g successfully-published narrative: no secret/unrelated-holding leak in result/report(.md/.html)/manifest/events/CLI; benign sentence retained; source unchanged; vendor stub reached; DATA_FAILURE/NOT_RUN. Residual: universal absence of arbitrary/paraphrased secrets in narrative depends on Redactor + GOV-004 (NOT RUN) |
| SEL-TA-NFR-004 | TC-NFR004-a..c | PARTIAL | `test/offline/test_nfr004_persistence.py` | Isolation + payload omission; failure walkthroughs (R13/R14) pending |
| SEL-TA-NFR-005 | TC-NFR005-a,b | PASS (offline) | `test/offline/test_nfr005_layering.py` | Structural import scan (INV-10) |
| SEL-TA-NFR-006 | TC-NFR006-a,b | PASS (offline) | `test/offline/test_nfr006_population.py` | Aggregation interface; zero-completed ⇒ insufficient |

## Governance requirements

| Req ID | Status | Evidence / owner | Notes |
|---|---|---|---|
| SEL-TA-GOV-001 | OWNED ELSEWHERE | E/human; transcript approval ref in test-plan §2 | Formal attributable sign-off pending in trace-matrix/CI |
| SEL-TA-GOV-002 | OWNED ELSEWHERE | A (schema); E (validate) | A's `requirements.yaml`/schema not delivered here |
| SEL-TA-GOV-003 | NOT VERIFIED | E (CI); baseline in verification-report §2 | Zero-regression blocked by BD-001 env failure decision |
| SEL-TA-GOV-004 | NOT VERIFIED | C/A rubric; D runner | **Semantic evaluation NOT RUN** — rubric/threshold unfrozen |
| SEL-TA-GOV-005 | NOT VERIFIED | E/all | AI-use-log gate not installed |
| SEL-TA-GOV-006 | NOT VERIFIED | B design; E enforce | Denied-write demo not installed |

## Baseline regression evidence

- Upstream suite: **1412 passed, 1 failed (BD-001, environmental), 0 skipped, 1 deselected**.
- C suite: **74 passed**.
- No new regressions attributable to C's tests (they live outside `tests/`/`testpaths`).
