# 019 Structured Contracts Implementation Checklist

## Purpose

This is the execution checklist for migrating the graph away from prose-first handoffs.

Use it together with:

- [017 Structured Contracts and Raw Context Experiment](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/017-structured-contracts-and-raw-context-experiment.md)
- [018 Agent Handoff Matrix](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/018-agent-handoff-matrix.md)

The goal is to make each node consume canonical structured state, keep markdown as presentation only, and reduce aborts caused by drift between nodes.

## Terminal Execution Assets

Use these while migrating node-by-node and validating each change live:

- [Node-by-Node Terminal Testing Guide](/Users/Ahmet/Repo/TradingAgents/docs/testing/node-by-node-terminal-guide.md)
- [run_node_live.py](/Users/Ahmet/Repo/TradingAgents/scripts/run_node_live.py)

## Guiding Rule

For each migration step:

1. add a structured state field
2. make it the canonical machine-truth output
3. derive markdown from the structured payload
4. update downstream consumers
5. demote the old prose field to presentation-only
6. remove the old field after all consumers move

## Phase 0: Immediate Safety Fixes

### 0.1 Portfolio Manager state ownership bug

- [ ] Change Portfolio Manager to stop treating `investment_plan` as the trader plan
- [ ] Read `trader_investment_plan` for the trader output until `trader_plan_structured` exists
- [ ] Add a unit test that fails if PM reads the wrong field

Files:

- [portfolio_manager.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/portfolio_manager.py)
- [test_portfolio_manager.py](/Users/Ahmet/Repo/TradingAgents/tests/unit/test_portfolio_manager.py)

Acceptance:

- PM prompt labels research manager output and trader output correctly
- final decision uses the actual trader handoff

### 0.2 Macro regime fallback removal

- [ ] Stop setting `macro_regime_report = report` based on prose phrase matching
- [ ] Require macro regime to come from explicit parsed regime output or remain empty
- [ ] Add coverage for missing regime data

Files:

- [market_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/market_analyst.py)
- [test_analyst_agents.py](/Users/Ahmet/Repo/TradingAgents/tests/unit/agents/test_analyst_agents.py)

Acceptance:

- no heuristic full-report fallback
- macro regime source is explicit and traceable

### 0.3 Stop using summary prose as the preferred machine input

- [ ] Identify every use of `research_packet_summary` as a preferred input
- [ ] Replace preference logic with structured packet lookup once `research_packet_structured` exists
- [ ] Keep summary only for rendering and logs

Files:

- [summary_context.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/summary_context.py)
- [context_summaries.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/context_summaries.py)

Acceptance:

- downstream logic does not rely on LLM-compressed packet prose when structured packet is available

## Phase 1: State Contract Foundation

### 1.1 Add canonical structured fields to agent state

- [ ] Add `market_report_structured`
- [ ] Add `sentiment_report_structured`
- [ ] Add `fundamentals_report_structured`
- [ ] Add `research_packet_structured`
- [ ] Add `investment_plan_structured`
- [ ] Add `trader_plan_structured`
- [ ] Add `risk_r1_aggressive_structured`
- [ ] Add `risk_r1_conservative_structured`
- [ ] Add `risk_r1_neutral_structured`
- [ ] Add `risk_r2_aggressive_structured`
- [ ] Add `risk_r2_conservative_structured`
- [ ] Add `risk_r2_neutral_structured`
- [ ] Add `risk_synthesis_structured`
- [ ] Add `final_trade_decision_structured`
- [ ] Add `include_raw_context`
- [ ] Add `optional_filtered_raw_context`

Files:

- [agent_states.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/agent_states.py)
- [propagation.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/propagation.py)
- engine/runtime config entrypoints that construct initial state

Acceptance:

- new fields are initialized everywhere a graph state is created
- no node crashes on missing structured fields

### 1.2 Define shared contract schemas and validation helpers

- [ ] Create shared typed helpers or schemas for analyst claims
- [ ] Create shared helpers for contract versioning
- [ ] Add sanitizers for empty, malformed, or partial structured outputs
- [ ] Add deterministic markdown render helpers from structured payloads

Candidate files:

- [output_validation.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py)
- new contract helper module under `tradingagents/agents/utils/`

Acceptance:

