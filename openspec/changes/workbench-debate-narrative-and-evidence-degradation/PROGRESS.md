# Project Status: Workbench Debate Narrative & Evidence Degradation

> Delivered through [PR #2](https://github.com/david188888/TradingAgents/pull/2),
> merged into `david188888/TradingAgents:main` as `73222cf5` on 2026-07-28,
> with Phase 5/6 continuation on `codex/workbench-debate-script-and-inspector`.
>
> Updated: 2026-07-28

## Scope status

| Phase | Status | Verified boundary |
|---|---|---|
| 0. Pre-flight | Complete | User approved the publish/continuation workflow; baseline and prior findings were recorded. |
| 1. Report rendering | Implemented and locally verified | Sanitized prose Markdown, literal data mode, bounded automatic response loading, and longest-run request volume are covered. |
| 2. Evidence verdict model | Implemented and verified | `PASS`, `LOW_CONFIDENCE`, and `FAIL_STOP` are distinct; hard identity/fatal core-data stops are preserved. |
| 3. Confidence propagation | Backend implemented and verified | Research/Portfolio prompts receive the low-confidence conviction cap. Evidence Steward and final Portfolio Manager turns expose verdict badges; real thin-coverage acceptance remains. |
| 3A. Debate turn authorship | Implemented and unit-verified | Prompt/storage contracts are covered; a real post-3A two-round provider run remains intentionally unperformed. |
| 4. Workflow map | Implemented and verified | Six stage groups, typed measured SVG edges, narrow-layout fallback, and live role state are covered. |
| 5. Debate stage | Implemented and verified | Ordered round/lane scripts, convergence verdicts, candidate labels, round budgets, and historical foreign-attribution protection are covered by unit and browser tests. |
| 6. Turn inspector | Implemented and verified | Flat turn-scoped identity/evidence/prompt/output sections and the run-header disclosure are covered by unit and browser tests. |
| 7. Verification/closeout | Partial | Frontend gates and deterministic Playwright pass; real-provider/thin-coverage acceptance and historical run-store comparison remain. |

## Implemented behavior

### Report rendering and response loading

- Pinned `react-markdown@9.1.0`, `remark-gfm@4.0.1`, and
  `rehype-sanitize@6.0.0`.
- `SafeMarkdown` has explicit `prose` and `data` modes. Prose uses the default
  sanitize schema plus an http/https-only anchor override; data remains literal
  inside a whitespace-preserving `<pre>`.
- Report artifacts, turn bodies, inspector output, and long upstream state fields
  use prose mode; prompts and machine payloads use data mode.
- `useTurnResponses` loads the initial 12 artifact-backed turns in full. Later
  turns load 800-character excerpts, expose “展开全文”, and refetch the selected
  artifact in full. The queue is de-duplicated and capped at four concurrent
  requests; state and stale async results are isolated by `run_id`.
- The 23-run local history was measured directly. The longest run,
  `run_20260720T121943222472Z_78a2924a`, contains 1,093 events and 13 completed
  artifact-backed turns, so initial loading issues at most 13 artifact requests,
  never more than four concurrently: 12 full responses plus one excerpt. Expanding
  that final turn adds at most one full refetch; no window adjustment is needed.

### Evidence degradation and confidence propagation

- `LOW_CONFIDENCE` is a terminal verdict; `NEEDS_ENRICHMENT` remains internal.
- Thin or zero usable news coverage after enrichment, non-fatal data warnings,
  unresolved A-share profile names, parse failures, and gate availability faults
  degrade rather than abort.
- Wrong-identity conflicts and fatal core-data patterns remain unconditional
  `FAIL_STOP` outcomes.
- `evidence_stop_on_fail` defaults to `False`.
- Environment overrides include `TRADINGAGENTS_EVIDENCE_STOP_ON_FAIL`,
  `TRADINGAGENTS_NEWS_MIN_COMPANY_ITEMS`,
  `TRADINGAGENTS_NEWS_MIN_MIXED_ITEMS`, and
  `TRADINGAGENTS_HALT_ON_MISSING_DATA`.
- Research and Portfolio Manager prompts apply the existing conviction vocabulary
  as a ceiling when evidence is low-confidence.
- Evidence Steward and Portfolio Manager response artifacts persist the explicit
  `evidence_status`; timeline badges read only that field. Historical Portfolio
  artifacts without it show no badge rather than misusing the long-form
  `risk_debate_state.judge_decision` report as a label.
- Unexpected Evidence Steward exceptions persist only the exception class, not
  raw exception text that might contain a URL, query parameter, or credential.

### Debate authorship and narrative

- Opening turns request an opening case and omit empty opponent labels;
  subsequent turns request a rebuttal and include the opposing argument.
- Each research/risk debater is instructed to speak only as itself, avoid
  moderator framing, and never fabricate dialogue for another participant.
- Per-side turn bodies are unlabelled. The composed transcript retains structural
  speaker labels for `context_compaction.py`.
- `debateScript()` sorts by `turn_index`, renders analysts as linear blocks,
  research and risk roles in round/lane blocks, and judging roles as full-width
  convergence verdicts.
- Candidate turns, round separators, and elapsed/configured round budgets remain
  explicit.
- Historical turn bodies are never rewritten. Redundant leading self-labels are
  suppressed at render time, while bodies that attribute speech to another
  participant are visibly marked rather than silently presented as the selected
  role’s own words. The debate stage reads per-side bodies, not compacted
  `history`.

### Workflow map

- All 13 roles are assigned exactly once across six labelled stages.
- Declarative edges distinguish handoff, adversarial, and convergence paths.
- Wide layouts compute an inline SVG overlay from measured role geometry;
  narrow/jsdom layouts retain the stage grid without relying on unavailable
  measurements.
- Role and active-stage states are derived from the run state, including terminal
  handling that cannot leave a role falsely running.
- Timeline turns and map roles with existing turns drive the same inspector
  scope; selecting a role with no turn does not discard the current scope.

### Turn inspector and run disclosure

- The turn inspector has four fixed sections in order: Identity, Evidence,
  Prompt / LLM input, and Output. Identity is always visible; Prompt is collapsed
  by default and its artifact is fetched only when expanded.
- Identity reports role, round, status, duration, provider, and model. Missing or
  zero-duration execution facts are shown as unavailable rather than fabricated
  measurements; the same duration rule applies to the swarm status table.
- Evidence reads upstream fields only from `state_snapshot.state_fields`; envelope
  metadata is not misrepresented as business input. The UI explicitly notes
  that `input.data_snapshot` currently has no producer.
- Tool calls include arguments, status, outcome, artifacts, hashes, and locators;
  vendor provenance and effective configuration remain auditable. A turn with no
  tool calls says so explicitly.
- Output uses the sanitized prose renderer. Remounting by selected-turn key keeps
  asynchronous content from a previous turn out of the new scope.
- A disclosure beneath the active-run header owns run input, reports published by
  `report.updated`, and the complete artifact index. Report bodies load only when
  their individual disclosure is expanded, and the run-scoped surface remains
  stable while turn selection changes.

## Verification evidence

- Node tooling is available from
  `/Users/david/.nvm/versions/node/v24.15.0/bin`: Node **24.15.0**, npm **11.12.1**,
  and npx **11.12.1**.
- Historical request-volume audit: **23 runs** inspected; longest run has **1,093
  events**, **13** completed artifact-backed turns, and a **4-request** concurrency
  ceiling. The configured 12-full + excerpt window remains bounded.
- Frontend strict TypeScript: passed.
- Frontend Vitest: **17 files, 106 tests passed**.
- Frontend production build: **323 modules transformed**.
- Deterministic Playwright: **9/9 passed (13.8s)** against
  `scripts/e2e_server.py` using the Conda `tradingagents` Python and fake runner.
  The final suite covers the flat inspector flow, run disclosure, tool/vendor
  evidence, and real-browser SVG edge presence. No real LLM/provider was called.
- Sandboxed Chromium first failed at macOS Mach-port bootstrap with permission
  error 1100. Re-running the same suite outside that sandbox passed twice; the
  final run includes the SVG-edge assertion, so this is a host-launch constraint,
  not an unresolved application assertion.
- Focused backend evidence/prompt/authorship suite: **49 passed**.
- Focused CI-regression suite for Windows console handling, canonical hashing,
  and debate authorship: **31 passed**.
- Full backend suite in the authoritative Conda `tradingagents` environment
  (Python 3.13.13): **1,333 passed, 19 warnings, 68 subtests passed**.
- GitHub Actions run `30323625615` passed all seven required jobs: tests on
  Python 3.10, 3.11, 3.12, and 3.13; clean-install smoke; strict full-repo Ruff;
  and the web Python/SPA/wheel-asset gate.
- Current built frontend assets:
  - `tradingagents/web/static/assets/index-QxTgIV19.js`: 400,669 bytes
  - `tradingagents/web/static/assets/index-Dd5IBIzk.css`: 32,632 bytes
  - combined assets: 433,301 bytes; +18,629 bytes versus the preceding
    414,672-byte committed build and +189,957 bytes versus the 243,344-byte 0.2
    baseline. A second fresh build produced identical SHA-256 checksums for the
    JS, CSS, and `index.html`.

## Verification boundaries

- The deterministic fake-runner E2E verifies the browser, SSE, store, artifact,
  static-build, debate narrative, inspector, run disclosure, and workflow-edge
  paths without provider cost.
- It does **not** verify provider billing/authentication, a real thin-coverage
  ticker reaching `LOW_CONFIDENCE`, post-3A model output, a real two-round debate,
  or pre-/post-3A historical run-store comparison.
- No paid provider call was made for this continuation slice.
- Cleanup candidates are retained until the user receives the closeout report and
  explicitly confirms destructive cleanup, per the neat-freak contract.

## Remaining work

1. Run the real thin-coverage acceptance only with explicit provider/data-cost
   approval (tasks 3.7 / 7.4).
2. Run a real post-3A analysis with at least two debate rounds (task 3A.12), then
   repeat the historical F6 scan and pre-/post-3A comparison (tasks 7.4a–7.4b).
3. Archive/sync the OpenSpec change only after the remaining acceptance evidence
   is complete or deliberately descoped.
