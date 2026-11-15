# ADR-0001: R4 Settlement Cost Policy

- Status: Adopted by the R4 owner; open to review during team integration
- Scope: Historical decision settlement and reflection, not live trade execution
- Requirement: [R4](../../req/requirements.yaml)

## Context

The original settlement writes price movement directly to the memory log. Later reflection may read that gross return as if it were achievable after fees. The log has no order quantity, currency conversion, or actual broker fee input, so R4 needs an explicit simplified cost assumption.

## Decision

1. The default holding period is five trading sessions. Configuration and `TRADINGAGENTS_HOLDING_DAYS` may override it; nonpositive values are rejected.
2. Cost adjustment is enabled by default. The default cost is 10 bps per side, charged on entry and exit. Minimum commission defaults to zero and assumed notional to 10000.
3. When minimum commission is positive, the effective per-side rate is `max(trading_cost_bps / 10000, min_commission / assumed_trade_notional)`. The two figures are alternative lower bounds for the same side, not additive charges. Commission and notional must use the same currency.
4. Net return is `(1 + gross_return) * (1 - fee)^2 - 1`. Net alpha is `gross_alpha - (gross_return - net_return)`. No separate fee is deducted from the benchmark return.
5. The log keeps its existing fields: net figures are written when costs are enabled, and gross figures when disabled. Reflection receives both gross and net figures in cost-adjusted mode. Legacy entries are not rewritten.

## Alternatives Considered

| Alternative | Reason not selected |
| --- | --- |
| Add bps and minimum commission directly | This can double-count a per-side fee, and a money amount cannot be added directly to a rate. |
| Build an order and cash ledger | Settlement lacks actual fills and quantities; this exceeds the verifiable R4 scope. |
| Keep only gross returns and mention costs in the prompt | The log would still store unadjusted figures as its final assessment. |
| Rewrite all legacy entries as net returns | Historical entries lack the fee and notional needed for reliable recalculation. |

## Consequences and Review

Enabling costs by default changes newly settled values. Comparisons with older results therefore need an isolated log and an explicit measurement basis. `tests/test_cost_adjusted_returns.py` covers the formula, switch, minimum commission, configuration, and failure handling. Manual live results are recorded in `R4测试记录.md` in the parent directory. This policy does not claim that net return equals a realizable trade return.

Actual order notionals, multicurrency commissions, broker fee details, or a need to combine legacy and new entries would trigger a review of this policy and possibly a versioned log field.
