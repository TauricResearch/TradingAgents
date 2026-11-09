# Financial Math Engine

Deterministic calculation and validation for every number a TradingAgents
decision depends on. An LLM is not an arithmetic unit: it may interpret
verified results, never produce them.

```
providers supply data
  -> code normalizes and validates     (dataflows/validator.py, math/precision.py)
  -> the engine computes               (dataflows/math/*, risk_engine.py, valuation.py)
  -> agents interpret verified results (prompts receive metric records)
  -> the Portfolio Manager proposes    (portfolio_decision.py)
  -> the Execution Gate authorizes     (execution_gate.py + math/math_gate.py)
```

## Module map and formula ownership

Each formula has exactly one owner. There are no near-duplicate
implementations, which is what previously let two components disagree about
the same percentage.

| Concern | Owner | Formulas |
|---|---|---|
| Percentage change, distances | `dataflows/arithmetic.py` | `percent_distance`, open→close, close→close |
| Decimal arithmetic, units, CAGR | `dataflows/math/precision.py` | `pct_change`, `convert_unit`, `cagr`, `mean`, `weighted_mean`, `annualize`, `Money` |
| Metric records | `dataflows/math/metric_record.py` | `MetricRecord`, `metric()` — formula, operands, statuses |
| Registry | `dataflows/math/registry.py` | `MetricRegistry` — verified **and refused** metrics |
| Indicators | `dataflows/math/technical.py` | SMA, EMA, VWMA, ATR, RSI, MACD, Bollinger, %B, Fibonacci, R:R, ATR distance |
| Valuation metrics | `dataflows/math/valuation.py` | market cap, EPS (GAAP/adjusted), P/E (trailing/forward), P/B, BVPS, D/E, ROE, ROA, equity/assets, growth, CAGR, dual-class BVPS |
| Valuation reconciliation | `dataflows/valuation.py` | BVPS/market-cap/P-B with currency and share-class guards |
| Numeric claims | `dataflows/math/claims.py` | claim classification, `check_claim`, `extract_claims` |
| Cross-report consistency | `dataflows/math/consistency.py` | stop distance, stale period, share-class mix, rating/order alignment |
| Risk and sizing | `dataflows/risk_engine.py` | stops, stress exit, sizing, exposure cap, tranches, aggregate |
| Gate translation | `dataflows/math/math_gate.py` | engine findings → gate reason codes |

`dataflows/{arithmetic,valuation,validator,risk_engine}.py` predate this work
and keep their ownership; the `math` package composes them rather than
reimplementing them.

## Precision (§3)

Monetary math uses `decimal.Decimal`. Three rules are enforced in
`precision.py` rather than left to callers:

1. **One quantum per domain.** `MONEY_QUANTUM` (0.01), `PERCENT_QUANTUM`
   (0.0001), `RATIO_QUANTUM` (0.0001), applied only at the output boundary.
2. **No float for money.** `as_decimal` converts a `float` through its
   shortest repr, so `570.89` enters as `Decimal("570.89")`, not as the
   binary approximation `570.89000000000004`. A `bool` is rejected.
3. **Nothing is invented.** Missing, non-finite, or zero-denominator input
   yields `None`, never `0.0`.

Rounding is `ROUND_HALF_UP`, not Python's default banker's rounding: 0.125
becomes 0.13, matching a broker statement rather than surprising it.

Units are carried, not assumed. `Money` pairs an amount with a currency and
a `Unit` (base/thousand/million/billion); `convert_unit(761368, MILLION,
BASE)` is `761368000000`. An unlabelled currency is *not* compatible with a
labelled one — "unknown" is not "the same as".

Percentages keep two distinct notions: `pct_change` is a relative change
(4.5% → 5.0% is +11.11%) and `percentage_points` an absolute one (+0.5).

## Metric records (§4, §13)

Every derived metric is a `MetricRecord`:

