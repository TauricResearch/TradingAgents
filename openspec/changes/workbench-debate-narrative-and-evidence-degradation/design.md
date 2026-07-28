## Context

The workbench is a localhost-only React+TS+Vite SPA served by FastAPI over
REST + SSE (`tradingagents/web/`), consuming a normalized event reducer
(`frontend/src/state/runReducer.ts`, 869 lines) that projects the observability
event stream into `ReducerState`. The committed build output lives in
`tradingagents/web/static/` so an installed wheel serves without Node.

Current state relevant to this change:

- `frontend/package.json` has exactly two runtime dependencies, `react` and
  `react-dom`. No markdown parser exists. `SafeMarkdown` HTML-escapes text into
  a `<pre>` and its own docstring states markdown is not parsed; it is imported
  only by a test file, so production renders agent prose through raw `<p>` and
  `<pre className="tool-body">` at 11–13px, with `.safe-markdown` styled as
  11px monospace.
- `WorkflowMap` is `repeat(6, 1fr)` CSS Grid over a hand-tuned 3-row layout in
  `domain/roles.ts`; there is no edge, arrow, or stage container in the DOM.
- `Timeline` renders `turnTimeline()` as one flat column of `.event` rows; bull
  vs bear differs only by `.event.bear .avatar` color, round appears only as a
  text tag from `tagTextFor()`, and turn bodies show the literal string
  "点击展开" until clicked.
- `Inspector` has 4 top-level tabs, one of which (`RoleInputPanel`) nests 5 more,
  mixing turn scope (data/state/prompt/raw/config/tools) with run scope
  (artifacts, run input).
- `ReducerState` already carries `turns[].turn_index`, `roles[].current_round`,
  `meta.max_debate_rounds`, `meta.max_risk_discuss_rounds`, `model_calls`,
  `tool_calls`, `vendor_calls`, and `graph_tasks` — the debate structure is in
  state and simply is not projected.

On the backend, `tradingagents/dataflows/evidence.py` implements a two-valued
gate (`EvidenceStatus.PASS` / `NEEDS_ENRICHMENT` / `FAIL_STOP`, where the middle
value is a routing state). `_fail_or_return` raises `EvidenceGateError` when
`evidence_stop_on_fail` is true — the default. The raise propagates through
`agents/evidence_steward.py` (no try/except), `ObservedNode`, and
`execution/runner.py` (cleanup then re-raise) to `web/manager.py`, which marks
the run failed with `error_category="evidence_rejection"`. The data layer below
it is already fail-open by design (`CLAUDE.md`: "Fail-open on data"), so this
gate is the sole place where thin news fails a run.

Constraints: localhost-only, no secrets in the browser, no private model
reasoning persisted, the 13-role convergence path is fixed,
`default_config.py` is the single source of truth for configuration, and the
frontend must stay synchronized with the backend contract and its committed
static build.

## Goals / Non-Goals

**Goals:**

- Make agent prose readable: real markdown parsing, sanitized, with prose and
  machine-data typography separated.
- Make the multi-agent process legible: stage-grouped directed flow map, and a
  round-grouped opposed-lane debate stage with explicit convergence points.
- Give the right column one job and one scope, removing the two-level tab
  hierarchy and evicting run-scoped surfaces.
- Turn evidence scarcity into a confidence signal that propagates to the final
  verdict, instead of a run failure.
- Derive everything from existing reducer state and existing event contracts;
  avoid new backend event types unless the confidence verdict genuinely requires
  one.
- Make one turn mean one speaker, so the transcript the UI renders is the
  transcript the agents actually produced: rebuttals only when there is something
  to rebut, attribution carried structurally, no invented participants.

**Non-Goals:**

- Adding a moderator role to the graph. The moderator the agents currently
  address does not exist anywhere in the code; it is removed from the prose, not
  created in the pipeline.
- Rewriting, backfilling, or migrating recorded debate payloads. Historical turns
  stay byte-identical and are handled by a rendering guard.
- Changing the substance of the debate prompts. The analytical instruction sets
  (growth/moat/indicators, risk/weakness/adverse evidence) are untouched; only
  who speaks, and when a rebuttal is asked for, changes.
- Changing `context_compaction.py`. Its transcript-splitting contract constrains
  this change but is not modified by it; the mid-sentence `bounded_tail` clip on
  short debates is documented, not fixed here.

