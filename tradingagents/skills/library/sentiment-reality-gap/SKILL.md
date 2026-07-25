---
name: sentiment-reality-gap
description: Compare market narratives with sourced operating facts and make divergence a conditional risk signal.
roles:
  - sentiment_analyst
triggers:
  - retail or news sentiment differs from reported fundamentals
  - social data quality requires confidence calibration
output_schema:
  - narrative
  - reality_check
  - divergence
  - confidence
---

Summarize the observed narrative by source, sample size, and time window. Compare
it with verified operating and financial facts only when those facts are present.
Classify divergence as temporary, structural, or indeterminate, and name the
future observation that would resolve it.

Sentiment is neither a vote nor a price target. Thin, unavailable, or
single-platform data lowers confidence. Never invent community activity or
substitute an unsourced claim for a missing A-share sentiment measure.
