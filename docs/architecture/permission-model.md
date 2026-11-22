# Permission Model — Coding Agent and Runtime Boundaries

- **Status:** PROPOSED — PENDING HUMAN APPROVAL
- **Owner:** D (D3 / NFR-05)
- **Related:** `execution_plan_261111.md` §6.2, `AGENTS.md` (MISSING), `Prompt.md`
  (MISSING), `.opencode/rules.md` (human-only, MISSING)

> Runtime enforcement is **not claimed**. At inspection time the repository has no
> `.opencode/` directory and no `AGENTS.md`/`Prompt.md`. This document is a policy
> artifact plus a checker specification. Only a human operator may create or edit
> `.opencode/rules.md`.

## 1. Two separate AI layers

| Layer | May read | May write | Must never do |
|---|---|---|---|
| Development coding agent (OpenCode) | Approved docs, contracts, own module, approved tests, selected upstream files | Own module, approved test/spec files, D docs/evidence | Edit other modules, contracts, human-only rules, CI/protection, approval records, credentials; push/merge/create PR without human authorization |
| Runtime financial analysis agent (TradingAgents graph) | Evidence pack, run spec, portfolio context | Only its analysis output/proposal | Modify files, approve itself, bypass budget/risk, write the ledger, call a broker |

## 2. Development roles

| Role | Read scope | Write scope | Forced refusal |
|---|---|---|---|
| Plan | Approved docs, contracts, own module, relevant baseline | Plan drafts for the work package | Business code, approved rules, secrets |
| Build-A/B/C/D/E | Contracts, own docs/tests, own module; B also the approved upstream adapter points | Own module and approved test files | Other modules, contracts, human-only files, approval records, credentials, protection rules |
| Verify | Source, tests, requirements, architecture, redacted logs | Independent verification report and approved test drafts | Business code, gate policy, fabricated test approval |
| Human reviewer | Review materials and GitHub review UI | Approve/reject, requirements decisions, review memo, human-only rules | Do not silently rewrite generated implementation; request agent fixes with evidence |

## 3. D file allowlist (this work package)

**Writable by D's coding agent**
- `src/egta/risk_gate/`
- `test/offline/risk_gate/`
- `test/fixtures/security/` (D-owned canaries, no real secrets)
- `tools/check_permissions.py`
- `tools/check_approval.py`
- `AGENTS.md` (D3 owner; human review still required before merge)
- `docs/architecture/adr/003-risk-authority.md`
- `docs/architecture/invariants.md` (D entries only)
- `docs/architecture/permission-model.md`
- `docs/code-governance/mcp-tool-manifest.md` (D portion)
- `docs/evidence/FR-04/`

**Human-only or out of bounds**
- `.opencode/rules.md` — human-only at every stage; agent may never write it.
- `.opencode/permissions.jsonc` — runtime configuration is not present; the agent only
  proposes a mapping and must not claim it is loaded.
- `src/egta/contracts/` — B-owned shared contracts; changes require producer and
  consumer review. D may request an RFC, not edit.
- `src/egta/evidence/`, `budget/`, `deliberation/`, `evaluation/` — other owners.
- Other members' tests, upstream `tradingagents/`, `.github/workflows/ci.yml`,
  `.github/CODEOWNERS`, rulesets, `docs/approvals/`, approval records, AI-use logs of
  other members.
- Credentials, API keys, `.env` contents, broker endpoints.

## 4. Tool and shell restrictions

- Shell/file tools must resolve paths inside the repository; no `..` traversal, no
  symlink escape to credential directories, no reading `~/.ssh`, `~/.config/gh`,
  `.env`, or cloud credential files.
- Network is not allowed for offline module work. Live/eval credentials are injected by
  a separate controlled runner, never printed to the coding-agent log.
- The coding agent must not run `git push`, create/merge PRs, approve reviews, change
  branch protection, or write approval records without explicit human authorization.
- The coding agent must not use Python/shell to indirectly rewrite a frozen file
  (contracts, `rules.md`, CI, approval records).
- Runtime RiskGate has **zero** tools: no LLM, no broker, no network, no file writes
  outside its SQLite database.

## 5. Runtime enforcement reality and OpenCode mapping

Observed repository facts:

- `.opencode/` does not exist.
- `AGENTS.md` now exists as the D3 entry point; `Prompt.md` and `.opencode/rules.md`
  are still missing.
- The current ruleset (`protect-main`) requires a PR and one approval but does not
  require status checks or CODEOWNERS review.
- The Phase 7 permission and approval checkers now exist as offline-tested tools;
  they are not yet wired into CI or runtime enforcement.

Mapping recommendation (for human review, not an executed configuration):

| Course artifact | Recommended OpenCode mapping | Verification status |
|---|---|---|
| `.opencode/rules.md` | Human-maintained rule file; read-only to agent | NOT PRESENT / NOT VERIFIED |
| `.opencode/permissions.jsonc` | File/tool allowlist consumed by a controlled launcher or mapped to the executor's actual config | NOT PRESENT / NOT VERIFIED |
| `AGENTS.md` | Static startup context with read order and boundaries | PRESENT (D3; human review pending) |
| `Prompt.md` | Static task-independent startup prompt | MISSING |
| `tools/check_permissions.py` | Independent CI/local checker over git diff and tree | IMPLEMENTED + OFFLINE-TESTED; NOT YET CI-WIRED |
| `tools/check_approval.py` | Independent CI/local checker over approval records and git history | IMPLEMENTED + OFFLINE-TESTED; NOT YET CI-WIRED |

Do not claim a policy is enforced merely because it appears in Markdown. Runtime
enforcement must be demonstrated by a real refusal test and recorded with command,
exit code and evidence path.

## 6. Checker requirements (Phase 7 specification)

`tools/check_permissions.py` should:

- detect writes to human-only or protected paths;
- enforce module allowlists per role/PR;
- reject cross-module private imports (e.g., direct ledger access);
- reject contract edits without a producer/consumer review marker;
- reject credential-path references and secret-like literals;
- flag CI/ruleset/CODEOWNERS/permission-file changes for human review;
- support a `--changed-only` or base/head mode for CI;
- return non-zero on any violation and print a machine-readable reason.

`tools/check_approval.py` should:

- resolve requirement IDs and approval records;
- verify the approved test paths/hashes against the protected baseline;
- verify the approver is not the implementation author;
- verify the implementation PR starts from a commit containing the approved tests;
- reject test changes made after approval without a new approval;
- return non-zero on missing, conflicting, or unverifiable evidence;
- rely on Git history and protected approval records, not editable PR prose alone.

Both checkers are implemented in `tools/` and covered by `test/offline/governance`.
CI integration and runtime enforcement remain unclaimed pending E's gate wiring and
the D1 requirements registry (#9).