- Exposing evidence thresholds in the web request schema. `AnalysisRequest` and
  the `effective_config` whitelist in `web/api.py` stay as they are; env
  overrides are the operator surface for this change.
- Any change to the 13-role graph topology, routing, or convergence path.
- Dark theme, or a general design-system refactor of `tokens.css` beyond adding
  a prose type scale.
- A graph layout engine, drag-to-rearrange, or zoom/pan on the flow map.
- Re-scoring or re-ranking news; only the verdict semantics change, not the
  retrieval or credibility pipeline.

## Decisions

### D1. Markdown via `react-markdown` + `remark-gfm` + `rehype-sanitize`

The three deps the existing `SafeMarkdown` docstring already names as deferred.
Rationale: `rehype-sanitize` sanitizes the HAST after parsing, which is what the
spec requires — sanitizing in the pipeline rather than pre-escaping the source,
so markdown stays parseable while embedded markup stays inert. A hand-rolled
parser would have to re-solve GFM tables and sanitization, both of which are
security-relevant and easy to get subtly wrong.

Alternatives rejected: `marked` + `DOMPurify` + `dangerouslySetInnerHTML` (keeps
a raw-HTML injection surface and loses React component mapping); keeping the
current escape-into-`<pre>` and only enlarging the font (does not satisfy the
requirement that headings, lists, and tables render as elements).

Sanitization schema: start from `defaultSchema`, and do not widen it. Restrict
anchor `href` to `http`/`https` and add `rel="noopener noreferrer"` plus
`target="_blank"` via a component override rather than by permitting extra
attributes in the schema.

### D2. One renderer component, two modes — `mode="prose" | "data"`

A single `SafeMarkdown` (name retained; `SafeMarkdown` is currently dead code so
there is no migration cost) takes a `mode` prop. `prose` runs the markdown
pipeline and emits a `.prose` container. `data` bypasses the pipeline entirely
and emits a `<pre className="datablock">`, because prompt snapshots and JSON must
render byte-faithfully and must not have `#` or `*` reinterpreted.

Rationale: the failure being fixed is content-type/presentation mismatch, so the
mode belongs at the render boundary where the caller knows the content type,
rather than being sniffed from content. Explicit beats inferred here — a JSON
artifact that happens to contain markdown-looking strings must not flip modes.

Prose typography lives in CSS as a `.prose` block with a type scale
(`--prose-size`, `--prose-line`, `--prose-measure` added to `tokens.css`), so the
scale is auditable in one place and reusable by the debate stage and the artifact
viewer.

### D3. Flow map as inline SVG edges over a CSS Grid of stage containers

Keep CSS Grid for stage containers and role nodes (accessible, text-selectable,
already styled), and overlay one absolutely-positioned inline `<svg>` for edges.
Edge endpoints are computed from measured node geometry via `ResizeObserver` on
the map container, not from hardcoded pixel coordinates.

Rationale: a full graph library (react-flow, dagre, elk) brings a layout engine
and a large dependency for a topology that is fixed, known at build time, and
only six stages wide. Hardcoded SVG coordinates were rejected because the map
must survive responsive width changes and Chinese label wrapping.

The edge set is declared as data in `domain/roles.ts` alongside the existing
stage table: `{ from, to, kind: "handoff" | "adversarial" | "convergence" }`.
Edge kind drives stroke treatment. This keeps the topology declarative and
testable without a DOM.

Fallback: if measurement is unavailable (jsdom in vitest), edges render with zero
length and the component still mounts — the grid remains the source of truth for
structure, so unit tests assert on stage containers and node presence, and
Playwright asserts on edge presence in a real browser.

### D4. Debate stage derived from a new pure selector, not from Timeline internals

Add `debateScript(state, filter)` to `state/selectors.ts` returning an ordered
list of blocks:

```
type DebateBlock =
  | { kind: "round"; stage: "research" | "risk"; index: number; lanes: Lane[] }
  | { kind: "verdict"; turn: Turn }
  | { kind: "linear"; turn: Turn }   // analysts, evidence, trader
```

Round membership comes from `turn.turn_index`; lane assignment comes from a
registry-derived `laneOf(actor_id)` (bull/bear for research, three risk roles for
risk) so no per-turn heuristic is involved, per the spec. Judging roles produce
`verdict` blocks. Non-adversarial roles produce `linear` blocks.

Rationale: putting grouping in a pure selector makes the round/lane/convergence
logic unit-testable without React and keeps `Timeline` a renderer. The current
`Timeline` mixes grouping, artifact fetching, and expansion state in one
component, which is why round structure never surfaced.

