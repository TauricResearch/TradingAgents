# FR-04 Phase 0–4 Spec Summary

- **Date:** 2026-11-20 (Asia/Hong_Kong)
- **Branch:** `spec/FR-04-risk-gate`
- **Initial spec commit:** `2bbbdc09f2eb9c9e6a2994b03253630205f47b12`
- **Test PR:** https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2
- **Status:** spec materials generated and pushed; Test PR #2 is OPEN and ready for
  review. Implementation **NOT STARTED**. No merge, approval record, self-approval,
  contract edit, CI edit, or human-only file edit was performed.

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
| 124-case manifest | VERIFIED green | `docs/evidence/FR-04/phase4-manifest-green.txt` |
| Red baseline capture | VERIFIED red, exit 1 | `docs/evidence/FR-04/phase4-red-baseline.txt` |
| Test-package lint | VERIFIED green | `docs/evidence/FR-04/phase4-ruff.txt` |
| Case construction dry run | VERIFIED green | `docs/evidence/FR-04/phase4-case-build.txt` |
| RiskGate implementation | NOT IMPLEMENTED (gated by GATE-01) | Phase 5 not started |
| Permission/approval checkers | NOT IMPLEMENTED (Phase 7) | not in this package |
| Test PR #2 | OPEN — ready for review | https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2 |
| A approval / protected record | PENDING HUMAN ACTION | independent approval not yet recorded |
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

## Test matrix

| Category | Cases | Focus |
|---|---:|---|
| ACT | 22 | actions, quantity/price legality, NaN/Inf/float/bool, HOLD |
| FND | 24 | cash, holdings, 20% concentration, 10% notional, fees, slippage, currency |
| EVD | 20 | EvidencePack, hashes, cutoff, freshness, expiry, policy version, timezone |
| IDM | 18 | proposal hash fields, duplicate/replay, restart, stored verdict |
| ATM | 24 | stale version, concurrent duplicate, cash race, oversell, crash, rollback, outbox |
| SEC | 16 | injection, no LLM, bypass signature/env, secrets, direct-write boundaries |
| **Total** | **124** | unique IDs, positive/negative, requirement-mapped |

Every case carries Test ID, requirement IDs, fixture parameters, expected
status/reason/ledger/version, positive/negative classification, component and failure
mode in `cases.py`. `test_spec_manifest.py` verifies uniqueness, counts, coverage and
wiring to the six behavioural modules.

## Verification outputs

| Command | Exit | Result |
|---|---:|---|
| `python -m pytest test/offline/risk_gate -q --tb=line` | 1 | 124 failed (missing `egta` implementation), 5 passed (manifest) |
| `python -m pytest test/offline/risk_gate/test_spec_manifest.py -q` | 0 | 5 passed |
| `python -m ruff check test/offline/risk_gate` | 0 | all checks passed |
| `python -m ruff check .` | 0 | all checks passed |
| case-construction dry run | 0 | 124 built; scenario keys wired |

The 124 failures are the **expected test-first red baseline**: the implementation is
absent, and no `xfail`/`skip` was used to hide that. The red output records the real
`ModuleNotFoundError` reason. This is not reported as PASS.

## Git / PR outputs

| Action | Result |
|---|---|
| Local commit | `2bbbdc09f2eb9c9e6a2994b03253630205f47b12` |
| Push | `origin/spec/FR-04-risk-gate` |
| Test PR | [#2](https://github.com/ZFebron491001/EGTA-CS5351-Group20/pull/2), open, ready for review |
| CI checks on PR #2 | none reported; `actions/workflows` total_count = 0 for this fork |
| Formal reviewer request | rejected (HTTP 422): `@yuxiangdu39` is not a collaborator |

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
13. **A is not a repository collaborator.** GitHub rejected the formal reviewer
    request with HTTP 422. An administrator must invite `@yuxiangdu39` before A's
    approval can satisfy the required-approval rule.
14. **CI workflows are not registered on this fork.** `actions/workflows` returns
    `total_count = 0` even though `.github/workflows/ci.yml` exists on `main`. No
    checks are reported on PR #2. E/an administrator must enable/register Actions
    and decide the approved bootstrap for the 124 expected red tests.

## GATE-01 handoff (human action required)

1. Administrator invites `@yuxiangdu39` (A) as a repository collaborator.
2. E/administrator enables/registers Actions and agrees how `test/offline` will be
   represented during the approved bootstrap (the 124 red tests are not blocking CI
   in this Test PR).
3. Member A independently reviews and approves the FR-04 tests on PR #2.
4. A protected approval record captures PR, test file hashes, approver and commit.
5. The Test PR is merged.
6. Only after the approved tests are merged/recorded may Phase 5 implementation start.

The agent created the authorized Test PR at D's explicit instruction. It did not
create an approval record, self-approve, merge, or start implementation.
