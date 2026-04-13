# TradingAgents research provenance, node guards, and profiling harness

Status: draft
Audience: orchestrator, TradingAgents graph, verification
Scope: document the Phase 1-4 provenance fields, Bull/Bear/Manager guard behavior, trace schema, and the smallest safe A/B workflow for verification

## 1. Why this document exists

Phase 1-4 convergence added three closely related behaviors:

1. research-stage provenance is carried inside `investment_debate_state` and surfaced into application-facing metadata;
2. Bull Researcher, Bear Researcher, and Research Manager are guarded so timeouts/exceptions degrade gracefully without changing the default full-debate path;
3. `orchestrator/profile_stage_chain.py` can be used as a minimal A/B harness to compare prompt/profile variants while preserving the production path.

The implementation is intentionally conservative:

- **no structured memo output** is introduced;
- **default behavior remains the full debate path** when no guard trips;
- **existing debate string fields stay authoritative** (`history`, `bull_history`, `bear_history`, `current_response`, `judge_decision`).

## 2. Provenance schema and ownership

### 2.1 Canonical provenance fields

The research provenance fields currently carried in `investment_debate_state` are:

| Field | Meaning | Primary source |
| --- | --- | --- |
| `research_status` | Research health/status. Current in-repo values are `full` and `degraded`; `failed` is tolerated in surfaced diagnostics. | `tradingagents/graph/propagation.py`, `tradingagents/graph/setup.py`, `tradingagents/agents/utils/agent_states.py` |
| `research_mode` | Research execution mode. Normal path is `debate`; degraded path is `degraded_synthesis`. | same |
| `timed_out_nodes` | Ordered list of guarded research nodes that hit timeout. | `tradingagents/graph/setup.py` |
| `degraded_reason` | Machine-readable reason string such as `bull_researcher_timeout`. | `tradingagents/graph/setup.py` |
| `covered_dimensions` | Which debate dimensions completed successfully so far (`bull`, `bear`, `manager`). | `tradingagents/graph/setup.py` |
| `manager_confidence` | Optional confidence marker for the research-manager layer. `1.0` on clean manager success, `0.5` when manager succeeds after prior degradation, `0.0` on manager fallback. | `tradingagents/graph/setup.py` |

### 2.2 Initialization and propagation

- `tradingagents/graph/propagation.py` initializes the default path with:
  - `research_status = "full"`
  - `research_mode = "debate"`
  - `timed_out_nodes = []`
  - `degraded_reason = None`
  - `covered_dimensions = []`
  - `manager_confidence = None`
- `tradingagents/graph/setup.py::_apply_research_success()` extends `covered_dimensions` and preserves the default debate mode while the research status remains `full`.
- `tradingagents/graph/setup.py::_apply_research_fallback()` marks the state as degraded, records the reason, and updates only the existing debate fields instead of inventing a parallel memo structure.

## 3. Guard behavior by node

`GraphSetup._guard_research_node()` wraps each research node in a single-worker thread pool and enforces `research_node_timeout_secs`.

### 3.1 Bull / Bear researcher fallback

On timeout or exception for `Bull Researcher` or `Bear Researcher`:

- the corresponding node name is added to `timed_out_nodes` when the reason includes `timeout`;
- `research_status` becomes `degraded`;
- `research_mode` becomes `degraded_synthesis`;
- a plain-text degraded argument is appended to:
  - `history`
  - the node-specific history field (`bull_history` or `bear_history`)
  - `current_response`
- `count` is incremented so the debate routing still advances.

This keeps the **existing debate output shape** intact: downstream consumers continue reading the same string fields they already depend on.

### 3.2 Research Manager fallback

On timeout or exception for `Research Manager`:

- provenance is marked degraded using the same schema;
- `manager_confidence` is forced to `0.0`;
- `judge_decision`, `current_response`, and returned `investment_plan` are set to a plain-text HOLD recommendation that explicitly calls out degraded research.

This is intentionally **string-first**, not schema-first, so the downstream plan/report path does not have to learn a new memo envelope.

## 4. Application-facing surfacing

### 4.1 LLM runner metadata

`orchestrator/llm_runner.py` extracts the provenance subset from `investment_debate_state` and stores it under:

