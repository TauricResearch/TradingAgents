# Course-aligned deliverables and individual ownership

Date: 2026-11-12 (Asia/Hong_Kong). Status: proposed team allocation for review. This reconciles the course specification with the previous ownership document; it does not claim group approval or replace the instructor's instructions.

## 1. Authority and boundaries

The course specification defines what must be submitted. This allocation assigns one accountable owner to each artifact; other members contribute/review without maintaining competing authoritative versions.

| Member | Accountable domain | Boundary |
|---|---|---|
| A | Requirements, priorities, acceptance criteria, changes and source traceability | Does not independently author architecture, test procedures or implementation. |
| B | Architecture, design decisions, interfaces, invariants, state and authority/permission design | Does not approve requirements for A, author C's verification conclusions, or implement application code for D. |
| C | Test plan, test code, independent verification, semantic rubric, defects and quality evidence | Does not silently redefine requirements/design; raises issues to A/B. |
| D | Application code, runnable configuration, baseline protocol/results and experiment metadata | Does not act as the sole independent verifier of its own implementation. |
| E | Agent governance, CI enforcement, shared traceability assembly, AI-use records, packaging and final report editing | Collects approved technical artifacts; does not silently rewrite A-D's owned content. |

All members contribute authentic agent-session evidence, approvals/rejections with rationale, time/contribution records and their own reflections. The course requests role rotation: retain accountable file owners while recording cross-role participation and review. A formally revised rotation/allocation is permitted if the team records it.

## 2. D1: machine-readable requirements

| Required/supplementary file | Owner | Inputs and acceptance of handoff |
|---|---|---|
| `docs/req/requirements.yaml` | A | IDs, types, statements, machine-checkable fit criteria, MoSCoW, tradeoffs and sources. C reviews testability; B reviews feasibility. |
| `docs/req/req-schema.json` | A | Schema for the registry; E connects its validation to CI. |
| `docs/req/change-log.md` | A | Timestamped decisions, scope changes and rationale. |
| `docs/req/requirement-source-notes.md` | A | Existing-system observations and course/team sources. |
| `docs/req/selected-requirements.md` | A after team adoption | Current human-readable working selection. B may propose the initial subset; it is not an approved YAML registry or a second final baseline. |

Page 5 refers to both a YAML PRD and consolidated registry but names only requirements.yaml. A/E should confirm whether one combined YAML satisfies both descriptions or a separate PRD YAML is required. Do not fabricate the instructor's answer.

## 3. D2: architecture artifacts

The course lists eight mandatory types and three optional types. All substantive architecture files are Markdown. B authors the design; E owns assembly of the shared trace matrix.

| Course item / canonical path | Owner | Required content |
|---|---|---|
| D2.1 `architecture-blueprint.md` | B | Scope, drivers, boundaries, components, advisory/authoritative responsibilities, agent workflow, permissions, verification strategy, observability and change policy. |
| D2.2 `docs/architecture/adr/001-<choice>.md` (and subsequent ADRs) | B | Candidate designs, choice, rationale, consequences, reopening conditions and design process. Include AI layered context, assembly pipeline, token cap, compaction threshold and critical-constraint re-injection. |
| D2.3 `docs/architecture/invariants.md` | B | Every invariant's source requirement, enforcing component, verification method and concrete operational fallback. A owns its requirement meaning; C supplies tests. |
| D2.4 `docs/architecture/trace-matrix.md` | E | Every requirement mapped to enforcement, tests/evidence and runtime monitor. A supplies IDs; B components/invariants/monitors; C test IDs/results; D module references. |
| D2.5 `docs/architecture/memory-design.md` | B | State across sessions/interruption/version; write/retrieval policy; ownership; retention; privacy. |
| D2.6 `docs/architecture/permission-model.md` | B | Coding-agent role/path read/write whitelists with default-deny reads and writes. E implements the approved enforcement. |
| D2.7 `docs/architecture/runtime-policy-catalog.md` | B | Each supported failure/degraded path: trigger, responsible component, fallback/action, output and diagnostic/monitor. |
| D2.8 `docs/architecture/evaluation-table.md` | B | Candidate comparison, criteria, assumptions, evidence, tradeoffs and justification. Estimates must be labelled. |
| D2.9 optional `docs/architecture/evaluation-logbook.md` | B | Evidence supporting architecture choices, without inventing implementation results. |
| D2.10 optional `docs/architecture/risk-list.md` | B | Assumptions, risks, owners and review triggers. |
| D2.11 optional `docs/architecture/option-ledger.md` | B | Rejected/deferred options and reconsideration conditions. |
| Team supplement `docs/architecture/interface-contracts.md` | B | Module inputs/outputs, schemas, pre/postconditions, errors, dependency contracts and integration boundaries. |

