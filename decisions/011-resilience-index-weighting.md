### Architecture Decision Record: ADR-001-Resilience-Weighting

**Date:** 2026-06-01
**Status:** In Progress
**Context:** The current market environment is characterized by "mercantile interference," where indices are being re-engineered to force capital into high-risk, low-float IPOs. Standard metrics like credit ratings for AI debt are deemed unreliable due to the systemic "sophistry" of labeling speculative debt as "AAA".

---

## ADR-011: Resilience Index Weighting

### Decision

We have established the `Resilience Index` formula with a 0.6 weighting for **Utility Stability** and a 0.4 weighting for **Debt/Productivity Metrics**.

### Rationale

* **Utility Stability (0.6):** This represents the "physical reality" of the economy—power, cooling, and data transit. In a Smithian analysis, this is the only part of the "supercycle" providing genuine, non-speculative value. We prioritize this because these assets have inherent utility that persists even if the "AI" narrative collapses.


* **Debt/Productivity Metrics (0.4):** This component tracks the disconnect between capital expenditure (CapEx) and realized GDP/Productivity gains. We weight this lower (0.4) because the market is currently "rigged" to ignore these fundamentals. By keeping the weight below 0.5, we ensure that while we monitor the "AI-Debt" bubble, we are not blindsided by a sudden "liquidity contagion" caused by index-weighting distortions.



### Consequences

* **Pros:** Protects the portfolio from reacting too slowly to "artificial" price movements caused by exchange rule changes.


* **Cons:** Might cause the agent to be "too early" in liquidating positions if it detects a liquidity drain before the broader market recognizes the risk.



---

**This ADR is now ready to be committed to the repository.** We have successfully framed the logic around Adam Smith’s caution against state-sanctioned monopolies and the necessity of focusing on physical capital over speculative debt.

**Are you ready to hand this off to the coding agents, or is there a specific nuance about the "kill-switch" logic you want to refine before we move to implementation?**