```json
{
  "metric": "price_to_book",
  "value": "1.4801",
  "unit": "multiple",
  "formula_id": "price_div_bvps",
  "operands": {"price": "570.89", "bvps": "385.70"},
  "period_end": "2026-09-30",
  "source_status": "LLM_CLAIMED",
  "calculation_status": "MISMATCH",
  "llm_claimed_value": "1.3500",
  "difference": "0.1301",
  "tolerance": "0.02",
  "reason": "the stated 1.35 contradicts the computed 1.4801 ..."
}
```

`source_status` and `calculation_status` are separate because they fail for
different reasons: a value a model typed is `LLM_CLAIMED` however plausible,
and a verified input this engine could not compute from produced no number.
A metric is usable only when both are `VERIFIED`.

Refusals are **kept**, not dropped. The audit can therefore show the rejected
1.35x next to the computed 1.4801 and state that the report was wrong,
instead of silently correcting it.

## Share classes (§5)

`dual_class_book_value_per_share` computes

```
B_equivalent = shares_B + shares_A * ratio
BVPS_B       = equity / B_equivalent
```

The ratio is a required parameter (defaulting to Berkshire's 1:1500 charter
term), not a constant applied to every ticker — a single-class issuer passes
nothing and no scaling happens. `validate_share_class_comparison` refuses a
cross-class P/B, which without conversion is wrong by the conversion factor.

## Technical verification (§2C, §6, §7)

Indicators are recomputed from the verified series so a report's claim can be
checked rather than believed. Standard conventions: Wilder's ATR and RSI, EMA
12/26/9 for MACD, Bollinger 20/2 population standard deviation.

Distances use the one `pct_change` convention, so "-2.63% from the high" and
"+9.46% over SMA50" cannot drift apart. `atr_distance` returns `None` for a
wrong-side stop: the side check reports the hazard, and a distance computed
from a nonsense price pair would look plausible.

## Claims validation (§9)

A numeric claim is classified `COMPUTED`, `OBSERVED`, `ESTIMATE`, `FORECAST`,
`SCENARIO` or `UNSUPPORTED`, then compared against the registry:

- `MATCHES` — inside tolerance.
- `MISMATCH` — the engine disproves it; blocks.
- `NOT_CHECKABLE` — no verified value exists; blocks for computed/observed
  claims, because an unverifiable number must not authorize an order.
- `ACCEPTED_NON_FACT` — an estimate or forecast, allowed to inform reasoning
  and never promoted to a fact.

Regex extraction is explicitly **not** the trust boundary. It locates claims
so they can be reported; what blocks execution is the structured comparison
against an engine value. A number regex misses is simply never verified —
the fail-closed direction.

## Execution Gate integration (§11)

`evaluate_math` translates findings into the gate's own vocabulary:

| Finding | Gate reason |
|---|---|
| P/B contradicted or refused | `INVALID_PRICE_TO_BOOK` |
| stop distance ≠ entry/ATR | `INVALID_STOP_ATR_DISTANCE` |
| wrong-side stop | `RISK_PLAN_BLOCKED` |
| other refused valuation | `INVALID_VALUATION_METRIC` |
| contradicted claim | `NUMERIC_CLAIM_CONTRADICTED` |
| unverifiable critical claim | `NUMERIC_CLAIM_UNVERIFIABLE` |
| metric from a stale period | `STALE_FUNDAMENTALS_PERIOD` |

These are appended before the gate's "not yet" logic, so a mathematical
contradiction can never be downgraded to a `WAIT`: a wrong number does not
become right later.

## Known limitations

- **Tolerance is policy, not truth.** A stated multiple within 0.02 of the
  computed one is accepted as rounding. A real error smaller than that would
  pass.
- **The claim extractor is conservative.** A figure written without a
  recognised label is not checked. That is safe (it is never verified) but it
  means unlabelled wrong numbers are not *reported* either.
- **Indicator conventions must match the vendor's.** A vendor using a
  different EMA seed will differ slightly; the audit shows the difference
  instead of hiding it, but the engine does not adjudicate which is correct.
- **Bollinger %B is undefined for a flat series** and returns `None` rather
  than an infinity.
- **No cross-symbol exposure aggregation** here: per-symbol caps are
  enforced, but the total book is only as good as the supplied
  `PortfolioContext`.
