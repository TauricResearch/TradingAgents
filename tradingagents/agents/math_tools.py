"""Mathematical tools (§3): the engine, callable from an agent's turn.

These tools exist so an analyst can *ask for* a number instead of computing
one. The distinction is the whole point of the task: a model may choose which
metric matters and interpret it, but the arithmetic, the units and the
certification come from code.

Every tool returns structured JSON carrying ``value``, ``formula_id``,
``operands``, ``source_status`` and ``calculation_status`` — the same shape as
``math/metric_record.py`` — so a downstream consumer (the Numeric Claims
validator, the Execution Gate, the audit) can check it without parsing prose.
A tool never returns a bare number that a model could restate.

The tools are deliberately narrow and typed. A ``calculate_financial_ratio``
that accepted arbitrary formulas would be a calculator handed to the model,
which is the defect this work removes.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from tradingagents.dataflows.math.claims import ClaimKind, NumericClaim, check_claim
from tradingagents.dataflows.math.consistency import check_stop_consistency
from tradingagents.dataflows.math.definitions import (
    DefinitionKind,
    MetricIdentity,
    reconcile_definitions,
)
from tradingagents.dataflows.math.metric_record import (
    CalculationStatus,
    SourceStatus,
    metric,
)
from tradingagents.dataflows.math.precision import (
    PERCENT_QUANTUM,
    RATIO_QUANTUM,
    as_decimal,
    cagr,
    convert_unit,
    pct_change,
    quantize,
    safe_ratio,
)
from tradingagents.dataflows.math.registry import MetricRegistry
from tradingagents.dataflows.math.session import assess_bar, assess_series
from tradingagents.dataflows.math.technical import (
    atr_distance,
    average_true_range,
    bollinger_bands,
    distance_from_level,
    exponential_moving_average,
    level_distance_from_price,
    macd,
    relative_strength_index,
    risk_reward_ratio,
    simple_moving_average,
    stop_for_atr_multiple,
    volume_weighted_moving_average,
)
from tradingagents.dataflows.math.valuation import (
    book_value_per_share,
    check_stated_multiple,
    earnings_per_share,
    price_to_book,
    price_to_earnings,
    return_on_equity,
)


def _payload(record) -> str:
    """Serialize a ``MetricRecord`` as the tool's JSON answer."""
    return json.dumps(record.summary(), ensure_ascii=False)


def _refused(name: str, formula_id: str, reason: str, **operands) -> str:
    """A tool answer for input the engine will not compute from.

    Refusing loudly matters: a tool that returned ``null`` would invite the
    model to fill the gap with its own arithmetic, which is exactly what the
    contract forbids.
    """
    return _payload(metric(
        name, None, formula_id=formula_id, operands=operands,
        calculation_status=CalculationStatus.NOT_COMPUTABLE, reason=reason,
    ))


@tool
def calculate_percentage_change(
    new_value: Annotated[float, "The later value"],
    reference_value: Annotated[float, "The baseline the change is measured from"],
) -> str:
    """Percentage change of one value against a reference, computed in code.

    Returns ``(new / reference - 1) * 100``. Use this instead of estimating a
    percentage: a report that states a figure the engine can recompute is
    checked against this, and a disagreement blocks execution.
    """
    value = pct_change(new_value, reference_value)
    if value is None:
        return _refused("percentage_change", "pct_change",
                        "a reference of zero or a missing value has no percentage",
                        new_value=new_value, reference_value=reference_value)
    return _payload(metric(
        "percentage_change", value, unit="percent", formula_id="pct_change",
        operands={"new_value": new_value, "reference_value": reference_value},
    ))


@tool
def calculate_cagr(
    begin_value: Annotated[float, "Value at the start of the period"],
    end_value: Annotated[float, "Value at the end of the period"],
    years: Annotated[float, "Duration in years, stated explicitly"],
) -> str:
    """Compound annual growth rate over an explicit duration, in percent.

    The duration is required rather than inferred from two dates: assuming a
    span is a common source of a plausible-looking wrong rate.
    """
    value = cagr(begin_value, end_value, years)
    if value is None:
        return _refused("cagr", "cagr",
                        "non-positive endpoint or duration: no compound rate exists",
                        begin=begin_value, end=end_value, years=years)
    return _payload(metric(
        "cagr", value, unit="percent", formula_id="cagr",
        operands={"begin": begin_value, "end": end_value, "years": years},
    ))


