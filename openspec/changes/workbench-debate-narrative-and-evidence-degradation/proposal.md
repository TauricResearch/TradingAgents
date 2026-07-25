# Workbench debate narrative and evidence degradation

## Why

The workbench currently renders a multi-agent debate as if it were a list of
finished documents: agent prose is shown as 11px monospace `<pre>` (no markdown
renderer is installed at all), the 13-role map is a static CSS grid with no
edges, and the debate transcript is a single flat bubble column where bull and
bear turns are distinguished only by avatar tint. The product's differentiator —
adversarial multi-round reasoning that converges to a decision — is invisible.

Separately, the Evidence Steward treats "few news items were found" as a system
fault: `evidence_stop_on_fail` defaults to `True`, so thin coverage raises
`EvidenceGateError` and fails the whole run. Evidence scarcity is a property of
the *conclusion*, not of the *execution*; for small-cap A-shares and low-coverage
tickers the correct response is a lower-confidence verdict, not a refusal.

## What Changes

### Report rendering

- Add a real markdown pipeline (`react-markdown` + `remark-gfm` +
  `rehype-sanitize`) and rebuild `SafeMarkdown` on it, replacing today's
  escape-into-`<pre>` implementation.
- Split long-form rendering into two typographic modes: **prose** for
  LLM-authored reports (readable body size, heading scale, lists, tables,
  measure-constrained) and **data** for machine payloads (prompt snapshots,
  JSON artifacts, vendor raw values — monospace, collapsible, copyable).
- Route all three long-text surfaces (debate transcript body, artifact viewer,
  prompt snapshot) through the correct mode. `SafeMarkdown` is currently dead
  code referenced only by tests.

### Debate narrative

- Replace the static 3×6 role grid with a **stage-grouped flow map** carrying
  explicit edges and direction (data sources → analysts → research debate →
  trader → risk → portfolio), with live flow highlighting driven by run state.
- Replace the single-column transcript with an **opposed debate stage**: bull
  left / bear right, grouped by round with explicit round separators, manager
  verdicts spanning full width as convergence points; the risk three-way debate
  reuses the same structure with three lanes.
- Surface debate structure that already exists in backend state but is not
  projected: `turn_index`, `max_debate_rounds` progress, rebuttal pairing
  between opposing turns, and candidate-vs-committed turn status.
- Render debate body content eagerly rather than behind a click-to-expand
  placeholder. E2E verification confirmed all 13 turns currently render the
  literal string `点击展开` as their entire body (`findings-e2e.md` F2).
- **Prerequisite defect**: constrain adversarial agents to author only their own
  speech. The bull researcher's turn currently opens with ~1300 characters of
  self-authored moderator narration and bear argument before its own case, which
  breaks the one-turn-one-speaker premise that lane rendering depends on
  (`findings-e2e.md` F6).
- Mark absent execution facts as unavailable rather than as zero: every
  `turn.completed` in the verified run carries `duration_ms: 0`, and the UI
  currently prints `0s` for all 13 roles (`findings-e2e.md` F3).

### Inspector information architecture

- **BREAKING (UI only)**: collapse the current 4 top-level tabs × 5 nested
  sub-tabs (9 entry points, two levels) into a single-scope vertical panel keyed
  to the selected turn: identity → evidence (upstream state + data fields + tool
  calls + vendor provenance, merged) → prompt (collapsed) → output.
- Move run-scoped surfaces (`本次输入` run input snapshot, `产物` full artifact
  list) out of the turn-scoped inspector into a run-header drawer.
- Remove the two inspector views filtered on `input.data_snapshot`, a capture
  kind the backend never emits — they render a permanent empty state for every
  turn of every run (`findings-e2e.md` F4).
- Fix the upstream-material view, which currently lists the capture envelope's
  five metadata keys instead of the upstream reports nested inside it
  (`findings-e2e.md` F5).

### Evidence gate degradation

