# Architecture Blueprint — Portfolio-Aware CLI and Auditable Reporting

Status: **architecture draft (Stage 3)** for Member B's session. Not implementation, not verification, not an approved course deliverable until E/team assembly and instructor reconciliation. Complements the D2 artifacts under `docs/architecture/`.

- Selection: **C2 — input-service + immutable `RunContext` boundary with a small lifecycle coordinator**, chosen by Brian (human) on 2026-11-12 based on **estimated** tradeoffs, not verified superiority.
- Target baseline: TradingAgents **v0.7.1** (`tradingagents/__init__.py:3`, `pyproject.toml`).
- Working scope: `docs/req/selected-requirements.md` (`SEL-TA-FR-001..007`, `SEL-TA-NFR-001..006`, `SEL-TA-GOV-001..006`). This is a working selection, **not** an approved D1 registry.
- Location convention (interim, pending course clarification): this root file is canonical; `docs/architecture/architecture-blueprint.md` is a pointer only.

> Honesty statement: This document specifies architecture and testability. It does **not** claim C's tests exist/pass, E's gates are enforced, or any approval has been obtained. Unknown test IDs and implementation links remain **pending**. Estimates are labelled **ESTIMATE**.

---

## 1. Scope and drivers

### 1.1 Scope
Extend the existing terminal UI (`cli/`), the Python/LangGraph workflow (`tradingagents/`), the portfolio loader (`tradingagents/portfolio.py`) and the Markdown/HTML reports (`tradingagents/reporting.py`, `tradingagents/report_html.py`) so a run can be performed in one of two input modes:

- `NO_PORTFOLIO` — the caller's holdings/cash are unknown; nothing is assumed.
- `PORTFOLIO_PROVIDED` — an explicitly selected, validated, frozen snapshot supplied by the user.

Both modes yield an auditable result with deterministic input provenance and a deterministic output check.

### 1.2 Drivers
| Driver | Source |
|---|---|
| Optional, explicitly confirmed holdings input | selected-requirements §1; Brian decision |
| No silent portfolio fallback; no invented zero holdings/cash | FR-003/004, NFR-001 |
| Deterministic check authority (model cannot override) | FR-007 |
| Frozen input provenance in every report | FR-006 |
| Secret/holdings privacy across sinks | NFR-003 |
| Reusable boundary without terminal prompts in engine/agents | NFR-005 |
| Reliable external-failure handling | NFR-001 |
| Structured observability | NFR-002 |
| Cohesive integration preserving upstream | NFR-005 |

### 1.3 Explicit non-goals (deferred; do not claim satisfied)
Web GUI; broker connection/order execution; exposure certification; automatic broker discovery; full twelve-channel evidence registry; new historical filtering/freshness rules; global source-confidence grades; R4–R6 sentiment correction; resume/checkpoint redesign; aggregate time/token/call budgets; debate convergence; analyst plugin redesign. (selected-requirements §5.)