@tool
def calculate_price_to_book(
    price: Annotated[float, "Share price, in the same class as the book value"],
    book_value_per_share: Annotated[float, "Book value per share, same class"],
    price_class: Annotated[str, "Share class of the price: A, B, or empty for single-class"] = "",
    bvps_class: Annotated[str, "Share class of the book value"] = "",
    period_end: Annotated[str, "Accounting period end of the book value, yyyy-mm-dd"] = "",
    price_period: Annotated[str, "Period the price refers to, yyyy-mm-dd"] = "",
) -> str:
    """Price-to-book with share-class and period consistency enforced.

    Refuses a cross-class comparison (Berkshire's ratio is 1:1500, so mixing
    classes is wrong by that factor) and refuses a book value from a different
    accounting period than the price's.
    """
    if price_class and bvps_class and price_class.upper() != bvps_class.upper():
        return _refused("price_to_book", "price_div_bvps",
                        f"a class-{price_class} price cannot be divided by a "
                        f"class-{bvps_class} book value without conversion",
                        price=price, bvps=book_value_per_share)
    record = price_to_book(price, book_value_per_share,
                           share_class=price_class or None,
                           period_end=price_period or None,
                           bvps_period_end=period_end or None)
    return _payload(record)


@tool
def calculate_book_value_per_share(
    equity: Annotated[float, "Equity attributable to common shareholders"],
    equity_unit: Annotated[str, "Unit of the equity figure: base, thousand, million, billion"] = "base",
    shares: Annotated[float, "Share count on the same basis as the equity"] = 0,
) -> str:
    """Book value per share, converting the equity's unit to base units first.

    Passing millions where base units were meant is a 1,000x error that looks
    entirely normal in the output, so the unit is an explicit argument.
    """
    if not shares:
        return _refused("book_value_per_share", "equity_div_shares",
                        "a share count is required; it is never assumed",
                        equity=equity)
    return _payload(book_value_per_share(equity, shares, equity_unit=equity_unit))


@tool
def calculate_valuation_ratio(
    numerator: Annotated[float, "The ratio's numerator, e.g. price for P/E"],
    denominator: Annotated[float, "The ratio's denominator, e.g. EPS for P/E"],
    ratio: Annotated[
        Literal["pe_trailing", "pe_forward", "earnings_yield", "debt_to_equity", "roe"],
        "Which ratio to compute",
    ],
    basis: Annotated[str, "For P/E and EPS: gaap, adjusted, or operating"] = "gaap",
) -> str:
    """One financial ratio, with its definition recorded in the formula id.

    ``basis`` is part of the identity: a trailing GAAP P/E and a forward
    adjusted one are different metrics, and the record says which was
    computed so the audit can prove they were not interchanged.
    """
    if ratio == "pe_trailing":
        return _payload(price_to_earnings(numerator, denominator, basis=basis))
    if ratio == "pe_forward":
        return _payload(price_to_earnings(numerator, denominator, basis=basis,
                                          forward=True))
    if ratio == "earnings_yield":
        value = safe_ratio(denominator, numerator)
        pct = quantize(value * 100, PERCENT_QUANTUM) if value is not None else None
        return _payload(metric(
            "earnings_yield", pct, unit="percent", formula_id="eps_div_price_pct",
            operands={"eps": denominator, "price": numerator},
        ))
    if ratio == "debt_to_equity":
        return _payload(metric(
            "debt_to_equity", safe_ratio(numerator, denominator), unit="multiple",
            formula_id="total_debt_div_equity",
            operands={"total_debt": numerator, "equity": denominator},
        ))
    if ratio == "roe":
        return _payload(return_on_equity(numerator, denominator))
    return _refused(ratio, "unknown_ratio", f"unknown ratio '{ratio}'")


