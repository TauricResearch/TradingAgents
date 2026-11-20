# FR-04 Phase 0–4 Spec Summary

- **Date:** 2026-11-20 (Asia/Hong_Kong)
- **Branch:** `spec/FR-04-risk-gate`
- **Initial spec commit:** `2bbbdc09f2eb9c9e6a2994b03253630205f47b12`
- **Review-response test content commit:** `9de822ff664546d0d741b00636702d176855105b`
- **Test PR:** https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2
- **Status:** A requested changes on `55df6ca`; B1–B6 and the five non-blocking
  items are addressed in `9de822f` plus the approval hash record. The PR is OPEN and
  awaits A's re-review on the new head. Implementation **NOT STARTED**. No merge,
  self-approval, contract edit, CI edit, or human-only file edit was performed.

## Deliverable status

| Item | Status | Evidence |
|---|---|---|
| Phase 0 repository reconnaissance | COMPLETED | read-only git/gh/environment inspection; no file writes |
| Threat model | COMPLETED (PROPOSED, not APPROVED) | `docs/architecture/threat-model.md` |
| Risk policy | COMPLETED (PROPOSED, not APPROVED) | `docs/architecture/risk-policy.md` |
| Security ADR-003 | COMPLETED draft (PROPOSED, not APPROVED) | `docs/architecture/adr/003-risk-authority.md` |
| Invariant register (D entries) | COMPLETED (PARTIAL file) | `docs/architecture/invariants.md` |
| Permission model | COMPLETED (policy only; runtime enforcement NOT verified) | `docs/architecture/permission-model.md` |
| MCP/tool manifest (D portion) | COMPLETED (policy only) | `docs/code-governance/mcp-tool-manifest.md` |
| FR-04 tests/fixtures | COMPLETED spec; expected red | `test/offline/risk_gate/` |
| 126-case manifest | VERIFIED green | `docs/evidence/FR-04/phase4-manifest-green.txt` |
| Harness self-check | VERIFIED green | `docs/evidence/FR-04/phase4-harness-green.txt` |
| Red baseline capture | VERIFIED red, exit 1 | `docs/evidence/FR-04/phase4-red-baseline.txt` |
| Test-package lint | VERIFIED green | `docs/evidence/FR-04/phase4-ruff.txt` |
| Case construction dry run | VERIFIED green | `docs/evidence/FR-04/phase4-case-build.txt` |
| A review B1–B6 | ADDRESSED in `9de822f` | this section + approval hash record |
| RiskGate implementation | NOT IMPLEMENTED (gated by GATE-01) | Phase 5 not started |
| Permission/approval checkers | NOT IMPLEMENTED (Phase 7) | not in this package |
| Test PR #2 | OPEN — A re-review pending | https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2 |
| A approval / protected record | PENDING HUMAN ACTION; hash record added with `approved_by: PENDING` | `docs/approvals/test-hash-FR-04-risk-gate.txt` |
| Security ADR human approval | PENDING HUMAN ACTION | status remains PROPOSED |

## Generated files

### D documents
- `docs/architecture/adr/003-risk-authority.md`
- `docs/architecture/threat-model.md`
- `docs/architecture/risk-policy.md`
- `docs/architecture/invariants.md`
- `docs/architecture/permission-model.md`
- `docs/code-governance/mcp-tool-manifest.md`
- `docs/ai-use-log-D-fragment.yaml`

### Tests and fixtures
- `test/offline/risk_gate/fakes.py`
- `test/offline/risk_gate/cases.py`
- `test/offline/risk_gate/conftest.py`
- `test/offline/risk_gate/_crash_child.py`
- `test/offline/risk_gate/test_spec_manifest.py`
- `test/offline/risk_gate/test_actions_quantities.py`
- `test/offline/risk_gate/test_funds_positions_costs.py`
- `test/offline/risk_gate/test_evidence_time_policy.py`
- `test/offline/risk_gate/test_identity_idempotency.py`
- `test/offline/risk_gate/test_atomicity_concurrency.py`
- `test/offline/risk_gate/test_security_boundaries.py`
- `test/offline/risk_gate/test_harness_selfcheck.py`
- `docs/approvals/test-hash-FR-04-risk-gate.txt`

