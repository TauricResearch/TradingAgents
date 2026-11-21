# Selected requirements: portfolio-aware CLI and auditable reporting

Date: 2026-11-12, Asia/Hong_Kong. Status: working selection authorized for architecture exploration by Brian; pending Member A/team approval as a final registry. This is not the final D1 YAML deliverable. IDs `SEL-TA-*` belong to this selection and do not silently modify/reuse the wider v2 IDs.

## 1. Scope and baseline

Target TradingAgents v0.7.1; extend its existing terminal UI, Python/LangGraph workflow, portfolio loader and Markdown/HTML reports. No new web GUI, broker connection, order execution, exposure certification or guaranteed investment outcome. Preserve baseline code/import structure until an approved layout decision.

This deliberately revises v2's exclusion of portfolio input. Both modes are supported: `NO_PORTFOLIO` (unknown holdings/cash) and `PORTFOLIO_PROVIDED` (explicit user-selected snapshot). An explicitly supplied empty positions list is a flat snapshot, not missing input. Reported holdings are user-supplied context, not independently verified account facts.

Existing v0.7.1: CLI `--portfolio PATH` calls `tradingagents.portfolio.load_portfolio`; its optional context reaches the graph and decision agents. No option means no context. It does not offer the proposed automatic folder picker/confirmation flow. Relevant sources: `cli/main.py`, `cli/run.py`, `tradingagents/portfolio.py`, `tradingagents/agents/context.py`, `tradingagents/graph/trading_graph.py`.

### Fixed working decisions

- Interface is the current CLI. `PORTFOLIO_DIR` defaults to `<project-root>/portfolios`; do not search the home directory, credentials or arbitrary folders. Interactive discovery is non-recursive and lists regular `.json` files in deterministic filename order; symlinks are excluded from discovery.
- Explicit `--portfolio PATH` remains supported, including a deliberately supplied path outside PORTFOLIO_DIR. Do not silently pick the newest/first file. Explicit paths are not an instruction to scan their parent directory.
- Noninteractive use requires either `--portfolio PATH` or a new explicit `--without-portfolio` flag. Neither means input error; both means input error. The ordinary Python API remains usable with `portfolio=None` and does not prompt. CLI flags express the consent that an unattended process cannot give interactively.
- A run begins only after input selection/validation/confirmation. Cancelled/rejected input starts no graph, makes zero LLM calls and creates no completed run. A fresh invocation creates a fresh run ID. Checkpoint resume, backtest changes, deadlines/token/call budgets and convergence changes are deferred from this selection.
- Snapshot timing: user confirms that selected holdings are intended for analysis date D; record `portfolio_as_of=D` and `as_of_basis=USER_CONFIRMED`. Never infer timing from file modification time or claim historical accuracy was verified. Noninteractive `--portfolio` users must supply `--portfolio-as-of D` matching the requested analysis date. Existing upstream loader schema stays unchanged; these are wrapper metadata.
- Selection reads the chosen file once, validates those bytes and freezes the normalized context for that run. Subsequent file changes cannot silently change the snapshot. Do not persist the full portfolio or other-position list in new report headers/logs/manifests; upstream decision prompts necessarily receive context and the provider disclosure is made before confirmation. Context-dependent generated narrative is still possible.

### Result and check contract

Every started run returns `run_outcome=COMPLETED|INCOMPLETE`. Completed means the workflow returned; its final `rating` is Buy/Overweight/Hold/Underweight/Sell or REVIEW. Incomplete has no final rating and has `stop_reason=MODEL_FAILURE|DATA_FAILURE|INTERNAL_ERROR|PERSISTENCE_ERROR|INTERRUPTED`. Use MODEL_FAILURE only for exhausted model/provider output failures; DATA_FAILURE for an unrecovered raised vendor/data exception; preserve baseline recoverable non-core unavailable-data behaviour. INTERRUPTED covers cooperative cancellation, not an impossible promise to persist through power loss.

