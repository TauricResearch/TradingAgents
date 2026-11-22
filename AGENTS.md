# AGENTS.md — EGTA Agent Operating Rules

- **Status:** D3 policy entry point; human review required before merge.
- **Owner:** D.
- **Related:** `docs/architecture/permission-model.md`,
  `docs/code-governance/mcp-tool-manifest.md`, `Prompt.md` (missing),
  `.opencode/rules.md` (human-only, missing).

This file is read by coding agents. It records boundaries and required evidence; it
does not by itself prove runtime enforcement. Enforcement is claimed only after a
real refusal test is recorded with command, exit code and evidence path.

## 1. Read order

Before a task, read in this order:

1. `AGENTS.md` (this file).
2. `Prompt.md` — static task-independent startup prompt. If it is missing, stop and
   request human instruction; do not invent a replacement.
3. Approved requirement and trace documents under `docs/req/`.
4. Architecture and policy: `docs/architecture/adr/003-risk-authority.md`,
   `docs/architecture/invariants.md`, `docs/architecture/risk-policy.md`,
   `docs/architecture/permission-model.md`.
5. Code governance: `docs/code-governance/mcp-tool-manifest.md`.
6. The approved tests, contracts and verification constraints for the current
   requirement.
7. The D/B/C/E AI-use log fragment and the current review evidence.

If a required document is missing or unapproved, record the gap and stop at the
relevant human gate. Do not reconstruct missing rules from memory.

## 2. Two AI layers

| Layer | May read | May write | Must never do |
|---|---|---|---|
| Development coding agent (OpenCode) | Approved docs, contracts, own module, approved tests, selected upstream files | Own module and approved test/spec files | Edit other modules, contracts, human-only files, approval records, CI, CODEOWNERS, credentials; push/PR/merge/self-approve without explicit human authorization |
| Runtime financial analysis agent | Evidence pack, run spec, portfolio context | Only its analysis output/proposal | Modify files, approve itself, bypass budget/risk, write the ledger, call a broker |

The runtime RiskGate is deterministic code: no LLM, no broker, no network, and no file
writes outside its own SQLite database.

## 3. Structural constraints

- Keep the modular monolith and the `src/egta/` module boundaries.
- The five business modules are `evidence`, `budget`, `deliberation`, `risk_gate` and
  `evaluation`; `contracts`, `app` and `adapters` are support components.
- A module may import `egta.contracts` and its own module. Cross-module private
  imports are forbidden; use an approved contract or injected port.
- Do not move upstream `tradingagents/` code or rewrite baseline behaviour without an
  ADR and regression evidence.
- The risk gate is the only authority allowed to change the paper ledger; budget
  admission must precede external model calls; evidence, risk and audit events must
  remain traceable.
- Preserve the frozen upstream licence and attribution.

## 4. Permission rules

The detailed file-level allowlist is in `docs/architecture/permission-model.md`.
Summary:

- A coding agent writes only its owner's module, approved tests and explicitly
  assigned documentation.
- D's scope includes `src/egta/risk_gate/`, D risk/permission docs, `AGENTS.md`, the
  two governance checkers and D evidence/log files.
- Contracts are B-owned and require producer and consumer review. No agent may edit
  them alone.
- CI, CODEOWNERS, rulesets, approval records and other members' AI-use logs are
  protected.
- Credential paths, `.env` contents, API keys, `~/.ssh` and broker credentials are
  outside every coding-agent scope.
- Shell and file tools must resolve inside the repository; no traversal or symlink
  escape to credential directories.
- `tools/check_permissions.py` is the independent checker for role-scoped diffs. It
  is implemented and offline-tested; CI wiring is E-owned.

## 5. Human-only rules

The following are human-only at every stage:

- `.opencode/rules.md` — human-maintained; an agent may never write it.
- Approval records under `docs/approvals/` and any co-signature fields.
- Human decisions on requirements, ADR status, branch protection and merge.
- Test approval and the independent review of tests.
- Changes that would relax an invariant, protected path or human gate.

The agent may propose text or a diff for these items, but may not mark them approved,
signed or merged. `.opencode/rules.md` is currently missing; this is a recorded gap,
not permission for an agent to create it.

## 6. MCP and tool boundary

`docs/code-governance/mcp-tool-manifest.md` is the authoritative tool manifest. In
summary:

- Read, search, test, lint, type-check and local git inspection are allowed within the
  role's scope.
- `git.commit` requires explicit human authorization for the PR.
- `git.push`, `pr.create`, `pr.approve`, branch-protection changes and merges are
  human-only.
- Live credentials are injected only by a controlled runner and never enter the
  coding-agent log.
- No MCP server is claimed to be loaded merely because this file or the manifest
  exists.

## 7. Verification and evidence

- Test-first: the test/spec PR is reviewed and merged before the implementation PR;
  the implementation must build on the approved test commit.
- Do not modify frozen tests, approval records, contracts, CI or human-only files to
  make a check pass.
- Do not use `xfail`/`skip` to hide a real failure; report the failure and stop.
- Run the applicable offline suites per suite, with exact expected counts; a missing
  suite is N/A, not a pass.
- Record the real command, exit code, output summary and evidence path.
- Update the owner's AI-use log fragment for code, test, script or prompt changes;
  do not edit another member's log.
- Save raw session evidence and human-intervention annotations; do not rewrite
  failures into a cleaner story.

## 8. Project covenant

- Prefer fail-closed behaviour over availability when audit, evidence, budget or risk
  authority is unavailable.
- Never fabricate a test result, approval, hash, CI run, session or security evidence.
- Never delete a failing sample or a negative result to improve a metric.
- Never claim runtime enforcement, production integration or investment performance
  without recorded evidence.
- Keep secrets out of prompts, reports, commits, logs and session exports.
- The author of an implementation or test baseline does not approve it.
- When a required gate is missing, stop and ask the human rather than inventing a
  bypass.

## 9. D3 evidence map

| D3 item | Where documented |
|---|---|
| Structural constraints | §3 of this file; `docs/architecture/invariants.md` |
| MCP tool manifest | §6 of this file; `docs/code-governance/mcp-tool-manifest.md` |
| Permission rules | §4 of this file; `docs/architecture/permission-model.md` |
| Human-only rules | §5 of this file |
| Project covenant | §8 of this file |

`GOV-03` is satisfied only when this file is reviewed and merged. `GOV-09` is not
satisfied by this file alone: it still requires the static root `Prompt.md` with the
plan-first, stop-for-approval and separate implementation/verification human gates.

## 10. Change control

Changes to this file require human review. An agent may propose a diff and explain
the requirement or invariant it serves, but may not approve, merge or declare the
policy enforced. When this file and an approved ADR or permission record conflict,
stop and ask the human owner to resolve the conflict.
