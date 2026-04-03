# 018 Agent Handoff Matrix

## Purpose

This document maps the current graph's node-to-node handoffs, identifies where the canonical payload is free-form prose, and defines the target structured contract for each boundary.

Use this as the implementation-facing inventory for replacing prose re-write chains with typed state.

Companion docs:

- [017 Structured Contracts and Raw Context Experiment](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/017-structured-contracts-and-raw-context-experiment.md)
- [019 Structured Contracts Implementation Checklist](/Users/Ahmet/Repo/TradingAgents/docs/agent/plans/019-structured-contracts-implementation-checklist.md)

## Current Handoffs

| From Node | Current Output Field | To Node(s) | Current Input Mode | Risk | Target Canonical Field |
|---|---|---|---|---|---|
| Market Analyst | `market_report` | Research Packet Summary, Research Manager, Trader, PM | Markdown / prose | High | `market_report_structured` |
| Social Media Analyst | `sentiment_report` | Research Packet Summary, Research Manager, Trader, PM | Markdown / prose | High | `sentiment_report_structured` |
| News Analyst | `news_report`, `news_report_structured` | Research Packet Summary, Research Manager, Trader, PM | Mixed | Medium | `news_report_structured` |
| Fundamentals Analyst | `fundamentals_report` | Research Packet Summary, Research Manager, Trader, PM | Markdown / prose | High | `fundamentals_report_structured` |
| Research Packet Summary | `research_packet_summary` | Bull Researcher, Bear Researcher, Research Manager, Risk Synthesis, PM | LLM-compressed prose | Very High | `research_packet_structured` |
| Bull Researcher | `investment_debate_state.current_response`, `history`, `current_bull_summary` | Bear Researcher, Research Manager | Prose | High | `bull_round_structured` |
| Bear Researcher | `investment_debate_state.current_response`, `history`, `current_bear_summary` | Bull Researcher, Research Manager | Prose | High | `bear_round_structured` |
| Research Manager | `investment_plan` | Trader, PM | Prose | Very High | `investment_plan_structured` |
| Trader | `trader_investment_plan` | Aggressive / Conservative / Neutral debators | Prose | Very High | `trader_plan_structured` |
| Risk Round 1 Debators | `risk_r1_*` | Round 2 debators, Risk Synthesis | Prose | Very High | `risk_r1_*_structured` |
| Risk Round 2 Debators | `risk_r2_*` | Risk Synthesis | Prose | Very High | `risk_r2_*_structured` |
| Risk Synthesis | `risk_debate_state.summary`, `history` | Portfolio Manager | Prose | Very High | `risk_synthesis_structured` |
| Portfolio Manager | `final_trade_decision` | Persistence, portfolio flows, UI | Prose | Medium | `final_trade_decision_structured` |

## Current State Field Re-Use That Causes Drift

### 1. Analyst Reports -> Research Packet Summary

Current canonical use:

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`
- `macro_regime_report`
- `scanner_context_packet`

Current transformation:

- An LLM rewrites all of the above into `research_packet_summary`

Why risky:

- data compression is not deterministic
- claim-level provenance is lost
- later nodes cannot distinguish fact from summary interpretation

Target:

- deterministic `research_packet_structured`
- optional `research_packet_summary` for rendering only

### 2. Research Packet Summary -> Research Manager

Current canonical use:

- `research_packet_summary` when present
- raw reports only as fallback

Current transformation:

- Research Manager reinterprets summary prose and debate prose into `investment_plan`

Why risky:

- strongest evidence can be dropped
- confidence labels are not machine-checkable
- claim lineage is lost

Target:

- consume `research_packet_structured`
- emit `investment_plan_structured`

### 3. Investment Plan -> Trader

Current canonical use:

- `investment_plan`

Current transformation:

- Trader turns free-form plan into `trader_investment_plan`

Why risky:

- entry / stop / target may not be linked to validated upstream claims
- dates can be invented despite prompt rules

Target:

- consume `investment_plan_structured`
- emit `trader_plan_structured`

### 4. Trader Plan -> Risk Debate

Current canonical use:

- `trader_investment_plan`

Current transformation:

- 3 debators create prose arguments in round 1
- 3 debators read each other's prose and create more prose in round 2

Why risky:

- disagreement often becomes style-driven rather than claim-driven
- risk arguments can introduce unsupported statistics or historical analogies

Target:

- consume `trader_plan_structured`
- emit `risk_r1_*_structured` and `risk_r2_*_structured`

### 5. Risk Debate -> Risk Synthesis

Current canonical use:

- `risk_r1_aggressive`
- `risk_r1_conservative`
- `risk_r1_neutral`
- `risk_r2_aggressive`
- `risk_r2_conservative`
- `risk_r2_neutral`

Current transformation:

- Risk Synthesis rewrites six prose blocks into one prose summary

Why risky:

- consensus can be overstated
- disagreement can be flattened
- specific risk controls can disappear

Target:

- consume structured round payloads
- emit `risk_synthesis_structured`

### 6. Risk Synthesis -> Portfolio Manager

Current canonical use:

- `risk_debate_state.history`
- `risk_debate_state.summary`
- `research_packet_summary`
- `investment_plan`

Current transformation:

- Portfolio Manager rewrites all of the above into `final_trade_decision`

Why risky:

- final thesis can drift from upstream evidence
- action can be justified by prose emphasis rather than validated claim weight

Target:

- consume `research_packet_structured`
- consume `investment_plan_structured`
- consume `trader_plan_structured`
- consume `risk_synthesis_structured`
- emit `final_trade_decision_structured`

## State Contract Changes

### Add

- `market_report_structured`
- `sentiment_report_structured`
- `fundamentals_report_structured`
- `research_packet_structured`
- `investment_plan_structured`
- `trader_plan_structured`
- `risk_r1_aggressive_structured`
- `risk_r1_conservative_structured`
- `risk_r1_neutral_structured`
- `risk_r2_aggressive_structured`
- `risk_r2_conservative_structured`
- `risk_r2_neutral_structured`
- `risk_synthesis_structured`
- `final_trade_decision_structured`
- `include_raw_context`
- `optional_filtered_raw_context`

### Demote from canonical status

- `research_packet_summary`
- `investment_plan`
- `trader_investment_plan`
- `risk_debate_state.history`
- `risk_debate_state.summary`
- `final_trade_decision`

These can remain as derived renderings during migration.

## Immediate Code-Level Fixes Before Full Migration

1. Portfolio Manager currently labels `investment_plan` as the trader's proposed plan. That field ownership should be corrected before further contract work.
2. `macro_regime_report` should stop relying on heuristic text fallback from market report prose.
3. `build_research_packet()` should stop preferring LLM-compressed prose over deterministic structured packet assembly.

## Contract Migration Rule

For every node migration:

1. add structured state field
2. make structured field canonical
3. derive markdown/text from structured field
4. update downstream consumers to use structured field
5. leave legacy text field as presentation-only until fully removed
