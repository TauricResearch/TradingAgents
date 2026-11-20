# FR-04 Phase 0–4 Spec Summary

- **Date:** 2026-11-20 (Asia/Hong_Kong)
- **Branch:** `spec/FR-04-risk-gate`
- **HEAD:** `9fa1196fffbcfd9de5146d2dd2869df84ab99838`
- **Status:** spec materials generated; implementation **NOT STARTED**; no commit,
  push, PR, merge, approval record, or contract edit was performed.

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
| Test PR / A approval | PENDING HUMAN ACTION | not created by agent |
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

## GATE-01 handoff (human action required)

1. Member D reviews this spec package and the 124-case manifest.
2. Member D commits the spec materials and opens the `spec/FR-04` Test PR.
3. Member A independently reviews and approves the FR-04 tests.
4. A protected approval record captures PR, test file hashes, approver and commit.
5. Only after the approved tests are merged/recorded may Phase 5 implementation start.

The agent did not create an approval record, did not approve its own tests, did not
push, and did not open a PR.
