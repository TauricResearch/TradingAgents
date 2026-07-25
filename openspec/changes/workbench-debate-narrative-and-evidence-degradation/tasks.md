## 0. Pre-flight

- [ ] 0.1 Confirm with the user how the existing dirty working tree (25+ modified files, 47 unpushed commits) should be handled — commit, stash, or dedicated branch — before any edit lands.
- [ ] 0.2 Record the baseline committed static bundle size of `tradingagents/web/static/` so the dependency-size delta in phase 1 is measurable.
- [ ] 0.3 Capture the current frontend test baseline: `npm --prefix frontend run typecheck` and `npm --prefix frontend run test -- --run` both green before changes.
- [ ] 0.4 Read `findings-e2e.md` before starting any phase — it records the E2E-verified current behavior (11 findings, 4 of which changed this change's scope) and the reproduction method: serve the real run store by running `scripts/e2e_server.py` with `TRADINGAGENTS_E2E_RUN_ROOT=$HOME/.tradingagents/web/runs`, then drive it with Playwright. Reuse that setup to verify each phase against real report payloads rather than the fake 13-role script, whose one-sentence reports hide every rendering defect.

## 1. Report rendering (spec: workbench-report-rendering)

- [ ] 1.1 Add pinned exact versions of `react-markdown`, `remark-gfm`, `rehype-sanitize` to `frontend/package.json` dependencies; install and verify the lockfile updates.
- [ ] 1.2 Add prose type-scale tokens (`--prose-size`, `--prose-line`, `--prose-measure`, heading steps) to `frontend/src/styles/tokens.css`.
- [ ] 1.3 Add a `.prose` block to `frontend/src/styles/workbench.css` styling headings, paragraphs, lists, tables, blockquote, inline/fenced code, and links against the new tokens; add a `.datablock` block for machine payloads (monospace, whitespace-preserved).
- [ ] 1.4 Rewrite `frontend/src/components/shared/SafeMarkdown.tsx` to take `mode: "prose" | "data"`: prose runs react-markdown + remark-gfm + rehype-sanitize over the unwidened `defaultSchema`; data emits `<pre className="datablock">` without markdown parsing.
- [ ] 1.5 Override the anchor component in prose mode to restrict `href` to http/https and add `rel="noopener noreferrer"` + `target="_blank"`, without widening the sanitize schema.
- [ ] 1.6 Extend the SafeMarkdown tests to cover: heading/list/GFM-table parsing, table alignment row consumed, script tag stripped, `onerror` attribute stripped, `javascript:` href rejected, and data mode leaving markdown syntax literal.
- [ ] 1.7 Route `Inspector`'s artifact viewer (`ReportBody`) through SafeMarkdown — prose for report-kind artifacts, data for JSON payloads.
- [ ] 1.8 Route `RoleInputPanel`'s `PromptBody` through SafeMarkdown in data mode, replacing the "SafeMarkdown is not yet available" placeholder comment.
- [ ] 1.9 Route the debate turn body through SafeMarkdown in prose mode, replacing `<p>{responseContent}</p>` in `Timeline.tsx`.
- [ ] 1.10 Add a `useTurnResponses` hook that fetches turn response text for a windowed set of turns with per-turn de-duplication and an excerpt budget, replacing the click-triggered `fetchResponse` in `Timeline.tsx`.
- [ ] 1.11 Replace the "点击展开" placeholder with an excerpt plus an expand control; keep an explicit in-progress indicator for turns with no artifact yet.
- [ ] 1.12 Measure request volume for `useTurnResponses` against the longest historical run in `reports/`; adjust the window if it exceeds a reasonable concurrent-request ceiling.
- [ ] 1.13 Run typecheck + vitest, rebuild `tradingagents/web/static/` via `npm --prefix frontend run build`, and record the bundle-size delta against the 0.2 baseline.

## 2. Evidence gate verdict model (spec: evidence-confidence-degradation)

- [ ] 2.1 Fix the enrichment credential read in `tradingagents/dataflows/evidence.py` to honor `TAVILY_API_KEYS` in addition to `TAVILY_API_KEY`, matching `tavily_news.py`; record a distinct "skipped: no credentials" reason when neither is set.
- [ ] 2.2 Fix `_assess_news_items` failure reasons to report credibility-weighted counts, matching the basis the verdict itself uses.
- [ ] 2.3 Add `LOW_CONFIDENCE` to `EvidenceStatus`; keep `NEEDS_ENRICHMENT` as the internal routing state.
- [ ] 2.4 Change the below-threshold branch of `_assess_news_items` to resolve to `LOW_CONFIDENCE` (carrying reasons and weighted counts) instead of falling through to `_fail_or_return`, including the zero-usable-items case.
- [ ] 2.5 Split `_assert_no_core_data_warnings`' flat pattern tuple into `FATAL_DATA_PATTERNS` (no usable financial statement) and `DEGRADED_DATA_PATTERNS` (the remaining five); degraded hits become recorded limitations contributing to `LOW_CONFIDENCE`, fatal hits stay `FAIL_STOP`.
- [ ] 2.6 Change the unresolved A-share `profile["name"]` branch from abort to a `LOW_CONFIDENCE` limitation.
- [ ] 2.7 Verify wrong-identity detection still produces `FAIL_STOP` unconditionally when the profile carries a usable name, independent of the strict-abort switch; add a test asserting it fails even when item counts exceed all thresholds.
- [ ] 2.7a Make `_find_wrong_identity_hits` abstain when `_profile_name_aliases` is empty: an empty alias set makes every candidate trivially "unrelated" via `_names_are_related`, which is how the correct company was rejected in `findings-e2e.md` F7. Record unverified identity as a `LOW_CONFIDENCE` limitation instead.
- [ ] 2.7b Add a regression test reproducing F7 exactly: unresolved profile name for `2513.HK` plus evidence containing `智谱（2513.HK）` must not produce an identity conflict.
- [ ] 2.7c Add a test asserting that additional correct enrichment evidence does not grow the conflict hit set when the profile is unresolved.
- [ ] 2.8 Add a parse-failure signal for the case where an upstream report is non-empty, does not declare absence of data, and yields zero parsed items; keep it distinct from genuine zero coverage in the recorded reason.
- [ ] 2.9 Update `_fail_or_return` so `evidence_stop_on_fail` only gates `FAIL_STOP`; `LOW_CONFIDENCE` never raises regardless of the switch.
- [ ] 2.10 Flip `evidence_stop_on_fail` default to `False` in `tradingagents/default_config.py`.
- [ ] 2.11 Add `_ENV_OVERRIDES` entries for `evidence_stop_on_fail`, `news_min_company_items`, `news_min_mixed_items`, and `halt_on_missing_data`; verify they appear in the run's effective configuration.
- [ ] 2.12 Wrap the evidence steward node (`tradingagents/agents/evidence_steward.py`) so unexpected non-verdict exceptions become a gate-unavailable outcome with the fault recorded, rather than failing the run with an evidence-rejection category.
- [ ] 2.13 Record the verdict, reasons, and weighted counts in the evidence ledger for all three terminal verdicts.
- [ ] 2.14 Add unit tests covering each spec scenario: below-threshold-but-present, thresholds met, zero usable evidence, default-config thin evidence not failing, strict mode with fatal vs low-confidence, identity conflict, degraded vs fatal core-data markers, incomplete profile, weighted reasons, credential variants, parse failure vs declared absence, and gate fault degradation.

## 3. Confidence propagation (spec: evidence-confidence-degradation)

- [ ] 3.1 Emit a deterministic machine-readable confidence line from `_format_evidence_report` naming the verdict and weighted counts against thresholds.
- [ ] 3.2 Add the conviction-ceiling instruction to the Research Manager prompt lens, reusing the existing conviction/abstain vocabulary from `portfolio/conviction.py` and `risk_mgmt/signals.py` rather than new terminology.
- [ ] 3.3 Add the equivalent instruction to the Portfolio Manager prompt lens.
- [ ] 3.4 Add a test asserting the confidence line actually reaches the manager prompt for a `LOW_CONFIDENCE` run.
- [ ] 3.5 Resolve the open question of whether the verdict must reach frontend turns other than the evidence steward's; if yes, route it through an existing projection field rather than a new event type.
- [ ] 3.6 Surface the verdict as a badge on the evidence steward's turn (and the final decision if 3.5 requires it), sourced from the `evidence_status` field `responseExtractor` already reads.
- [ ] 3.7 Run a real minimum-depth analysis against a thin-coverage A-share ticker and confirm the run reaches a non-failed terminal status with the verdict visible.

## 4. Debate narrative — flow map (spec: workbench-debate-narrative)

- [ ] 4.1 Add a declarative edge table to `frontend/src/domain/roles.ts`: `{ from, to, kind: "handoff" | "adversarial" | "convergence" }` covering stage handoffs, bull↔bear, the risk three-way, and each debate's convergence into its judge.
- [ ] 4.2 Add pure unit tests over the stage and edge tables asserting every registry role occupies exactly one position and every declared edge references known roles.
- [ ] 4.3 Restructure `WorkflowMap.tsx` to render six labelled stage containers holding their role nodes, replacing the hand-tuned 3-row layout.
- [ ] 4.4 Add an absolutely-positioned inline SVG edge overlay whose endpoints are computed from measured node geometry via `ResizeObserver`; edge kind drives stroke treatment.
- [ ] 4.5 Define a minimum map width below which the map degrades to the stage-grouped grid without edges, and implement that fallback.
- [ ] 4.6 Ensure the component mounts and asserts correctly under jsdom where measurement is unavailable (zero-length edges acceptable; grid structure is the test surface).
- [ ] 4.7 Derive per-role live state from run state for not-reached / running / completed / failed / skipped, and mark the active stage; assert no role shows running when run state reports it terminal.
- [ ] 4.8 Rewrite `WorkflowMap.test.tsx` for stage containers, edge presence, role positions, and each live-state scenario.

## 5. Debate narrative — debate stage (spec: workbench-debate-narrative)

- [ ] 5.0a **Prerequisite**: constrain the bull and bear researcher prompts so each authors only its own argument. The verified run's bull turn opens with ~1300 chars of self-authored `**Moderator:**` and `**Bear Analyst:**` dialogue before its own case (`findings-e2e.md` F6); lane rendering would display the bear's argument inside the bull lane.
- [ ] 5.0b Add a test asserting a debate role's turn output contains no speaker attribution naming another role.
- [ ] 5.0c Investigate the `investment_debate_state.history` 12000-character boundary observed in the verified run while `bull_history` and `bear_history` are untruncated; confirm whether compaction is silently truncating debate history and whether the debate stage should read the per-side histories instead.
- [ ] 5.1 Add `laneOf(actor_id)` to the role domain, deriving lane assignment from the registry (two research lanes, three risk lanes, none for other roles).
- [ ] 5.2 Add a `debateScript(state, filter)` selector to `frontend/src/state/selectors.ts` returning ordered `round` / `verdict` / `linear` blocks, grouping by `turn.turn_index` and never by arrival order.
- [ ] 5.3 Unit-test `debateScript` for: two-round research debate, in-progress round 1 of 3, three-way risk round, judging turns as verdict blocks, and analyst turns as linear blocks.
- [ ] 5.4 Rewrite `Timeline.tsx` as a renderer over `debateScript`: opposed lanes per round, explicit round boundaries, and rounds-elapsed against the stage's configured round budget.
- [ ] 5.5 Render judging turns as full-width convergence elements terminating the round group they resolve, visually distinct from lane turns.
- [ ] 5.6 Keep candidate-vs-committed turn distinction with an explicit candidate label.
- [ ] 5.7 Add CSS for lanes, round separators, round-budget display, and the convergence element.
- [ ] 5.8 Rewrite `Timeline.test.tsx` for round grouping, lane assignment, convergence rendering, candidate labelling, and eager body content.
- [ ] 5.9 Verify turn selection from the debate stage and role selection from the map both drive inspector scope, and that selecting a role with no turns leaves scope unchanged.
- [ ] 5.10 Run typecheck + vitest, rebuild the static bundle, and commit the static drift.

## 6. Turn inspector (spec: workbench-turn-inspector)

- [ ] 6.1 Rewrite `Inspector.tsx` as four flat sections in fixed order — identity, evidence, prompt, output — with no tab strip and no nested tabs; identity always expanded, prompt collapsed by default.
- [ ] 6.2 Build the identity section from run state: role display name, round, turn status, duration, and the producing model call's provider and model; render missing execution facts as explicitly unavailable rather than substituting defaults.
- [ ] 6.2a Apply the same rule to the role-status table in `SwarmStatusCard`, which currently prints `0s` for all 13 roles because every `turn.completed` carries `duration_ms: 0` (`findings-e2e.md` F3). Decide separately whether the backend should record real durations — the UI must not present 0 as a measurement either way.
- [ ] 6.3 Merge `RoleInputPanel`'s five sub-tabs plus the former `数据与工具` tab content into subsections of the evidence section: upstream state fields, resolved data fields, tool calls with status and outcome, vendor provenance (vendor, hash, locator), and effective config.
- [ ] 6.3a Audit every inspector view's capture-kind filter against the kinds `tradingagents/observability/` actually emits; drop `input.data_snapshot`-filtered views (`数据字段`, `原始值`) since that kind has zero producers and zero occurrences across all 23 historical runs (`findings-e2e.md` F4). Decide whether vendor lineage moves onto the tool-call subsection or onto `state_snapshot`.
- [ ] 6.3b Fix the upstream-material view to render the fields nested inside the capture envelope rather than the envelope's own top-level keys (`actor_id`, `effective_config_artifact_id`, `node_id`, `projection_version`, `state_fields`), and route long field values through the prose renderer (`findings-e2e.md` F5).
- [ ] 6.3c Add a test asserting the upstream view of a real `state_snapshot` payload surfaces upstream report field names and not envelope metadata keys.
- [ ] 6.3d Collapse the duplicated `.inspector` class applied to both the layout `aside` and the `Inspector` root `div` (`findings-e2e.md` F10).
- [ ] 6.4 State explicitly when a turn issued no tool calls rather than omitting the subsection.
- [ ] 6.5 Build the output section from the turn's response artifact, rendered in prose mode.
- [ ] 6.6 Move `RunInputTab` and the full run artifact list out of the inspector into a run-header disclosure owned by `WorkbenchLayout`; decide drawer vs modal vs route at this point.
- [ ] 6.6a Decide how the run-scoped artifact list should present roles that emit no `report.updated` event: the verified run lists only 6 of 13 role outputs (evidence, research manager, and the three risk roles are absent) (`findings-e2e.md` F9).
- [ ] 6.7 Verify run-scoped surfaces remain stable across turn selection and that switching turns updates every inspector section with no residual content from the previous turn.
- [ ] 6.8 Rewrite `Inspector` and `RoleInputPanel` tests for the flat-section structure, the merged evidence section, the identity facts, and the empty state.
- [ ] 6.9 Run typecheck + vitest, rebuild the static bundle, and commit the static drift.

## 7. Verification and closeout

- [ ] 7.1 Update `frontend/e2e/workbench.spec.ts` for the new flow map, debate stage, and inspector; assert SVG edge presence in a real browser.
- [ ] 7.2 Run the full backend suite (`pytest`) and confirm no regression from the evidence changes.
- [ ] 7.3 Run `npm --prefix frontend run test:e2e` against `scripts/e2e_server.py`.
- [ ] 7.4 Drive a real end-to-end run in the browser and confirm: prose reports readable, flow map edges live, rounds and lanes correct, inspector single-scope, and a thin-coverage ticker completing with a visible low-confidence verdict.
- [ ] 7.5 Update `CLAUDE.md` with the new evidence verdict model and the `evidence_stop_on_fail` default flip.
- [ ] 7.6 Update `CHANGELOG.md` recording the behavior change and the new frontend dependencies.
- [ ] 7.7 Update `Handoff.md` and the README web section for the new workbench structure.
- [ ] 7.8 Update `.env.example` with the newly exposed evidence env overrides.
- [ ] 7.9 Confirm the committed `tradingagents/web/static/` matches a fresh build and report the final bundle-size delta.
