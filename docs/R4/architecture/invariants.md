# R4 Invariants

This page lists constraints that must hold for R4. See the [trace matrix](trace-matrix.md) for implementation and evidence links.

1. **Complete window:** The holding period counts the ticker's trading sessions. Fewer than `holding_period_days + 1` closes, or benchmark data that does not cover the exit date, must produce no outcome or reflection.
2. **Nonnegative fees:** Cost bps and minimum commission cannot be negative. The effective per-side rate must be below 100%. A positive minimum commission requires a finite, positive assumed notional.
3. **Gross/net relationship:** For valid returns and nonnegative fees, `net_return <= gross_return`. Net alpha falls by the same cost difference as return. A zero fee leaves both figures unchanged.
4. **Switch compatibility:** With cost adjustment disabled, settlement, the log, and the reflection prompt retain the gross-return behavior.
5. **Settle once:** A `(ticker, trade_date)` decision is stored once. A pending entry becomes resolved only after reflection succeeds; a failure remains retryable.
6. **Time boundary:** The resolution date is the trading date of the exit close. Historical analyses read only reflections resolved by their analysis date, never future outcomes.
7. **Legacy measurement basis:** Old resolved entries lack a cost-policy marker and cannot automatically be treated as net-return data.

`tests/test_cost_adjusted_returns.py` covers fixed-price examples and failure paths. Existing memory tests also cover log idempotency and point-in-time filtering.