- `metadata.research`
- `metadata.data_quality`
- `metadata.sample_quality`

Current conventions:

- normal path: `data_quality.state = "ok"`, `sample_quality = "full_research"`;
- degraded path: `data_quality.state = "research_degraded"`, `sample_quality = "degraded_research"`.

### 4.2 Live-mode contract projection

`orchestrator/live_mode.py` forwards provenance under top-level `research` in live-mode payloads for both:

- `completed` / `degraded_success` results; and
- structured failures that carry research diagnostics in `source_diagnostics`.

This means consumers can inspect research degradation without parsing raw debate text.

## 5. Profiling trace schema

`orchestrator/profile_stage_chain.py` is the current timing/provenance trace tool.

### 5.1 Top-level payload

Successful runs write a JSON payload with:

- `status`
- `ticker`
- `date`
- `selected_analysts`
- `analysis_prompt_style`
- `node_timings`
- `phase_totals_seconds`
- `dump_path`
- `raw_events` (normally empty unless explicitly requested on failure)

Error payloads add:

- `run_id`
- `error`
- `exception_type`

### 5.2 `node_timings[]` entry schema

Each node timing entry currently contains:

| Field | Meaning |
| --- | --- |
| `run_id` | Correlates all rows from one profiling run |
| `nodes` | Node names emitted by the LangGraph update |
| `phases` | Normalized application phase names (`analyst`, `research`, `trading`, `risk`, `portfolio`) |
| `llm_kinds` | Normalized LLM bucket labels (`quick`, `deep`) |
| `start_at` / `end_at` | Relative offsets from run start, in seconds |
| `elapsed_ms` | Duration since the previous event |
| `selected_analysts` | Analyst slice used for the run |
| `analysis_prompt_style` | Prompt profile used for the run |
| `research_status` | Provenance snapshot extracted from `investment_debate_state` |
| `degraded_reason` | Provenance reason snapshot |
| `history_len` | Current debate history length |
| `response_len` | Current response length |

This schema is intentionally **trace-oriented**, not a replacement for the application result contract.

## 6. Minimal A/B harness guidance

Use `orchestrator/profile_stage_chain.py` when you want a small, explicit comparison harness without changing the production default path.

### 6.1 Safe comparison knobs

Run the harness from the repo root as a module (`python -m orchestrator.profile_stage_chain`) so package imports resolve without extra path tweaking.

The smallest useful A/B comparisons are:

- `--analysis-prompt-style` (for example `compact` vs another supported style)
- `--selected-analysts` (for example a narrower analyst slice vs a broader slice)
- provider/model/timeout settings while keeping the graph semantics fixed

### 6.2 Recommended invariants

Keep these fixed when doing an A/B comparison:

- the same `--ticker`
- the same `--date`
- the same provider/model unless the provider/model itself is the experimental variable
- the same `--overall-timeout`
- `max_debate_rounds = 1` and `max_risk_discuss_rounds = 1` as currently baked into the harness

### 6.3 Example commands

```bash
python -m orchestrator.profile_stage_chain \
  --ticker AAPL \
  --date 2026-04-11 \
  --selected-analysts market \
  --analysis-prompt-style compact

python -m orchestrator.profile_stage_chain \
  --ticker AAPL \
  --date 2026-04-11 \
  --selected-analysts market \
  --analysis-prompt-style detailed
```

Compare the generated JSON dumps by focusing on:

- `phase_totals_seconds`
- `node_timings[].elapsed_ms`
- provenance changes (`research_status`, `degraded_reason`)
- history/response growth (`history_len`, `response_len`)

## 7. Review guardrails

When modifying this area, keep these invariants intact unless a broader migration explicitly approves otherwise:

1. **Do not change the default path**: normal successful runs should still stay in `research_status = "full"` and `research_mode = "debate"`.
2. **Do not introduce structured memo output** for degraded research unless all downstream consumers are migrated together.
3. **Preserve debate output shape**: downstream readers still expect plain strings in `history`, `bull_history`, `bear_history`, `current_response`, `judge_decision`, and `investment_plan`.
4. **Keep provenance additive**: provenance fields should explain degraded behavior, not replace the existing textual debate artifacts.