`output_check=PASSED|NEEDS_REVIEW|NOT_RUN`; incomplete always NOT_RUN. A deterministic component owns the check. Rules: Q1 final rating readable, Q2 header matches trusted input snapshot metadata, Q3 disclaimer present, Q4 prohibited guarantee phrases absent. Each broken rule is a blocking finding; checker exception yields blocking CHECK_ERROR. No findings means PASSED. PASSED certifies only these checks, not factual accuracy or account suitability. This selection does not introduce global source-confidence scoring, sentiment correction or twelve-channel availability grading.

Frozen strings: no-portfolio notice = `Holdings and cash were not provided; no account ownership is assumed.` Disclaimer = `Research output only. User-supplied holdings are unverified. No order is placed and no return is guaranteed.` Q4 checks the model-generated narrative for case-insensitive phrases `guaranteed profit`, `guaranteed returns`, `capital protection is guaranteed`. The trusted disclaimer is excluded. These limited phrase checks are complemented by SEL-TA-GOV-004 semantic evaluation and are not claimed to prove universal absence of paraphrased guarantees.

## 2. Functional requirements

Each criterion below is a proposed acceptance obligation, not an existing test/result. All offline tests use isolated folders, a scripted model and no network. C owns actual test IDs, files and procedures.

### SEL-TA-FR-001 Discover and select a portfolio file

- Type: functional. Priority: Must. Source: Brian's new holdings workflow; extends v2 FR-007 scope.
- Statement: In interactive mode without an explicit input-mode flag, the CLI lists eligible filenames from PORTFOLIO_DIR and offers select one, continue without portfolio, or cancel. A missing/empty directory proceeds to the explicit no-portfolio confirmation; a directory read error is shown and offers retry, explicit no-portfolio confirmation, or cancel. It is never described as an empty directory.
- Fit: With eligible `a.json`, `b.json`, a nested JSON, symlink and text file, exactly a/b appear once in sorted order; selecting b passes only b to validation. Separate empty/missing/unreadable fixtures follow their declared branch; cancelling dispatches zero LLM calls. One invalid selection does not pick a default.
- Baseline: --portfolio exists; picker is new. Tradeoff: an extra interaction prevents silent selection.

### SEL-TA-FR-002 Explicit mode confirmation

- Type: functional. Priority: Must. Depends: FR-001.
- Statement: Interactive no-portfolio choice shows the frozen notice and asks to proceed, default No. File choice shows basename, analysis date, unverified/as-of statement, and that holdings will be sent to the configured model provider; it asks to proceed, default No. Confirming without holdings passes actual None, not an empty PortfolioContext. Automated invocation follows the flag rules above; an explicit flag is consent and prompts are suppressed.
- Fit: Yes/No/EOF fixtures for each mode: only Yes starts one graph. No/EOF starts zero and exits cleanly. Noninteractive neither/both flags produce a readable input error and zero graph/LLM calls; valid --without-portfolio starts once with None.
- Tradeoff: adds confirmation while preserving deliberate unattended use. API calls do not gain interactive prompts.

### SEL-TA-FR-003 Validate and freeze the selected snapshot

- Type: functional. Priority: Must. Depends: FR-001/002.
- Statement: Require top-level JSON object with explicit `positions` list. Each position has ticker and finite numeric quantity; optional average_price and cash are null or finite JSON numbers (booleans and numeric strings are rejected). Optional currency is a string or null. Reuse upstream model validation after these input prechecks. Empty positions is valid; malformed/missing fields, NaN/Infinity, unreadable paths and as-of mismatch stop input before dispatch. Explain filename plus bad field/path without exposing file contents or credentials. Permit reselect/cancel; no silent no-portfolio fallback.
- Fit: Valid populated, explicit empty and null-cash fixtures load; six invalid classes (bad JSON, missing positions, missing quantity, nonfinite number, wrong scalar type, unreadable file) and as-of mismatch each dispatch zero calls with a field/file diagnostic. Editing the file after confirmation does not change the context used or fingerprint recorded.
- Baseline: upstream validates many invalid files; explicit shape/type/as-of and freezing are project extensions. Tradeoff: previously permissive `{}` input is rejected to avoid treating absent data as an intentionally empty book.