Eager body rendering (spec: content visible without interaction) changes the
fetch pattern: today `fetchResponse` is triggered on click. Move artifact text
fetching into a `useTurnResponses(turns)` hook that fetches for turns currently
in the viewport-adjacent window, with a per-turn excerpt budget and an expand
control for the remainder. This bounds concurrent requests while satisfying the
"no bare click-prompt" requirement.

### D5. Inspector as flat sections, run scope moved to a run-header drawer

Replace the tab strip with four `<section>`s in fixed order (identity, evidence,
prompt, output), the latter three collapsible via `<details>`-like state.
`RoleInputPanel`'s five sub-tabs collapse into subsections of `evidence`, joined
with the tool-call and vendor-provenance content currently under the separate
`数据与工具` tab.

Rationale: the two current top-level tabs `角色输入` and `数据与工具` were split
by *event provenance* (artifact-carried vs tool-event-carried), which is an
implementation detail; the user's question is "what did this turn read", so they
merge. Turn-scoped and run-scoped content are separated because mixing scopes in
one column prevents the user from forming a "the right column follows my
selection" model.

Run-scoped surfaces (`RunInputTab`, the full `reports` list) move behind a
disclosure in the run header owned by `WorkbenchLayout`. This is the only place
in the change where a component moves between columns.

### D6. `LOW_CONFIDENCE` as a real verdict, with a routing state kept separate

Extend `EvidenceStatus` with `LOW_CONFIDENCE`. Keep `NEEDS_ENRICHMENT` as the
internal routing state it already is — enrichment runs, then the assessment
resolves to one of the three terminal verdicts. `_assessment_pass` already
carries a `low_coverage: bool`; the change is that the *below-threshold* branch
now resolves to `LOW_CONFIDENCE` instead of falling through to
`_fail_or_return`.

Rationale for a third enum member rather than reusing `PASS` plus the existing
`low_coverage` flag: the verdict must be visible in the ledger, in the
projection the frontend consumes, and in the downstream prompt lens. A boolean
riding alongside `PASS` is easy for any one of those three consumers to ignore,
which is precisely how the current `low_coverage` flag became inert.

`evidence_stop_on_fail` default flips to `False` in `default_config.py`. When an
operator re-enables it, only `FAIL_STOP` aborts — `LOW_CONFIDENCE` proceeds
regardless, so the switch cannot resurrect the current behavior for thin news.

### D7. Graded core-data warnings

Replace the flat `warning_patterns` tuple in `_assert_no_core_data_warnings`
with two tuples: `FATAL_DATA_PATTERNS` (no usable financial statement) and
`DEGRADED_DATA_PATTERNS` (supplemental source unavailable, `暂未获取`,
`未获取到完整`, Yahoo warnings, `Data unavailable`). Degraded hits become
recorded limitations contributing to `LOW_CONFIDENCE`; only fatal hits reach
`FAIL_STOP`.

Rationale: this check is the widest source of false failures for A-share runs and
is unrelated to news volume, yet shares the same abort path. Grading it is a
smaller and more honest change than deleting it — the information is still
surfaced, just not as a fault.

Similarly, unresolved A-share `profile["name"]` becomes a `LOW_CONFIDENCE`
limitation rather than an abort: the ticker is known and downstream prompts can
work from it, so a Tushare token problem should not fail the analysis.

Wrong-identity detection is untouched and stays `FAIL_STOP`, unconditional on
the strict-abort switch, per the spec.

### D8. Machine-readable confidence line in `evidence_report`

`_format_evidence_report` emits one deterministic line, e.g.
`Evidence confidence: LOW_CONFIDENCE (company 1.5/3, mixed 2.0/5)`, using
weighted counts. Downstream Research Manager and Portfolio Manager prompt lenses
gain an instruction tying `LOW_CONFIDENCE` to reduced conviction, reusing the
existing conviction/abstain vocabulary in `portfolio/conviction.py` and
`risk_mgmt/signals.py` rather than inventing a parallel notion.

The frontend surfaces the verdict as a badge on the evidence steward's turn and
on the final decision, sourced from the existing `evidence_status` field the
`responseExtractor` already reads for `evidence.steward`. If the verdict needs to
reach the frontend for turns other than the steward's, it travels through the
existing `EVIDENCE_CONFIG_FIELDS`/projection path — no new event type.

