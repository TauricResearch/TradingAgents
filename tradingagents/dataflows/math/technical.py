"""Technical math (§2C): indicators and the distances derived from them.

Providers already compute indicators; this module exists for a different
reason. A report says "price is 4.5% above SMA200 and 11.3% below the
52-week high" — and those two figures were computed by a language model
from numbers it saw in a table. This module recomputes every derived
technical quantity from the verified series, so the claim can be checked
rather than believed.

Indicators here are *verification* implementations, not a trading library:
they follow the standard definitions (Wilder's ATR and RSI, the common EMA
seeding, MACD 12/26/9, Bollinger 20/2) and are written to be obviously
correct against an independent calculation. If a vendor's ATR differs
slightly because of its own seeding convention, the difference is visible
in the audit rather than hidden.

Every function is pure, ticker-agnostic, and returns ``None`` where the
series is too short rather than a number computed from insufficient data.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from tradingagents.dataflows.math.precision import (
    as_decimal,
    pct_change,
    quantize,
)

# Standard parameters. Named so a report can state the convention it used.
DEFAULT_SMA_WINDOWS = (50, 200)
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
RSI_PERIOD = 14
ATR_PERIOD = 14
BOLLINGER_PERIOD = 20
BOLLINGER_STDDEV = 2.0


def _numbers(series: Sequence[object] | None) -> list[float] | None:
    """A clean ``float`` series, or ``None`` if any point is unusable.

    A single hole in a moving-average window makes that average wrong, so a
    missing point fails the whole computation rather than being skipped:
    skipping would silently shorten the window and change the indicator's
    meaning.
    """
    if not series:
        return None
    out: list[float] = []
    for point in series:
        decimal = as_decimal(point)
        if decimal is None:
            return None
        out.append(float(decimal))
    return out


def simple_moving_average(series: Sequence[object] | None,
                          window: int) -> Decimal | None:
    """SMA over the last ``window`` points of ``series``.

    Uses the trailing window: ``series`` is oldest-first, so the last
    ``window`` entries are the most recent ones.
    """
    values = _numbers(series)
    if values is None or window <= 0 or len(values) < window:
        return None
    window_values = values[-window:]
    return quantize(Decimal(repr(sum(window_values) / window)),
                    Decimal("0.000001"))


def exponential_moving_average(series: Sequence[object] | None,
                               window: int) -> Decimal | None:
    """EMA with the standard ``k = 2/(window+1)`` smoothing.

    Seeded with the SMA of the first ``window`` points, which is the
    convention most vendors use and the one that makes the first value
    comparable to a published EMA. Fewer than ``window`` points yields
    ``None``.
    """
    values = _numbers(series)
    if values is None or window <= 0 or len(values) < window:
        return None
    k = 2.0 / (window + 1.0)
    ema = sum(values[:window]) / window
    for price in values[window:]:
        ema = price * k + ema * (1.0 - k)
    return quantize(Decimal(repr(ema)), Decimal("0.000001"))


def volume_weighted_moving_average(prices: Sequence[object] | None,
                                   volumes: Sequence[object] | None,
                                   window: int) -> Decimal | None:
    """VWMA over the trailing window: ``sum(price*volume)/sum(volume)``.

    A zero total volume yields ``None`` — the average price of nothing is
    not a price.
    """
    prices_f, volumes_f = _numbers(prices), _numbers(volumes)
    if prices_f is None or volumes_f is None or window <= 0:
        return None
    if len(prices_f) != len(volumes_f) or len(prices_f) < window:
        return None
    window_prices = prices_f[-window:]
    window_volumes = volumes_f[-window:]
    total_volume = sum(window_volumes)
    if total_volume <= 0:
        return None
    weighted = sum(p * v for p, v in zip(window_prices, window_volumes, strict=True))
    return quantize(Decimal(repr(weighted / total_volume)), Decimal("0.000001"))


def true_range(high: float, low: float, previous_close: float | None) -> float:
    """The true range of one bar: max of the three standard spans."""
    if previous_close is None:
        return high - low
    return max(high - low, abs(high - previous_close), abs(low - previous_close))


def average_true_range(highs: Sequence[object] | None, lows: Sequence[object] | None,
                       closes: Sequence[object] | None,
                       period: int = ATR_PERIOD) -> Decimal | None:
    """Wilder's ATR: the smoothed average of the true range.

    Needs ``period + 1`` bars (one for the initial true range against the
    prior close). The first ATR is the simple mean of ``period`` true
    ranges, then Wilder smoothing applies — the published convention.
    """
    highs_f, lows_f, closes_f = _numbers(highs), _numbers(lows), _numbers(closes)
    if highs_f is None or lows_f is None or closes_f is None:
        return None
    if not (len(highs_f) == len(lows_f) == len(closes_f)):
        return None
    if len(closes_f) < period + 1:
        return None
    ranges = [
        true_range(highs_f[i], lows_f[i], closes_f[i - 1])
        for i in range(1, len(closes_f))
    ]
    atr = sum(ranges[:period]) / period
    for value in ranges[period:]:
        atr = (atr * (period - 1) + value) / period
    return quantize(Decimal(repr(atr)), Decimal("0.000001"))


def relative_strength_index(series: Sequence[object] | None,
                            period: int = RSI_PERIOD) -> Decimal | None:
    """Wilder's RSI in 0..100, or ``None`` without enough history.

    A window with no losses gives RSI 100 by definition (limit of the
    formula); a window with no gains gives 0. Those are real values, not
    errors, and are handled explicitly rather than dividing by zero.
    """
    values = _numbers(series)
    if values is None or period <= 0 or len(values) < period + 1:
        return None
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0:
        return Decimal(100) if avg_gain > 0 else Decimal(50)
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return quantize(Decimal(repr(rsi)), Decimal("0.0001"))


def macd(series: Sequence[object] | None, fast: int = MACD_FAST,
         slow: int = MACD_SLOW, signal: int = MACD_SIGNAL
         ) -> tuple[Decimal, Decimal, Decimal] | None:
    """MACD line, signal line and histogram.

    Computed as ``EMA(fast) - EMA(slow)`` on the full series with a proper
    EMA series, so the signal line is the EMA of the MACD line rather than
    of a single point. Returns ``None`` when the series cannot support the
    slow window plus the signal window.
    """
    values = _numbers(series)
    if values is None or len(values) < slow + signal:
        return None

    def ema_series(points: list[float], window: int) -> list[float]:
        k = 2.0 / (window + 1.0)
        out = [sum(points[:window]) / window]
        for price in points[window:]:
            out.append(price * k + out[-1] * (1.0 - k))
        return out

    fast_ema = ema_series(values, fast)
    slow_ema = ema_series(values, slow)
    # Align the two EMA series on their last common length.
    offset = len(fast_ema) - len(slow_ema)
    macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema, strict=True)]
    if len(macd_line) < signal:
        return None
    signal_line = ema_series(macd_line, signal)
    histogram = macd_line[-1] - signal_line[-1]
    q = Decimal("0.000001")
    return (quantize(Decimal(repr(macd_line[-1])), q),
            quantize(Decimal(repr(signal_line[-1])), q),
            quantize(Decimal(repr(histogram)), q))


def standard_deviation(values: Sequence[float], ddof: int = 0) -> float | None:
    """Population (``ddof=0``) or sample standard deviation.

    Bollinger bands use the population form, which is the published default;
    ``ddof`` lets a caller ask for the sample form explicitly.
    """
    n = len(values)
    if n == 0 or n - ddof <= 0:
        return None
    mean_value = sum(values) / n
    variance = sum((v - mean_value) ** 2 for v in values) / (n - ddof)
    return math.sqrt(variance)


@dataclass(frozen=True)
class BollingerBands:
    """The band triple plus the derived figures reports quote.

    Two width percentages are kept separate because they answer different
    questions and are routinely confused (§2 case C):

    ``bandwidth_pct``
        ``(upper - lower) / middle * 100`` — the standard Bollinger
        bandwidth, measured against the band's own centre.
    ``width_over_price_pct``
        ``(upper - lower) / price * 100`` — the band's span as a share of the
        traded price.

    On the regression figures (upper 580.114, lower 512.863, middle 546.488,
    price 573.095) they are 12.31% and 11.73%: both correct, neither
    interchangeable. A report that quotes one number without naming its
    denominator cannot be checked, which is why both carry explicit names.
    """

    upper: Decimal
    middle: Decimal
    lower: Decimal
    bandwidth_pct: Decimal | None
    percent_b: Decimal | None
    width_over_price_pct: Decimal | None = None

    def summary(self) -> dict:
        return {
            "upper": str(self.upper),
            "middle": str(self.middle),
            "lower": str(self.lower),
            "bandwidth_pct": str(self.bandwidth_pct) if self.bandwidth_pct is not None else None,
            "bandwidth_denominator": "middle",
            "width_over_price_pct": (
                str(self.width_over_price_pct)
                if self.width_over_price_pct is not None else None
            ),
            "width_over_price_denominator": "price",
            "percent_b": str(self.percent_b) if self.percent_b is not None else None,
        }


def bollinger_bands(series: Sequence[object] | None, window: int = BOLLINGER_PERIOD,
                    deviations: float = BOLLINGER_STDDEV,
                    price: object | None = None) -> BollingerBands | None:
    """Bollinger bands over the trailing window, with bandwidth and %B.

    ``bandwidth_pct = (upper - lower) / middle * 100`` and
    ``%B = (price - lower) / (upper - lower)``. %B needs a price — the
    latest close is assumed when none is given. A zero-width band (a flat
    series) makes %B undefined, so it is ``None`` rather than a division by
    zero reported as infinity.
    """
    values = _numbers(series)
    if values is None or window <= 0 or len(values) < window:
        return None
    window_values = values[-window:]
    middle = sum(window_values) / window
    stdev = standard_deviation(window_values)
    if stdev is None or middle == 0:
        return None
    q = Decimal("0.000001")
    upper = middle + deviations * stdev
    lower = middle - deviations * stdev
    bandwidth = (upper - lower) / middle * 100.0

    last = as_decimal(price) if price is not None else as_decimal(values[-1])
    percent_b = None
    if last is not None and (upper - lower) != 0:
        percent_b = quantize((last - Decimal(repr(lower))) / Decimal(repr(upper - lower)),
                             Decimal("0.0001"))
    # The band span as a share of the price — a different metric from the
    # bandwidth above, with a different denominator, so a different name.
    width_over_price = None
    if last is not None and last != 0:
        width_over_price = quantize(
            Decimal(repr(upper - lower)) / last * Decimal(100),
            Decimal("0.0001"),
        )
    return BollingerBands(
        upper=quantize(Decimal(repr(upper)), q),
        middle=quantize(Decimal(repr(middle)), q),
        lower=quantize(Decimal(repr(lower)), q),
        bandwidth_pct=quantize(Decimal(repr(bandwidth)), Decimal("0.0001")),
        width_over_price_pct=width_over_price,
        percent_b=percent_b,
    )


def distance_from_level(price: object, level: object,
                        quantum: Decimal = Decimal("0.0001")) -> Decimal | None:
    """How far the **price** sits from a level, as a share of the level.

    ``((price / level) - 1) * 100``. Negative when below, positive when
    above — so "-2.63% from the high" and "+9.46% over SMA50" come from one
    implementation and cannot drift apart.

    The denominator is the **level**. Its converse, where the *level* is
    measured against the *price*, is a different metric with a different
    denominator and a different answer — see ``level_distance_from_price``.
    """
    return pct_change(price, level, quantum=quantum)


def level_distance_from_price(price: object, level: object,
                              quantum: Decimal = Decimal("0.0001")
                              ) -> Decimal | None:
    """How far a **level** sits from the price, as a share of the price.

    ``((level / price) - 1) * 100``. The 19:24 report quoted the Bollinger
    middle against the price this way: ``(546.488 / 573.095 - 1) * 100``
    is -4.64%, whereas measuring the price against the middle gives +4.87%.

    The two are **not** negatives of each other, because a percentage change
    is not symmetric: -4.64% and +4.87% describe the same pair of numbers
    under different denominators. Keeping one function for both would make
    the validator reject a correct figure, which is why the denominator is
    part of the metric's identity rather than an implementation detail.
    """
    return pct_change(level, price, quantum=quantum)


def fibonacci_retracement(high: object, low: object,
                          ratios: Sequence[float] = (0.236, 0.382, 0.5, 0.618, 0.786)
                          ) -> dict[str, Decimal] | None:
    """Retracement levels measured down from ``high`` toward ``low``.

    Returned as labels -> price. An inverted or zero range yields ``None``:
    a retracement of a non-range is not a level.
    """
    high_d, low_d = as_decimal(high), as_decimal(low)
    if high_d is None or low_d is None or high_d <= low_d:
        return None
    span = high_d - low_d
    q = Decimal("0.0001")
    return {f"{ratio:.3f}": quantize(high_d - span * Decimal(repr(ratio)), q)
            for ratio in ratios}


def risk_reward_ratio(entry: object, stop: object,
                      target: object) -> Decimal | None:
    """Reward per unit of risk: ``|target-entry| / |entry-stop|``.

    A LONG and a SHORT are both handled by the absolute distances, and a
    zero risk distance yields ``None`` — the ratio does not exist when the
    stop sits at the entry.
    """
    entry_d, stop_d, target_d = as_decimal(entry), as_decimal(stop), as_decimal(target)
    if entry_d is None or stop_d is None or target_d is None:
        return None
    risk = abs(entry_d - stop_d)
    if risk == 0:
        return None
    return quantize(abs(target_d - entry_d) / risk, Decimal("0.0001"))


def atr_distance(entry: object, stop: object, atr: object,
                 direction: str = "LONG") -> Decimal | None:
    """Stop distance in ATR units, signed by the position's side (§7).

    ``risk_per_share / atr`` with ``risk_per_share = entry - stop`` for a
    LONG and ``stop - entry`` for a SHORT. A stop on the wrong side returns
    ``None`` — the caller's side check is what reports the hazard, and
    computing a distance from a nonsense price pair would produce a
    plausible-looking number for a plan that protects nothing.
    """
    entry_d, stop_d, atr_d = as_decimal(entry), as_decimal(stop), as_decimal(atr)
    if entry_d is None or stop_d is None or atr_d is None or atr_d <= 0:
        return None
    if direction.upper() == "LONG":
        risk = entry_d - stop_d
    elif direction.upper() == "SHORT":
        risk = stop_d - entry_d
    else:
        return None
    if risk <= 0:
        return None
    return quantize(risk / atr_d, Decimal("0.0001"))


def stop_for_atr_multiple(entry: object, atr: object, multiple: object,
                          direction: str = "LONG") -> Decimal | None:
    """The stop level implied by an ATR multiple — the inverse of §7's test.

    For LONG 557.00 with ATR 9.408 at 2.5x this is 533.48, the arithmetic the
    task names explicitly. The result is a *level*, not an endorsement: the
    risk engine still decides whether that stop is acceptable.
    """
    entry_d, atr_d, mult = as_decimal(entry), as_decimal(atr), as_decimal(multiple)
    if entry_d is None or atr_d is None or mult is None or mult <= 0:
        return None
    distance = atr_d * mult
    q = Decimal("0.0001")
    if direction.upper() == "LONG":
        return quantize(entry_d - distance, q)
    if direction.upper() == "SHORT":
        return quantize(entry_d + distance, q)
    return None
