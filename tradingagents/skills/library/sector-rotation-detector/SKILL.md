---
name: sector-rotation-detector
description: Relate macro evidence and industry conditions to a sector view without overstating causal attribution.
roles:
  - news_analyst
triggers:
  - macro developments may affect sector leadership
  - industry rotation is relevant to company news
output_schema:
  - macro_driver
  - affected_sector
  - company_exposure
  - confidence
---

Identify only evidenced macro drivers, then explain the sector exposure and the
company-specific channel. Compare relative beneficiaries and losers where the
available data supports it. Treat policy headlines, commodity moves, and index
performance as inputs rather than proof of a durable rotation.

State the data window and confidence. Do not claim industry leadership or use a
sector statistic unless a supplied source supports the number and date.
