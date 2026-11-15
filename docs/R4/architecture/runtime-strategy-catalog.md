# R4 Runtime Strategy Catalog

These are the current behaviors of the R4 settlement path. They do not define global error handling for other CLI modules.

| Trigger | System behavior | Evidence |
| --- | --- | --- |
| Incomplete price window or benchmark missing the exit date | Do not record a partial return; the decision stays `pending`. | `settlement.fetch_returns()`, `test_incomplete_window_stays_pending_without_reflection` |
| Yahoo price retrieval fails | Add the entry to the failure result and leave it pending. The graph's memory step reports a note without aborting the analysis. | `settlement.settle_pending()`, `trading_graph._memory_step()` |
| Invalid cost settings | Write no outcome, report `invalid cost config`, and allow a later retry. | `apply_trading_costs()`, `test_invalid_cost_config_and_reflection_failure_stay_pending` |
| LLM reflection fails | Leave the decision pending; do not write a partial log entry. | `settlement.settle_pending()`, the same failure test |
| A decision is stored or settled again | Keep one entry; a resolved decision does not trigger another reflection. | `TradingMemoryLog.store_decision()`, `update_with_outcome()`, settlement tests |
| Cost adjustment is disabled | Store gross return and alpha and use the legacy reflection prompt. | `test_switch_off_preserves_gross_settlement`, `test_reflection_without_gross_values_keeps_legacy_prompt` |

In the live CLI smoke test, agents such as the Research Manager may fall back from structured output to plain text. That is an existing LLM invocation strategy, not an R4 settlement retry. A passing smoke test confirms that the workflow completed; it does not establish the quality of investment advice.