@tool
def calculate_eps(
    net_income: Annotated[float, "Net income attributable to common shareholders"],
    weighted_average_shares: Annotated[
        float, "Weighted-average shares outstanding — the GAAP EPS denominator"
    ],
    adjusted: Annotated[bool, "Whether this is a non-GAAP adjusted EPS"] = False,
    period_end: Annotated[str, "Period the earnings cover, yyyy-mm-dd"] = "",
) -> str:
    """EPS using the weighted-average share count, not end-of-period shares.

    End-of-period shares divided into a TTM figure produce a plausible but
    wrong number. If only a period-end count is known, the caller should not
    call this tool — the metric is then UNVERIFIED rather than approximated.
    """
    record = earnings_per_share(net_income, weighted_average_shares,
                                adjusted=adjusted, period_end=period_end or None)
    return _payload(record)


@tool
def calculate_indicator(
    indicator: Annotated[
        Literal["sma", "ema", "vwma", "rsi", "macd", "atr", "bollinger"],
        "Which technical indicator",
    ],
    closes: Annotated[list[float], "Closing prices, oldest first"],
    highs: Annotated[list[float] | None, "High prices, same order (ATR only)"] = None,
    lows: Annotated[list[float] | None, "Low prices, same order (ATR only)"] = None,
    volumes: Annotated[list[float] | None, "Volumes, same order (VWMA only)"] = None,
    window: Annotated[int, "Lookback window"] = 20,
) -> str:
    """A technical indicator computed from the series, never eyeballed.

    Returns the indicator with its convention (window, and the standard
    parameters where they are fixed) so a report quoting it can be checked.
    Insufficient history returns NOT_COMPUTABLE rather than a short-window
    number that would mean something different.
    """
    if indicator == "sma":
        value = simple_moving_average(closes, window)
        return _payload(metric("sma", value, unit="price", formula_id=f"sma_{window}",
                               operands={"window": window}))
    if indicator == "ema":
        value = exponential_moving_average(closes, window)
        return _payload(metric("ema", value, unit="price", formula_id=f"ema_{window}",
                               operands={"window": window}))
    if indicator == "vwma":
        value = volume_weighted_moving_average(closes, volumes or [], window)
        return _payload(metric("vwma", value, unit="price", formula_id=f"vwma_{window}",
                               operands={"window": window}))
    if indicator == "rsi":
        value = relative_strength_index(closes, window or 14)
        return _payload(metric("rsi", value, unit="index", formula_id=f"rsi_{window or 14}",
                               operands={"window": window or 14}))
    if indicator == "macd":
        result = macd(closes)
        if result is None:
            return _refused("macd", "macd_12_26_9",
                            "insufficient history for the slow window plus the signal window")
        line, signal, histogram = result
        return json.dumps({
            "metric": "macd",
            "value": str(line),
            "signal": str(signal),
            "histogram": str(histogram),
            "unit": "price",
            "formula_id": "macd_12_26_9",
            "operands": {"fast": 12, "slow": 26, "signal": 9},
            "source_status": str(SourceStatus.VERIFIED),
            "calculation_status": str(CalculationStatus.VERIFIED),
        })
    if indicator == "atr":
        value = average_true_range(highs or [], lows or [], closes, window or 14)
        return _payload(metric("atr", value, unit="price", formula_id=f"atr_wilder_{window or 14}",
                               operands={"window": window or 14}))
    if indicator == "bollinger":
        bands = bollinger_bands(closes, window or 20)
        if bands is None:
            return _refused("bollinger", "bollinger_20_2",
                            "insufficient history or a flat series")
        payload = bands.summary()
        payload["metric"] = "bollinger"
        payload["formula_id"] = "bollinger_20_2"
        payload["source_status"] = str(SourceStatus.VERIFIED)
        payload["calculation_status"] = str(CalculationStatus.VERIFIED)
        return json.dumps(payload, ensure_ascii=False)
    return _refused(indicator, "unknown_indicator", f"unknown indicator '{indicator}'")