### SEL-TA-FR-004 Propagate explicit context without inventing holdings

- Type: functional. Priority: Must. Depends: FR-003.
- Statement: Pass exactly the frozen validated snapshot through the existing portfolio argument to the decision agents. Retain upstream instrument alias matching. Missing cash is not zero; absent context is not a flat book. No-portfolio prompts do not refer to the user's existing position. Portfolio-provided prompts may refer only to explicitly supplied facts, labelled as user-supplied; they do not claim account verification.
- Fit: Capture Trader/Portfolio Manager prompts for no portfolio, explicit flat, held ticker, broker-alias ticker and null-cash fixtures. All five preserve their distinct state; missing cash renders no invented number. Assert selected fixture values occur, another file's unique marker does not, and no-portfolio calls contain the frozen notice.
- Baseline: optional rendering/alias distinctions already exist; unified confirmation-to-report identity and strengthened wording are new. Tradeoff: preserving unknowns limits account-specific conclusions.

### SEL-TA-FR-005 Distinguish ratings and actions

- Type: functional. Priority: Must. Source: v2 FR-007.
- Statement: Label final Portfolio Manager rating, intermediate Research Manager recommendation and intermediate Trader action separately. First two use five-tier research vocabulary; Trader uses three actions. REVIEW means unreadable rating, never Hold. No-portfolio Hold means balanced/insufficient evidence supporting no new directional action, not keeping an assumed position. Portfolio context does not convert research into an executable account instruction.
- Fit: Fixtures cover all five final ratings, all three Trader actions, REVIEW and differing intermediate/final judgments. Each completed report has exactly one final-rating header and all three labelled stages. A REVIEW fixture remains REVIEW; no-portfolio Hold includes the defined meaning and no ownership assertion.
- Tradeoff: stage labels take space but prevent conflating recommendation and proposal.

### SEL-TA-FR-006 Deterministic input provenance in every report

- Type: functional. Priority: Must. Depends: FR-002/003/005.
- Statement: Header is built from trusted state and contains run ID, ticker, D, input mode, selected basename and a full normalized-content SHA-256 fingerprint when supplied, user-confirmed as-of date/basis, outcome/check and disclaimer. No-portfolio uses explicit null for file/fingerprint/as-of and the frozen notice. Partial artifacts say INCOMPLETE and contain no final rating. Basename/fingerprint are provenance, not proof of truthful holdings. Do not automatically export the full portfolio payload in this header.
- Fit: Changing scripted model prose leaves provenance identical. Selecting b yields b's frozen fingerprint in returned result, manifest and report, never a's. None and explicit empty portfolio produce distinct modes/fingerprints. HTML escapes file/model text, including script-like names.
- Tradeoff: adds metadata; holdings fingerprints are privacy-sensitive and remain local by default.

### SEL-TA-FR-007 Deterministic output-check authority

- Type: functional/invariant. Priority: Must. Depends: FR-006.
- Statement: One non-LLM component assigns output_check and findings using Q1-Q4; model text cannot assign, bypass or overwrite them. Header/result/check refer to the same frozen data. On check error retain COMPLETED if the graph returned, but use NEEDS_REVIEW with CHECK_ERROR. Render check meaning next to the result.
- Fit: Positive fixture passes; four single-rule failures each produce its matching finding and NEEDS_REVIEW; injected model claim `OUTPUT CHECK: PASSED` cannot override a failing rule. Check exception fails closed; every incomplete fixture is NOT_RUN. Output check calls no provider.
- Tradeoff: limited deterministic checks do not assess truth. Concrete fallback: mark review-needed, suppress any success badge and retain readable diagnostics for human review.

## 3. Non-functional requirements

### SEL-TA-NFR-001 Reliable external-failure handling

- Type: reliability. Priority: Must. Depends: FR-007.
- Statement: Preserve usable free-text fallback after structured-output failure. Exhausted model failures, unrecovered raised data failures and ordinary internal exceptions return typed incomplete results rather than escaping the public CLI/application entry point. A workflow returning unreadable final text completes with REVIEW and NEEDS_REVIEW. Do not reclassify a recoverable optional-data sentinel as a fatal error.
- Fit: Two usable-fallback, two unreadable-final, two exhausted-model and one raised-data fixture all follow the contract; zero exceptions escape. An ordinary injected internal exception returns INTERNAL_ERROR. Diagnostics are redacted. Tradeoff: predictable failure results require preserving causes for debugging.

