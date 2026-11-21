# MCP / Agent Tool Manifest — D Portion

- **Status:** PROPOSED — PENDING HUMAN APPROVAL
- **Owner:** D (D3); assembled by E/B as needed
- **Related:** `docs/architecture/permission-model.md`,
  `execution_plan_261111.md` §6.2

> This is a policy manifest, not evidence that a runtime MCP server is configured or
> loaded. No OpenCode runtime configuration exists in the repository at inspection
> time. The coding agent must not claim enforcement until a real refusal is recorded.

## 1. Development-agent tools

| Tool | Roles allowed | Read scope | Write scope | Network | Approval condition | Log fields |
|---|---|---|---|---|---|---|
| `repo.read` | Plan, Build, Verify | Repo files, approved docs/contracts, own module, approved tests | None | None | Always allowed within read scope | path, commit SHA, agent role, timestamp |
| `repo.write` | Build (own module), Verify (report/test draft) | Target file must be in the role allowlist | Own module/approved tests/docs | None | Human plan approval; no protected path | path, old/new hash, diff summary, requirement ID |
| `repo.search` | Plan, Build, Verify | Read scope | None | None | Always allowed within read scope | query, paths, result count |
| `test.run` | Build, Verify | Test files and source needed by tests | Test cache/artifacts only | None for offline | Plan approval; no live secrets | command, exit code, pass/fail/skip, duration, env |
| `lint.run` | Build, Verify | Source/tests | None | None | Always allowed | command, exit code, findings |
| `typecheck.run` | Build, Verify | `src/egta` | None | None | Always allowed | command, exit code, findings |
| `sqlite.inspect` | Build, Verify | D-owned test DB | None by default | None | Test-only; path must be under the workspace/tmp | DB path, query class, row counts, no secrets |
| `git.read` | Plan, Build, Verify | Status/diff/log/show of the local repo | None | None | Always allowed | command, exit code, SHA |
| `git.commit` | Build | Staged changes | Local commit only | None | Explicit human authorization per PR | files, commit SHA, message, requirement IDs |
| `git.push` | Human only | N/A | Remote branch | HTTPS to origin | Explicit human authorization; never automatic | remote, branch, SHA, actor |
| `pr.create` | Human only | N/A | GitHub PR | HTTPS to GitHub | Explicit human authorization | PR number, base/head, SHA, approval link |
| `pr.approve` | Human only | Review materials | GitHub review | HTTPS to GitHub | Human reviewer only; author cannot self-approve | PR, reviewer, commit SHA, decision |
| `secrets.read` | Human/controlled runner only | Injected live credentials | None | Provider-specific | Never available to coding agent | never logged; redacted reference only |

## 2. Runtime RiskGate tools

The runtime RiskGate has **no** MCP tools and no external ports:

| Capability | Allowed? | Reason |
|---|---|---|
| LLM call | No | Final rules must be deterministic and prompt-injection resistant |
| Broker/paper API | No | Paper-only local ledger; no real account |
| Arbitrary network | No | Offline, reproducible demo |
| File write outside its SQLite DB | No | Single-writer boundary |
| Direct ledger write from another module | No | INV-01 |
| Read environment secrets | No | INV-07 |
| Read/write user home or credential paths | No | Permission boundary |

## 3. Logging fields

Every tool event must record: `session_id`, `student/role`, `agent/tool/model/version`,
`timestamp` (UTC and local), `requirement_ids`, `writable_path`, `tool_name`,
`target_path` or `command`, `exit_code`, `result_summary`, `human_approval_link` (if
applicable), and `cost_or_unknown`. Secrets and raw credential values must never be
logged.

## 4. Approval conditions for this work package

- Plan approval: human Member D approves the Phase 0 plan before test generation.
- Test approval: Member A independently approves the FR-04 test baseline; Member D
  does not self-approve.
- Implementation start: only after the approved Test PR is merged/recorded under
  GATE-01.
- Security ADR: human approval required; the agent cannot mark it APPROVED.
- Git push/PR/merge: explicit human authorization only.

## 5. Limitations

- This manifest does not prove that an executor loads it.
- A malicious local process with DB/file access is outside the runtime boundary.
- Secret scanning and export checks are shared with E; D's gate only controls fields
  it persists.
