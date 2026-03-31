# Senior QA Engineer Report: Pipeline Latency and Recursion Analysis

**Status**: Investigated
**Date**: 2026-03-31
**Subject**: AAPL Pipeline apparent "stuck" state during Risk Debate

## Executive Summary
The "stuck" state reported during the AAPL pipeline execution is not a terminal deadlock but a combination of **high-recursion graph logic** and **LLM inference latency**. The pipeline eventually completes, but the user experience is degraded by a ~15-minute wait during the Phase 2/3 transition.

## Findings

### 1. Risk Debate Cycle (Intended but slow)
The `debate_graph` is configured with `max_risk_discuss_rounds = 2`. The `ConditionalLogic.should_continue_risk_analysis` implementation translates this into a 3-step cycle per round:
1.  **Aggressive Analyst** -> Risk Summary
2.  **Conservative Analyst** -> Risk Summary
3.  **Neutral Analyst** -> Risk Summary

For 2 rounds, this results in **6 sequential calls** to the `Risk Debate Summary` node.

### 2. Latency Bottleneck: Summarization
Logs show the following average latencies:
- **Analyst Nodes**: ~40-60s
- **Risk Debate Summary**: **~70-100s**

Because the summary is "rolling" (it takes the previous summary as input), these calls cannot be parallelized. Total time spent just on summarization for one ticker is ~10 minutes.

### 3. Tier Assignment Mismatch
I discovered a configuration bug in `tradingagents/graph/setup.py` where the **Fundamentals Analyst** was assigned to the `quick_thinking_llm` instead of the `mid_thinking_llm`. This degrades analysis quality for one of the most data-intensive nodes.

## Root Cause
The process feels "stuck" because the `quick_thinking_llm` (Qwen 3.5 9B) is being used for complex 200+ word summarization tasks that trigger its maximum output latency. Sequential dependencies in the risk-debate loop multiply this latency.

## Recommendations
1.  **Promote Summary Node**: Move `Risk Debate Summary` to the `mid_thinking_llm` tier. While the model is larger, its higher throughput and better reasoning may reduce total wall-clock time and improve summary coherence.
2.  **Parallel Analysts**: Refactor the risk debate to run Analysts in parallel and perform a single "Final Risk Synthesis" instead of a rolling summary.
3.  **Fix Tier Wiring**: Correct the `Fundamentals Analyst` LLM assignment (applied in this PR).
4.  **UI Progress**: Improve the UI to show specific sub-node progress (e.g., "Summarizing Risk Debate (Round 1/2)...") to reduce perceived "stuckness".

---
*Report by Senior QA Engineer*
