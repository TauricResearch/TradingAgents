# Memory and State Design (Member B)

Status: architecture draft. Distinguishes pre-run cancellation, fresh started runs, transient state, immutable final artifacts, user-supplied portfolio data, provider transmission and retention/privacy. Resume changes are deferred (selected-requirements §5) and are **not** designed here.

## 1. Lifecycle states

| State | Meaning | Persisted? | LLM calls |
|---|---|---|---|
| Pre-run cancellation/rejection | Discovered/cancelled/invalid input before consent, or consent declined | **No completed run**; no artifact; counted separately (NFR-006) | Zero |
| Fresh started run | A new invocation after consent; gets a unique `run_id` | Transient during run; final artifacts after finalization | Yes |
| Transient run state | In-memory graph state, message buffer, intermediate chunks | In-memory (plus existing log files) | — |
| Immutable final artifacts | Final report (MD/HTML), manifest (published run directory) | **Yes, write-once** | — |
| User-supplied portfolio data | Frozen snapshot from selected file | Held in `RunContext`; **not** written whole to new sinks | — |
| Provider transmission | Holdings sent to configured model provider | Intentionally disclosed pre-consent as a notice; actual transmission **after** consent | Yes (during run) |
| Retention/privacy | What persists locally and what is redacted | Per §4 | — |

A fresh invocation always creates a fresh `run_id` (no resume in this selection).

## 2. Owned state
- **`RunContext`** owns the immutable input identity (mode, frozen snapshot reference, full-64 fingerprint, as-of/basis, consent state). It is the authoritative provenance for report/result/manifest/check.
- **Transient graph state** (`tradingagents/graph/propagation.py`, `agents/state.py`) carries rendered `portfolio_context` (string) to the decision agents — upstream behaviour preserved. The rendered string is derived once at run start (`trading_graph.py:293-307`).
- **User-supplied portfolio data** is read **once**, validated, frozen; the file is never re-read after freeze (interface-contracts §4).

## 3. Write/retrieval policy
- Each fresh run writes into its **own run-ID-isolated** location. Same-ticker/same-date runs must not overwrite a prior run's artifacts (INV-12); the legacy date-keyed state log (`full_states_log_{trade_date}.json`, `trading_graph.py:472`) is addressed in §5.
- The manifest is written **atomically once** after artifact/check finalization, from the `SafeRunMetadata` projection — never the full `RunContext`/payload.
- Retrieval for reads (e.g., console "where is my report") uses redacted paths; no secrets.
- Resume: **deferred**. A final record is never mutated to simulate a resume.

## 4. Retention, retrieval and privacy (B3-09)

- **Transient snapshot lifetime:** the frozen snapshot value tuples live only in `RunContext` for the duration of the process/run; they are **never written** to durable sinks and are released on process exit. No durable copy of holdings is created by this extension.
- **Durable retention:** by default, artifacts persist under the run's isolated results directory **until the user deletes them**. This selection does **not** introduce automatic deletion or a cross-run catalogue (deferred). **Deletion owner:** the end user (application role); E/ops may define a later retention policy but must not silently delete user artifacts.
- **Retrieval policy:** reads for provenance/console use the redacted `SafeInputMetadata`/`SafeRunMetadata`; the portfolio source file is not re-read after freeze; no full payload is retrieved from manifests/logs.
- **Redaction ≠ suppression:** masking secrets (NFR-003) is **distinct** from suppressing raw holdings/prompt dumps. Both are required: raw portfolio bytes, full `RunContext`, raw provider prompts/payloads are **not persisted** in new sinks regardless of redaction.
- **Provider retention:** holdings **transmitted to the provider after consent** are subject to the **provider's own retention/logging policy, outside application control**; the notice states this is intentional provider transmission. The application is not represented as local-only.
- **Secrets:** never persisted; redaction boundary at every sink (§5).
- **Source files:** portfolio source files are kept **read-only**; their bytes are not copied into manifests/transcripts.

## 5. Sink handling (existing + new)

Each sink: decision (retain/adapt/disable/replace), output location, run-ID isolation, overwrite prevention, permitted content, redaction boundary, raw-payload suppression, failure handling, responsible component. Criticality and ordering are in `interface-contracts.md` §7.

| Sink | Decision | Output location | Run-ID isolation & overwrite prevention | Permitted content | Redaction boundary | Raw payload suppression | Failure handling | Responsible component |
|---|---|---|---|---|---|---|---|---|
| `message_tool.log` (`cli/run.py:139-164`) | **Adapt** | per-run results dir (`results_dir/<ticker>/<run_id>/message_tool.log`) | Under run-ID-isolated dir; never append across runs | Model/system narrative; no raw portfolio bytes/other-position dump | `Redactor` per line | Yes | **Best-effort:** failure ⇒ redacted note; does not flip COMPLETED (not a promised artifact) | Persist + Redactor |
| Graph state JSON `full_states_log_{trade_date}.json` (`trading_graph.py:472`) | **Adapt (replace path keying)** | per-run results dir | **Legacy date-keyed overwrites same ticker+date.** Replace with run-ID-qualified filename; refuse-if-exists | Existing narrative fields + safe provenance projection; never raw payload | `Redactor` on serialized entry | Yes | **Best-effort:** failure ⇒ redacted note; prior run preserved | Persist (path) + Redactor |
| Markdown report (`reporting.py`) | **Adapt** | per-run dir (`reports/complete_report.md`) | Run-ID-qualified; **critical**: written to `_staging`, published only by the single directory commit (§interface-contracts §7); refuse silent overwrite | Checked body + trusted envelope from safe projection | Redact body **before** check; escape/redact provenance | Yes | **Critical:** staging/commit failure ⇒ INCOMPLETE/PERSISTENCE_ERROR; no success exposed (§7) | reporting + Persist |
| HTML report (`report_html.py`) | **Retain escaping, adapt provenance source** | alongside MD (`complete_report.html`) | Same as MD (critical when enabled) | Same checked body + escaped envelope | Already escapes (`:10,226,255`); extend to provenance | Yes | Same as MD | reporting + Persist |
| **Manifest (new)** | **New** | per-run dir (`manifest.json`) | Run-ID-qualified; **written into `_staging` before the single commit**; immutable after commit; refuse overwrite | `Manifest` (`SafeRunMetadata` + paths + `terminal_event.durable`, decided pre-commit); **no payload/secret endpoints** | `Redactor` before staging write | Yes | **Critical:** staging/commit failure ⇒ INCOMPLETE/PERSISTENCE_ERROR; nothing published | Persist |
| **JSONL event sink (new)** | **New** | per-run dir (`events.jsonl`) | Run-ID-qualified; **terminal event appended to `_staging` before commit (sets `durable`)**; other progress events best-effort | Fixed fields (§interface-contracts §3.9) | `Redactor` per event | Yes | **Best-effort, non-critical: terminal append failure ⇒ `terminal_event.durable=false` (manifest states it) but the logical outcome is preserved and the run is published; progress-event failure ⇒ redacted note, never changes the immutable manifest** | EventSink + Persist |

**Disclosure distinction:** decision-agent narrative necessarily receives provider-summarized context **after consent** (intentional disclosure). This is distinct from copying **raw portfolio bytes / full provider payloads** into manifests/logs/events/state JSON, which is prohibited (INV-06).

## 6. Non-goals
No resume/checkpoint redesign, no cross-run catalogue, no aggregate budget persistence. Upstream checkpoint fingerprint (12-char) remains a checkpoint concern, preserved unchanged.