### D9. Two defect fixes bundled

Enrichment credential read (`evidence.py` reads only `TAVILY_API_KEY`, missing
`TAVILY_API_KEYS`) and reasons-vs-verdict counting basis. Both are in the code
being touched anyway, both silently corrupt the very degradation path this change
introduces, and shipping the new verdict model on top of them would produce
`LOW_CONFIDENCE` verdicts caused by a credential bug rather than by real
scarcity.

### D11. Single-speaker turns fixed at the source, with a rendering guard behind it

F6 is in scope as agent-behavior work, not as a rendering workaround. Four
decisions:

**D11.1 — The rebuttal instruction becomes conditional.** The polluted turn is
the debate's first round, where the opposing argument does not yet exist
(`bear_history` empty, `current_response` empty) but the prompt still demands a
rebuttal and still prints `Last bear argument:` with nothing after it. The prompt
SHALL branch: on an opening turn it asks for an opening case only; on a
subsequent turn it asks for a rebuttal and includes the opposing argument. The
alternative — keeping one prompt and adding "do not invent the other side" — was
rejected because it leaves a self-contradicting instruction in place and relies
on the model resolving the contradiction the way we want.

**D11.2 — The speaker label lives in exactly one place: the state envelope, not
the body.** Today the code prepends `Bull Analyst: ` / `Bear Analyst: `
(`bull_researcher.py:76`, `bear_researcher.py:73`, and `:54` in each of the three
risk debators) *and* the model re-emits its own `**Bear Analyst:**` heading
because the `history` it reads back is formatted as a labelled transcript. The
turn body SHALL carry no speaker label; attribution is structural, held by the
turn's `actor_id`, and rendered by the UI as an avatar and name. The
transcript-shaped `history` string stays labelled — it is a prompt input that
needs speaker attribution inline — so the label is added when composing
`history`, not when storing the turn's own body.

This split is not cosmetic. `context_compaction.py:20` splits the transcript on
`^(?:Bull Analyst|Bear Analyst|Aggressive Analyst|Conservative Analyst|Neutral
Analyst):` under `re.MULTILINE`; strip the labels from `history` and every
transcript becomes one unsplittable turn, which forces the `bounded_tail` branch
to clip mid-sentence on every run instead of dropping whole old turns. The label
therefore leaves the stored body and stays in the composed transcript, and the
compactor is left untouched.

**D11.3 — No moderator is introduced.** Both researchers currently address a
moderator and the research manager's verdict opens
`### Moderator's Ruling & Action Plan`, but no moderator node exists in the role
registry or the graph. Rather than adding one, the prompts SHALL stop staging a
moderated panel: the debate is a direct exchange, and the judging role is the
convergence point the flow map already draws. Adding a real moderator node was
rejected as a pipeline change well beyond this change's scope.

**D11.4 — The renderer still defends itself.** Prompt constraints are
probabilistic; historical runs already in the store keep their polluted bodies
forever. The debate stage SHALL therefore detect a foreign speaker attribution in
a turn body and SHALL NOT present it as the authoring role's own words. Marking
it visibly (rather than stripping silently) is the chosen behavior: silent
stripping would hide a real agent defect from the person best placed to notice
it, and this workbench exists to make agent behavior auditable.

Historical data is not rewritten. The 2 polluted payloads of 35 stay as they are;
the guard in D11.4 is what makes them readable.

### D10. Sequencing

Rendering (D1, D2) first: it is independent, low-risk, and is the change the user
feels immediately. Then the evidence backend (D6–D9), because it is what unblocks
runs on thin-coverage tickers and it needs a real run to validate. Then
single-speaker turns (D11), which is backend prompt work that must land before
the lanes exist to expose it. Then the debate stage (D3, D4), the largest
frontend piece. Then the inspector (D5). Rebuild and commit
`tradingagents/web/static/` once per frontend-touching phase, not once at the
end, so static drift stays reviewable.

D11 lands before D3/D4 for a practical reason: a fresh run is needed to confirm
turns are clean, and that run takes minutes, so starting it before the largest
frontend piece means its result is ready when the lanes are.

## Risks / Trade-offs

- [First runtime deps beyond React enter the frontend bundle] → `react-markdown`
  + `remark-gfm` + `rehype-sanitize` add roughly 100–150 KB minified to a bundle
  currently around 215 KB. This is a localhost tool with no cold-start budget;
  accept it. Pin exact versions and verify the committed static build size delta
  is reported in the change's closeout.