@tool
def calculate_price_distance(
    price: Annotated[float, "The price to measure"],
    level: Annotated[float, "The reference level: a moving average, a high, a low"],
) -> str:
    """Percentage distance of a price from a level, signed.

    Negative below the level, positive above — one convention for every
    distance a report quotes, so "+9.46% over SMA50" and "-2.63% from the
    high" cannot drift apart.
    """
    value = distance_from_level(price, level)
    if value is None:
        return _refused("price_distance", "pct_change",
                        "a zero level has no distance", price=price, level=level)
    return _payload(metric(
        "price_distance", value, unit="percent", formula_id="pct_change",
        operands={"price": price, "level": level},
    ))


@tool
def calculate_stop_distance(
    entry: Annotated[float, "The actual or intended entry price"],
    stop: Annotated[float, "The protective stop price"],
    atr: Annotated[float, "ATR over the policy's window"],
    direction: Annotated[Literal["LONG", "SHORT"], "Position direction"] = "LONG",
) -> str:
    """Risk per share, ATR distance, and whether the stop protects anything.

    A stop on the wrong side of the entry returns NOT_COMPUTABLE with that
    reason: the distance from a nonsense price pair would look plausible, and
    the plan protects nothing.
    """
    finding = check_stop_consistency(entry, stop, atr, direction=direction)
    if finding is not None and finding.code == "STOP_WRONG_SIDE":
        return _refused("stop_distance", "entry_minus_stop",
                        finding.message, entry=entry, stop=stop, atr=atr)
    risk_per_share = (entry - stop) if direction == "LONG" else (stop - entry)
    distance = atr_distance(entry, stop, atr, direction=direction)
    return json.dumps({
        "metric": "stop_distance",
        "value": str(quantize(as_decimal(risk_per_share), RATIO_QUANTUM)),
        # 21.00 USD of risk per share on entry 552 and stop 531, at an ATR of
        # 9.397, is 2.23 ATR — computed here, never in prose.
        "atr_distance": str(distance) if distance is not None else None,
        "unit": "price_per_share",
        "formula_id": "entry_minus_stop",
        "operands": {"entry": entry, "stop": stop, "atr": atr,
                     "direction": direction},
        "source_status": str(SourceStatus.VERIFIED),
        "calculation_status": str(CalculationStatus.VERIFIED),
    })


@tool
def calculate_stop_for_atr(
    entry: Annotated[float, "Entry price"],
    atr: Annotated[float, "ATR over the policy's window"],
    atr_multiple: Annotated[float, "Desired stop distance in ATR units"],
    direction: Annotated[Literal["LONG", "SHORT"], "Position direction"] = "LONG",
) -> str:
    """The stop level implied by an ATR multiple.

    Returns a *level*, not an endorsement: the risk engine still decides
    whether that stop is acceptable.
    """
    value = stop_for_atr_multiple(entry, atr, atr_multiple, direction=direction)
    return _payload(metric(
        "stop_level", value, unit="price", formula_id="entry_minus_atr_multiple",
        operands={"entry": entry, "atr": atr, "multiple": atr_multiple,
                  "direction": direction},
    ))


@tool
def calculate_risk_reward(
    entry: Annotated[float, "Entry price"],
    stop: Annotated[float, "Protective stop"],
    target: Annotated[float, "Profit target"],
) -> str:
    """Reward per unit of risk: ``|target-entry| / |entry-stop|``."""
    value = risk_reward_ratio(entry, stop, target)
    if value is None:
        return _refused("risk_reward", "reward_div_risk",
                        "the stop sits at the entry: risk is zero",
                        entry=entry, stop=stop, target=target)
    return _payload(metric(
        "risk_reward", value, unit="multiple", formula_id="reward_div_risk",
        operands={"entry": entry, "stop": stop, "target": target},
    ))


