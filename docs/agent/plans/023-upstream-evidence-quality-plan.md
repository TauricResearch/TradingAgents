# 023 Upstream Evidence Quality Plan

## Purpose

This plan addresses the report-quality issues observed in the completed live auto run:

- run id: `01KNYA8AQ71JA85B2HQP1GR9V7`
- date: `2026-04-10`
- mode: `auto`
- constraints: `max_tickers=2`, `include_portfolio_holdings=false`

The workflow completed end-to-end and event propagation worked, but report quality was mixed. The strongest path was `NVDA`, which completed the full analyst, debate, risk, and portfolio sequence. `JPM` correctly entered the terminal critical-abort path. The weaker quality surfaced upstream in scanner and summary nodes where some reports contained planned tool calls, pending-data language, sparse summaries, or JSON-shaped tool intent text.

## Working Diagnosis

Model selection matters, but it is not the primary quality bottleneck.

The current evidence-quality problem has four distinct causes:

1. Tool-required nodes can produce text that describes an intended tool call instead of grounding the report in an observed tool result.
2. Summary nodes can compress sparse or placeholder upstream output into downstream-ready text without marking it as insufficient evidence.
3. Synthesis nodes can receive mixed-quality prose and treat it as equivalent evidence.
4. Some long-running pure reasoning nodes, especially `macro_synthesis`, can hold the auto workflow open longer than is useful unless they are bounded.

A stronger model may improve language quality, but it will not reliably fix missing evidence, failed tool invocation, or placeholder propagation. The system needs explicit evidence contracts and gates before model selection can have predictable impact.

## Quality Bar

A report section is high quality only if it satisfies all of these:

- grounded in actual observed data, not planned data collection
- contains exact dates, values, metrics, or source labels where available
- marks unavailable evidence explicitly instead of implying it exists
- avoids conversational filler and process text
- is machine-usable by downstream nodes
- preserves structured state alongside prose

The following phrases and shapes should be treated as quality failures in final upstream outputs:

- `I will call`
- `awaiting`
- `pending`
- `stand by`
- `no data provided`
- `scanner tool pending`
- `Completed.` as the only substantive output
- bare JSON tool arguments such as `{"topic": "...", "limit": 5}` when no `tool_result` is present

## Implementation Plan

### Phase 0: Stabilize Long-Running Synthesis

Status: partially implemented in this PR.

Scope:

- Bound `macro_synthesis` LLM invocation.
- Use deterministic fallback from scanner rankings when the model times out.
- Preserve `macro_scan_summary` output shape so downstream auto flow can continue.

Acceptance:

- `macro_synthesis` cannot hang indefinitely.
- Timeout fallback returns valid JSON.
- Fallback candidates are repaired through `_repair_macro_summary`.
- Existing idempotency and report persistence behavior is preserved.

Tests:

- Add a unit test with a sleeping fake LLM and a small timeout.
- Assert the node returns in bounded time.
- Assert returned JSON contains `stocks_to_investigate`.
- Assert `sender == "macro_synthesis"`.

### Phase 1: Add Upstream Report Quality Validator

Add a shared validator for scanner and summary outputs.

Proposed module:

- `tradingagents/agents/utils/report_quality.py`

Responsibilities:

- detect placeholder/process language
- detect bare tool-call JSON in final report text
- detect empty or extremely short outputs
- detect reports that contain no numeric evidence where numeric evidence is required
- return a structured result:

```json
{
  "status": "ok|warn|fail",
  "issues": ["placeholder_language", "missing_numeric_evidence"],
  "evidence_count": 3,
  "tool_result_count": 1
}
```

Acceptance:

- Validator is pure and deterministic.
- It does not call external services.
- It can be reused by scanner nodes, summaries, and tests.

Tests:

- `I will call get_market_indices` fails.
- `{"topic":"geopolitical risk","limit":5}` fails when treated as final report text.
- a numeric row with date/source passes.
- `Completed.` fails.

### Phase 2: Require Real Tool Results For Tool-Required Nodes

Scanner nodes that require tools should not pass if no tool result was actually observed.

Target nodes:

- `gatekeeper_scanner`
- `geopolitical_scanner`
- `market_movers_scanner`
- `sector_scanner`
- `factor_alignment_scanner`
- `drift_scanner`
- `smart_money_scanner`
- `fundamentals_analyst`

Rule:

- If the node requires tools, at least one real tool result must be present.
- If the first model response only describes a tool call, retry once with explicit correction.
- If the retry still has no tool result, emit a structured unavailable report instead of prose.

Unavailable report shape:

```json
{
  "status": "insufficient_evidence",
  "node": "market_movers_scanner",
  "reason": "required_tool_result_missing",
  "required_tools": ["get_market_indices"],
  "tools_called": [],
  "usable_evidence": []
}
```

Acceptance:

- Tool-required nodes cannot save planned tool calls as evidence.
- Downstream nodes can distinguish unavailable evidence from weak prose.
- Existing live observability still records node start/end and tool events.

Tests:

- Mock LLM returns tool-call-shaped text, no tool result: node retries.
- Retry still fails: node emits `insufficient_evidence`.
- Real tool result: node passes and saves report.

### Phase 3: Introduce Evidence Packets

Every upstream scanner node should output a structured evidence packet alongside prose.

Suggested state fields:

