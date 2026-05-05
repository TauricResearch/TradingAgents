# TradingAgents Methodology Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the shadow pipeline from a narrative-first trading demo into a run-scoped, source-cited, quantitatively scored advisory system that Flint can trust as evidence rather than opinion.

**Architecture:** Keep TradingAgents as an advisory sidecar, but split the workflow into four hard layers: evidence capture, claim/skill extraction, deterministic scoring, and final judgement. The model may explain and reconcile, but it should not invent unsupported facts or skip the source chain. Hidden chain-of-thought is not a stored artifact; only structured rationales, claim summaries, citations, and audit metadata should persist.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, Postgres, LangGraph/LangChain callbacks, OpenTelemetry/Langfuse-compatible traces, local artifact storage under `output/`, current TradingAgents graph/runtime, pytest.

---

## Baseline Findings

The latest live runs and repo inspection show the methodology gap clearly:

- Final decisions can still invalidate on missing citations even when the upstream graph produced source objects and raw tool outputs.
- Ticker/date scoping is not yet enough to guarantee a sound recommendation when the market date is a non-trading day or the news layer drifts to unrelated issuers.
- The deterministic scorecard is still a keyword scaffold, not a proper factor model.
- The service has useful artifacts, but they are not yet fully run-scoped, token-accounted, or judge-ready.
- The current community signal says this is credible as a research/shadow-analysis tool, not as an autonomous trading engine.

This plan closes that gap in layers instead of trying to “prompt harder.”

## Definition Of Done

The work is done when all of these are true:

- Every final recommendation cites structured source IDs and any raw-tool IDs it relies on.
- Every run stores telemetry for prompts, tool calls, latency, token counts, and artifact hashes under a unique `run_id`.
- Every recommendation includes target profile context: investor type, horizon, benchmark, risk appetite, and exposure constraints.
- Every scorecard uses deterministic quantitative inputs, not only keyword matches.
- Every run has a judge result that distinguishes evidence quality, scope validity, scorecard reconciliation, and decision readiness.
- Every analyst report and final decision explains source counts, freshness, and source trust.
- Every evaluation can be replayed from stored telemetry and artifacts without depending on hidden model reasoning.

---

### Task 1: Research The Methodology Gap And Write The Policy Memo

**Files:**
- Create: `docs/flint/METHODOLOGY_RESEARCH_MEMO_2026-05-05.md`
- Create: `docs/flint/METHODOLOGY_GAP_BACKLOG_2026-05-05.md`
- Modify: `docs/flint/FORENSIC_RECOMMENDATION_METHODOLOGY_2026-05-01.md`
- Modify: `docs/flint/SHADOW_OBSERVABILITY_EVALUATION_LAYER.md`

- [ ] **Step 1: Re-run the live research scans and capture the evidence**

Run:

```bash
cd /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow
cd /Users/sydneymilton/.hermes/skills/research/last30days && \
python3.14 scripts/last30days.py \
  "LLM trading agents observability evaluation provenance citations token telemetry risk metrics" \
  "quant trader skepticism LLM signal engine backtest reproducibility model drift" \
  --days 30 --depth quick --emit md \
  --save-dir /Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow/tmp \
  --save-suffix methodology_gap
```

Expected: saved markdown briefing in `tmp/` plus a source-ranked summary of current observability, quant skepticism, and failure-mode evidence.

- [ ] **Step 2: Convert the evidence into a method policy**

Write the memo so it answers:

1. What is a fact, a claim, a score, and a judgement?
2. Which source classes are allowed to drive a recommendation?
3. Which model outputs are advisory prose only and not evidence?
4. Which target profiles can consume the recommendation?
5. Which failure modes should hard-fail the run?

The memo must explicitly state that hidden chain-of-thought is not persisted. Store structured rationale, not private reasoning traces.

- [ ] **Step 3: Add the backlog of unresolved methodology questions**

Backlog items must include:

1. Which news providers are trusted and why.
2. How many sources are required before a bullish or bearish statement is allowed.
3. What counts as stale market data on a weekend or holiday trade date.
4. What macro features are mandatory before a buy recommendation can be called robust.
5. Which judge outputs block Flint ingestion automatically.