**Location reconciliation:** page 5 places D2 under docs/architecture; page 9 puts the blueprint at the root. Proposed interim convention: root blueprint is canonical; `docs/architecture/architecture-blueprint.md` is a pointer. E confirms instructor expectations; if two full copies are required, one must be mechanically generated, never independently edited. Use lowercase `adr/` consistently on WSL.

**Trace ownership:** replace the previous independently located CSV with the canonical required Markdown, or retain CSV only as E's single source with a generated Markdown view. B submits mapping rows to E; B does not publish a competing complete matrix.

## 4. D3: coding governance

| Required file | Owner | Contributions / boundary |
|---|---|---|
| Root `AGENTS.md` | E | Build target, reading order, baseline, readable/modifiable/frozen paths, module organization, contracts and verification rules; A/B/C/D supply their domain rules. |
| `docs/code-governance/structural-constraints.md` | E | Enforce B's approved module/authority design; extend baseline rather than replace it; architecture/invariant references in code as required by course. |
| `docs/code-governance/mcp-tool-manifest.md` | E | Approved tools, role permissions and limits; B supplies permission design. |
| `.opencode/permissions.jsonc` | E | Machine-readable permissions/guard enforcement consistent with B's design. |
| `.opencode/rules.md` | E, human-authored only | Always-on behaviour. The course explicitly marks this human-only; AI agents must not create or edit it. |
| `.agent/rules.md` | E | Covenant: abstraction/dependency limits, test independence, negative tests, human approval/ADR for safety changes, context freshness. |

These canonical course paths supersede the previous `docs/governance/structural-constraints.md` and `tool-manifest.md` names. Do not create duplicate independently edited equivalents.

## 5. D4: verification governance and records

| Required or team supplement | Owner | Required content |
|---|---|---|
| `docs/code-governance/verification-constraints.md` | C | Fit-criterion coverage, negative tests for invariants, test-to-requirement references and zero prior-suite regressions; structural/regression/behavioural tiers. E implements CI enforcement. |
| `docs/review-memo.md` | C | PR-indexed review entries: spec/design alignment, code/test quality, metadata, security/efficiency, verdict APPROVE / CHANGES REQUIRED / REJECT. |
| `docs/debt-register.md` | C | Prompt rot, hallucinated/hidden dependencies, untouchable code, bloat, evaluation/guardrail/human debt; owners/actions. D/E contribute implementation/process debt. |
| `docs/bug-diary.md` | C | Significant bug entries: symptom, reproduction, classification, root cause, fix and invariant gap. D supplies fix evidence. |
| `docs/verification/test-plan.md` | C | Levels, fixtures, environments, entry/exit criteria, test independence and human approval reference. |
| `docs/verification/verification-report.md` | C | Actual outcomes, limitations, coverage and unresolved defects. |
| `docs/verification/semantic-evaluation.md` | C | Fixed cases, rubric, thresholds, judges/review protocol and results. D supplies runnable models and baseline measurements. |
| `docs/verification/defect-log.md` if retained | C | Optional operational index linking bugs; not a substitute for the required root-cause diary. |

## 6. D5: authentic agent-session transcripts

| Artifact | Owner | Rule |
|---|---|---|
| `transcripts/<student-id>-<student-name>.md` | Each named member | Full authentic exported session with marked human interventions and rationale. Retain raw source export and identify annotations/redactions. E checks completeness. |
| `transcripts/index.md` (supplement) | E | Maps actual sessions to requirements classification, architecture candidates/evaluation, plan approval, build, verification and evidence-led architecture revision. |
| `docs/ai-use-log.yaml` | E | Every member supplies actual tools, tasks, interventions, approvals and evidence references. Required and current at submission. |

The course overview says five transcripts; D5 says one full raw session, and collectively requires the whole supervised pipeline. For a five-member team, plan an authentic complete session per member, collectively spanning the pipeline, and seek clarification on whether each must itself include a build. Do not invent missing stages or reconstruct a transcript as raw evidence. A design-only session cannot claim test-led revision before actual evidence exists.

