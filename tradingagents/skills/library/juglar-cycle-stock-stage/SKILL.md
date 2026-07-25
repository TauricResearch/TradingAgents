---
name: juglar-cycle-stock-stage
description: Classify the business cycle with explicit evidence and uncertainty instead of a single deterministic label.
roles:
  - fundamentals_analyst
triggers:
  - company results need macro-cycle context
  - China market or industry-cycle exposure is material
output_schema:
  - cycle_evidence
  - likely_stage
  - alternative_stage
  - confidence
---

Separate observed facts from the cycle interpretation. Consider demand, capacity,
inventory, margins, credit conditions, capital expenditure, pricing, employment,
and policy only when evidence is available. State the most likely stage and a
plausible alternative, then name the observations that would falsify the view.

Use a cycle label only as context for the company analysis; it is not a trading
signal by itself. Missing China-specific data must reduce confidence, not be
filled with assumptions from another market.