- [Sanitization regression opens an XSS path in a browser holding no secrets but
  running on the user's machine] → Do not widen `defaultSchema`. Keep the
  existing `SafeMarkdown` adversarial tests (script tag, event handler,
  `javascript:` URI) and add the anchor-scheme case; treat them as the security
  gate for this component.
- [Eager artifact fetching for debate bodies multiplies HTTP requests on
  long runs] → Windowed fetching with per-turn excerpt budget and request
  de-duplication in `useTurnResponses`; measure against the longest historical
  run in `reports/` before landing.
- [SVG edge geometry breaks under narrow widths or long Chinese labels] →
  Geometry is measured, not hardcoded; define a minimum map width below which
  the map degrades to the stage-grouped grid without edges rather than drawing
  crossing spaghetti.
- [Flipping `evidence_stop_on_fail` lets genuinely unusable evidence reach a
  final recommendation] → This is the deliberate trade the user chose, bounded
  three ways: wrong-identity stays a hard stop, fatal core-data absence stays a
  hard stop, and `LOW_CONFIDENCE` is required to cap downstream conviction. The
  residual risk is that a judging role ignores the conviction ceiling; cover it
  with a test asserting the confidence line reaches the manager prompt.
- [Changing debate prompts changes analytical output, not just formatting] →
  Removing the moderated-panel framing and branching the rebuttal instruction
  alters what the researchers write, so recommendation text will differ from
  historical runs even on identical inputs. This is an accepted behavior change,
  bounded by keeping the substantive instruction set (growth/moat/indicators for
  bull, risk/weakness/adverse-evidence for bear) untouched and changing only who
  speaks and when a rebuttal is requested. Verify on a fresh run that both sides
  still produce a full argument and that the research manager still reaches a
  rating.
- [Stripping the code-side speaker prefix breaks consumers that parse it] →
  `history`, `bull_history`, `bear_history` and any downstream prompt lens that
  splits on `Bull Analyst:` / `Bear Analyst:` must be audited before the prefix
  moves out of the turn body. Grep for the literal labels across
  `tradingagents/agents/` and `tradingagents/observability/` first; keep the
  labels in the composed `history` transcript so lenses that rely on them keep
  working.
- [Existing tests encode the current UI shape] → `Inspector`, `Timeline`,
  `WorkflowMap`, `RoleInputPanel`, `Controls`, `RunHistory` vitest suites and
  `e2e/workbench.spec.ts` will need rewriting, not just patching. Treat test
  rewriting as in-scope work per phase, not as cleanup at the end.
- [The repository has 47 unpushed commits and a large dirty working tree] →
  Do not fold this change's edits into unrelated pending modifications. Confirm
  with the user how the existing dirty state should be handled before the first
  implementation commit.

## Migration Plan

No data migration. Behavior migration in two parts:

1. **Config default flip.** Operators who relied on `evidence_stop_on_fail=True`
   can restore aborting by setting the new env override; document this in
   `CLAUDE.md` and `CHANGELOG.md` as a behavior change. Runs recorded before the
   flip keep their `evidence_rejection` categories; no backfill.
2. **Frontend static build.** Each frontend phase rebuilds
   `tradingagents/web/static/`. Rollback for the UI is a revert of the phase's
   commit plus a rebuild; the backend and frontend phases are independently
   revertable because the confidence verdict travels through existing contract
   fields.

## Resolved Questions

- *Should the F6 debate-authorship defect be folded into this change or split into
  its own?* Resolved by the user on 2026-07-25: folded in. It is now capability
  `debate-turn-authorship` with its own implementation phase (3A), rather than a
  prerequisite bullet hanging off the debate-stage phase. The reason it belongs
  here is that the opposed-lane debate stage — the centrepiece of this change —
  presumes one turn carries one speaker, and that presumption is currently false.

## Open Questions

- Does the confidence verdict need to reach frontend turns other than the
  evidence steward's? If the final-decision badge must show it, confirm whether
  `run.meta` or an existing projection field can carry it before adding anything
  to the event contract.
- Should the run-header disclosure holding run input and the artifact list be a
  drawer, a modal, or a route? Deferred to the inspector phase; it does not
  affect the earlier phases.
- The existing dirty working tree (25+ modified files, 47 unpushed commits) needs
  a decision — commit, stash, or branch — before implementation starts.
