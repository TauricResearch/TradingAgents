---
name: full-analysis
description: A full research analysis of one company: its business and results, valuation, how its stock has traded, the macro backdrop, the risks and the range of outcomes, weighed into a view. Use it when the user asks for an analysis of a company, or for a view, a rating or a recommendation on one.
metadata:
  group: Companies
---

A full analysis looks at a company from several disciplines and weighs them into one view. Past research on the company (recall_memory) shows what was thought before and what was learned; it is context, not evidence about today. A plan (update_plan) lets the user follow the work as it goes.

The specialists each own one discipline: Equity Research the business, results and valuation; Quant Research how the stock has traded and what its numbers say; Macro Strategy the backdrop that bears on it; Risk Analysis what could make a position lose. Briefed in one step, they work in parallel, each on its own part, and each brief names the company, the question and any date. A specialist with nothing to read for the instrument (Equity Research for an index, say) is better left out, with the reason. Risk Analysis can be briefed with the others, or after them with their reports passed by id in `evidence`, so it weighs what they found.

The answer weighs the evidence into a view, as a research report would: the investment summary, the business and its results, valuation, the range of outcomes (scenario-analysis), the risks that would change the view, and the macro and market context, each resting on cited evidence. When the evidence is mixed or the view is strong, thesis-review tests it before it is given. What was missing is part of the answer.

When the user asks for a rating, a common scale has five tiers: Buy (strong conviction to enter or add), Overweight (favorable, gradually increase exposure), Hold (maintain the position), Underweight (reduce, take partial profits), Sell (exit or avoid). A rating means something only with its horizon. record_decision keeps a rating given at the user's request and later checks it against how the price moved, so later runs can learn from it.
