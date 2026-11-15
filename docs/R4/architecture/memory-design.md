# R4 Memory and State Design

R4 uses the existing Markdown memory log. It adds neither a database nor new log fields. The relevant implementation is in `tradingagents/memory/log.py`, `settlement.py`, and `reflection.py`.

## State Transitions

| Event | Log state | R4 behavior |
| --- | --- | --- |
| Analysis completes | `pending` | Store the final decision under `(ticker, trade_date)`; a rerun does not insert a duplicate. |
| Holding window is incomplete | `pending` | Do not calculate a partial return or generate a reflection. |
| Price, configuration, or model call fails | `pending` | Return a failure reason to the caller and allow a later retry. |
| Price window is complete and reflection succeeds | `resolved:<exit trading date>` | Atomically update return, alpha, holding period, and reflection. |

`settle_pending()` calculates gross return from the ticker and benchmark closes before deciding whether to apply costs. With costs enabled, the existing `raw` and `alpha` positions store net return and net alpha. Gross figures are used in that run's reflection and are not separately stored. With costs disabled, those positions continue to store gross figures. The reflection prompt shows both measurement bases only when costs are enabled.

## Consistency and Time Boundary

- Decision writes check for an existing entry with the same ticker and date. Settlement uses a separate cross-process lock to avoid paying for the same reflection twice in concurrent runs.
- Settlement writes through a temporary file and replacement. State is unchanged until reflection succeeds.
- The `resolved` date is the date of the exit close at `holding_period_days`. Historical analysis uses `get_past_context(as_of=...)` to read only reflections known by its date.
- Legacy resolved entries have no snapshot of the cost switch or fee rate. The current defaults cannot reconstruct their measurement basis. Demonstrations should use a fresh, isolated log.

Local price sequences and log assertions are in `tests/test_cost_adjusted_returns.py`. Real Yahoo prices and the course model are used only in manual live verification and are not written to a repository log.
