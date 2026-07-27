# Project Status: Workbench Debate Narrative & Evidence Degradation

> Implementation branch: `feat/workbench-debate-narrative`
>
> Planned continuation branch after merge: `codex/workbench-debate-script-and-inspector`
>
> Updated: 2026-07-27

## Scope status

| Phase | Status | Verified boundary |
|---|---|---|
| 0. Pre-flight | Complete except historical-run request-volume measurement | User approved committing/publishing this dirty tree; baseline and prior findings were recorded. |
| 1. Report rendering | Implemented and verified | Sanitized prose Markdown, literal data mode, windowed automatic response loading. |
| 2. Evidence verdict model | Implemented and verified | `PASS`, `LOW_CONFIDENCE`, `FAIL_STOP`; hard identity/fatal core-data stops preserved. |
| 3. Confidence propagation | Backend implemented and verified | Research/Portfolio prompts receive the low-confidence conviction cap. Final-decision UI badge remains Phase 5 work. |
| 3A. Debate turn authorship | Implemented and verified without a paid run | Prompt builders and storage-label contracts are covered; historical artifacts are untouched. |
| 4. Workflow map | Implemented and verified | Six stage groups, typed measured SVG edges, narrow-layout fallback, live role state. |
| 5. Debate stage | Not implemented | `laneOf()` exists, but round/lane script grouping, convergence blocks, and historical-attribution guard remain. |
| 6. Turn inspector | Not implemented | Current tabbed inspector remains; flat identity/evidence/prompt/output sections remain. |
| 7. Verification/closeout | Partial | Deterministic tests complete; real-provider/thin-coverage acceptance and historical run-store comparison remain. |

## Implemented behavior

### Report rendering and response loading

- Pinned `react-markdown@9.1.0`, `remark-gfm@4.0.1`, and
  `rehype-sanitize@6.0.0`.
- `SafeMarkdown` has explicit `prose` and `data` modes. Prose uses the default
  sanitize schema plus an http/https-only anchor override; data remains literal
  inside a whitespace-preserving `<pre>`.
- Report artifacts and turn bodies use prose mode; prompts/machine payloads use
  data mode.
- `useTurnResponses` loads the initial 12 artifact-backed turns in full. Later
  turns load 800-character excerpts, expose “展开全文”, and refetch the selected
  artifact in full. The queue is de-duplicated and capped at four concurrent
  requests; state and stale async results are isolated by `run_id`.

### Evidence degradation and confidence propagation

- `LOW_CONFIDENCE` is a terminal verdict; `NEEDS_ENRICHMENT` remains internal.
- Thin or zero usable news coverage after enrichment, non-fatal data warnings,
  unresolved A-share profile names, parse failures, and gate availability faults
  degrade rather than abort.
- Wrong-identity conflicts and fatal core-data patterns remain unconditional
  `FAIL_STOP` outcomes.
- `evidence_stop_on_fail` defaults to `False`.
- Environment overrides now include
  `TRADINGAGENTS_EVIDENCE_STOP_ON_FAIL`,
  `TRADINGAGENTS_NEWS_MIN_COMPANY_ITEMS`,
  `TRADINGAGENTS_NEWS_MIN_MIXED_ITEMS`, and
  `TRADINGAGENTS_HALT_ON_MISSING_DATA`.
- Research and Portfolio Manager prompts apply the existing conviction vocabulary
  as a ceiling when evidence is low-confidence.
- Unexpected Evidence Steward exceptions persist only the exception class (for
  example `RuntimeError`), not raw exception text that might contain a URL,
  query parameter, or credential.

### Debate authorship

- Opening turns request an opening case and omit empty opponent labels;
  subsequent turns request a rebuttal and include the opposing argument.
- Each research/risk debater is instructed to speak only as itself, avoid
  moderator framing, and never fabricate dialogue for another participant.
- Per-side turn bodies are unlabelled. The composed transcript retains structural
  speaker labels for `context_compaction.py`.
- This changes prompt behavior, so identical inputs/models may produce text and
  recommendations different from historical runs. Existing artifacts are not
  rewritten; two known historical multi-speaker payloads remain for Phase 5's
  rendering guard.

### Workflow map

- All 13 roles are assigned exactly once across six labelled stages.
- Declarative edges distinguish handoff, adversarial, and convergence paths.
- Wide layouts compute an inline SVG overlay from measured role geometry;
  narrow/jsdom layouts retain the stage grid without relying on unavailable
  measurements.
- Role and active-stage states are derived from the run state, including terminal
  handling that cannot leave a role falsely running.

## Verification evidence

- `node v24.15.0`, `npm 11.12.1`, and `npx 11.12.1` are available when the NVM
  path `/Users/david/.nvm/versions/node/v24.15.0/bin` is loaded.
- Frontend strict TypeScript: passed.
- Frontend Vitest: **13 files, 94 tests passed**.
- Frontend production build: **321 modules transformed**.
- Focused backend evidence/prompt/authorship suite: **49 passed**.
- Focused CI-regression suite for Windows console handling, canonical hashing,
  and debate authorship: **31 passed**.
- Full backend suite in the authoritative Conda `tradingagents` environment
  (Python 3.13.13): **1,333 passed, 19 warnings, 68 subtests passed**.
- CI dependency installation now uses `.[dev,web]`, so the Python 3.10-3.13
  matrix installs the canonical-JSON dependency required during collection.
- Production timestamp helpers and their tests use `datetime.timezone.utc`
  rather than the Python 3.11-only `datetime.UTC` alias, so collection remains
  compatible with the declared Python 3.10 floor.
- Wheel packaging contains the SPA index/JavaScript assets, and the installed
  wheel exposes working CLI help.
- Deterministic Playwright browser suite: **9 passed (14.8s)** in the release
  verification run using the fake runner, with no real LLM/provider call.
- During the final CI-closure pass, the exact Playwright rerun was blocked before
  assertions by the execution host (sandboxed Chromium Mach-port permission,
  followed by an in-app-browser policy stop). A fresh deterministic browser run
  still verified page load, 13/13 completion, all role labels, completed history,
  automatic timeline response text, inspector-tab presence, 13 response bubbles,
  13 completed role cards, configured-key status, and absence of secret names or
  values. The only current `scripts/e2e_server.py` diff is a trailing newline.
- Final committed frontend assets:
  - `tradingagents/web/static/assets/index-B0ahB111.js`: 388,038 bytes
  - `tradingagents/web/static/assets/index-02lLBz7O.css`: 26,634 bytes
  - combined: 414,672 bytes versus the 243,344-byte committed baseline
    (`+171,328` bytes, uncompressed).

## Verification boundaries

- The deterministic fake-runner E2E verifies the browser, SSE, store, artifact,
  and static-build path, including the 13-role workflow and automatic response
  display.
- It does **not** verify a real provider, provider billing/authentication, a real
  thin-coverage ticker reaching `LOW_CONFIDENCE`, post-3A model output, or the
  Phase 5/6 designs.
- No paid provider call was made for this release slice.
- Isolated verification homes/run roots are intentionally retained until the
  user approves cleanup after the release report.

## Remaining work

1. Phase 5: implement `debateScript`, round/lane/convergence rendering, candidate
   labels, and the historical foreign-attribution guard.
2. Phase 6: replace the tabbed inspector with turn-scoped flat sections and move
   run-scoped inputs/artifacts into a run-header surface.
3. Run a real two-round post-3A analysis and a thin-coverage ticker acceptance
   only after explicit approval for provider/data-source cost and credentials.
4. Compare pre-3A and post-3A run-store payloads and complete the historical F6
   scan.
