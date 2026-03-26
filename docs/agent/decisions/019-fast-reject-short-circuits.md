---
type: decision
status: active
date: 2026-03-26
agent_author: "kilocode"
tags: [performance, optimization, short-circuit, critical-abort]
related_files: [tradingagents/graph/conditional_logic.py, tradingagents/agents/analysts/fundamentals_analyst.py, tradingagents/agents/analysts/market_analyst.py, tradingagents/agents/managers/portfolio_manager.py, tradingagents/agents/utils/agent_states.py]
---

## Context

The TradingAgentsGraph currently forces every stock through the entire analysis pipeline: Market Analyst → Social → News → Fundamentals → Bull/Bear Debate → Risk Debate → Portfolio Manager.

If a stock is fundamentally bankrupt or facing catastrophic SEC delisting, we waste API tokens and time running 5 LLMs through debate rounds. This is inefficient and costly, especially when early analysis clearly indicates the stock should be avoided.

## The Decision

Implement a [CRITICAL ABORT] trigger mechanism that allows early analysts (Fundamentals_Analyst, Market_Analyst) to short-circuit the pipeline and route directly to Portfolio_Manager for an immediate AVOID/SELL decision.

The trigger will be a special string "[CRITICAL ABORT]" embedded in analyst reports that signals the system to bypass remaining analysis phases and proceed directly to portfolio decision-making.

## Constraints

- Must maintain backward compatibility with existing workflows
- Should not interfere with normal analysis flow for healthy stocks
- Must be detectable by conditional logic without breaking existing state transitions
- Should work with both Market Analyst and Fundamentals Analyst
- The Portfolio Manager must recognize and properly handle critical abort scenarios

## Actionable Rules

1. **Trigger Format**: Analysts should include the exact string "[CRITICAL ABORT]" in their report when they detect catastrophic conditions (bankruptcy, SEC delisting, etc.)

2. **Eligible Analysts**: Only Market_Analyst and Fundamentals_Analyst can trigger critical aborts, as they are the earliest in the pipeline and can identify fundamental issues

3. **Routing Logic**:
   - Modify conditional_logic.py to check for "[CRITICAL ABORT]" in market_report or fundamentals_report
   - When detected, bypass Social, News, and Debate phases and route directly to Portfolio Manager
   - The Portfolio Manager should receive a special context indicating this is a critical abort scenario

4. **Portfolio Manager Handling**:
   - When receiving a critical abort signal, the Portfolio Manager should automatically recommend "SELL" or "AVOID"
   - The decision should include reasoning based on the aborting analyst's report
   - No further debate or risk analysis should be performed

5. **State Preservation**:
   - The aborting analyst's report should be preserved in the state
   - Other report fields can be left empty or marked as "SKIPPED DUE TO CRITICAL ABORT"
   - Investment debate state and risk debate state should reflect that these phases were skipped

6. **Logging and Monitoring**:
   - Critical abort events should be logged for audit purposes
   - Metrics should track the number of aborts vs full pipeline executions