## 7. D6-D9 and final packaging

| Deliverable / path | Owner | Inputs |
|---|---|---|
| D6 root `Report.md` | E, sole final editor | A requirements, B architecture/interfaces/rationale, C verification/quality, D implementation/experiments, E process/governance. All names/IDs, relative contribution, process evidence, limitations and individual reflections. Apply course length/layout requirements and clarify any ambiguous interpretation. |
| Individual reflection, approximately 300-500 words each | Each member | Personal authorship; E inserts without changing substance. |
| D7 GitHub repository, meaningful history, branch protection | E | D source/builds; C tests; A schema; B safety/architecture constraints. README explains gates. |
| `.github/workflows/ci.yml` and other workflows | E | Mandatory gates below. C owns verification content; E owns enforcement. |
| D8 application source: course `src/` | D | Preserve upstream `tradingagents/`, `cli/` imports until instructor/team agrees a layout reconciliation; do not relocate code solely for cosmetic conformity. |
| D8 `test/offline/`, `test/live/` | C | Separate deterministic no-network tests from API-dependent tests; preserve upstream `tests/` and clarify how it is included in the accepted layout. |
| `prompts/prompt_v*.yaml` | D | Versioned application prompt implementation; B defines context/assembly constraints, A semantics, C semantic evaluation, E merge gates. |
| D9 root `Prompt.md` | E after integration | Static launch prompt reads governance, produces execution plan (traceability/contracts/scope/testing/steps), and stops before code for human approval; later build/self-verification remain gated. B supplies architecture reading order. Current B session prompt is provisional until E integrates it. |
| Root `README.md` | E | Purpose/architecture, file layout, offline/live/full test commands and real GitHub URL; D/C supply verified commands. |
| `docs/experiments/baseline-protocol.md`, `baseline-results.md`, `run-manifests/` | D | Reproducible workloads/configuration, timing/token/failure/quality observations; no secrets. C evaluates verification claims. |
| `docs/submission/contents-and-build.md`, `submission/` | E | Final inventory, exact reproduction instructions and zip assembly. |
| Separate 10-minute demo video | E coordinates; all contribute | Introduction requests before/after behaviours, SE ideas, traceability/governance; do not include video inside the zip. |

### Six mandatory course gates

E implements: (1) tests approved before implementation; (2) lint/type/dependency checks on commits and contract/security/API/permission checks on safety PRs; (3) YAML/schema validation; (4) fixed semantic evaluation thresholds before prompt/model changes reach production; (5) complete prior regression suites; (6) AI-use log updates for code/prompt PRs. Branch protection requires CI and human review plus ADR for safety-critical paths. C supplies test/evaluation definitions; A registry/schema; B structural/safety constraints; D runnable code.

No unapproved non-blocking semantic-gate startup exception is represented here as course compliance.

## 8. Handoffs and current state

1. A reviews the selected working scope and publishes approved requirement entries/schema.
2. B uses an authentic supervised OpenCode session to generate/evaluate candidates and prepare D2 drafts; human chooses the architecture.
3. C writes the independent plan/tests and records attributable approval before implementation starts.
4. D directs OpenCode to plan, stop for approval, implement against B's contracts, and supply runnable evidence.
5. C verifies; D fixes code; A/B resolve requirement/design changes. Record actual architecture revisions from test evidence.
6. E maintains one shared trace matrix, CI, AI-use evidence and final package. Each owner reviews their own report content.

At this handoff only the selected working requirements, this allocation and a provisional architecture-session Prompt.md are supplied. Other members' files are not claimed to exist or be approved. The agent must not fill missing approvals, results, signatures or transcripts with invented content.

## 9. Sources and unresolved course ambiguities

Sources: `CS5351-2026-2027-project.pdf`, pages 3-10; `CS5351 introduction (extract group project part).pdf`, pages 1, 3-4; `Deliverables-and-Ownership.pdf`, pages 1-4, all from the group's Windows project directory. E coordinates clarification of blueprint location, transcript/session wording, upstream source/test layout versus sample tree, and separate PRD YAML. These are open interpretations, not instructor-approved exceptions.

Change log: 2026-11-12 +08:00 - Initial course-aligned proposed allocation; original PDFs and team ownership document unchanged.
