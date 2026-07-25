---
name: financial-statement-analyzer
description: Ground a fundamental view in cash flow, profitability quality, leverage, and explicit red flags.
roles:
  - fundamentals_analyst
triggers:
  - financial statements are available
  - profitability or governance quality needs assessment
output_schema:
  - earnings_quality
  - balance_sheet_risk
  - cash_conversion
  - red_flags
---

Start from reported figures, not narrative. Reconcile revenue, operating profit,
net income, operating cash flow, free cash flow, debt, and working capital.
Explain material changes with dated evidence. Distinguish sustainable operating
improvement from one-off gains, accounting changes, or balance-sheet financing.

Report a compact scorecard: profitability quality, cash conversion, leverage and
liquidity, working-capital direction, and governance or accounting red flags.
If a metric cannot be computed from the available statements, mark it unavailable
rather than estimating it. Do not make a price target from this method alone.