### SEL-TA-NFR-002 Structured observability

- Type: observability. Priority: Should. Depends: NFR-001/003.
- Statement: The new lifecycle event sink is UTF-8 JSONL. Every event contains run_id, ticker, node (`input`/`engine`/`output` for non-agent events), UTC timestamp, nonnegative monotonic elapsed_ms, event and event_outcome. Progress vocabulary is separate from terminal run_outcome. Console presentation may remain human-readable; raw provider payload logging is disabled by default in this selection.
- Fit: Parse every line from one completed and one incomplete run: 100% parse, required fields non-null and elapsed nonnegative. Exactly one terminal event per run. No full portfolio payload or planted secret appears. Existing upstream state snapshots are not falsely described as JSONL. Tradeoff: machine-readable logs need a human-friendly console view.

### SEL-TA-NFR-003 Credential and holdings privacy

- Type: security/privacy. Priority: Must.
- Statement: Central output/error redaction covers the selected CLI, model/data exception messages, new events, report headers and manifests. Never emit API keys, OAuth access/refresh tokens or bearer credential values. Keep portfolio source files read-only. Do not copy raw portfolio bytes into manifests/transcripts or print other-position lists in the selection UI. The confirmed disclosure to the model provider is intentional, not represented as local-only processing.
- Fit: Four planted secret types across each named sink and model/data error path yield zero values; marker for an unrelated holding does not appear in UI/header/events/manifest. Source bytes are unchanged after success/failure. Secret leakage inside arbitrary generated narratives is also scanned; redact before delivery. Tradeoff: diagnostic detail is reduced. C expands the named-path inventory as integrations grow.

### SEL-TA-NFR-004 Distinct immutable fresh-run artifacts

- Type: reproducibility. Priority: Should. Depends: FR-006, NFR-003.
- Statement: Each started fresh run gets a unique ID and its own report directory and final manifest. Write manifest atomically once after artifact/check finalization. Record times, code version/source identifier, prompt hash, safe effective config, input provenance and result fields. Do not serialize secret endpoints; record safe provider identifiers. Failed runs keep available partial artifacts. Durable records during total disk failure/power loss are not promised; return a redacted persistence diagnostic if commit fails.
- Fit: Two same-ticker/date runs produce two directories; first hashes remain unchanged. Config-only comparison of two manifests differing in one selected config key finds exactly that config difference; IDs/timing/results are excluded from that assertion. Prompt edit changes hash. Required result fields are validated conditionally: incomplete has no rating, completed has no stop_reason. Resume is deferred, not implemented by mutating a final record.
- Tradeoff: extra storage; no automatic deletion in this selection.

### SEL-TA-NFR-005 Cohesive, compatible integration