@tool
def convert_money_unit(
    value: Annotated[float, "The amount as reported"],
    from_unit: Annotated[str, "Reported unit: base, thousand, million, billion"],
    to_unit: Annotated[str, "Target unit: base, thousand, million, billion"] = "base",
) -> str:
    """Rescale a money amount between reporting units.

    An unknown unit returns NOT_COMPUTABLE: assuming base units for a figure
    reported in millions is a three-orders-of-magnitude error.
    """
    converted = convert_unit(value, from_unit, to_unit)
    if converted is None:
        return _refused("unit_conversion", "unit_factor",
                        f"unknown unit: {from_unit!r} or {to_unit!r}",
                        value=value, from_unit=from_unit, to_unit=to_unit)
    return _payload(metric(
        "unit_conversion", converted, unit=str(to_unit), formula_id="unit_factor",
        operands={"value": value, "from_unit": from_unit, "to_unit": to_unit},
    ))


@tool
def validate_stated_multiple(
    metric_name: Annotated[str, "Which multiple is being claimed, e.g. price_to_book"],
    claimed_value: Annotated[float, "The value the report states"],
    numerator: Annotated[float, "Numerator the multiple should come from"],
    denominator: Annotated[float, "Denominator the multiple should come from"],
) -> str:
    """Check a multiple a report asserts against the code's own computation.

    Returns MISMATCH when the claim contradicts the arithmetic. A report may
    round; it may not be a different number.
    """
    check = check_stated_multiple(metric_name, claimed_value, numerator,
                                  denominator, formula_id="stated_multiple_check")
    payload = check.summary()
    payload["blocks_decision"] = check.blocks
    return json.dumps(payload, ensure_ascii=False)


@tool
def validate_stated_percentage(
    label: Annotated[str, "What the percentage refers to"],
    claimed_pct: Annotated[float, "The percentage the report states"],
    new_value: Annotated[float, "Later value"],
    reference_value: Annotated[float, "Reference value"],
) -> str:
    """Compare a stated percentage against the computed one.

    A claim that disagrees beyond rounding is recorded as MISMATCH, and the
    audit keeps both numbers so the report can say the claim was wrong rather
    than silently correct it.
    """
    computed = pct_change(new_value, reference_value)
    claim = NumericClaim(
        claim_id=f"tool:{label}", label=label, value=claimed_pct,
        unit="percent", agent="tool", kind=ClaimKind.COMPUTED,
    )
    result = check_claim(claim, computed, formula_id="pct_change")
    payload = result.summary()
    payload["blocks_decision"] = result.blocks
    return json.dumps(payload, ensure_ascii=False)


@tool
def validate_metric_definitions(
    left_definition: Annotated[
        Literal["consolidated", "segment", "adjusted", "operating", "gaap", "unknown"],
        "What the first figure measures",
    ],
    right_definition: Annotated[
        Literal["consolidated", "segment", "adjusted", "operating", "gaap", "unknown"],
        "What the second figure measures",
    ],
    left_period: Annotated[str, "Period of the first figure, e.g. 2026-Q3"] = "",
    right_period: Annotated[str, "Period of the second figure"] = "",
    left_currency: Annotated[str, "Currency of the first figure"] = "",
    right_currency: Annotated[str, "Currency of the second figure"] = "",
    left_unit: Annotated[str, "Unit of the first figure: base, million, billion"] = "",
    right_unit: Annotated[str, "Unit of the second figure"] = "",
) -> str:
    """Whether two figures may be combined into one metric (§5).

    Half of every reported revenue discrepancy is definitional, not
    arithmetic: a segment total against a consolidated one, or adjusted
    against GAAP. Growth across them is well-formed and meaningless, so the
    check has to happen before the division, on what the figures mean.

    An unlabelled figure on either side is refused: two numbers without a
    stated definition are not thereby compatible.
    """
    left = MetricIdentity(
        definition=DefinitionKind(left_definition),
        period=left_period or None,
        currency=left_currency or None,
        unit=left_unit or "base",
    )
    right = MetricIdentity(
        definition=DefinitionKind(right_definition),
        period=right_period or None,
        currency=right_currency or None,
        unit=right_unit or "base",
    )
    verdict = reconcile_definitions(left, right)
    return json.dumps(verdict.summary(), ensure_ascii=False)


