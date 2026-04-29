# ADR 028: Deterministic Sizing Guard for Portfolio Decisions

**Date**: 2026-04-29
**Status**: Proposed
**Tags**: [reliability, arithmetic-integrity, position-sizing, deterministic]
**Related**: ADR 027 (Robust but Fail-Loud), ADR 024 (Cash Integrity Guard)

## Context

Current production runs using high-fidelity LLMs (like Kimi-k2.6) for the `make_pm_decision` node exhibit a recurring failure mode: **Arithmetic Drift**. 

The LLM successfully generates a "Forensic Execution Dashboard" with deep strategic reasoning, but fails to maintain strict adherence to portfolio constraints in its final share-count calculations. For example, in run `01KQAXZ7HP61CJ4NHAQDEVAXRZ`, the model proposed a strategy that resulted in a projected cash balance of **-$1,379.03**, violating the 10% minimum cash reserve invariant.

Per ADR-027, the system correctly "Fails Loud" via the `pm_decision_postcheck` node. However, this creates a high operational burden where a 15-minute, 5,000-token high-quality analysis is discarded due to minor mathematical rounding errors.

## Principle

> Strategy is probabilistic; Arithmetic is deterministic.
> Decouple the **selection** of assets (LLM) from the **sizing** of positions (Python).

## Decision

Introduce a **Deterministic Sizing Guard** node into the portfolio graph. This node sits immediately after `make_pm_decision` and before `pm_decision_postcheck`.

### Architecture Change

The graph flow evolves from:
`make_pm_decision (LLM)` → `pm_decision_postcheck (Validation)`

To:
`make_pm_decision (LLM Intent)` → **`deterministic_sizing_guard (Python Math)`** → `pm_decision_postcheck (Final Validation)`

### Responsibilities of the Sizing Guard (Pure Python)

The Guard node will perform the following deterministic adjustments to the LLM's proposed trade list:

1.  **Hard Position Cap**: Clamp any buy order to `max_position_pct` (default 15%) of the current Total Portfolio Value.
2.  **Sector Exposure Cap**: If multiple buys in a single sector exceed `max_sector_pct` (default 40%), scale them down proportionally.
3.  **Minimum Cash Floor**: If total proposed buys would leave cash below `min_cash_pct` (default 10%), scale all buys down proportionally until the cash floor is respected.
4.  **Hold/Sell Validation**: Ensure proposed holds and sells refer to valid existing positions (rejecting LLM "hallucinated" holdings).

### The "Intent" Contract

The LLM remains the authoritative source for **Intent** (which tickers to buy and the rationale). The Guard node acts as a **Scaling Filter**. If the LLM proposes buying 1,000 shares but the budget only allows 950, the Guard scales it to 950 and logs a `logger.info` event. If the LLM proposes a buy that is fundamentally impossible (e.g. buying a ticker it never researched), the Guard passes it through to `postcheck` which will still Fail-Loud.

## Rationale

-   **Robustness**: Prevents run mortality from "Death by Arithmetic."
-   **Separation of Concerns**: Allows the LLM to focus on complex multi-factor synthesis (Macro + Micro + Memory) without being burdened by precise NAV calculation.
-   **Auditability**: The logs will show exactly what the LLM *wanted* to do vs. what the Deterministic Guard *permitted* it to do.
-   **Efficiency**: Reduces the need for expensive "Self-Correction" LLM loops which often fail to fix their own math errors.

## Consequences

-   **Success Rate**: Significantly higher percentage of "Auto" runs will reach the `execute_trades` node.
-   **Complexity**: Adds one additional (but fast and unit-testable) node to the graph.
-   **Permissiveness**: This is **not** a permissive fallback; it is a mathematical refinement. It will never *add* tickers or *increase* sizes; it only *scales down* to fit the physical constraints of the account.

## Implementation Notes

-   The node should be implemented in `tradingagents/graph/nodes/sizing_guard.py`.
-   It must be strictly read-only regarding external APIs; it only transforms the `pm_decision` dictionary within the LangGraph state.
-   It should use `decimal` or precision-rounded `float` for all calculations to avoid floating-point drift.
