# Plan: Summary-First Workflow Refactor

**Status**: proposed
**Type**: PR summary + development plan
**Proposed Branch**: `codex/summary-first-workflow`
**Depends on**:
- `docs/graph_execution_reference.md`
- `docs/agent/context/FILTERING_AND_NODE_FEEDS.md`
- `agent_os/backend/services/langgraph_engine.py`

## PR Summary

This PR improves the current workflow without introducing a new memory layer.

The main problem is not the absence of storage. The main problem is that the
system already generates compact summaries in Phase 1, but the scanner-to-
analyst handoff largely ignores them and rebuilds Phase 2 context from raw
reports.

Today the flow is:

1. scanner agents produce raw reports
2. scanner summarizers compress them for Phase 1 fan-in
3. `macro_synthesis` consumes those compact summaries
4. Phase 2 then rebuilds `scanner_context_packet` mostly from raw reports
5. analyst prompts inherit that oversized packet

This PR changes that design.

New direction:

1. keep scanner summaries for Phase 1
2. stop building the Phase 2 packet from raw scanner reports
3. build the Phase 2 packet from:
   - `macro_scan_summary`
   - scanner summaries
   - compact structured ground-truth blocks
   - ticker-specific extracted rows only
4. simplify the later summary layer by removing redundant summary nodes
5. keep only the summary nodes that still have a clear fan-in or PM-facing role

This is a summary-first refactor, not a SQLite/memory PR.

## Why This PR Exists

The current code already has a compact summary layer in the scanner graph:

- `summarize_gatekeeper`
- `summarize_geopolitical`
- `summarize_market_movers`
- `summarize_sector`
- `summarize_factor_alignment`
- `summarize_drift`
- `summarize_smart_money`
- `summarize_industry_deep_dive`

Those summaries are actively used by:

- `industry_deep_dive`
- `macro_synthesis`

But they are not used properly for Phase 2 handoff.

Instead, `_build_scanner_context_packet()` in
`agent_os/backend/services/langgraph_engine.py` reconstructs a large packet
from raw scanner reports plus large earnings/economic calendar blocks.

That defeats the summary layer and reintroduces prompt bloat before the
analyst stage even starts.

## Goals

1. Reuse the scanner summaries we already compute.
2. Shrink the Phase 2 packet before it reaches analyst nodes.
3. Make each retained summary node have a clear, necessary purpose.
4. Remove summary nodes that are only weak glue or heuristic duplication.
5. Re-measure the workflow before deciding whether a dedicated memory layer is
   still necessary.

## Non-Goals

This PR does not:

- introduce SQLite or a new cache layer
- redesign the scanner graph topology
- rewrite every analyst prompt
- normalize all raw tool outputs into structured storage
- change portfolio decision policy

## Keep / Remove Decisions

### Keep and Improve

- `macro_synthesis`
- scanner `summarize_*` nodes
- `research_packet_summary`
- `risk_synthesis`
- `macro_summary`
- `micro_summary`

### Remove or Fold Into Upstream State

- `investment_debate_summary`
- `risk_debate_summary`

## What Changes In The Workflow

### Current scanner-to-analyst handoff

Phase 2 packet is built from:

- raw `smart_money_report`
- raw `factor_alignment_report`
- raw `drift_opportunities_report`
- raw `geopolitical_report`
- raw `sector_performance_report`
- fresh earnings/economic calendar dumps
- a small amount of structured content from `macro_scan_summary`

### Target scanner-to-analyst handoff

Phase 2 packet should be built from:

- `macro_scan_summary`
- `geopolitical_summary`
- `market_movers_summary`
- `sector_summary`
- `factor_alignment_summary`
- `drift_opportunities_summary`
- `smart_money_summary`
- `industry_deep_dive_summary` where useful
- compact structured blocks:
  - commodity snapshot
  - FX snapshot
  - filtered earnings rows
  - filtered economic events
- ticker-specific extracted rows only

## Proposed Phase 2 Packet Contract

The scanner-to-analyst handoff should be a fixed compact contract, not a
reconstructed blob.

Recommended sections:

1. `Selection Context`
   - ticker rationale
   - conviction
   - thesis angle
   - catalysts
   - risks

2. `Ground Truth`
   - commodity snapshot
   - FX snapshot
   - filtered earnings rows
   - filtered economic events

3. `Ticker-Relevant Scanner Signals`
   - smart money lines relevant to the ticker
   - factor alignment lines relevant to the ticker
   - drift lines relevant to the ticker

4. `Sector Context`
   - the ticker sector summary
   - optional one related spillover line

5. `Macro Themes`
   - top themes from `macro_scan_summary`

6. `Risk Factors`
   - top risk factors from `macro_scan_summary`

## Workstreams

## Workstream 1 — Refactor Phase 2 Packet Construction

Primary target:

- `agent_os/backend/services/langgraph_engine.py`

Changes:

- rewrite `_build_scanner_context_packet()`
- stop injecting raw scanner reports into Phase 2
- use summary fields wherever they already exist
- keep structured live data, but aggressively compact it
- extract ticker-specific lines from smart money, drift, and factor summaries

