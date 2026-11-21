# Risk List (Member B)

Status: architecture draft. Assumptions, risks, owners and review triggers. Ownership follows `docs/project-deliverables-and-ownership.md`. Nothing here is a claimed mitigation already in place unless explicitly marked resolved.

| ID | Type | Description | Impact | Owner | Review trigger |
|---|---|---|---|---|---|
| R-GOV | Governance gap | `AGENTS.md` and `.opencode/` absent at drafting; no verified OpenCode permission enforcement | Agent edits unguarded | E | Before any implementation |
| R-API | Boundary (B3-01) | Raw engine primitive (`TradingAgentsGraph.propagate/stream_run`) bypasses the shared execution service (no `OutputChecker`/redaction/manifest). **Design resolved:** supported project API routes through `runapi/execution.run_analysis_api` (full coverage); primitive is a declared reduced-coverage compatibility path. Residual: product reliance on the primitive requires A approval. | Only if primitive used for product | A (approve scope) / B / D | A approval of reduced-coverage scope |
| R-C1 | Design (rejected alt) | If C1 were chosen, reporting could re-derive provenance from `final_state`, breaking shared identity | Latent FR-006/007 | B (record) | If reopening C1 |
| R-DRIFT | Provenance drift | Reporting/result/check reading different provenance sources | Audit inconsistency | B/D | Code review of boundary |
| R-CANON | Fingerprint (B3-03) | Canonicalization specified (`interface-contracts.md` §2.2): encoding, key order, separators, null==absent, numeric normalization, list sort, symbol spelling, exclusions. Residual: D must implement exactly. | Incorrect identity if misimplemented | B (spec) / D | Implementation review |
| R-OVERWRITE | Data loss | Legacy date-keyed state log overwrites same ticker+date; must be replaced by run-ID keying | Lost prior run | B/D | Implementation |
| R-PRIV | Privacy | Redactor gaps across new sinks; household secrets in narrative | Secret/holdings leak | B (design) / C (test) | Security test review |
| R-PROMPT | Semantics | Manager rating-legend "current position" wording (PM `portfolio_manager.py:51-55`, RM `research_manager.py:30-34`) must be mode-conditioned; no-portfolio Hold meaning defined | FR-004/005 violation | B (spec) / D | Prompt change review |
| R-LABEL | NFR-006 | Completion accounting must count all started runs and zero-completed → insufficient evidence | Misleading quality | B/D | Evaluation design |
| R-SEMANTIC | GOV-004 | Semantic rubric/threshold unset; B cannot supply | Gate unimplementable until fixed | C/A | Before semantic approval |
| R-EST | Estimate | All scores/effort are design estimates, not measurements | False confidence | B | On test evidence |
| R-LAYOUT | Course ambiguity | Blueprint location / source-test layout / transcript wording pending instructor | Deliverable mismatch | E | Instructor clarification |
| R-D1 | Requirements | `selected-requirements.md` is working input, not approved D1 | Scope churn | A | Final D1 approval |

## Assumptions
- CLI-only UI (selected). `PORTFOLIO_DIR=<root>/portfolios`. Full-64 fingerprint for new provenance; upstream 12-char checkpoint fingerprint preserved.
- Blocking ambiguities already resolved by Brian (Stage 1 §5.3–5.4).

## Open decisions (not B's)
Final D1 (A); semantic rubric/threshold (C/A); governance install (E); instructor layout (E); A's approval of any product reliance on the reduced-coverage raw engine primitive (R-API). **API routing is a closed design decision** — the supported project API traverses `runapi/execution.run_analysis_api`; no future ADR is required to *decide* that (implementation is D's).