- Type: maintainability. Priority: Should. Depends: FR-003/004.
- Statement: One reusable selection/input service and one shared result/reporting boundary support CLI without putting interactive prompts inside agents or the Python engine API. Reuse the upstream portfolio model/rendering and selected graph contract. Do not replace the baseline or duplicate independent JSON validators in every agent. Preserve upstream tests and explicitly document intentional CLI/type-validation changes.
- Fit: One mocked API call with portfolio=None completes without terminal reads; explicit valid portfolio CLI call invokes selection service once and graph once. Structural check finds zero terminal prompt imports in tradingagents/agents/** and graph/**. Full prior offline suite has zero unapproved regressions. Tradeoff: added adapter boundary in exchange for testability.

### SEL-TA-NFR-006 Transparent evaluation population

- Type: evaluation quality. Priority: Should. Depends: NFR-004.
- Statement: Completion fraction counts all started fresh runs; pre-run rejected/cancelled inputs are counted separately. Quality summaries use completed runs and show count, NEEDS_REVIEW count and incomplete-reason counts alongside scores. Zero completed samples means insufficient evidence, never a passing quality result. Controlled before/after experiments may differ in declared changed factors; repeated fixed-condition benchmarks require matching controls.
- Fit: Ten started records (six completed, two of those review-needed; four incomplete) plus two pre-run cancellations produce completion 6/10, review-needed 2, cancellations 2 and no dropped starts. Zero-completed fixture returns insufficient evidence. Changed prompt experiment is labelled as such, not rejected merely for its hash. Tradeoff: denominators expose unavailable delivery rather than hide it.

## 4. Mandatory process requirements (additional to the seven FRs/six NFRs)

These follow the course brief, not optional v2 startup exemptions. Accountable owners are separate from the implementation designer.

| ID | Type / priority | Statement and fit criterion | Owner |
|---|---|---|---|
| SEL-TA-GOV-001 | Governance / Must | Before implementation, record attributable approval of the independent test plan. An implementation PR with no prior approval fails its required check. | C plan; E enforcement; human approver |
| SEL-TA-GOV-002 | Governance / Must | Registry validates against its schema. One valid/one invalid registry fixture proves pass/fail. A supplies final YAML/schema; this working Markdown is not substituted for them. | A/E |
| SEL-TA-GOV-003 | Governance / Must | Prior tests run with zero unapproved regression; lint/type/dependency checks run on commits; safety PRs also run contract/security/API/permission checks. Introduced negative fixtures fail the matching required check. | C/E |
| SEL-TA-GOV-004 | Governance / Must | Prompt/model changes replay fixed semantic cases against human-approved quality thresholds before production. Cases cover conditional ownership, rating/action distinction, guarantee language and injection. Below threshold or no valid samples cannot pass. C freezes rubric/population/threshold with A; D measures; E enforces. No unapproved non-blocking startup claim. | C/D/E |
| SEL-TA-GOV-005 | Governance / Must | Code/prompt PR without AI-use log update is blocked. Demonstrate one rejected and one accepted fixture/change. Record real tools/model/session/interventions only. | E/all |
| SEL-TA-GOV-006 | Governance/invariant / Must | Branch protection requires passing checks and human review plus ADR for safety changes; agent file access follows approved default-deny whitelists. A denied write attempt is blocked and logged without changing the file. | E with B permission design |

## 5. Test profile, ownership and deferred scope

Pinned offline workload: isolated temporary directories, fake portfolio files (no real holdings/keys), scripted models following v0.7.1 test seams, no network and no provider billing. A/C turn the acceptance sketches into an approved fixture inventory and executable tests; they must not assert tests exist/pass yet. API/CLI/Markdown/HTML paths are distinct integration obligations. Exact semantic scoring threshold is an open C/A decision and must be fixed before semantic approval, not invented by an architecture agent.

B designs enforcing components, contracts, invariant fallbacks, state/privacy and permission boundaries. D implements via supervised OpenCode. C owns test code and independent verification. E owns enforcement/packaging; A owns final requirements. All selected runtime requirements are Must or Should with dependencies no lower in priority. Mandatory minimal result persistence belongs to FR-006; optional richer experiment metadata belongs to NFR-004.

Deferred: web GUI; exposure caps/position validation; automatic broker discovery; order execution; full stable-evidence registry across twelve channels; new historical filtering/freshness rules; global source-confidence grades; R4-R6 sentiment correction; resume/catalogue redesign; aggregate time/token/call limits; debate convergence; analyst plugin redesign. Preserve upstream safeguards while deferring their extension. Do not claim deferred v2 requirements are satisfied by this selection.

Open items do not authorize silent improvisation: final D1 approval, semantic rubric/threshold, exact source/test layout accepted by instructor and the governance setup are unresolved. They do not prevent design candidate exploration; implementation/production gates remain real. Use the working decisions above for architecture unless a direct contradiction is found.

Change log: 2026-11-12 +08:00 - Initial seven-FR/six-NFR/six-governance working selection, incorporating explicitly confirmed optional holdings. No v2 source file modified; new input-mode scope awaits A/team adoption.