- `gatekeeper_evidence_packet`
- `geopolitical_evidence_packet`
- `market_movers_evidence_packet`
- `sector_evidence_packet`
- `factor_alignment_evidence_packet`
- `drift_evidence_packet`
- `smart_money_evidence_packet`
- `industry_deep_dive_evidence_packet`

Evidence packet schema:

```json
{
  "status": "ok|insufficient_evidence|error",
  "as_of_date": "2026-04-10",
  "node": "market_movers_scanner",
  "tools_called": ["get_market_indices"],
  "evidence_rows": [
    {
      "source": "get_market_indices",
      "retrieved_at": "2026-04-11T15:05:22Z",
      "data_date": "2026-04-10",
      "scope": "index",
      "identifier": "SPX",
      "metric": "daily_change",
      "value": "+0.75%"
    }
  ],
  "gaps": [],
  "quality_issues": []
}
```

Acceptance:

- Evidence packets are JSON-serializable.
- Packets are persisted in scan artifacts or report JSON.
- `macro_synthesis` can rank from packets before reading prose.
- Missing evidence is explicit.

Tests:

- Packets survive report-store serialization.
- Packets with unavailable status do not produce ticker candidates.
- Packets with numeric ticker evidence contribute to candidate ranking.

### Phase 4: Make Summaries Evidence-Aware

Summary nodes should summarize evidence packets first and prose second.

Rule:

- If upstream packet status is `insufficient_evidence`, summary must preserve that status.
- Summary must not invent candidate rows from placeholder input.
- Summary output should contain a compact `Unavailable Evidence` line when needed.

Acceptance:

- No summary converts missing upstream data into actionable thesis text.
- Placeholder language is filtered or triggers fallback.
- Summary text stays concise and machine-usable.

Tests:

- Empty upstream packet yields unavailable summary.
- Numeric upstream packet yields exact value preservation.
- Placeholder upstream prose fails validation.

### Phase 5: Harden Macro Synthesis Candidate Ranking

Move ticker selection toward deterministic evidence-first ranking.

Current behavior already uses deterministic rankings from prose. Improve it to:

- prefer structured evidence packets
- require candidate ticker support from at least one usable evidence row
- track support count and source nodes
- exclude unavailable packet sources
- enforce `max_tickers`

Acceptance:

- `max_tickers=2` always yields at most two candidates.
- Candidate JSON includes source support metadata.
- A ticker is not selected solely because it appears in placeholder prose.

Tests:

- More than two candidates are truncated deterministically.
- Placeholder-only ticker mention is ignored.
- Evidence-backed ticker survives.

### Phase 6: Model Selection Policy

Use model upgrades selectively after evidence gates exist.

Recommended policy:

- scanner/tool nodes: use the most reliable tool-calling model available, not necessarily the strongest reasoning model
- summaries: use cheap/fast model after validation
- `macro_synthesis`: use stronger reasoning model with bounded timeout and deterministic fallback
- `Research Manager`, `Risk Synthesis`, `Portfolio Manager`: use stronger reasoning model
- final report polishing: optional, only after evidence contracts pass

Acceptance:

- Model policy is documented in config docs.
- Tool-required nodes are not assigned models known to emit tool-call text without calling tools.
- Stronger models are reserved for synthesis and final decisions.

Validation:

- Repeat the `2026-04-10` auto run with `max_tickers=2`, no holdings.
- Compare weak-output counts before and after model policy changes.

### Phase 7: Live Quality Audit Command

Add a local audit script for run artifacts.

Suggested command:

```bash
uv run python scripts/audit_run_quality.py \
  --run-id 01KNYA8AQ71JA85B2HQP1GR9V7 \
  --date 2026-04-10
```

Checks:

- run completed
- required artifacts exist
- `run_events.jsonl` contains tool events where expected
- no final upstream report contains placeholder/process language
- ticker count matches `max_tickers`
- incomplete ticker analyses are excluded from portfolio stage
- final PM decision cites only completed ticker analyses

Acceptance:

- Returns non-zero on quality failures.
- Emits a concise JSON summary usable in CI or manual diagnostics.

## Suggested Test Matrix

Unit:

```bash
pytest \
  tests/unit/test_report_quality.py \
  tests/unit/agents/test_macro_synthesis.py \
  tests/unit/test_scanner_context_packet_summary_first.py \
  -q
```

Regression:

```bash
pytest \
  tests/unit/test_langgraph_engine_run_modes.py \
  tests/unit/agents/test_analyst_agents.py \
  tests/unit/test_output_validation.py \
  tests/unit/test_ground_truth_propagation.py \
  -q
```

Live smoke:

```bash
python - <<'PY'
import requests
payload = {
  "date": "2026-04-10",
  "portfolio_id": "main_portfolio",
  "max_tickers": 2,
  "include_portfolio_holdings": False,
}
r = requests.post("http://localhost:8088/api/run/auto", json=payload, timeout=30)
print(r.status_code, r.text)
PY
```

## Exit Criteria

This work is complete when:

- upstream nodes never save planned tool calls as evidence
- unavailable evidence is explicit and structured
- summary nodes preserve insufficient-evidence status
- `macro_synthesis` cannot stall the auto workflow indefinitely
- auto runs with `max_tickers=2` and no holdings complete consistently
- final portfolio decisions only use completed ticker analyses
- a quality audit command can flag weak artifacts before a report is trusted

