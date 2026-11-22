# Phase 7 Governance Tools — Test-First Spec Summary

- **Status:** test/spec only; `tools/` implementation NOT PRESENT.
- **Branch:** `spec/FR-04-governance-tools`
- **Test baseline:** 32 governance cases (16 permission + 16 approval), plus 6
  manifest meta-tests.
- **Reviewer requested:** A (`@yuxiangdu39`) for independent test approval.
- **No test changes after approval; no implementation in this PR.**

## Planned CLI (defined by the tests)

```text
python tools/check_permissions.py \
  --repo <path> --base <sha> --head <sha> --role <role> [--json]

python tools/check_approval.py \
  --repo <path> --record <path> \
  --implementation-base <sha> --implementation-head <sha> \
  --registry <path> --author <login> [--json]
```

Exit codes: `0` clean/valid, `1` violation/invalid/unverifiable, `2` usage/tool
error. Human-readable output contains a stable code such as `PATH_NOT_ALLOWED`;
`--json` returns `{"ok": bool, "violations": [...]}`.

## Permission cases (16)

Covered codes include `PATH_NOT_ALLOWED`, `HUMAN_ONLY`, `PROTECTED_PATH`,
`CONTRACT_PROTECTED`, `APPROVAL_PROTECTED`, `CROSS_MODULE_IMPORT`,
`CREDENTIAL_REFERENCE`, `ROLE_NOT_ALLOWED`.

They cover allowed D module/docs, other modules, `.opencode/rules.md`, CI,
contracts, approval records, cross-module vs allowed contracts imports, `.env` and
`~/.ssh` references, deletion of protected files, human vs verify roles, clean
diffs and JSON output.

## Approval cases (16)

Covered codes include `RECORD_MISSING`, `APPROVAL_PENDING`, `SELF_APPROVAL`,
`REQUIREMENT_UNKNOWN`, `REGISTRY_MISSING`, `HASH_MISMATCH`,
`AGGREGATE_MISMATCH`, `TEST_BASE_MISSING`, `TEST_DRIFT`,
`REVIEWED_HEAD_MISSING`, `RECORD_INVALID`.

The approval checker must use Git history and hashes, not PR prose: per-file and
aggregate test hashes, approver != author, reviewed/test commit ancestry,
implementation must not change approved test paths, and Requirement IDs must resolve
against a registry.

## Requirements registry dependency (A-owned)

`docs/req/requirements.yaml` is currently **MISSING** on main. The tests use a
temporary registry fixture. The production checker must fail closed with
`REGISTRY_MISSING` when the registry is absent; A must land the D1 registry before
E can enable the approval checker as a blocking CI gate.

## Verification evidence

- `pytest test/offline/governance` → **32 failed, 6 passed**, expected red:
  `tools/check_permissions.py` / `tools/check_approval.py` do not exist. No
  xfail/skip.
- `pytest test/offline/governance/test_spec_manifest.py -q` → 6 passed.
- `ruff check .` → All checks passed.
- Evidence:
  - `docs/evidence/FR-04/phase7-governance-red.txt`
  - `docs/evidence/FR-04/phase7-governance-manifest-green.txt`
  - `docs/evidence/FR-04/phase7-governance-ruff.txt`

## Approval requested

A: please review the 32-case permission/approval specification, the expected red
baseline, the planned CLI and the temporary-registry approach. After A approves and
the Test PR is merged, the checkers will be implemented in a separate implementation
PR; E will integrate them into CI.
