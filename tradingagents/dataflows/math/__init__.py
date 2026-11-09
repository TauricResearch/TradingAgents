"""Financial Math Engine — precision, units and traceable metric records.

This package is the single owner of every financial calculation the
application performs. The architectural rule it enforces:

    providers supply data -> code normalizes and validates -> this engine
    computes -> agents interpret verified results -> the Portfolio Manager
    proposes -> the Execution Gate authorizes any simulated order.

An LLM is not an arithmetic unit and must never be the source of truth for
quantities, multiples, percentages or risk. Anything a decision depends on
is computed here, and carries the formula, the operands and the units that
produced it.

Modules
-------
``precision``
    ``Decimal`` arithmetic, explicit rounding, unit conversion between
    dollars / thousands / millions / billions. Nothing here guesses.
``metric_record``
    The structured record every derived metric is wrapped in, so the audit
    can reproduce the number and the report can show which figures were
    verified and which were refused.
``technical``
    Moving averages, MACD, RSI, ATR, Bollinger bands and the distances
    derived from them.
``claims``
    The numeric-claims validator: compares what an agent asserted against
    the engine's computed values and refuses unsupported figures.

Already-existing modules keep their ownership and are not duplicated here:
``dataflows.arithmetic`` (percentage statements), ``dataflows.valuation``
(BVPS / market cap / P-B with currency and share-class guards),
``dataflows.risk_engine`` (stops, sizing, exposure caps, tranches) and
``dataflows.validator`` (OHLCV, units, currency, share classes).
"""

from tradingagents.dataflows.math.claims import (
    ClaimKind,
    ClaimResult,
    ClaimsReport,
    ClaimVerdict,
    NumericClaim,
    accept_non_fact,
    check_claim,
    check_reports,
    extract_claims,
)
from tradingagents.dataflows.math.consistency import (
    ConsistencyReport,
    Finding,
    FindingKind,
    check_report_consistency,
    check_stop_consistency,
)
from tradingagents.dataflows.math.math_gate import (
    MathVerdict,
    evaluate_math,
    stop_only_math_verdict,
)
from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    MetricRecord,
    SourceStatus,
    metric,
)
from tradingagents.dataflows.math.precision import (
    DEFAULT_ROUNDING,
    MONEY_QUANTUM,
    PERCENT_QUANTUM,
    RATIO_QUANTUM,
    Money,
    Unit,
    annualize,
    as_decimal,
    cagr,
    convert_unit,
    divide,
    mean,
    pct_change,
    percentage_points,
    quantize,
    safe_ratio,
    weighted_mean,
)
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.technical import (
    BollingerBands,
    atr_distance,
    average_true_range,
    bollinger_bands,
    distance_from_level,
    exponential_moving_average,
    fibonacci_retracement,
    macd,
    relative_strength_index,
    risk_reward_ratio,
    simple_moving_average,
    stop_for_atr_multiple,
    volume_weighted_moving_average,
)

__all__ = [
    "DEFAULT_ROUNDING",
    "MONEY_QUANTUM",
    "PERCENT_QUANTUM",
    "RATIO_QUANTUM",
    "BollingerBands",
    "CalculationStatus",
    "ClaimKind",
    "ClaimResult",
    "ClaimVerdict",
    "ClaimsReport",
    "ConsistencyReport",
    "Finding",
    "FindingKind",
    "MathVerdict",
    "MetricRecord",
    "MetricRegistry",
    "Money",
    "NumericClaim",
    "SourceStatus",
    "Unit",
    "accept_non_fact",
    "annualize",
    "as_decimal",
    "atr_distance",
    "average_true_range",
    "bollinger_bands",
    "cagr",
    "check_claim",
    "check_report_consistency",
    "check_reports",
    "check_stop_consistency",
    "convert_unit",
    "distance_from_level",
    "divide",
    "evaluate_math",
    "exponential_moving_average",
    "extract_claims",
    "fibonacci_retracement",
    "macd",
    "mean",
    "metric",
    "pct_change",
    "percentage_points",
    "quantize",
    "relative_strength_index",
    "risk_reward_ratio",
    "safe_ratio",
    "simple_moving_average",
    "stop_for_atr_multiple",
    "stop_only_math_verdict",
    "volume_weighted_moving_average",
    "weighted_mean",
]