## Test matrix

| Category | Cases | Focus |
|---|---:|---|
| ACT | 22 | actions, quantity/price legality, NaN/Inf/float/bool, HOLD |
| FND | 24 | cash, holdings, 20% concentration, 10% notional, fees, slippage, currency |
| EVD | 22 | EvidencePack, hashes, cutoff, freshness, expiry, policy version, timezone, availability |
| IDM | 18 | proposal hash fields, duplicate/replay, restart, stored verdict |
| ATM | 24 | stale version, concurrent duplicate, cash race, oversell, crash, rollback, outbox |
| SEC | 16 | injection, no LLM, bypass signature/env, secrets, direct-write boundaries |
| **Total** | **126** | 119 behavioural + 7 static; unique IDs, requirement-mapped |

Every case carries Test ID, requirement IDs, fixture parameters, expected
status/reason/ledger/version, outcome-only classification (`positive` iff APPROVED),
`test_kind` (`outcome`/`idempotency`/`atomicity`/`security`/`static`), component and
failure mode in `cases.py`. `test_spec_manifest.py` verifies uniqueness, counts,
coverage, classification/status consistency, hash-rule consistency, the HOLD evidence
rule, availability cases, and wiring to the six behavioural modules. Two additional
harness self-tests exercise `assert_case` itself.

## Verification outputs

| Command | Exit | Result |
|---|---:|---|
| `python -m pytest test/offline/risk_gate -q --tb=line` | 1 | 126 failed (missing `egta` implementation), 13 passed (11 manifest + 2 harness) |
| `python -m pytest test/offline/risk_gate/test_spec_manifest.py -q` | 0 | 11 passed |
| `python -m pytest test/offline/risk_gate/test_harness_selfcheck.py -q` | 0 | 2 passed |
| `python -m ruff check test/offline/risk_gate` | 0 | all checks passed |
| `python -m ruff check .` | 0 | all checks passed |
| case-construction dry run | 0 | 126 built; scenario keys wired; 119 behavioural + 7 static |

The 126 failures are the **expected test-first red baseline**: the implementation is
absent, and no `xfail`/`skip` was used to hide that. The red output records the real
`ModuleNotFoundError` reason. This is not reported as PASS. The 13 green tests are
meta-tests (manifest + harness), not the risk gate.

## Git / PR outputs