- [ ] **Step 4: Verify the memo against current repo behavior**

Run:

```bash
pytest tests/test_quality_assessment.py tests/test_evaluation_observability.py -q
```

Expected: tests still reflect the current gap, and the memo references the failing behaviors directly instead of hand-waving them away.

---

### Task 2: Add Run-Scoped Evidence, Prompt, And Token Telemetry

**Files:**
- Create: `tradingagents_service/telemetry.py`
- Create: `tradingagents_service/llm_traces.py`
- Modify: `tradingagents_service/provenance.py`
- Modify: `tradingagents_service/trace.py`
- Modify: `tradingagents_service/db/models.py`
- Modify: `tradingagents_service/db/repository.py`
- Modify: `tradingagents_service/runner/shadow_job.py`
- Modify: `tradingagents_service/worker/loop.py`
- Modify: `tests/test_tool_provenance.py`
- Modify: `tests/test_trace_dashboard.py`
- Modify: `tests/test_service_contract.py`

- [ ] **Step 1: Define the telemetry schema**

Persist, per run and per stage:

1. `run_id`
2. `node_name`
3. `prompt_hash`
4. `response_hash`
5. `tool_name`
6. `tool_args_hash`
7. `latency_ms`
8. `token_input`
9. `token_output`
10. `token_total`
11. `provider`
12. `model`
13. `artifact_uri`
14. `artifact_sha256`

Store the raw payloads as run-scoped artifacts and keep a DB pointer to each artifact.

- [ ] **Step 2: Move provenance output off ticker/date-only paths**

Any artifact path keyed only by `ticker/trade_date` must gain `run_id` scoping. Keep ticker/date for human lookup, but do not use them as the only isolation boundary.

- [ ] **Step 3: Capture the prompt and tool trace**

Emit a structured trace record for every LLM call and every tool call. If Langfuse is configured, export to it; otherwise keep the same record format locally so the trace viewer stays stable.

- [ ] **Step 4: Add tests for isolation and replay**

Write tests that prove:

1. Two runs for the same ticker/date do not overwrite each other.
2. A replay can reconstruct the run from stored artifacts and telemetry.
3. Token counts and hashes are present in the trace payload.

Run:

```bash
pytest tests/test_tool_provenance.py tests/test_trace_dashboard.py tests/test_service_contract.py -q
```

Expected: all telemetry fields are present in the API responses and stored artifacts.

---

### Task 3: Replace Ad Hoc Narrative Synthesis With Skills And Claim Graphs