### 1.4 Authority of current selection vs open decisions
- **Approved working input (use directly):** CLI-only UI; `PORTFOLIO_DIR=<project-root>/portfolios`; `--without-portfolio`; `--portfolio-as-of`; consent behaviour; full normalized-content SHA-256 (64-char) fingerprint.
- **Open (not B's to close; do not invent):** final D1 YAML/schema approval (A); semantic rubric/threshold (`GOV-004`, C/A); instructor-accepted source/test layout and transcript wording; governance install (E); blueprint location final convention (E).

---

## 2. System and deployment boundaries

- **Runtime:** a single local Python process. The user interacts through the terminal (the existing CLI). No network is required for input selection/validation; network/provider calls occur only inside the graph after confirmation.
- **Requested interface:** current CLI (`cli/main.py`), extended with input-mode flags. This is the only new user-facing surface; no new web application.
- **Baseline preserved:** `tradingagents/`, `cli/`, `pyproject.toml` and existing tests are preserved. The extension is discovery, explicit consent, frozen provenance and coherent reporting (Prompt.md "Session objective and input precedence" / "Access and output boundaries").
- **Trust boundary for data:** user-supplied portfolio files are *context*, never verified account facts. The trusted state used to build provenance is the frozen snapshot produced by the input service, not model text and not re-read file bytes.

### 2.1 Data-flow (C2)
```
terminal user
   │  (interactive, or flags)
   ▼
CLI adapter (cli/main.py)  ──►  PortfolioInputService (discover → validate/precheck → freeze)
   │                                         │
   │                                         ▼
   │                              RunContext (deeply immutable)
   │             frozen snapshot + mode + full-64 fingerprint + as-of + disclosure flags
   │                                         │
   │   [notice shown; consent gate]
   │                                         │
   ▼                                         ▼
runapi/execution.run_analysis_api  ── consent confirmed ──►  engine.stream_run
   │  (CLI single-run orchestration, no LLM)         (portfolio=None | frozen snapshot)
   │                                         │
   │                                         ▼
   │                     runapi/checks.py OutputChecker (non-LLM, authoritative)
   │                                         │
   │                                         ▼
   │                  runapi/finalize.py OutcomeFinalizer (COMPLETED|INCOMPLETE)
   │                                         │
   ▼                                         ▼
Artifact boundary (redaction + run-ID isolation)  →  report(MD/HTML), manifest, JSONL events, logs, state JSON
```

---

## 3. Components

Concrete planned module paths are in `docs/architecture/interface-contracts.md` §1 (B3-10). Reusable noninteractive services live under `tradingagents/runapi/` and must not import `cli`.

| Component | Responsibility | Where (planned) | Needs baseline change? |
|---|---|---|---|
| **Shared execution service** | **Common application entry** `run_analysis_api(RunContext, …)`: consent check → run → render → check → finalize → stage/publish → terminal event. Prompt-free; used by CLI and supported API. | `tradingagents/runapi/execution.py` | additive |
| `PortfolioInputService` | Noninteractive discovery/precheck/freeze; **sole** discoverer/validator; prompt-free. | `tradingagents/runapi/input_service.py` | additive |
| `RunContext` / `FrozenSnapshot` (deeply immutable) | Frozen value tuples + mode + full-64 fingerprint + as-of/basis + consent_state; read-only provenance source. | `tradingagents/runapi/context.py` | additive |
| `OutputChecker` | Deterministic Q1–Q4 on the checked **body**; assigns `output_check` + findings. Authoritative, non-LLM. | `tradingagents/runapi/checks.py` | additive |
| `OutcomeFinalizer` | Maps graph return/exceptions/attempted critical-persistence failure to `run_outcome` + `stop_reason`. | `tradingagents/runapi/finalize.py` | additive |
| `Redactor` | Central masking (keys/tokens/bearer, unsafe diagnostics) at every sink. | `tradingagents/runapi/redact.py` | additive |
| `EventSink` (JSONL) | Fixed-field structured events. | `tradingagents/runapi/events.py` | additive |
| Persistence/Manifest | Staging (report+manifest **critical**; terminal event **best-effort**) → single atomic directory commit; manifest via `SafeRunMetadata`; `terminal_event.durable` decided pre-commit without blocking publication. | `tradingagents/runapi/persist.py` | additive |
| Result schemas | `RunResult`, `CheckResult`, `Finding`, `InputError`, `SafeInputMetadata`, `SafeRunMetadata`, `EffectiveConfig`. | `tradingagents/runapi/result.py` | additive |
| CLI input UI | Interactive discovery/consent **only** here. | `cli/input_ui.py` | additive |
| CLI adapter | Thin wiring; adds `--without-portfolio`, `--portfolio-as-of`; suppresses prompts under flags. | `cli/main.py` | adapted |
| Prompt/context semantics | Mode-aware rating-scale legend; no-portfolio Hold meaning; user-supplied/unverified wording. | `tradingagents/agents/context.py`, manager/trader prompts | adapted |
| Reporting boundary | Renders checked **body** + trusted **envelope header** from `SafeRunMetadata`; stage labels. | `tradingagents/reporting.py`, `tradingagents/report_html.py` | adapted |
| Existing loader/model | `PortfolioContext`/`Position` validation and rendering; alias matching. | `tradingagents/portfolio.py` (preserved) | unchanged semantics |
| Raw engine primitive | `TradingAgentsGraph.propagate/stream_run/create_run_state` signature preserved; **does not** traverse the boundary (reduced scope, A approval for product use). | `tradingagents/graph/trading_graph.py` | signature preserved |

---

## 4. Advisory versus authoritative data

| Data | Nature | Authority |
|---|---|---|
| Model narrative, ratings text, recommendations | **Advisory** | Cannot set `output_check`/`run_outcome`/provenance |
| Final rating (Buy/Overweight/Hold/Underweight/Sell/REVIEW) | Derived deterministically from the PM output | Reported, but check Q1 only *reads* readability |
| Frozen snapshot metadata (mode, basename, fingerprint, as-of) | **Authoritative** (trusted state) | Built by input service; used by header/result/check |
| `output_check` (PASSED/NEEDS_REVIEW/NOT_RUN) + findings | **Authoritative** (deterministic) | `OutputChecker` only |
| `run_outcome` (COMPLETED/INCOMPLETE) + `stop_reason` | **Authoritative** (deterministic) | `OutcomeFinalizer` only |

The disclaimer and no-portfolio notice are **frozen strings** (selected-requirements §1) and are treated as trusted content, excluded from Q4 phrase scanning.

---

## 5. Workflow (selected C2)

1. **Discover** eligible `.json` files (non-recursive, sorted, symlinks excluded) from `PORTFOLIO_DIR` — or accept explicit `--portfolio PATH` (outside dir allowed; parent not scanned).
2. **Select** one file, or choose no-portfolio, or cancel.
3. **Validate/precheck** the frozen bytes; reuse upstream model validation after explicit shape/type/as-of prechecks. Empty positions is valid (flat); no silent fallback.
4. **Freeze** → `RunContext` (deeply immutable value tuples; full-64 canonical fingerprint; as-of/basis recorded). Consent state `FROZEN`.
5. **Notice** (portfolio mode; §6) then **confirm** → `CONFIRMED` (default No). Non-interactive: valid flags are the consent expression.
6. **Run** via the **shared execution service** (`runapi/execution.py`): rejects any `RunContext` not `CONFIRMED`. Holdings reach the provider **only after** confirmation.
7. **Render body → scrub → single check (Q1–Q4; Q2 inspects the pre-check provenance fragment against explicit trusted metadata) → finalize → build trusted envelope → stage report+manifest (critical) → one atomic directory commit; terminal JSONL append is best-effort.** Incomplete runs bypass the checker and get `NOT_RUN`. The checked body is delivered unchanged; the envelope adds only trusted metadata. Terminal-event durability is decided before the manifest is staged but does not block publication; a terminal-append failure preserves the logical outcome and records `durable=false`. (§ interface-contracts §6–§7).
8. Pre-run cancellation/rejection starts **no graph, zero LLM calls, no completed run**; a critical persistence failure yields a typed INCOMPLETE result that never contradicts a returned success.

Detailed state machine, schemas, canonicalization, ordering and failure simulations: `docs/architecture/interface-contracts.md`.

### 5.1 Synthetic input-mode walkthrough (document example, not a passing test)
- **Interactive, portfolio:** user sees `a.json`, `b.json`; selects `b.json`; precheck passes; freezes `b` (fingerprint Fb); notice shows basename `b.json`, date D, as-of basis, provider-transmission statement; user answers Yes → `CONFIRMED`; run transmits frozen `b` after consent; report header carries Fb and mode `PORTFOLIO_PROVIDED`.
- **Interactive, no portfolio:** empty directory → no-portfolio confirmation with frozen notice; Yes → `CONFIRMED` with `portfolio=None`; header shows `NO_PORTFOLIO`, null file/fingerprint/as-of.
- **Noninteractive:** `--portfolio b.json --portfolio-as-of D` → freezes b, consent via flags, no prompt. `--without-portfolio` → `NO_PORTFOLIO`. Neither/both → `InputError`, zero calls.
- **Cancelled:** user answers No at consent → zero graph/LLM, no completed run, counted as a pre-run attempt (NFR-006).

---

## 6. Permissions and consent

- Interactive discovery/selection/consent lives **only** in the CLI (`cli/`). Agents and the engine never prompt.
- **Consent gate** is an explicit coordinator transition between freeze and run. A frozen snapshot is a *candidate input*, **not** a confirmed selection; immutability alone does **not** prevent bypass. Only a coordinator transition to `CONFIRMED` permits run entry (see interface-contracts §4, ADR §Consent).
- Mandatory execution, exception mapping, checks and artifact finalization sit behind a **shared application boundary** (`tradingagents/runapi/execution.py: run_analysis_api`) usable without terminal prompts. The upstream Python API signature is **preserved**; the supported project API routes through `run_analysis_api` (full requirement coverage). A raw low-level engine primitive (`TradingAgentsGraph.propagate/stream_run`) remains available but **does not** traverse the boundary and **does not** satisfy FR-006/FR-007/NFR-002/003/004; its scope is declared and product reliance requires **A's approval** (residual risk R-API, pending A). See `docs/architecture/interface-contracts.md` §5.
- Coding-agent file permissions (separate concern) are in `docs/architecture/permission-model.md`; E implements enforcement.

---

## 7. Observability

- New lifecycle event sink: UTF-8 JSONL; fixed fields `run_id, ticker, node, ts(UTC), elapsed_ms, event, event_outcome`. Console stays human-readable. Raw provider payload logging disabled by default. Progress vocabulary is separate from terminal `run_outcome`.
- Existing sinks are adapted, not silently trusted: see memory-design §Sinks and runtime-policy-catalog.

---

## 8. Verification strategy (design-level only)

- **Testability seams** (for C): `PortfolioInputService` (discover/validate/freeze), `RunContext` identity, `OutputChecker` (Q1–Q4 with injected model claims), `OutcomeFinalizer` (typed exceptions), redaction at each sink, manifest atomicity, same-date isolation.
- **Observable positive/negative seams** are listed per requirement in `docs/architecture/traceability-inputs-member-b.md` for C. B does not write test code or claim results.
- **Document consistency checks** (this session) are **not** application verification.

---

## 9. Change policy

- ADRs required for safety-affecting changes (`GOV-006`); changes to provenance identity, check authority, redaction boundary or consent transitions require a new/updated ADR.
- Preserve upstream `tradingagents/`, `cli/`, `pyproject.toml` and tests unless an approved layout decision changes this.
- Intentional CLI/type-validation changes are documented in the ADR; they are not treated as accidental compatibility failures.
- Later architecture revisions based on real test evidence must cite that evidence (not manufactured now).

---

## 10. Requirement allocation summary

Full per-ID allocation (enforced-by component, fallback, other-owner/deferred) is in `docs/architecture/invariants.md` and `docs/architecture/traceability-inputs-member-b.md`. Summary:

- FR-001/002/003/004 → `PortfolioInputService` + `RunContext` + prompt semantics + coordinator consent.
- FR-005 → reporting stage labels; reuse `tradingagents/agents/rating.py` (REVIEW ≠ Hold).
- FR-006/FR-007 → provenance projection + `OutputChecker` (authoritative).
- NFR-001 → `runapi/finalize.py`; NFR-002 → `runapi/events.py`; NFR-003 → `runapi/redact.py`; NFR-004 → `runapi/persist.py` + fresh run ID; NFR-005 → `runapi/execution.py` shared service + preserved signature; NFR-006 → `RunRecord` accounting (interface-contracts §10).
- GOV-001..006 → allocated to C/E/A/human; B contributes permission model for `GOV-006`.

---

## 11. Provenance and limitations of this draft

- Alternatives and the human selection rationale: `docs/architecture/adr/001-portfolio-aware-cli.md`; scores and weights in `docs/architecture/evaluation-table.md`; process evidence in `docs/architecture/evaluation-logbook.md`.
- Unresolved decisions and pending evidence are recorded in `docs/architecture/risk-list.md` and the traceability handoff. No approvals, measurements or transcripts are invented here.
- This file is one of the approved B write set; `docs/architecture/architecture-blueprint.md` is a pointer to it.
