"""Experimental leg detection with Reference Card 1 boundary formulas."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Literal

import pandas as pd

from tradingagents.surge.scorecard import ScoreEvidence, score_evidence

BOUNDARY_VERSION = "surge-card-20260501-boundaries-v1"


@dataclass(frozen=True)
class DetectorConfig:
    atr_period: int = 14
    max_base_candles: int = 4
    max_base_body_fraction: float = 0.5
    max_base_range_atr: float = 1.0
    min_impulse_body_atr: float = 0.8
    min_impulse_body_fraction: float = 0.6
    structure_lookback: int = 10

    def __post_init__(self):
        for value in (self.atr_period, self.max_base_candles, self.structure_lookback):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Lookbacks and candle counts must be positive integers")
        for value in (self.max_base_body_fraction, self.min_impulse_body_fraction):
            if not math.isfinite(value) or not 0 < value <= 1:
                raise ValueError("Body fractions must be in (0, 1]")
        for value in (self.max_base_range_atr, self.min_impulse_body_atr):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("ATR thresholds must be finite and positive")


@dataclass(frozen=True)
class Zone:
    zone_id: str
    symbol: str
    timeframe: str
    pattern: str
    side: Literal["Demand", "Supply"]
    leg_in: str
    formation: str
    base_end: str
    confirmed_at: str
    proximal: float
    distal: float
    width: float
    base_candles: int
    departure_body_atr: float
    departure_distance_atr: float
    relative_volume: float | None
    bos: bool
    fvg: bool
    rule_version: str = BOUNDARY_VERSION
    detection_version: str = "experimental-single-leg-v1"
    status: str = "confirmed; lifecycle not evaluated"
    official_score: None = None
    score_explanation: str = "Partial: only Time has automatically verified evidence"


def zone_boundaries(
    pattern: str, leg_in: pd.DataFrame, base: pd.DataFrame, leg_out: pd.DataFrame
) -> tuple[float, float]:
    """Card 1 p1, body-edge proximal option; caller supplies identified leg spans.

    Reversals include the incoming leg in distal extrema; continuations exclude
    it. Both include the whole departing leg. This does not validate segmentation.
    """
    if pattern not in ("RBR", "DBR", "RBD", "DBD"):
        raise ValueError("Unknown Supply/Demand pattern")
    if any(part.empty for part in (leg_in, base, leg_out)):
        raise ValueError("Leg in, base and leg out must be nonempty")
    parts = [leg_in, base, leg_out] if pattern in ("DBR", "RBD") else [base, leg_out]
    span = pd.concat(parts)
    demand = pattern[-1] == "R"
    proximal = float(
        base[["open", "close"]].max().max() if demand else base[["open", "close"]].min().min()
    )
    distal = float(span.low.min() if demand else span.high.max())
    return proximal, distal


def zone_scorecard(zone: Zone):
    """Only base count is verified automatically; do not equate BOS with card breakout."""
    return score_evidence(
        ScoreEvidence(as_of=zone.confirmed_at, side=zone.side, base_candles=zone.base_candles)
    )


def validate_bars(bars):
    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(bars):
        raise ValueError("Bars need open, high, low, close, volume")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("Bar index must contain aware completion timestamps")
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("Bars must be uniquely sorted chronologically")
    values = bars[list(required)]
    if values.isna().any().any() or not values.map(math.isfinite).all().all():
        raise ValueError("Bars contain non-finite OHLCV")
    if (
        (bars[["open", "high", "low", "close"]] <= 0).any().any()
        or (bars.volume < 0).any()
        or (bars.high < bars[["open", "close", "low"]].max(axis=1)).any()
        or (bars.low > bars[["open", "close", "high"]].min(axis=1)).any()
    ):
        raise ValueError("Invalid OHLCV relationships")


def detect_zones(bars: pd.DataFrame, symbol: str, config=None, *, as_of=None) -> list[Zone]:
    """Confirm only at departure close. Only prefix values contribute to each zone.

    Longest compact base wins when nested alternatives share one departure.
    ATR is a simple rolling true-range mean shifted one bar. Card 1 bounds are
    applied to experimental single-candle leg spans, not certified segmentation.
    BOS is a trailing-high/low close break, not a controlling-swing algorithm.
    """
    config = config or DetectorConfig()
    validate_bars(bars)
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is None:
            raise ValueError("as_of must be timezone aware")
        bars = bars.loc[bars.index <= cutoff]
    if bars.empty:
        return []
    high, low, close = bars.high, bars.low, bars.close
    body = (close - bars.open).abs()
    ranges = high - low
    tr = pd.concat([ranges, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(
        axis=1
    )
    # Reset the warmup after gaps or price-scale changes.
    discontinuities = pd.Series(False, index=bars.index)
    for column in ("adjustment_break", "gap_before"):
        if column in bars:
            discontinuities |= bars[column].fillna(True).astype(bool)
    groups = discontinuities.cumsum()
    atr = tr.groupby(groups).transform(
        lambda series: series.rolling(config.atr_period).mean().shift(1)
    )
    zones = []

    def impulse(index, baseline):
        return (
            body.iloc[index] >= baseline * config.min_impulse_body_atr
            and ranges.iloc[index] > 0
            and body.iloc[index] / ranges.iloc[index] >= config.min_impulse_body_fraction
        )

    for depart in range(config.atr_period + 2, len(bars)):
        baseline = atr.iloc[depart]
        if pd.isna(baseline) or baseline <= 0 or not impulse(depart, baseline):
            continue
        bullish = close.iloc[depart] > bars.open.iloc[depart]
        for count in range(config.max_base_candles, 0, -1):
            first, incoming = depart - count, depart - count - 1
            if incoming < config.atr_period or pd.isna(atr.iloc[incoming]):
                continue
            # Neither pattern context nor indicator warmup can bridge missing data/actions.
            context_start = max(0, incoming - config.structure_lookback)
            if discontinuities.iloc[context_start : depart + 1].any():
                continue
            base = bars.iloc[first:depart]
            base_range = ranges.iloc[first:depart]
            if (base_range <= 0).any():
                continue
            if (body.iloc[first:depart] / base_range > config.max_base_body_fraction).any():
                continue
            if base.high.max() - base.low.min() > baseline * config.max_base_range_atr:
                continue
            if not impulse(incoming, atr.iloc[incoming]):
                continue
            if bullish and close.iloc[depart] <= base.high.max():
                continue
            if not bullish and close.iloc[depart] >= base.low.min():
                continue
            arriving_up = close.iloc[incoming] > bars.open.iloc[incoming]
            pattern = ("R" if arriving_up else "D") + "B" + ("R" if bullish else "D")
            proximal, distal = zone_boundaries(
                pattern, bars.iloc[incoming:first], base, bars.iloc[depart : depart + 1]
            )
            if proximal == distal:
                continue
            context = bars.iloc[max(0, first - config.structure_lookback) : first]
            bos = bool(
                close.iloc[depart] > context.high.max()
                if bullish
                else close.iloc[depart] < context.low.min()
            )
            fvg = bool(
                low.iloc[depart] > high.iloc[depart - 2]
                if bullish
                else high.iloc[depart] < low.iloc[depart - 2]
            )
            volume = bars.volume.iloc[max(0, depart - config.atr_period) : depart].mean()
            fingerprint = json.dumps(
                [
                    BOUNDARY_VERSION,
                    symbol,
                    bars.index[depart].isoformat(),
                    pattern,
                    proximal,
                    distal,
                    asdict(config),
                ],
                sort_keys=True,
            )
            zones.append(
                Zone(
                    zone_id=hashlib.sha256(fingerprint.encode()).hexdigest()[:20],
                    symbol=symbol,
                    timeframe="1d",
                    pattern=pattern,
                    side="Demand" if bullish else "Supply",
                    leg_in=bars.index[incoming].isoformat(),
                    formation=bars.index[first].isoformat(),
                    base_end=bars.index[depart - 1].isoformat(),
                    confirmed_at=bars.index[depart].isoformat(),
                    proximal=proximal,
                    distal=distal,
                    width=abs(proximal - distal),
                    base_candles=count,
                    departure_body_atr=float(body.iloc[depart] / baseline),
                    departure_distance_atr=float(abs(close.iloc[depart] - proximal) / baseline),
                    relative_volume=float(bars.volume.iloc[depart] / volume)
                    if volume > 0
                    else None,
                    bos=bos,
                    fvg=fvg,
                )
            )
            break
    return zones
