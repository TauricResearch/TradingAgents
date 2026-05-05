# Critical Workflow Evaluation: TradingAgents Flint Shadow

Date: 2026-05-01  
Repo: `/Users/sydneymilton/dev/_sandbox/tradingagents-flint-shadow`

## Summary Judgment

The workflow is doing real operational work: it accepts API requests, queues
jobs, invokes the TradingAgents graph, writes lifecycle state, persists
decisions, and records artifact manifests.

However, the current evidence does not prove high-quality financial analysis.
It proves that an advisory multi-agent pipeline can run and produce auditable
outputs. The analysis content itself shows material quality issues: weak source
grounding, hallucinated or cross-contaminated entities, coarse event telemetry,
and insufficient traceability from final claims back to raw market/news inputs.

This should be treated as a shadow comparator and workflow prototype, not as a
decision-grade research engine.

## What Work Is Actually Being Done

### 1. Request intake and validation

The API accepts structured inputs:

- `ticker`
- `trade_date`
- `selected_analysts`
- optional provider/model fields

The request is persisted in Postgres and receives a stable `run_id`.

Actual value: good control-plane behavior.  
Current limitation: validation proves shape, not semantic correctness of the
market request or source availability.

### 2. Queue and worker orchestration

The worker claims queued jobs and runs `run_shadow_job(...)`, which builds a
TradingAgents config and calls:

```python
TradingAgentsGraph(...).propagate(ticker, trade_date)
```

Actual value: real async execution and durable status transitions.  
Current limitation: worker telemetry is too coarse. Events generally show
`running` and `succeeded/failed`; they do not expose each analyst/tool stage,
source fetch result, retry, or model call as first-class events.

### 3. Agentic graph execution

TradingAgents decomposes work across analyst roles and final synthesis roles.
The observed logs show structured-output retries:

- Research Manager structured-output failure -> free-text retry
- Trader structured-output failure -> free-text retry
- Portfolio Manager structured-output failure -> free-text retry

Actual value: there is real multi-stage orchestration and fallback behavior.  
Current limitation: fallback hides schema failure. A run can succeed while
important intermediate structured contracts failed.

### 4. Output persistence

The system persists:

- status
- event timeline
- final rating
- final decision markdown
- provider/model metadata
- artifact manifests with SHA-256 and byte count

Actual value: strong enough for run receipt and audit trail.  
Current limitation: the manifest proves files existed and were hashed; it does
not prove the final reasoning is source-grounded or financially valid.

## Evidence From Real Runs

### AAPL

- `run_id`: `0cc06896-e041-47cc-9824-387237df4e0f`
- `status`: `succeeded`
- `final_rating`: `Buy`
- provider/model: `ollama`, `llama3.2:latest`

Critical content issue:

The final AAPL decision contains entity contamination and likely hallucination:

- refers to `Marvell Technology Group Ltd. (AAPL)`;
- introduces `Avalyn Pharma Inc. (AVLN)` as if relevant to AAPL;
- recommends exposure to unrelated names and ETFs;
- cites vague signals and endorsements without attached evidence.

Interpretation: the workflow completed, but the output is not reliable as a
clean AAPL investment analysis.

### NVDA

- `run_id`: `f4edc7b4-95f8-448b-90dc-d9e0f98919e7`
- `status`: `succeeded`
- `final_rating`: `Hold`
- provider/model: `ollama`, `llama3.2:latest`

Critical content issue:

The final decision is coherent at a surface level but includes unsupported
claims, such as supply-chain concerns and a target price, without inline source
evidence or a source-to-claim trace.

Interpretation: more plausible than the AAPL output, but still not
decision-grade without citations and source linkage.

### Failure Path

- `run_id`: `23e617d3-d2a6-4e82-955a-44c5d044b2d2`
- `status`: `failed`
- `error_message`: `Connection error.`

Interpretation: failure capture works. This is important operationally because
bad provider/runtime connectivity does not silently vanish.

### MSFT

- `run_id`: `726acf0f-7705-43c8-9111-833e68e2f970`
- `status`: `succeeded`
- observed behavior: higher latency and structured-output fallback logs.

Interpretation: the graph can complete under fallback, but latency and schema
fragility need hardening before production-style use.

## What The Workflow Proves

The current workflow proves:

1. API-driven shadow runs are feasible.
2. Jobs can be queued and processed asynchronously.
3. TradingAgents can be invoked inside the worker.
4. Results can be normalized for downstream Flint ingestion.
5. Artifacts can be hashed and listed.
6. Failures and successes are visible through API and DB records.

## What The Workflow Does Not Yet Prove

The current workflow does not prove:

1. The analysis is factually correct.
2. The final recommendation is source-grounded.
3. The tool can reliably distinguish ticker-specific evidence from unrelated
   entity contamination.
4. The model output is stable across repeated runs.
5. The analyst roles are producing usable intermediate research.
6. The data vendor fetches are complete, timely, or captured with enough
   provenance.
7. The worker can run at scale without DB connection pressure.

## Key Risks

### Analytical quality risk

The AAPL example is the strongest warning sign. A successful run produced a
decision that confused Apple with Marvell and mixed in unrelated assets.

Impact: a downstream consumer could treat an auditable artifact as credible
because the service envelope looks robust.

### Source-grounding risk

The final outputs do not include claim-level citations or raw source excerpts.
The artifact JSON may contain intermediate state, but the service does not yet
promote source evidence into the decision response.

Impact: human review must inspect raw state logs manually, which weakens Flint
handoff quality.

### Observability risk

The event stream is too thin. It records lifecycle state, not the actual
analyst/tool/model stages.

Impact: debugging bad analysis requires log spelunking rather than structured
inspection.

### Reliability risk

DB saturation (`too many clients already`) was observed after repeated runs.

Impact: current worker/session design is not ready for parallel or hosted load
without pooling limits and cleanup.

## Recommended Next Work

1. Add stage-level events:
   - analyst started/completed
   - source fetch started/completed
   - structured parse failed
   - fallback used
   - final synthesis started/completed

2. Add source evidence objects:
   - source type
   - source URI/vendor
   - fetched timestamp
   - ticker/date scope
   - extracted facts
   - claim links in final decision

3. Add quality gates before `succeeded`:
   - ticker mismatch detection
   - unrelated entity detection
   - missing citation detection
   - empty/low-confidence source fetch detection

4. Separate execution success from analysis quality:
   - `status=succeeded`
   - `quality_status=passed|warning|failed`
   - `quality_findings=[...]`

5. Harden worker/Postgres behavior:
   - reuse session factory/engine
   - set pool size and max overflow
   - add retry/backoff for DB operational errors
   - add worker heartbeat

6. Add a grounded evaluation suite:
   - run fixed tickers/dates
   - assert ticker consistency
   - inspect final output for unrelated entities
   - compare against expected source availability

## Bottom Line

The actual work being done is valuable orchestration and evidence capture. It is
not yet reliable financial interpretation.

The service should be described as:

> A working async shadow-analysis harness around TradingAgents that produces
> auditable advisory artifacts, with current analytical outputs requiring
> strict human review and additional quality gates before Flint ingestion.