Acceptance:

- no raw scanner report sections copied directly into the Phase 2 packet
- packet sections are bounded and purpose-labeled
- packet length is materially smaller than current raw-based construction

## Workstream 2 — Keep Scanner Summaries, Tighten Their Contract

Primary targets:

- `tradingagents/agents/scanners/scanner_summarizer.py`
- `tradingagents/agents/scanners/macro_synthesis.py`

Changes:

- confirm each scanner summary is short and reusable
- bias summaries toward:
  - candidate rows
  - sector ranking
  - macro implication
  - dates and exact numbers
- avoid prose that only makes sense for human reading

Acceptance:

- Phase 1 summaries are directly reusable for Phase 2 handoff
- `macro_synthesis` quality does not regress

## Workstream 3 — Simplify Debate Summary Layer

Primary targets:

- `tradingagents/agents/managers/context_summaries.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- graph wiring in `tradingagents/graph/setup.py`

Changes:

- remove `investment_debate_summary`
- remove `risk_debate_summary`
- keep summary fields in state where needed
- make bull/bear nodes write compact structured round summaries directly
- keep `risk_synthesis` as the real post-debate consolidator

Acceptance:

- downstream manager nodes still receive the needed compressed debate context
- no fragile dependency on string splitting alone
- one true risk summary path remains

## Workstream 4 — Improve Research Packet Summary

Primary target:

- `tradingagents/agents/managers/context_summaries.py`

Changes:

- keep `research_packet_summary`
- make it summarize the new compact Phase 2 packet plus analyst outputs
- stop feeding it the oversized raw scanner packet

Acceptance:

- downstream bull/bear researchers read a compact packet
- `research_packet_summary` becomes meaningfully smaller and more stable

## Workstream 5 — Harden Portfolio Summary Nodes

Primary targets:

- `tradingagents/agents/portfolio/macro_summary_agent.py`
- `tradingagents/agents/portfolio/micro_summary_agent.py`
- `tradingagents/agents/portfolio/pm_decision_agent.py`

Changes:

- keep `macro_summary`
- keep `micro_summary`
- reduce arbitrary truncation where it removes useful evidence
- enforce more stable output shape
- ensure PM receives summary fields that are actually decision-useful

Acceptance:

- PM inputs are smaller but still sufficient
- summary outputs are more consistent across runs

## Workstream 6 — Measure Before Considering Memory

Primary targets:

- prompt logs
- run artifacts
- node-by-node wall time

Changes:

- compare prompt sizes before and after the summary-first refactor
- compare runtime for:
  - `market_analyst`
  - `news_analyst`
  - `fundamentals_analyst`
  - `research_packet_summary`
  - `macro_summary`
  - `micro_summary`

Acceptance:

- decide from measured evidence whether filtering alone is enough
- only then decide whether a memory layer is still required

## File-Level Scope

### Must Change

- `agent_os/backend/services/langgraph_engine.py`
- `tradingagents/agents/managers/context_summaries.py`
- `tradingagents/graph/setup.py`

### Likely Change

- `tradingagents/agents/scanners/scanner_summarizer.py`
- `tradingagents/agents/scanners/macro_synthesis.py`
- `tradingagents/agents/researchers/bull_researcher.py`
- `tradingagents/agents/researchers/bear_researcher.py`
- `tradingagents/agents/portfolio/macro_summary_agent.py`
- `tradingagents/agents/portfolio/micro_summary_agent.py`
- `tradingagents/agents/utils/summary_context.py`

### Should Not Change In This PR

- `tradingagents/memory/context_cache.py`
- `tradingagents/memory/news_evidence.py`
- persistence schema / storage backends

## Sequence

1. Refactor `_build_scanner_context_packet()`
2. Validate the new Phase 2 packet shape on one or two tickers
3. Remove `investment_debate_summary`
4. Remove `risk_debate_summary`
5. Improve `research_packet_summary`
6. Harden `macro_summary` and `micro_summary`
7. Measure prompt size and runtime deltas
8. Decide whether memory is still needed

## Verification

### Functional

- run one scan and inspect `macro_scan_summary`
- run one ticker pipeline and inspect the new `scanner_context_packet`
- confirm analyst prompts no longer depend on raw scanner reports in the
  handoff packet
- confirm debate and risk flow still function after summary-node removal

### Quality

- compare packet size before and after the refactor
- compare analyst prompt size before and after the refactor
- confirm no missing ticker rationale, themes, or risk sections

### Regression

- ensure `macro_synthesis` still produces valid structured scan summaries
- ensure `pm_decision` still receives usable `macro_brief` and `micro_brief`

## Expected Outcome

If this PR succeeds:

- Phase 1 summaries will finally be reused for Phase 2
- analyst prompts will shrink before any memory layer is introduced
- redundant summary nodes will be removed
- the remaining summary nodes will have clear ownership and purpose

After that, the team can make a cleaner decision on whether a storage-backed
memory layer is still necessary, and if so, how much of one is actually needed.