- each structured payload can be validated without regex-parsing markdown
- markdown views are reproducible from structured state

## Phase 2: Analyst Contract Migration

### 2.1 Market analyst

- [ ] Add `market_report_structured` output
- [ ] Encode claim objects instead of only markdown
- [ ] Keep rendered `market_report` as derived view
- [ ] Include explicit macro regime field inside the structured payload

Files:

- [market_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/market_analyst.py)
- related analyst tests

Acceptance:

- all material market claims have claim IDs and provenance
- macro regime is explicit and not inferred from prose

### 2.2 Fundamentals analyst

- [ ] Add `fundamentals_report_structured`
- [ ] Encode metrics, values, dates, and source/tool provenance
- [ ] Render `fundamentals_report` from the structured payload

Files:

- [fundamentals_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/fundamentals_analyst.py)
- related tests

Acceptance:

- downstream nodes can consume fundamentals claims without re-parsing markdown

### 2.3 Social analyst

- [ ] Add `sentiment_report_structured`
- [ ] Split sentiment observations from conclusions
- [ ] Capture origin of social signals and confidence
- [ ] Render `sentiment_report` from structured output

Files:

- [social_media_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/social_media_analyst.py)
- related tests

Acceptance:

- social claims have explicit provenance and confidence fields

### 2.4 News analyst

- [ ] Keep `news_report_structured` as canonical
- [ ] Remove any remaining prose-first assumptions in downstream consumers
- [ ] Keep markdown rendering strictly derived from validated JSON

Files:

- [news_analyst.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/analysts/news_analyst.py)
- [news_fact_checker.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/news_fact_checker.py)
- [output_validation.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/output_validation.py)

Acceptance:

- source validation is evidence-driven only
- hallucinated claims are removed without collapsing valid report content

## Phase 3: Deterministic Research Packet

### 3.1 Replace summary-first canonical handoff

- [ ] Build `research_packet_structured` deterministically from structured analyst outputs
- [ ] Keep `scanner_context_packet` as the compact scanner packet
- [ ] Keep `research_packet_summary` as an optional rendering only
- [ ] Remove any downstream preference for prose summary over structured packet

Files:

- [context_summaries.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/context_summaries.py)
- [summary_context.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/utils/summary_context.py)
- graph setup files that wire the summary node

Acceptance:

- canonical research packet is deterministic
- downstream consumers can access claim IDs by domain

### 3.2 Optional raw context experiment

- [ ] Add `include_raw_context` plumbing to runtime config and request models
- [ ] Add `optional_filtered_raw_context` builder
- [ ] Filter only ticker-scoped relevant raw evidence
- [ ] Apply hard bounds to each section
- [ ] Omit the section entirely when filtering yields nothing

Files:

- `langgraph_engine.py`
- scanner packet preparation code
- metadata persistence code

Acceptance:

- default remains summary-first only
- raw context is opt-in and bounded
- raw context is never appended as an unfiltered dump

## Phase 4: Manager and Debate Contract Migration

### 4.1 Research manager

- [ ] Add `investment_plan_structured`
- [ ] Make manager consume `research_packet_structured`
- [ ] Restrict manager to selecting and weighing upstream claim IDs
- [ ] Render `investment_plan` from structured output

Files:

- [research_manager.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/research_manager.py)
- debate state helpers if needed

Acceptance:

- manager introduces no unsupported new facts
- plan can be traced to upstream claims

### 4.2 Bull / Bear researchers

- [ ] Decide whether bull/bear round outputs stay as separate nodes
- [ ] If retained, add `bull_round_structured` and `bear_round_structured`
- [ ] If removed, document replacement and simplify the graph

Files:

- current investment debate node implementations
- graph setup and conditional routing

Acceptance:

- no prose-only debate state is required for manager reasoning

### 4.3 Trader

- [ ] Add `trader_plan_structured`
- [ ] Consume `investment_plan_structured`
- [ ] Validate entry, stop, target, size, and catalysts
- [ ] Render `trader_investment_plan` from structured output during migration

Files:

- [trader.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/trader/trader.py)
- trader tests

Acceptance:

- trader parameters are explicit and machine-checkable
- new dates cannot appear without provenance

### 4.4 Risk debators

