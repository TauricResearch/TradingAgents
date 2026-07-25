---
name: buy-side-equity-research-memo
description: Turn research into a falsifiable portfolio memo with base, upside, downside, catalysts, and monitoring conditions.
roles:
  - portfolio_manager
triggers:
  - final portfolio decision requires a concise investment memo
  - risk debate and research need a decision-ready synthesis
output_schema:
  - thesis
  - scenarios
  - reverse_case
  - catalysts
  - monitoring
---

Lead with the decision and the evidence that changes it. Describe base, upside,
and downside scenarios with stated assumptions; include the strongest reverse
case and the observation that would invalidate the thesis. Identify dated
catalysts and monitoring metrics, with data limitations visible.

This method does not override deterministic portfolio constraints. A suggested
order must remain within the legal action set supplied by the system; when no
action is available, state Hold rather than implying an executable trade.