- Introduce a third evidence verdict `LOW_CONFIDENCE` between `PASS` and
  `FAIL_STOP`: items present but below threshold passes the gate carrying an
  explicit confidence downgrade instead of routing to failure.
- **BREAKING (behavior)**: flip `evidence_stop_on_fail` default to `False` so a
  weak-evidence verdict no longer fails the run.
- Demote the core-data warning check from fail-stop to warning, retaining
  fail-stop only for genuinely fatal absence (no usable financial statement).
- Keep wrong-identity conflict detection as a hard fail-stop **when it has a
  resolved profile to compare against**, and make it abstain when it does not.
  E2E verification found this check rejecting the *correct* company: with an
  unresolved profile its alias set is empty, so every candidate name is
  trivially "unrelated" and each enrichment round of correct evidence deepens
  the misjudgement. See `findings-e2e.md` F7.
- Propagate the confidence signal into `evidence_report` in machine-readable
  form so Research Manager and Portfolio Manager must downgrade conviction, and
  surface it in the workbench as an explicit badge rather than hiding it.
- Add env-override entries for the evidence threshold keys, which today are
  code-only.
- Fix two defects found while scoping: evidence enrichment reads only
  `TAVILY_API_KEY` and ignores `TAVILY_API_KEYS` (silently returning no
  enrichment for multi-key deployments), and the gate's failure reasons use
  unweighted counts while the verdict uses credibility-weighted counts,
  producing misleading messages.

## Capabilities

### New Capabilities

- `workbench-report-rendering`: how agent-authored prose and machine payloads
  are rendered and typographically separated in the workbench.
- `workbench-debate-narrative`: how multi-agent flow, rounds, opposition, and
  convergence are projected from run state into the workbench's structural and
  transcript views.
- `workbench-turn-inspector`: the single-scope audit surface answering "how did
  this statement come to be", and the boundary between turn-scoped and
  run-scoped information.
- `evidence-confidence-degradation`: the evidence gate's verdict model,
  degradation semantics, downstream confidence propagation, and which checks
  remain hard failures.

### Modified Capabilities

None. `openspec/specs/` is currently empty, so all four capabilities are new.

## Impact

Frontend (`frontend/`):
- New runtime dependencies: `react-markdown`, `remark-gfm`, `rehype-sanitize`
  (first non-React runtime deps in `package.json`).
- Rewritten: `components/shared/SafeMarkdown.tsx`,
  `components/workflow/WorkflowMap.tsx`, `components/timeline/Timeline.tsx`,
  `components/inspector/Inspector.tsx`,
  `components/inspector/RoleInputPanel.tsx`, `domain/roles.ts` (edge/stage
  layout), `styles/workbench.css`, `styles/tokens.css` (prose type scale).
- Touched: `components/layout/WorkbenchLayout.tsx` (selection model, run-header
  drawer), `state/selectors.ts` (round grouping, opposition pairing).
- Tests: existing vitest suites for the rewritten components, plus
  `e2e/workbench.spec.ts`.
- Committed build output `tradingagents/web/static/` must be rebuilt.

Backend:
- `tradingagents/dataflows/evidence.py` (verdict model, degradation, core-data
  demotion, Tavily key read, reasons weighting).
- `tradingagents/default_config.py` (`evidence_stop_on_fail` default,
  `_ENV_OVERRIDES` additions).
- `tradingagents/agents/evidence_steward.py` (gate-unavailable fallback).
- `tradingagents/observability/projections.py` if the confidence verdict enters
  the event/projection contract consumed by the frontend.
- Downstream prompt lenses for Research Manager / Portfolio Manager conviction.

Docs: `CLAUDE.md`, `CHANGELOG.md`, `Handoff.md`, `README.md` web section.

Out of scope: exposing evidence thresholds in the web request schema
(`AnalysisRequest` / `effective_config` whitelist stays as-is); dark theme;
changes to the 13-role convergence path.