**Files:**
- Create: `tradingagents/agents/skills/__init__.py`
- Create: `tradingagents/agents/skills/market_qa.py`
- Create: `tradingagents/agents/skills/entity_resolution.py`
- Create: `tradingagents/agents/skills/source_triage.py`
- Create: `tradingagents/agents/skills/claim_extraction.py`
- Create: `tradingagents/agents/skills/macro_regime.py`
- Create: `tradingagents/agents/skills/risk_policy.py`
- Create: `tradingagents/agents/skills/judge.py`
- Create: `tradingagents/agents/claims.py`
- Create: `tradingagents/agents/source_registry.py`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`
- Modify: `tradingagents/agents/utils/recommendation_audit.py`
- Modify: `tradingagents/agents/utils/agent_states.py`
- Modify: `tradingagents_service/recommendation_contract.py`
- Modify: `tests/test_recommendation_contract.py`
- Modify: `tests/test_structured_agents.py`

- [ ] **Step 1: Define the skill registry**

The skill registry must separate concerns:

1. Market QA: validate price data freshness and market calendar status.
2. Entity resolution: decide whether a report is truly about the requested issuer.
3. Source triage: rank source quality and trust.
4. Claim extraction: turn prose into citeable claims.
5. Macro regime: summarize rates, volatility, breadth, and sector context.
6. Risk policy: state what risk posture the recommendation assumes.
7. Judge: assess whether the evidence chain is adequate.

- [ ] **Step 2: Replace hidden reasoning with claim summaries**

The portfolio manager should no longer rely on free-form “because it sounds right” synthesis. It should assemble a claim graph of:

1. claim text
2. supporting source IDs
3. counterevidence IDs
4. confidence
5. timestamp / as-of date
6. scope status

Only those claims may flow into the final decision.

- [ ] **Step 3: Require target-profile context before the final synthesis**

Add fields to the recommendation contract for:

1. intended user type
2. strategy horizon
3. benchmark
4. risk appetite
5. exposure limit
6. position sizing policy

The final decision must say who the recommendation is for and why it fits that profile.

- [ ] **Step 4: Test that unsupported prose can no longer pass as evidence**

Run:

```bash
pytest tests/test_recommendation_contract.py tests/test_structured_agents.py -q
```

Expected: a final recommendation without citeable claims fails fast.

---

### Task 4: Build A Deterministic Scoring Layer And A Judge Layer

**Files:**
- Create: `tradingagents/agents/utils/factor_model.py`
- Create: `tradingagents_service/judging.py`
- Modify: `tradingagents/agents/utils/recommendation_audit.py`
- Modify: `tradingagents_service/evaluations.py`
- Modify: `tradingagents_service/quality.py`
- Modify: `tests/test_signal_processing.py`
- Modify: `tests/test_quality_assessment.py`
- Modify: `tests/test_evaluation_observability.py`

- [ ] **Step 1: Replace keyword scoring with factor scoring**

The scorecard must compute at least these factors:

1. technical trend
2. momentum
3. volatility
4. news sentiment
5. fundamentals
6. risk posture
7. macro regime adjustment

Each factor should expose its inputs, weight, and reason for the score.

- [ ] **Step 2: Make the judge read the scorecard and the traces**

The judge layer should score:

1. evidence traceability
2. entity/ticker scope
3. scorecard reconciliation
4. decision readiness

It should reject a run when the final decision diverges from the scorecard without an explicit reconciliation.

- [ ] **Step 3: Add metrics for calibration**

Track per run:

1. scorecard vs final rating agreement
2. judge label
3. failed citation count
4. missing source count
5. unsupported claim count
6. token usage by stage
7. latency by stage

These metrics are the basis for later frontier-model calibration.

- [ ] **Step 4: Make the failure modes hard and visible**

If a run has no citeable evidence, no target profile, or no scorecard reconciliation, it should be labeled `insufficient_evidence` or `failed`, not silently allowed through.

Run:

```bash
pytest tests/test_signal_processing.py tests/test_quality_assessment.py tests/test_evaluation_observability.py -q
```

Expected: the heuristic gate becomes a real, measured judge instead of a loose postscript.

---

### Task 5: Define Market Data, News Source Policy, And Macro Context

**Files:**
- Modify: `tradingagents/dataflows/interface.py`
- Modify: `tradingagents/dataflows/y_finance.py`
- Modify: `tradingagents/dataflows/yfinance_news.py`
- Modify: `tradingagents/dataflows/stockstats_utils.py`
- Create: `tradingagents/dataflows/source_policy.py`
- Create: `docs/flint/SOURCE_POLICY_AND_MACRO_CONTEXT_2026-05-05.md`
- Modify: `docs/flint/FORENSIC_RECOMMENDATION_METHODOLOGY_2026-05-01.md`
- Modify: `tests/test_signal_processing.py`

- [ ] **Step 1: Write the source policy**

Document:

1. which news sources count as primary
2. how many sources are required per claim class
3. freshness windows per source type
4. how entity matching is done
5. what makes a source too broad to support a company-specific claim

- [ ] **Step 2: Make the market calendar explicit**

Weekend or holiday dates must not be treated as real market sessions. If the user requests a non-trading day, the system must say whether it is using:

1. the prior session
2. the next session
3. a stale snapshot

and the final decision must say so in plain language.

- [ ] **Step 3: Add macro regime features**

At minimum, the macro layer should capture:

1. index and sector context
2. rates / yield pressure
3. volatility regime
4. peer comparison
5. event lag and ripple effects
6. earnings-calendar pressure

This is where the system stops being a one-stock story generator and starts acting like a financial analyst.

- [ ] **Step 4: Test source counts and contamination**

Run:

```bash
pytest tests/test_signal_processing.py tests/test_ticker_validation_service.py -q
```

Expected: unrelated issuers and low-quality broad news cannot silently pass as issuer evidence.

---

### Task 6: Make Recommendation Output Fit A Real User And A Real Portfolio Policy

**Files:**
- Modify: `tradingagents_service/schemas/shadow_runs.py`
- Modify: `tradingagents_service/api/routes/shadow_runs.py`
- Modify: `tradingagents_service/reporting.py`
- Modify: `tradingagents_service/schemas/reports.py`
- Modify: `docs/flint/SHADOW_USERLAND_FEATURE_PRD.md`
- Create: `docs/flint/DECISION_POLICY_AND_TARGET_PROFILE_2026-05-05.md`
- Modify: `tradingagents/agents/managers/portfolio_manager.py`

- [ ] **Step 1: Add target-profile fields to the API**

The create-run request should be able to carry:

1. target user type
2. strategy style
3. horizon
4. benchmark
5. risk appetite
6. max exposure
7. sizing rule

Without this, a `Buy` or `Overweight` label is context-free and commercially weak.

- [ ] **Step 2: Make the final report explain the audience**

The final decision should answer:

1. who this is for
2. why this recommendation fits that profile
3. what risks would invalidate it
4. what evidence was strongest
5. what evidence was missing

- [ ] **Step 3: Keep Flint handoff payloads explicit**

The handoff artifact must include:

1. run_id
2. ticker
3. trade_date
4. final rating
5. decision markdown
6. model/provider metadata
7. artifact manifest
8. source summary
9. judge result
10. target profile

- [ ] **Step 4: Validate the userland product shape**

Run:

```bash
pytest tests/test_reports.py tests/test_service_contract.py -q
```

Expected: the report and handoff surfaces stay aligned with the PRD and do not hide failed or low-confidence outputs.

---

### Task 7: Verify The New Methodology And Roll It Out Safely

**Files:**
- Modify: `docs/flint/CRITICAL_WORKFLOW_EVALUATION_2026-05-01.md`
- Modify: `docs/flint/WORK_PERFORMED_IO_ANALYSIS_REPORT_2026-05-01.md`
- Modify: `docs/flint/REAL_SEARCH_EXAMPLES_END_TO_END_REPORT_2026-05-01.md`
- Modify: `tests/test_service_contract.py`
- Modify: `tests/test_worker_loop.py`
- Modify: `tests/test_trace_dashboard.py`

- [ ] **Step 1: Run the full method-focused test set**

Run:

```bash
pytest tests/test_tool_provenance.py tests/test_trace_dashboard.py tests/test_recommendation_contract.py tests/test_quality_assessment.py tests/test_evaluation_observability.py tests/test_signal_processing.py -q
```

Expected: the methodology checks now fail for missing evidence, bad scope, weak scorecard reconciliation, and missing telemetry, instead of letting those problems drift into production.

- [ ] **Step 2: Re-run the live three-stock smoke test**

Use three distinct stocks and compare the outputs end to end. The test is only useful if it exposes the new evidence chain, the scorecard, the judge result, and the target profile clearly for each run.

- [ ] **Step 3: Confirm the old failure modes are gone**

The plan is not finished until:

1. run-scoped artifacts stop colliding,
2. non-trading-day handling is explicit,
3. unsupported prose is blocked,
4. token and telemetry data are visible,
5. the final recommendation is explained in investor terms.

---

## Research Questions Still Open

These should remain open until the research memo resolves them:

1. What minimum source set is enough to support a company-specific buy case?
2. Which macro signals should be mandatory for different strategy horizons?
3. Which parts of the pipeline should remain deterministic and which can stay LLM-mediated?
4. Which judge outputs are good enough for Flint ingestion without human review?
5. Which external data vendors have licensing terms that are commercially usable here?

## Implementation Order

1. Research memo and policy.
2. Run-scoped telemetry and evidence storage.
3. Skills and claim graph.
4. Deterministic scoring and judge.
5. Market/news/macro policy.
6. Target profile and handoff payloads.
7. Verification and rollout.