@tool
def calculate_distance_from_level(
    price: Annotated[float, "The price"],
    level: Annotated[float, "The reference level: moving average, band, high, low"],
    denominator: Annotated[
        Literal["level", "price"],
        "What the percentage is measured against (§2 case B)",
    ] = "level",
) -> str:
    """Distance between a price and a level, with the denominator named.

    The two conventions are both legitimate and give different answers, because
    a percentage change is not symmetric:

    - ``denominator="level"`` → ``(price / level - 1) * 100``. The 570.89
      close against a 497.723 SMA200 is **+14.70%**.
    - ``denominator="price"`` → ``(level / price - 1) * 100``. The Bollinger
      middle 546.488 against a 573.095 price is **-4.64%**.

    A report that quotes a distance without saying which denominator it used
    cannot be checked; this tool makes the choice explicit so it can be.
    """
    if denominator == "price":
        value = level_distance_from_price(price, level)
        formula = "level_div_price"
    else:
        value = distance_from_level(price, level)
        formula = "price_div_level"
    if value is None:
        return _refused("distance_from_level", formula,
                        "a zero denominator has no percentage",
                        price=price, level=level, denominator=denominator)
    return _payload(metric(
        f"distance_from_level_{denominator}", value, unit="percent",
        formula_id=formula,
        operands={"price": price, "level": level, "denominator": denominator},
    ))


@tool
def calculate_eps_change(
    eps_ttm: Annotated[float, "Trailing-twelve-month EPS"],
    eps_forward: Annotated[float, "Forward EPS estimate"],
) -> str:
    """Percentage change from TTM to forward EPS, signed by direction.

    The 19:24 report claimed a 37% contraction where 22.43 against 39.76 is
    **-43.59%**. Both figures are on the same basis, so the comparison is
    legitimate; only the arithmetic was wrong, and this is the arithmetic.
    """
    value = pct_change(eps_forward, eps_ttm)
    if value is None:
        return _refused("eps_change", "pct_change",
                        "EPS TTM of zero has no percentage change",
                        eps_ttm=eps_ttm, eps_forward=eps_forward)
    return _payload(metric(
        "eps_change_ttm_to_forward", value, unit="percent",
        formula_id="pct_change",
        operands={"eps_ttm": eps_ttm, "eps_forward": eps_forward},
    ))


@tool
def calculate_quantity_sensitivity(
    previous_atr: Annotated[float, "ATR before the change"],
    new_atr: Annotated[float, "ATR after the change"],
    previous_qty: Annotated[int, "Quantity sized with the previous ATR"],
) -> str:
    """How a quantity changes when ATR changes, at constant monetary risk.

    At a fixed risk budget and the same ATR multiple, the quantity is
    inversely proportional to ATR, so it scales by ``previous_atr / new_atr``.
    ATR 6.36 to 9.524 therefore cuts the size by **33.22%**, not the
    "40-50%" the report asserted without a calculation.
    """
    from tradingagents.dataflows.risk_engine import quantity_sensitivity_to_atr

    result = quantity_sensitivity_to_atr(previous_atr, new_atr,
                                         previous_qty=previous_qty)
    return json.dumps(result.summary(), ensure_ascii=False)


@tool
def validate_market_bar(
    bar_timestamp: Annotated[str, "Timestamp of the price bar, ISO 8601"],
    analysis_time: Annotated[str, "When the analysis runs, ISO 8601"] = "",
) -> str:
    """Whether a bar is a final end-of-day close or still forming.

    A strategy that requires a confirmed close must not be decided on a
    partial bar: the price it uses is still moving.
    """
    assessment = assess_bar(bar_timestamp, analysis_time=analysis_time or None)
    return json.dumps(assessment.summary(), ensure_ascii=False)


@tool
def validate_market_series(
    timestamps: Annotated[list[str], "Bar timestamps, oldest first"],
    analysis_time: Annotated[str, "When the analysis runs, ISO 8601"] = "",
) -> str:
    """Whether a series' last bar is partial, so an indicator can declare it."""
    return json.dumps(
        assess_series(timestamps, analysis_time=analysis_time or None),
        ensure_ascii=False,
    )


