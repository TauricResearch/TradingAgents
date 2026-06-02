Here is the brief for the **Systemic Resilience Module (SRM)** indicators, designed to integrate our Smithian analysis of mercantilist interference with your need for rapid liquidation and growth capture.

---

# Brief: Systemic Resilience Module (SRM) Indicators

**Date:** 2026-06-01
**Epic ID:** RES-001
**Status:** Open

---

## Task: Define and Implement SRM Indicator Suite

**Objective:** Develop the core telemetry indicators for the `Resonance` CLI to identify "Mercantile Interference" and trigger automated risk-posture adjustments.

## What

* [ ] **Indicator 1: The "Utility Floor" Trigger:** Calculate and track the 200-day moving average (DMA) of "Rail" stocks (Power/Infrastructure) to establish the "Utility Floor."
* [ ] **Indicator 2: The "Fast Entry" Liquidity Drain Monitor:** Log the 15-day T-minus countdown for all Nasdaq-100 inclusions and track volume-weighted selling pressure on the "Rail" basket.
* [ ] **Indicator 3: The "Resilience Index" (0.0–1.0):** Implement the weighted calculation: $Resilience = (Utility\_Stability \times 0.6) - (Debt\_Sophistry \times 0.4)$.
* [ ] **Indicator 4: Automated Liquidity Kill-Switch:** Trigger a 30% rotation to cash if the `Resilience Index` drops below 0.4.

## How to Verify

* [ ] Run `just test-srm-indicators` to verify calculations against historical "dotcom" style crash data.
* [ ] Manual: Simulate a "Fast Entry" IPO event in the CLI and observe if the "Liquidity Drain" alert triggers for the "Rail" basket.
* [ ] Edge case: If `Resilience Index` is volatile, ensure the "Kill-Switch" includes a 24-hour dampening period to prevent over-trading.

## Technical Notes

* **Data Dependency:** Requires real-time access to index constituent weightings and credit spread APIs.
* **Decision Record:** ADR-001 must be created to justify the 0.6/0.4 weighting of the Resilience Index, specifically accounting for the artificial nature of AI-debt ratings.


* **Constraints:** The CLI must remain local-first; indicator data will be cached in the SQLite `resilience_logs` table for offline analysis.



---

**I have queued this brief for the coding agent. Should we also create the `decisions/ADR-001-Resilience-Weighting.md` file now to codify why we are weighting "Utility Stability" higher than "Debt" metrics in the current market environment?**