- [ ] Add structured round outputs for each debator
- [ ] Make debators consume `trader_plan_structured` and claim IDs
- [ ] Stop debating over free-form trader prose
- [ ] Keep round markdown only as observability output

Files:

- [aggressive_debator.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/risk_mgmt/aggressive_debator.py)
- [conservative_debator.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/risk_mgmt/conservative_debator.py)
- [neutral_debator.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/risk_mgmt/neutral_debator.py)

Acceptance:

- round outputs reference explicit claim IDs and trader parameters
- unsupported risk arguments can be isolated and removed

### 4.5 Risk synthesis

- [ ] Add `risk_synthesis_structured`
- [ ] Synthesize structured round outputs, not round prose
- [ ] Derive `risk_debate_state.summary` only for backward presentation during migration

Files:

- [risk_synthesis.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/risk_mgmt/risk_synthesis.py)

Acceptance:

- synthesis preserves disagreements and recommended controls explicitly

## Phase 5: Portfolio Decision Contract

### 5.1 Portfolio manager

- [ ] Add `final_trade_decision_structured`
- [ ] Consume only canonical structured upstream payloads
- [ ] Render `final_trade_decision` from the structured output
- [ ] Keep presentation and persistence compatible during migration

Files:

- [portfolio_manager.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/managers/portfolio_manager.py)
- downstream persistence and portfolio pipeline files

Acceptance:

- final action, thesis, execution, and risk controls are claim-linked
- final decision is no longer synthesized from debate prose alone

### 5.2 Persistence and downstream readers

- [ ] Update result serialization to persist structured contracts
- [ ] Update report writers to render from structured state
- [ ] Update portfolio summary helpers that still read prose-only fields

Files:

- [trading_graph.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/trading_graph.py)
- [macro_bridge.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/pipeline/macro_bridge.py)
- [micro_summary_agent.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/micro_summary_agent.py)
- [holding_reviewer.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/agents/portfolio/holding_reviewer.py)
- [portfolio_setup.py](/Users/Ahmet/Repo/TradingAgents/tradingagents/graph/portfolio_setup.py)

Acceptance:

- saved artifacts include canonical structured payloads
- portfolio utilities can operate without depending on prose-only fields

## Phase 6: Removal of Unnecessary Nodes and Fields

This phase should happen only after structured contracts are stable.

### Removal candidates

- [ ] Remove `Research Packet Summary` as a canonical dependency
- [ ] Remove prose-first fallback logic in `summary_context.py`
- [ ] Remove any node whose only role is to paraphrase already-structured state
- [ ] Remove heuristic macro-regime inference from prose
- [ ] Remove debate history as a required machine input
- [ ] Remove prose-first validation logic that parses rendered markdown

Potential node simplifications to evaluate:

- `Research Packet Summary` node may become rendering-only or disappear
- Bull/Bear investment debate may be simplified if manager can directly reason over structured claims
- Round 2 risk debate may be reduced if structured round 1 plus synthesis covers the same signal

Acceptance:

- every removed node or field has a surviving structured replacement
- graph behavior is simpler, not just renamed

## Test Checklist

### Contract tests

- [ ] Analyst structured payload validation tests
- [ ] Research packet deterministic assembly tests
- [ ] Manager / trader / risk / PM contract validation tests
- [ ] Malformed payload sanitization tests

### Wiring tests

- [ ] Downstream nodes prefer structured fields when present
- [ ] Rendered markdown matches structured payload content
- [ ] No node crashes when presentation fields are empty

### Raw context experiment tests

- [ ] `include_raw_context=False` produces summary-only prompts
- [ ] `include_raw_context=True` appends filtered bounded raw context
- [ ] Empty filtered raw context is omitted entirely
- [ ] prompt growth stays within defined caps

### Artifact-backed tests

- [ ] Re-run representative saved runs and compare abort reasons
- [ ] Verify that false-positive hallucination aborts decrease
- [ ] Verify that valid claim retention improves when partial invalid output is pruned

## Exit Criteria

The migration is complete when all of the following are true:

- every major node has a canonical structured output
- downstream nodes consume structured state, not prose summaries
- prose fields are derived artifacts only
- critical aborts are driven by structured validation, not regex guesses over markdown
- optional raw context remains an experiment toggle, not the default path