@tool
def validate_trade_proposal(
    entry: Annotated[float, "Proposed entry price"],
    stop: Annotated[float, "Proposed stop price"],
    atr: Annotated[float, "ATR used for the stop policy"],
    direction: Annotated[Literal["LONG", "SHORT"], "Direction"] = "LONG",
    stated_atr_distance: Annotated[float, "ATR multiple the report claims"] = 0,
) -> str:
    """Check a proposal's own numbers before it can become an executable order.

    Reports whether the stop protects the position and whether the stated ATR
    distance matches the entry, stop and ATR that produced it.
    """
    finding = check_stop_consistency(entry, stop, atr, direction=direction,
                                     stated_atr_distance=stated_atr_distance or None)
    if finding is None:
        return json.dumps({
            "status": "OK",
            "blocks_decision": False,
            "atr_distance": str(atr_distance(entry, stop, atr, direction=direction)),
        })
    payload = finding.summary()
    payload["blocks_decision"] = finding.blocks
    return json.dumps(payload, ensure_ascii=False)


@tool
def get_certified_metric(
    metric_name: Annotated[str, "Metric to read from this run's registry"],
    ticker: Annotated[str, InjectedState("company_of_interest")] = "",
) -> str:
    """Read a verified metric from the run's registry, or report it unverified.

    This is how a report should quote a number: by its certified value, not
    by restating whatever an earlier model wrote. A metric the engine never
    computed is UNVERIFIED here, which is the honest answer — and one that
    cannot authorize an order.
    """
    registry = _run_registry()
    record = registry.get(metric_name) if registry is not None else None
    if record is None:
        return json.dumps({
            "metric": metric_name,
            "value": None,
            "ticker": ticker,
            "source_status": str(SourceStatus.MISSING),
            "calculation_status": str(CalculationStatus.UNSUPPORTED),
            "reason": "the engine has not computed this metric in this run",
            "blocks_decision": True,
        })
    return _payload(record)


# The run's registry, attached by the graph before the agents run. A module
# global is deliberate: the tool functions are invoked by LangGraph without a
# handle to the run, and a per-run dict keyed by run id would be no safer.
_REGISTRY: MetricRegistry | None = None


def _run_registry() -> MetricRegistry | None:
    return _REGISTRY


def set_run_registry(registry) -> None:
    """Attach this run's metric registry so the tools can read it."""
    global _REGISTRY
    _REGISTRY = registry


MATH_TOOLS = [
    calculate_percentage_change,
    calculate_cagr,
    calculate_price_to_book,
    calculate_book_value_per_share,
    calculate_valuation_ratio,
    calculate_eps,
    calculate_indicator,
    calculate_price_distance,
    calculate_distance_from_level,
    calculate_eps_change,
    calculate_quantity_sensitivity,
    calculate_stop_distance,
    calculate_stop_for_atr,
    calculate_risk_reward,
    convert_money_unit,
    validate_stated_multiple,
    validate_stated_percentage,
    validate_metric_definitions,
    validate_market_bar,
    validate_market_series,
    validate_trade_proposal,
    get_certified_metric,
]
"""Every mathematical tool, for a graph node to bind in one place."""

# The market analyst reasons about prices and indicators, so it gets the
# measurement tools and the bar validator: a distance from a moving average,
# an ATR or "is this bar a real close" are all questions it must ask rather
# than answer.
TOOLS_FOR_MARKET = (
    calculate_indicator,
    calculate_price_distance,
    calculate_distance_from_level,
    calculate_quantity_sensitivity,
    calculate_stop_distance,
    calculate_stop_for_atr,
    calculate_risk_reward,
    calculate_percentage_change,
    validate_market_bar,
    validate_market_series,
    get_certified_metric,
)

# The fundamentals analyst reasons about valuation, so it gets the metrics
# whose arithmetic caused the P/B and EPS defects, plus the multiple checker
# that refuses a figure contradicting them.
TOOLS_FOR_FUNDAMENTALS = (
    calculate_price_to_book,
    calculate_eps_change,
    calculate_book_value_per_share,
    calculate_valuation_ratio,
    calculate_eps,
    calculate_percentage_change,
    calculate_cagr,
    convert_money_unit,
    validate_stated_multiple,
    validate_stated_percentage,
    validate_metric_definitions,
    get_certified_metric,
)
