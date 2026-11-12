# Option Ledger (Member B)

Status: architecture draft. Rejected/deferred options and their reconsideration conditions. This preserves actual alternatives; it does not claim an earlier decision history.

| Option | Status | Why rejected/deferred | Reconsideration condition |
|---|---|---|---|
| C1 minimal baseline extension | Rejected (not selected) | Lifecycle sequencing inline; provenance-drift risk; weakest typed failure behaviour (score 3.30) | If C's real tests show C1 cleanly testable with no provenance drift; or file-count constraint |
| C3 phased single-run orchestrator façade | Rejected (not selected) | Broad `cli/run.py` change; highest coupling/surface; scope-creep risk (score 3.75) | If instructor mandates a single orchestration façade |
| Inline validation in `cli/main.py` without shared service | Rejected | Duplicated-validator risk; violates NFR-005 | — |
| Newest/first-file default selection | Rejected | Violates FR-001/003 no-silent-fallback | — |
| Treat absent portfolio as flat / missing cash as 0 | Rejected | Invents account facts (FR-003/004) | — |
| Persist full portfolio payload in new headers/manifests | Rejected | Privacy (NFR-003/DQ6) | — |
| Truncated 12-char fingerprint for new provenance | Rejected for new provenance | Insufficient identity; upstream 12-char kept only for checkpoint signature | Only if a compatibility argument is made in a new ADR |
| Full web GUI / broker connection / order execution | Deferred (v2 scope) | Out of selection; safety | Separate approved scope |
| Resume/checkpoint redesign | Deferred | selected-requirements §5 | Separate approved scope |
| Aggregate run-token/time/call budgets | Deferred | Not requested; this is context-management, not run budget | Separate approved scope |
| Global source-confidence / sentiment correction / 12-channel grading | Deferred | selected-requirements §5 | Separate approved scope |
| Route API through common execution service (`run_analysis_api`) | **Accepted (designed)** | Supported project API must satisfy mandatory checks/finalization (B3-01) | — (implemented by D later) |
| Keep raw `TradingAgentsGraph` primitive as the only API | Rejected | Bypasses checks/redaction/manifest | Only as a declared low-level compatibility path, product use needing A approval |
| Remove raw primitive entirely | Deferred (not selected) | Preserves upstream tests/compat; removal is a larger compatibility change | If A/D choose to make it internal via a wrapper |

## Selection recorded
C2 selected by Brian (human) 2026-11-12 on estimated tradeoffs (see `adr/001-portfolio-aware-cli.md`, `evaluation-table.md`, `evaluation-logbook.md`).
