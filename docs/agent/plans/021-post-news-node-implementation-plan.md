# 021 Post-News Node Implementation Plan

## Purpose

This plan defines the remaining structured-contract and hallucination-hardening work after the news node fix.

Scope starts from the current state:

- news prompt rigidity has been reduced
- news fact-checking can preserve valid partial output
- terminal tooling now exists for node-by-node live validation

The remaining work is to remove the next highest-probability prose drift and state ownership failures in top-down graph order.

Use together with:

- [019 Structured Contracts Implementation Checklist](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/019-structured-contracts-implementation-checklist.md)
- [020 Structured Contracts Revised Plan](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/020-structured-contracts-revised-plan.md)
- [Node-by-Node Terminal Testing Guide](/Users/Ahmet/Repo/TradingAgents/docs/testing/node-by-node-terminal-guide.md)
- [run_node_live.py](/Users/Ahmet/Repo/TradingAgents/scripts/run_node_live.py)

## Current Boundary

Completed enough to move forward:

- news node hardening
- evidence-driven source validation for news
- terminal runner for live node monitoring

Still unresolved:

- market node still mixes prose output with inferred machine state
- analyst completion/empty/abort status is not uniformly explicit
- research packet still has prose-first risk
- PM/trader/research-manager ownership and handoff contracts remain weak
- debate and risk nodes still rewrite upstream prose instead of selecting canonical claims
- optional raw-context experiment should not begin until the above path is stable

## Execution Rule

Move strictly from upstream to downstream.

For each node or contract boundary:

1. change the contract
2. add or update deterministic validation
3. run targeted unit tests
4. run one live scoped node test from terminal
5. inspect artifacts before moving on

Do not start raw-context expansion while downstream consumers still depend on prose summaries.

## Phase 1: Market Node Stabilization

### Goal

Remove the next largest upstream hallucination surface after news.

### Work

- stop heuristic fallback that sets macro regime from full report prose
- add `market_report_structured` as the canonical machine output
- keep `market_report` as rendered presentation
- include explicit `status`, `contract_version`, `macro_regime`, `key_levels`, and compact metrics
- make missing regime explicit instead of inferred

### Files

- [market_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/market_analyst.py)
- [output_validation.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py)
- [test_analyst_agents.py](/Users/Ahmet/Repo/TradingAgents/tests/unit/agents/test_analyst_agents.py)

### Acceptance

- no prose-derived macro regime fallback remains
- market node can emit a valid partial structured payload
- markdown is reproducible from structured output

### Live test

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market \
  --show-system \
  --watch-nodes "Market Analyst,__system__"
```

## Phase 2: Analyst Status Contract

### Goal

Make missing output explicit so downstream nodes stop guessing from empty prose.

### Work

- add uniform status metadata to analyst structured outputs:
  - `status`
  - `claim_count`
  - `abort_reason`
  - `contract_version`
- ensure all analysts return `completed | failed | empty | aborted`
- expose empty/aborted analysts in packet assembly

### Files

- [agent_states.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/agent_states.py)
- [propagation.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/propagation.py)
- analyst modules under [analysts](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts)
- packet builder modules

### Acceptance

- no downstream node needs to infer analyst failure from blank strings
- run artifacts show explicit domain status for each analyst

## Phase 3: Deterministic Research Packet

### Goal

Replace summary-first machine handoff with a deterministic structured packet.

### Work

- add `research_packet_structured`
- build it deterministically from:
  - scanner context
  - structured analyst outputs
  - analyst status metadata
- keep `research_packet_summary` as presentation only
- make the packet degrade gracefully when some domains are empty

### Files

- [context_summaries.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/context_summaries.py)
- [summary_context.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/summary_context.py)
- graph wiring files

### Acceptance

- packet is non-empty whenever any upstream signal exists
- packet provenance is explicit by domain
- downstream nodes prefer structured packet over prose summary

### Live test

```bash
./scripts/run_node_live.py \
  --trigger \
  --ticker AAPL \
  --date 2026-03-31 \
  --analysts market,news,fundamentals,social \
  --show-system
```

Artifact check:

- inspect run events and saved reports for `research_packet_structured`
- confirm packet includes analyst status for missing domains

## Phase 4: Research Manager and Trader Ownership

### Goal

Stop downstream managers from inventing or mislabeling upstream conclusions.

### Work

- add `investment_plan_structured`
- restrict research manager to selecting and weighting upstream evidence
- fix PM/trader ownership so PM reads trader output from the correct field
- add `trader_plan_structured` when trader contract work begins

### Files

- [research_manager.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/research_manager.py)
- [portfolio_manager.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/portfolio_manager.py)
- trader node implementation
- PM/trader tests

### Acceptance

- PM no longer treats research-manager prose as trader output
- manager and trader outputs can be traced to upstream packet inputs

## Phase 5: Debate and Risk Contracts

### Goal

Reduce hallucination created by repeated prose rewriting across bull/bear/risk rounds.

### Work

- decide whether bull/bear nodes stay
- if retained, add compact structured outputs rather than freeform restatements
- add structured risk round outputs
- make risk synthesis operate over explicit inputs instead of summary prose

### Files

- debate graph nodes
- risk nodes
- graph setup and routing

### Acceptance

- each round records what upstream claims it selected, rejected, or reweighted
- contradiction and synthesis happen over machine fields, not prose paraphrases

## Phase 6: Optional Raw Context Experiment

### Goal

Run the raw-context A/B only after the core pipeline completes reliably.

### Work

- add `include_raw_context`
- add `optional_filtered_raw_context`
- filter raw evidence per ticker and per report type
- bound prompt growth deterministically

### Acceptance

- default remains summary-first
- raw context is opt-in and bounded
- experiment compares stable baseline vs raw-augmented prompts

## Per-Phase Test Gate

A phase is not complete until all are true:

1. targeted unit tests pass
2. one live scoped run is attempted with `run_node_live.py`
3. artifacts confirm the contract change is actually present
4. downstream consumer for that boundary reads the new machine field

## Recommended Work Order

1. market node stabilization
2. analyst status contract
3. deterministic research packet
4. PM/trader ownership fix finalization
5. research manager structured handoff
6. debate/risk contract migration
7. optional raw-context experiment

## Stop Conditions

Pause and investigate before continuing if:

- a node starts emitting empty structured output more often than before
- a downstream consumer still prefers prose after the structured field exists
- prompt size expands materially without accuracy gain
- the live run stalls for reasons unrelated to the contract change
