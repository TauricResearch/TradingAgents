# Senior Analysis Integration Design

**Date:** 2026-03-24

**Goal**

Upgrade TradingAgents into a senior-level research system by salvaging selected upstream PRs, adding structured underwriting roles for stocks, integrating the full Polymarket module, and standardizing final outputs under a concise chief-analyst summary layer.

## Scope

This design covers:

- Salvage and integration of upstream PRs:
  - `#401` role-based LLM routing
  - `#244` Macro Analyst
  - `#399` social sentiment tool
  - `#359` Factor Rule Analyst
  - `#392` medium-term positioning upgrade
  - `#452` Chief Analyst supervisor
  - `#432` full Polymarket module
- New stock-analysis roles:
  - `Valuation Analyst`
  - `Segment Analyst`
  - `Scenario & Catalyst Analyst`
  - `Position Sizing Analyst`
- Isolation of all work in in-repo git worktrees and branches
- Push of resulting branches to the `guanghan` fork

## Non-Goals

- No direct order placement or brokerage execution
- No attempt to preserve each PR verbatim if it conflicts with current `main`
- No change to the current dirty local checkout on `main`

## Constraints

- The current repository contains local uncommitted work on `main`; all integration must happen in isolated worktrees.
- Upstream PRs overlap on graph wiring, config, state schema, CLI flows, and reporting.
- Several upstream PRs are closed without merge, so behavior must be salvaged rather than blindly cherry-picked.

## Integration Strategy

Use a phased branch family instead of a single large merge:

1. `integration/upstream-stock`
   - Salvage `#401`, `#244`, `#399`, `#359`, `#392`
   - Stabilize the stock pipeline and shared infrastructure
2. `integration/senior-stock-roles`
   - Add new structured stock roles
   - Upgrade stock outputs from verbose prose to machine-readable underwriting artifacts plus short human summaries
3. `integration/polymarket-full`
   - Merge full `#432` on a clean parallel branch
   - Keep prediction-market architecture parallel to stocks
4. `integration/chief-analyst-final`
   - Salvage `#452`
   - Reconcile final summary/reporting behavior across stocks and Polymarket
5. `integration/final`
   - Final conflict resolution, CLI/reporting cleanup, validation, and push-ready polish

## Stock Pipeline Target Architecture

### Core Analysts

- `market`
- `social`
- `news`
- `fundamentals`
- `macro`
- `factor_rule` optional

### Senior Underwriting Analysts

- `valuation`
  - fair value range
  - reverse DCF / expectation check
  - comp-based valuation sanity check
  - expected return profile
- `segment`
  - business unit decomposition
  - segment economics
  - value-driver map
- `scenario_catalyst`
  - bull/base/bear cases
  - probabilities
  - dated catalyst map
  - thesis invalidation triggers
- `position_sizing`
  - conviction tier
  - target weight
  - initial size
  - add/trim/exit bands
  - max loss / risk budget

### Synthesis Layer

- Bull and bear researchers consume all analyst outputs
- Research manager produces a structured investment plan
- Risk debate argues over explicit scenario, valuation, and sizing fields instead of re-paraphrasing prose
- Portfolio manager produces the canonical action recommendation

### Final Compression Layer

- `Chief Analyst`
  - reads full final state
  - emits concise structured output
  - validates that the final recommendation matches supporting evidence

Required top-level output fields:

- `verdict`
- `fair_value`
- `catalysts`
- `execution`
- `tail_risk`
- `variant_perception`

## Polymarket Target Architecture

Adopt `#432` as a parallel product module rather than forcing it into the stock graph.

Shared conventions that should be standardized across both products:

- role-based LLM routing
- structured final recommendation schema
- chief-analyst summary format
- report/export conventions
- sizing vocabulary

## Data Model Changes

The current stock system primarily passes long text reports between nodes. That is the main reason downstream reasoning becomes repetitive and weakly quantitative.

Each senior stock role must emit:

1. a structured machine-readable object for downstream nodes
2. a short markdown summary for saved reports

Examples:

- `valuation_report` + `valuation_data`
- `segment_report` + `segment_data`
- `scenario_catalyst_report` + `scenario_catalyst_data`
- `position_sizing_report` + `position_sizing_data`

Research manager, portfolio manager, and chief analyst must consume the structured fields first and use report text only as supporting narrative.

## Expected Quality Gains

This design directly addresses the current weaknesses:

- financial modeling: `valuation`
- scenario analysis: `scenario_catalyst`
- concision: `chief analyst`
- segment breakdown: `segment`
- peer comp: `#392` plus `valuation`
- catalyst dating: `scenario_catalyst`
- sizing framework: `position_sizing`
- technical-fundamental integration: richer synthesis prompts plus structured cross-role outputs
- regulatory quantification: modeled under scenarios and valuation sensitivities
- non-consensus insight: explicit `variant_perception` output

## Known Conflict Hotspots

- `tradingagents/graph/setup.py`
- `tradingagents/graph/trading_graph.py`
- `tradingagents/default_config.py`
- `cli/main.py`
- `cli/utils.py`
- `tradingagents/agents/utils/agent_states.py`
- `tradingagents/agents/utils/agent_utils.py`
- reporting and final-output rendering paths

## Conflict Resolution Rules

- Prefer current `main` architecture as the baseline
- Salvage upstream behavior, not exact file diffs
- Normalize all final outputs onto one structured schema
- Keep Polymarket parallel where product boundaries differ
- Preserve backward compatibility where practical, but favor correctness over perfect prompt compatibility

## Validation Requirements

Each phase must leave the branch runnable and testable.

Minimum validation per phase:

- targeted unit tests for new modules and graph wiring
- `python -m compileall tradingagents tests`
- CLI smoke checks where relevant
- end-to-end stock analysis smoke check after stock phases
- end-to-end Polymarket smoke check after Polymarket phase

## Deliverables

- isolated branch family in `.worktrees/`
- implementation plan document
- integrated branches pushed to `guanghan`
- final integration branch that combines stock upgrades, Polymarket, and chief-analyst output standardization