| Action | Result |
|---|---|
| Initial spec commit | `2bbbdc09f2eb9c9e6a2994b03253630205f47b12` |
| Review-response test content commit | `9de822ff664546d0d741b00636702d176855105b` |
| Push | `origin/spec/FR-04-risk-gate` |
| Test PR | [#2](https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2), open; A requested changes on `55df6ca`, new head awaits re-review |
| A review | `CHANGES_REQUESTED` on `55df6ca`; B1–B6 addressed in `9de822f` |
| Approval hash record | `docs/approvals/test-hash-FR-04-risk-gate.txt`, `approved_by: PENDING` |
| CI checks on PR #2 | none reported; `actions/workflows` total_count = 0 for this fork |

## A review response (CHANGES_REQUESTED on `55df6ca`)

- **B1 — reason vocabulary/hash rule:** EVD-19 → `INVALID_CITATION`; EVD-02 →
  `INTEGRITY_VIOLATION`; EVD-15 → `INTEGRITY_VIOLATION`; EVD-16 → `INVALID_TIME`;
  EVD-08 → `STALE_DATA`. One rule: malformed hash syntax → `INVALID_OUTPUT`;
  well-formed content/run/policy binding mismatch → `REJECTED/INTEGRITY_VIOLATION`
  (EVD-02/03/04/11/15, IDM-02/05..09/14). No ledger mutation.
- **B2 — availability:** EVD-21 sole support `unreachable` →
  `REVIEW/VENDOR_UNAVAILABLE`; EVD-22 sole support `stale` → `REVIEW/STALE_DATA`.
- **B3 — pending parameters:** test fixture values are now explicit test-only
  parameters (`240`/`10`/`0`); EVD-07/08 assert the freshness rule against the
  parameter, not a product default of 300. Product thresholds remain PENDING;
  invalid/unconfigured policy must reject (FND-13/14/15, EVD-12/13/14).
- **B4 — harness never executed:** `test_harness_selfcheck.py` adds one satisfying
  stub and one violating stub; `assert_case` is now exercised.
- **B5 — approval record:** `docs/approvals/test-hash-FR-04-risk-gate.txt` added in
  the FR-05 three-commit-bound format, with per-file SHA-256, aggregate hash,
  `approved_by: PENDING`, fixture parameters and blocking dependencies.
- **B6 — classification:** `positive` iff `expected_status == APPROVED`; otherwise
  `negative`. `test_kind` separates outcome/idempotency/atomicity/security/static.
  7 static cases, 119 behavioural.
- **Non-blocking answers:** HOLD requires a valid pack; HOLD without a pack is
  `REVIEW/EVIDENCE_MISSING`. HOLD is an action, not a verdict status; it is
  `APPROVED` no-action. ATM-07/ATM-09/FND-19 now assert the discriminating
  position/raw state. The PR states 119 behavioural + 7 static. Gate →
  `RunEvent.RunStatus`: APPROVED→OK, REJECTED→BLOCKED, REVIEW→REVIEW,
  BLOCKED→BLOCKED; INCOMPLETE is B/app-level. Instrument identity is a blocking
  dependency in the hash record.

## Interface blockers / pending collaboration

1. **`AdvisoryProposal` missing** (C/B). The tests use a test-only fake.
2. **`EvidencePack` missing** (A). The tests use a test-only fake.
3. **`RiskVerdict` missing** (D proposes; B/E review).
4. **`PortfolioSnapshot` missing** (B).
5. **Instrument identity gap:** the execution plan's `AdvisoryProposal` does not name
   the traded instrument. Tests use a test-only `ticker` field. C/B must resolve by
   adding an approved field or freezing a `run_id -> RunSpec.ticker` lookup.
6. **E `RunEvent`** is on draft PR #1 with `CHANGES_REQUESTED`; not frozen/merged.
7. **`AuditSink`/outbox mapping** with E is not frozen.
8. **Hash canonicalization** for proposal/policy/evidence/outbox is proposed, not
   approved.
9. **`pyproject.toml`/CI** only collect `tests/`; E must add `test/offline` to the
   gate before the FR-04 tests can block CI.
10. **`.opencode` runtime permission config** is absent; no runtime enforcement is
    claimed.
11. **`python -m egta risk-check --case oversized-order`** cannot run; B's CLI and
    packaging are not implemented.
12. **Unapproved policy thresholds:** price freshness, fee and slippage remain
    PENDING; unconfigured policy must safely reject.
13. **A re-review pending.** A reviewed `55df6ca` as a collaborator and requested
    changes; the new head must be re-reviewed. The approval hash record is prepared
    with `approved_by: PENDING`.
14. **CI workflows are not registered on this fork.** `actions/workflows` returns
    `total_count = 0` even though `.github/workflows/ci.yml` exists on `main`. No
    checks are reported on PR #2. E/an administrator must enable/register Actions
    and decide the approved bootstrap for the 126 expected red tests.

## GATE-01 handoff (human action required)

1. A re-reviews the new PR head and confirms B1–B6 and the non-blocking answers.
2. E/administrator enables/registers Actions and agrees how `test/offline` will be
   represented during the approved bootstrap (the 126 red tests are not blocking CI
   in this Test PR).
3. Member A independently approves the FR-04 tests on PR #2 and co-signs the hash
   record with the reviewed head SHA.
4. The protected approval record captures PR, test file hashes, approver and commit.
5. The Test PR is merged.
6. Only after the approved tests are merged/recorded may Phase 5 implementation start.

The agent addressed A's review and added the FR-04 hash record at D's explicit
instruction. It did not fill `approved_by`, self-approve, merge, or start
implementation.
