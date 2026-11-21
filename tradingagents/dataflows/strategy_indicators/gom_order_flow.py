"""Gom Pro Pack: order-flow footprint, levels, cumulative delta and market profile.

After the NinjaTrader 8 add-on ``GomProPackNT8.dll`` (assembly GomProPackNT8
10.0.0.5, gomicators.com). That assembly is protected with Agile.NET: its
method bodies are encrypted in the file and decrypted only by the protector's
native runtime when the add-on is loaded, so the code was **not** read. This is
a clean-room implementation. What was taken from the assembly is its public
surface, read statically from the metadata with REA: the indicators, their
inputs and outputs, and the option sets of its enums. The calculations follow
the published definitions of the order-flow terms those names use. Where a
name leaves the rule open, the choice made here is stated next to it.

Indicators and their counterparts in the add-on:

* :func:`compute_order_flow` — ``GomOrderFlowProValues``: per session buys,
  sells, delta, its intrabar min/max and which was touched last, the point of
  control, diagonal/horizontal imbalances with two criteria, stacked-imbalance
  support/resistance zones, imbalances and unfinished auctions at the high and
  low, the extreme ratios, COT (delta since the high / low was made) and
  "declining volume" reversals.
* :func:`compute_order_flow_levels` — ``GomOrderFlowProLevels``: naked POCs,
  naked unfinished auctions and the stacked-imbalance zones still active, the
  five nearest above and below the close.
* :func:`compute_cumulative_delta` — ``GomCD``: cumulative delta as an OHLC
  series per session, with its trend and divergence from price.
* :func:`compute_market_profile` — ``GomMPProLevels``: volume (or time) at
  price per day, week and month: POC, value area, VWAP, the previous period's,
  and high/low volume nodes.

Adaptations, because the add-on reads every trade and this port reads bars:

* The add-on classifies each trade as a buy or a sell, by bid/ask (its
  ``BidAsk`` mode) or by up/down tick (``UpDownTick``). Quotes are not
  available here, so the up/down-tick rule is applied to hourly bars: a bar
  that closes above the previous close is buying, below it selling, and an
  unchanged close keeps the last direction. The bar's volume is spread evenly
  over the price levels it traded. Every reading is therefore an estimate of
  the order flow, coarser than a tick footprint.
* A session is one trading day of hourly bars, which Yahoo serves for about
  the last 730 days; older dates have no order-flow reading.
* The price level is ``tick_size × ticks_per_price_level``. With no
  ``ticks_per_price_level`` given it is chosen so that a median day spans about
  ``levels_per_range`` levels, since hourly bars cannot fill a one-tick ladder.
* Volume thresholds of the add-on are in contracts. Here the minimum volume of
  an imbalance's winning side defaults to the session's mean volume per level
  and side, so it scales with the instrument.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tradingagents.dataflows.strategy_indicators.calc import Result, day, num
from tradingagents.dataflows.strategy_indicators.jfts_forces import default_tick
from tradingagents.dataflows.vendors.yahoo.ohlcv import MAX_OHLCV_STALE_DAYS

# The add-on's option sets (enum members of Gom.OrderFlow and Gom.MP).
DIRECTIONS = ("diagonal", "horizontal", "none")                       # ImbalanceDirectionType
COMPARISONS = ("ratio", "difference")                                 # ImbalanceComparisonType
SR_EXITS = ("full_candle_cross", "simple_cross", "poc_cross")         # SRZoneEndConditionType
POC_POSITIONS = ("anywhere", "in_declining_zone", "in_declining_side_half_of_bar",
                 "in_declining_side_third_of_bar")                    # ReversalPocPositionType
PROFILE_DATA = ("volume", "tick")                                     # ProfileData
NEAREST = 5  # the Levels indicator plots five levels on each side


@dataclass(frozen=True)
class GomParams:
    """The add-on's inputs. Its default values are in the encrypted code, so the
    defaults here are this port's choices."""

    tick_size: float | None = None
    ticks_per_price_level: int | None = None
    levels_per_range: int = 20
    imbalance_criterion1_direction: str = "diagonal"
    imbalance_criterion1_comparison: str = "ratio"
    imbalance_criterion1_value: float = 3.0
    imbalance_criterion2_direction: str = "none"
    imbalance_criterion2_comparison: str = "difference"
    imbalance_criterion2_value: float = 0.0
    imbalance_min_winning_side_volume: float | None = None  # None: the session's mean per level and side
    imbalance_max_losing_side_volume: float = 0.0           # 0: no limit
    sr_nb_levels: int = 3
    sr_min_total_volume: float = 0.0
    sr_exit: str = "full_candle_cross"
    min_num_of_declining_levels: int = 3
    imbalance_in_declining_zone_authorized: bool = False
    min_size_of_counter_side_imbalance: int = 0
    reversal_poc_position: str = "anywhere"
    declining_tot_vol_smaller_than_opposite_side_tot_vol: bool = False
    reinit_session: bool = False
    va_percent: float = 0.70
    vn_size: int = 3
    nb_smooth: int = 1
    profile_data: str = "volume"

    def __post_init__(self):
        for value, allowed in ((self.imbalance_criterion1_direction, DIRECTIONS),
                               (self.imbalance_criterion2_direction, DIRECTIONS),
                               (self.imbalance_criterion1_comparison, COMPARISONS),
                               (self.imbalance_criterion2_comparison, COMPARISONS),
                               (self.sr_exit, SR_EXITS), (self.reversal_poc_position, POC_POSITIONS),
                               (self.profile_data, PROFILE_DATA)):
            if value not in allowed:
                raise ValueError(f"{value!r} is not one of {allowed}")


DEFAULT_PARAMS = GomParams()


# ---------------------------------------------------------------------------
# Footprint: one volume-at-price ladder per session
# ---------------------------------------------------------------------------


@dataclass
class Footprint:
    """One session's ladder. Index ``i`` is the price level ``(base + i) × level``."""

    session: pd.Timestamp
    level: float
    base: int
    buys: np.ndarray
    sells: np.ndarray
    neutral: np.ndarray   # volume of bars with no direction yet
    ticks: np.ndarray     # hourly bars that traded the level (the "tick" profile)
    open: float
    high: float
    low: float
    close: float
    vwap: float
    bar_deltas: np.ndarray
    high_bar: int         # last bar that made the session high
    low_bar: int
    stats: dict = field(default_factory=dict)

    @property
    def total(self) -> np.ndarray:
        return self.buys + self.sells + self.neutral

    def price(self, i: int) -> float:
        return (self.base + i) * self.level


def price_level(intraday: pd.DataFrame, params: GomParams = DEFAULT_PARAMS) -> float:
    tick = params.tick_size or default_tick(intraday["Close"])
    if params.ticks_per_price_level:
        return tick * params.ticks_per_price_level
    sessions = intraday.groupby("Session").agg(High=("High", "max"), Low=("Low", "min"))
    median_range = float((sessions["High"] - sessions["Low"]).tail(20).median())
    if not math.isfinite(median_range) or median_range <= 0:
        return tick
    return tick * max(1, round(median_range / max(1, params.levels_per_range) / tick))


def _index(price: float, level: float) -> int:
    return int(round(price / level))


def build_footprints(intraday: pd.DataFrame, level: float) -> list[Footprint]:
    """One :class:`Footprint` per session, classifying bars by the up/down-tick rule.

    The rule's state (last close and direction) runs across sessions, as the
    add-on's ``DeltaCalculator`` keeps ``lastprice`` and ``lastdirection``.
    """
    o = intraday["Open"].to_numpy(float)
    h = intraday["High"].to_numpy(float)
    lo = intraday["Low"].to_numpy(float)
    c = intraday["Close"].to_numpy(float)
    v = intraday["Volume"].to_numpy(float)
    sessions = intraday["Session"].to_numpy()

    direction = np.zeros(len(c), dtype=int)
    last_dir, last_close = 0, None
    for k in range(len(c)):
        if last_close is not None:
            if c[k] > last_close:
                last_dir = 1
            elif c[k] < last_close:
                last_dir = -1
        direction[k] = last_dir
        last_close = c[k]

    out: list[Footprint] = []
    starts = np.r_[0, np.flatnonzero(sessions[1:] != sessions[:-1]) + 1, len(c)]
    for a, b in zip(starts[:-1], starts[1:], strict=True):
        lo_i = np.array([_index(x, level) for x in lo[a:b]])
        hi_i = np.maximum(np.array([_index(x, level) for x in h[a:b]]), lo_i)
        base, top = int(lo_i.min()), int(hi_i.max())
        n = top - base + 1
        buys, sells, neutral, ticks = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
        for k in range(b - a):
            s, e = lo_i[k] - base, hi_i[k] - base + 1
            share = v[a + k] / (e - s)
            target = buys if direction[a + k] > 0 else sells if direction[a + k] < 0 else neutral
            target[s:e] += share
            ticks[s:e] += 1
        bar_deltas = v[a:b] * direction[a:b]
        session_high, session_low = h[a:b].max(), lo[a:b].min()
        typical = (h[a:b] + lo[a:b] + c[a:b]) / 3
        vol = v[a:b].sum()
        out.append(Footprint(
            session=pd.Timestamp(sessions[a]), level=level, base=base,
            buys=buys, sells=sells, neutral=neutral, ticks=ticks,
            open=float(o[a]), high=float(session_high), low=float(session_low), close=float(c[b - 1]),
            vwap=float((typical * v[a:b]).sum() / vol) if vol > 0 else float(typical.mean()),
            bar_deltas=bar_deltas,
            high_bar=int(np.flatnonzero(h[a:b] == session_high)[-1]),
            low_bar=int(np.flatnonzero(lo[a:b] == session_low)[-1]),
        ))
    return out


# ---------------------------------------------------------------------------
# Imbalances, zones, auctions and reversals (GomOrderFlowProValues)
# ---------------------------------------------------------------------------


def _meets(win: float, lose: float, comparison: str, value: float) -> bool:
    if win <= 0:
        return False
    if comparison == "ratio":
        return lose <= 0 or win / lose >= value
    return win - lose >= value


def imbalances(fp: Footprint, params: GomParams = DEFAULT_PARAMS) -> tuple[np.ndarray, np.ndarray]:
    """Buy and sell imbalance flags per level.

    Diagonal compares buys at a level with sells one level below (a buy
    imbalance) and sells at a level with buys one level above (a sell
    imbalance); horizontal compares the two sides of the same level. A level
    outside the ladder has no volume. Both criteria must hold; a criterion whose
    direction is ``none`` is skipped, and with the first one ``none`` there are
    no imbalances. ``imbalance_max_losing_side_volume`` > 0 caps the losing side.
    """
    n = len(fp.buys)
    is_buy, is_sell = np.zeros(n, dtype=bool), np.zeros(n, dtype=bool)
    if params.imbalance_criterion1_direction == "none":
        return is_buy, is_sell
    min_win = params.imbalance_min_winning_side_volume
    if min_win is None:
        min_win = float(fp.buys.sum() + fp.sells.sum()) / (2 * n)
    criteria = [(params.imbalance_criterion1_direction, params.imbalance_criterion1_comparison,
                 params.imbalance_criterion1_value)]
    if params.imbalance_criterion2_direction != "none":
        criteria.append((params.imbalance_criterion2_direction, params.imbalance_criterion2_comparison,
                         params.imbalance_criterion2_value))
    cap = params.imbalance_max_losing_side_volume

    def side(i: int, buy: bool) -> bool:
        win = fp.buys[i] if buy else fp.sells[i]
        if win <= 0 or win < min_win:
            return False
        for direction, comparison, value in criteria:
            if direction == "diagonal":
                j = i - 1 if buy else i + 1
                lose = (fp.sells[j] if buy else fp.buys[j]) if 0 <= j < n else 0.0
            else:
                lose = fp.sells[i] if buy else fp.buys[i]
            if cap > 0 and lose > cap:
                return False
            if not _meets(win, lose, comparison, value):
                return False
        return True

    for i in range(n):
        is_buy[i], is_sell[i] = side(i, True), side(i, False)
    return is_buy, is_sell


def _runs(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    runs, start = [], None
    for i, f in enumerate(np.r_[flags, False]):
        if f and start is None:
            start = i
        elif not f and start is not None:
            if i - start >= min_len:
                runs.append((start, i - 1))
            start = None
    return runs


def _declining(side_vol: np.ndarray, from_top: bool) -> int:
    """Levels over which one side's volume falls, level by level, into the extreme."""
    n, steps = len(side_vol), 0
    while steps + 1 < n:
        a, b = (n - 1 - steps, n - 2 - steps) if from_top else (steps, steps + 1)
        if side_vol[a] < side_vol[b]:
            steps += 1
        else:
            break
    return steps


def _reversal(fp: Footprint, poc: int, is_buy, is_sell, at_top: bool, params: GomParams) -> bool:
    """Declining-volume reversal at one extreme.

    At the high: buying falls level by level into the high over at least
    ``min_num_of_declining_levels`` levels (buyers ran out). The zone is those
    levels. Further filters, as the add-on's inputs name them: no buy imbalance
    in the zone unless authorized, at least ``min_size_of_counter_side_imbalance``
    sell-imbalance levels in it, the POC's position, and buys in the zone below
    sells in it. The low mirrors this with selling.
    """
    side = fp.buys if at_top else fp.sells
    other = fp.sells if at_top else fp.buys
    steps = _declining(side, at_top)
    if steps < max(1, params.min_num_of_declining_levels):
        return False
    n = len(side)
    zone = range(n - 1 - steps, n) if at_top else range(0, steps + 1)
    same_imb, counter_imb = (is_buy, is_sell) if at_top else (is_sell, is_buy)
    if not params.imbalance_in_declining_zone_authorized and any(same_imb[i] for i in zone):
        return False
    if sum(counter_imb[i] for i in zone) < params.min_size_of_counter_side_imbalance:
        return False
    position = params.reversal_poc_position
    if position == "in_declining_zone" and poc not in zone:
        return False
    if position in ("in_declining_side_half_of_bar", "in_declining_side_third_of_bar"):
        part = 2 if position.endswith("half_of_bar") else 3
        reach = (n - 1) / part
        if (at_top and poc < n - 1 - reach) or (not at_top and poc > reach):
            return False
    return not (params.declining_tot_vol_smaller_than_opposite_side_tot_vol
                and sum(side[i] for i in zone) >= sum(other[i] for i in zone))


def _ratio(a: float, b: float) -> float:
    return a / b if b > 0 else float("nan")


def analyse(fp: Footprint, params: GomParams = DEFAULT_PARAMS) -> dict:
    """The ``GomOrderFlowProValues`` outputs of one session (cumulative delta aside)."""
    total = fp.total
    n = len(total)
    top = n - 1
    poc = int(np.argmax(total))  # lowest level on a tie
    is_buy, is_sell = imbalances(fp, params)
    support = [z for z in _runs(is_buy, params.sr_nb_levels)
               if total[z[0]:z[1] + 1].sum() >= params.sr_min_total_volume]
    resist = [z for z in _runs(is_sell, params.sr_nb_levels)
              if total[z[0]:z[1] + 1].sum() >= params.sr_min_total_volume]
    running = np.cumsum(fp.bar_deltas)
    buys, sells = float(fp.buys.sum()), float(fp.sells.sum())
    stats = {
        "Buys": buys, "Sells": sells, "TotalVolume": float(total.sum()), "Delta": buys - sells,
        "MinDelta": float(running.min()), "MaxDelta": float(running.max()),
        # the last bar at the extreme, so a delta that ends at its max "finished" there
        "MaxDeltaTouchedLast": bool(len(running) - 1 - np.argmax(running[::-1])
                                    > len(running) - 1 - np.argmin(running[::-1])),
        "HighCOT": float(fp.bar_deltas[fp.high_bar:].sum()),
        "LowCOT": float(fp.bar_deltas[fp.low_bar:].sum()),
        "POCPrice": fp.price(poc), "PocVolume": float(total[poc]),
        "NbBuyImbalances": int(is_buy.sum()), "VolBuyImbalances": float(fp.buys[is_buy].sum()),
        "NbSellImbalances": int(is_sell.sum()), "VolSellImbalances": float(fp.sells[is_sell].sum()),
        "SupportZones": [(fp.price(a), fp.price(b)) for a, b in support],
        "ResistanceZones": [(fp.price(a), fp.price(b)) for a, b in resist],
        "SupportZoneOnHigh": any(b == top for _, b in support),
        "ResistanceZoneOnLow": any(a == 0 for a, _ in resist),
        "BuyImbalanceOnHigh": bool(is_buy[top]), "SellImbalanceOnHigh": bool(is_sell[top]),
        "BuyImbalanceOnLow": bool(is_buy[0]), "SellImbalanceOnLow": bool(is_sell[0]),
        "BuysAtHigh": float(fp.buys[top]), "SellsAtHigh": float(fp.sells[top]),
        "BuysAtLow": float(fp.buys[0]), "SellsAtLow": float(fp.sells[0]),
        # sellers one level under the high against sellers at it; buyers mirrored at the low
        "RatioHigh": _ratio(fp.sells[top - 1], fp.sells[top]) if n > 1 else float("nan"),
        "RatioLow": _ratio(fp.buys[1], fp.buys[0]) if n > 1 else float("nan"),
        # an auction is unfinished where both sides still traded the extreme
        "HighUA": bool(fp.buys[top] > 0 and fp.sells[top] > 0),
        "LowUA": bool(fp.buys[0] > 0 and fp.sells[0] > 0),
        "BearishReversal": _reversal(fp, poc, is_buy, is_sell, True, params),
        "BullishReversal": _reversal(fp, poc, is_buy, is_sell, False, params),
    }
    fp.stats = stats
    return stats


def order_flow(intraday: pd.DataFrame, params: GomParams = DEFAULT_PARAMS) -> tuple[pd.DataFrame, list[Footprint]]:
    """Per-session order-flow values, with cumulative delta as OHLC (``GomCD``)."""
    level = price_level(intraday, params)
    fps = build_footprints(intraday, level)
    rows, cum = [], 0.0
    for fp in fps:
        s = analyse(fp, params)
        if params.reinit_session:
            cum = 0.0
        path = cum + np.cumsum(fp.bar_deltas)
        rows.append({"Date": fp.session, "Open": fp.open, "High": fp.high, "Low": fp.low, "Close": fp.close,
                     "CumDeltaOpen": cum, "CumDeltaHigh": max(cum, float(path.max())),
                     "CumDeltaLow": min(cum, float(path.min())), "CumDeltaClose": float(path[-1]), **s})
        cum = float(path[-1])
    return pd.DataFrame(rows), fps


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _vol(x: float) -> str:
    if x is None or not math.isfinite(x):
        return "N/A"
    a = abs(x)
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if a >= div:
            return f"{x / div:+.2f}{suffix}" if x < 0 else f"{x / div:.2f}{suffix}"
    return f"{x:.0f}"


def _signed(x: float) -> str:
    return ("+" if x > 0 else "") + _vol(x)


def _away(price: float, close: float) -> str:
    return f"{(price / close - 1) * 100:+.2f}%" if close else "N/A"


def _zones(zones: list[tuple[float, float]]) -> str:
    return ", ".join(f"{num(a)}–{num(b)}" for a, b in zones) or "-"


def _no_volume(intraday: pd.DataFrame) -> bool:
    return float(intraday["Volume"].sum()) <= 0


def _stale(df: pd.DataFrame, intraday: pd.DataFrame) -> Result | None:
    """A reading refused because the hourly bars end well before the daily ones."""
    last_daily, last_hourly = df["Date"].iloc[-1], intraday["Session"].iloc[-1]
    lag = (last_daily - last_hourly).days
    if lag > MAX_OHLCV_STALE_DAYS:
        return Result(f"No order-flow reading: the latest hourly bar is from {day(last_hourly)}, {lag} days "
                      f"before the latest daily bar ({day(last_daily)}).")
    return None


NO_VOLUME = Result("No order-flow reading: the hourly bars carry no volume (an index, a currency pair or "
                   "a thin listing), and order flow is volume by price.")
METHOD_NOTE = ("Estimated from hourly bars by the up/down-tick rule (a bar closing above the previous close "
               "is buying, below it selling), each bar's volume spread over the levels it traded; not tape "
               "data. Clean-room port after the Gom Pro Pack (its code is encrypted and was not read).")


def _since(table: pd.DataFrame, since: pd.Timestamp, minimum: int = 5) -> pd.DataFrame:
    sub = table[table["Date"] >= since]
    return sub if len(sub) >= minimum else table.tail(minimum)


def _date_gap_note(df: pd.DataFrame, intraday: pd.DataFrame) -> list[str]:
    last_daily, last_hourly = df["Date"].iloc[-1], intraday["Session"].iloc[-1]
    if last_hourly < last_daily:
        return [f"The latest hourly session is {day(last_hourly)}, before the latest daily bar "
                f"({day(last_daily)}); order flow is read through {day(last_hourly)}."]
    return []


# ---------------------------------------------------------------------------
# GomOrderFlowProValues
# ---------------------------------------------------------------------------


def compute_order_flow(df: pd.DataFrame, since: pd.Timestamp, intraday: pd.DataFrame,
                       params: GomParams = DEFAULT_PARAMS) -> Result:
    if (refused := _stale(df, intraday)) is not None:
        return refused
    if _no_volume(intraday):
        return NO_VOLUME
    table, fps = order_flow(intraday, params)
    last = table.iloc[-1]
    vol = float(last["TotalVolume"])
    share = last["Delta"] / vol if vol else float("nan")
    finish = "buyers (max delta touched last)" if last["MaxDeltaTouchedLast"] else "sellers (min delta touched last)"
    events = []
    if last["BearishReversal"]:
        events.append("bearish declining-buying reversal at the high")
    if last["BullishReversal"]:
        events.append("bullish declining-selling reversal at the low")
    if last["SupportZones"]:
        events.append(f"{len(last['SupportZones'])} stacked buy-imbalance zone(s)")
    if last["ResistanceZones"]:
        events.append(f"{len(last['ResistanceZones'])} stacked sell-imbalance zone(s)")
    headline = (f"Session {day(last['Date'])}: delta {_signed(last['Delta'])} ({share * 100:+.1f}% of volume), "
                f"finished by {finish}; {int(last['NbBuyImbalances'])} buy / {int(last['NbSellImbalances'])} sell "
                f"imbalances, POC {num(last['POCPrice'])}" + (f"; {', '.join(events)}." if events else "."))

    recent = table.tail(5)
    facts = [
        ("Price level size", f"{num(fps[-1].level)} ({len(fps[-1].buys)} levels in the last session)"),
        ("Buys / sells / volume", f"{_vol(last['Buys'])} / {_vol(last['Sells'])} / {_vol(vol)}"),
        ("Intrabar delta min / max", f"{_signed(last['MinDelta'])} / {_signed(last['MaxDelta'])}"),
        ("COT at high / at low", f"{_signed(last['HighCOT'])} since the high / {_signed(last['LowCOT'])} since the low"),
        ("POC", f"{num(last['POCPrice'])} ({_vol(last['PocVolume'])}; close {_away(last['Close'], last['POCPrice'])} from it)"),
        ("Buy / sell imbalance volume", f"{_vol(last['VolBuyImbalances'])} / {_vol(last['VolSellImbalances'])}"),
        ("Support zones (stacked buy imbalances)", _zones(last["SupportZones"])),
        ("Resistance zones (stacked sell imbalances)", _zones(last["ResistanceZones"])),
        ("At the high", f"buys {_vol(last['BuysAtHigh'])}, sells {_vol(last['SellsAtHigh'])}; "
                        f"{'unfinished auction' if last['HighUA'] else 'auction finished'}; "
                        f"ratio {num(last['RatioHigh'])}"),
        ("At the low", f"buys {_vol(last['BuysAtLow'])}, sells {_vol(last['SellsAtLow'])}; "
                       f"{'unfinished auction' if last['LowUA'] else 'auction finished'}; "
                       f"ratio {num(last['RatioLow'])}"),
        ("Imbalance at the extremes", ", ".join(k for k, f in (
            ("buy on high", last["BuyImbalanceOnHigh"]), ("sell on high", last["SellImbalanceOnHigh"]),
            ("buy on low", last["BuyImbalanceOnLow"]), ("sell on low", last["SellImbalanceOnLow"]),
            ("support zone on high", last["SupportZoneOnHigh"]),
            ("resistance zone on low", last["ResistanceZoneOnLow"])) if f) or "none"),
        ("Delta, last 5 sessions", f"{_signed(float(recent['Delta'].sum()))} "
                                   f"({int((recent['Delta'] > 0).sum())} of 5 positive)"),
        ("Imbalance rule", f"{params.imbalance_criterion1_direction} {params.imbalance_criterion1_comparison} "
                           f"≥ {params.imbalance_criterion1_value:g}"
                           + (f" and {params.imbalance_criterion2_direction} {params.imbalance_criterion2_comparison} "
                              f"≥ {params.imbalance_criterion2_value:g}"
                              if params.imbalance_criterion2_direction != "none" else "")
                           + f"; zones of ≥ {params.sr_nb_levels} levels"),
    ]

    shown = _since(table, since)
    flow = pd.DataFrame({
        "Date": shown["Date"], "Close": shown["Close"], "Volume": shown["TotalVolume"].round().astype(int),
        "Delta": shown["Delta"].round().astype(int),
        "Delta %": (shown["Delta"] / shown["TotalVolume"].where(shown["TotalVolume"] > 0) * 100).round(1),
        "Min delta": shown["MinDelta"].round().astype(int), "Max delta": shown["MaxDelta"].round().astype(int),
        "Finish": np.where(shown["MaxDeltaTouchedLast"], "max", "min"), "POC": shown["POCPrice"],
    })
    structure = pd.DataFrame({
        "Date": shown["Date"], "Buy imb.": shown["NbBuyImbalances"], "Sell imb.": shown["NbSellImbalances"],
        "Support zones": shown["SupportZones"].map(_zones), "Resistance zones": shown["ResistanceZones"].map(_zones),
        "High UA": shown["HighUA"], "Low UA": shown["LowUA"],
        "Reversal": [("bearish" if b else "") + (" / " if b and u else "") + ("bullish" if u else "") or "-"
                     for b, u in zip(shown["BearishReversal"], shown["BullishReversal"], strict=True)],
    })
    return Result(headline, facts, [("Footprint by session", flow), ("Imbalances, zones and auctions", structure)],
                  [METHOD_NOTE, *_date_gap_note(df, intraday)])


# ---------------------------------------------------------------------------
# GomOrderFlowProLevels
# ---------------------------------------------------------------------------


def _zone_ended(kind: str, zl: float, zh: float, later: pd.DataFrame, exit_rule: str) -> bool:
    if later.empty:
        return False
    if kind == "support":
        probe = later["High"] if exit_rule == "full_candle_cross" else \
            later["Close"] if exit_rule == "simple_cross" else later["POCPrice"]
        return bool((probe < zl).any())
    probe = later["Low"] if exit_rule == "full_candle_cross" else \
        later["Close"] if exit_rule == "simple_cross" else later["POCPrice"]
    return bool((probe > zh).any())


def order_flow_levels(table: pd.DataFrame, level: float, params: GomParams = DEFAULT_PARAMS) -> pd.DataFrame:
    """Levels still open after the last session: naked POCs (not traded by a later
    session), naked unfinished auctions (not traded beyond by a later session) and
    stacked-imbalance zones that ``sr_exit`` has not ended."""
    highs, lows = table["High"].to_numpy(float), table["Low"].to_numpy(float)
    last = len(table) - 1
    rows = []
    for t, r in enumerate(table.itertuples(index=False)):
        later = slice(t + 1, None)
        lh, ll = highs[later], lows[later]
        poc = r.POCPrice
        if not ((ll <= poc) & (lh >= poc)).any():
            rows.append({"Kind": "naked POC", "Low": poc, "High": poc, "From": r.Date, "Sessions ago": last - t})
        if r.HighUA and not (lh >= r.High + level / 2).any():
            rows.append({"Kind": "naked UA high", "Low": r.High, "High": r.High, "From": r.Date,
                         "Sessions ago": last - t})
        if r.LowUA and not (ll <= r.Low - level / 2).any():
            rows.append({"Kind": "naked UA low", "Low": r.Low, "High": r.Low, "From": r.Date,
                         "Sessions ago": last - t})
        rest = table.iloc[t + 1:]
        for kind, zones in (("support", r.SupportZones), ("resistance", r.ResistanceZones)):
            for zl, zh in zones:
                if not _zone_ended(kind, zl, zh, rest, params.sr_exit):
                    rows.append({"Kind": f"{kind} zone", "Low": zl, "High": zh, "From": r.Date,
                                 "Sessions ago": last - t})
    return pd.DataFrame(rows, columns=["Kind", "Low", "High", "From", "Sessions ago"])


def _nearest(levels: pd.DataFrame, close: float, above: bool) -> pd.DataFrame:
    if levels.empty:
        return levels
    side = levels[levels["Low"] > close] if above else levels[levels["High"] < close]
    key = (side["Low"] - close) if above else (close - side["High"])
    return side.assign(_k=key).sort_values("_k").head(NEAREST).drop(columns="_k")


def compute_order_flow_levels(df: pd.DataFrame, since: pd.Timestamp, intraday: pd.DataFrame,
                              params: GomParams = DEFAULT_PARAMS) -> Result:
    if (refused := _stale(df, intraday)) is not None:
        return refused
    if _no_volume(intraday):
        return NO_VOLUME
    table, fps = order_flow(intraday, params)
    levels = order_flow_levels(table, fps[-1].level, params)
    close = float(table["Close"].iloc[-1])
    above, below = _nearest(levels, close, True), _nearest(levels, close, False)
    inside = levels[(levels["Low"] <= close) & (levels["High"] >= close)]

    def first(frame: pd.DataFrame, kind: str, edge: str) -> str:
        hit = frame[frame["Kind"] == kind]
        return "none" if hit.empty else f"{num(hit[edge].iloc[0])} ({_away(hit[edge].iloc[0], close)})"

    headline = (f"Close {num(close)}: nearest naked POC above {first(above, 'naked POC', 'Low')}, below "
                f"{first(below, 'naked POC', 'High')}; {int((levels['Kind'] == 'support zone').sum())} support and "
                f"{int((levels['Kind'] == 'resistance zone').sum())} resistance zone(s) still active.")
    facts = [
        ("Sessions scanned", f"{len(table)} ({day(table['Date'].iloc[0])} to {day(table['Date'].iloc[-1])})"),
        ("Naked POCs", str(int((levels["Kind"] == "naked POC").sum()))),
        ("Naked unfinished auctions", str(int(levels["Kind"].str.startswith("naked UA").sum()))),
        ("Nearest support zone below", first(below, "support zone", "High")),
        ("Nearest resistance zone above", first(above, "resistance zone", "Low")),
        ("Zone end rule", params.sr_exit.replace("_", " ")),
    ]
    if not inside.empty:
        facts.append(("Price inside", ", ".join(f"{k} {num(lo)}–{num(hi)}" for k, lo, hi in
                                                inside[["Kind", "Low", "High"]].itertuples(index=False))))

    def shape(frame: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"Kind": frame["Kind"], "Low": frame["Low"], "High": frame["High"],
                             "Distance": [_away((lo if lo > close else hi), close)
                                          for lo, hi in zip(frame["Low"], frame["High"], strict=True)],
                             "From": frame["From"], "Sessions ago": frame["Sessions ago"]})

    tables = []
    for title, kind in (("naked POCs", "naked POC"), ("unfinished auctions", "naked UA"),
                        ("stacked-imbalance zones", " zone")):
        both = pd.concat([above[above["Kind"].str.contains(kind)].iloc[::-1],
                          below[below["Kind"].str.contains(kind)]])
        if not both.empty:
            tables.append((f"Nearest {title} above and below the close", shape(both)))
    return Result(headline, facts, tables, [METHOD_NOTE, *_date_gap_note(df, intraday)])


# ---------------------------------------------------------------------------
# GomCD
# ---------------------------------------------------------------------------


def compute_cumulative_delta(df: pd.DataFrame, since: pd.Timestamp, intraday: pd.DataFrame,
                             params: GomParams = DEFAULT_PARAMS, lookback: int = 20) -> Result:
    if (refused := _stale(df, intraday)) is not None:
        return refused
    if _no_volume(intraday):
        return NO_VOLUME
    table, _ = order_flow(intraday, params)
    cd, price = table["CumDeltaClose"], table["Close"]
    n = min(lookback, len(table) - 1)
    change = float(cd.iloc[-1] - cd.iloc[-1 - n]) if n > 0 else 0.0
    price_change = float(price.iloc[-1] / price.iloc[-1 - n] - 1) if n > 0 else 0.0
    window = table.tail(n + 1)
    divergence = "none"
    if n >= 5:
        p_hi, p_lo = window["High"].iloc[-1] >= window["High"].max(), window["Low"].iloc[-1] <= window["Low"].min()
        cd_hi = window["CumDeltaHigh"].iloc[-1] >= window["CumDeltaHigh"].max()
        cd_lo = window["CumDeltaLow"].iloc[-1] <= window["CumDeltaLow"].min()
        if p_hi and not cd_hi:
            divergence = f"bearish: price at a {n}-session high, cumulative delta not"
        elif p_lo and not cd_lo:
            divergence = f"bullish: price at a {n}-session low, cumulative delta not"
        elif cd_hi and not p_hi:
            divergence = f"bullish: cumulative delta at a {n}-session high, price not"
        elif cd_lo and not p_lo:
            divergence = f"bearish: cumulative delta at a {n}-session low, price not"
    agree = (change > 0) == (price_change > 0)
    headline = (f"Cumulative delta {'rose' if change > 0 else 'fell'} {_signed(change)} over {n} sessions while "
                f"price moved {price_change * 100:+.2f}% ({'confirming' if agree else 'not confirming'}); "
                f"divergence: {divergence}.")
    last = table.iloc[-1]
    up_sessions = int((window["Delta"] > 0).sum())
    facts = [
        ("Cumulative delta (close)", f"{_signed(last['CumDeltaClose'])}"
                                     + (" (reset each session)" if params.reinit_session else
                                        f" since {day(table['Date'].iloc[0])}")),
        ("Last session CD open / high / low / close",
         " / ".join(_signed(last[k]) for k in ("CumDeltaOpen", "CumDeltaHigh", "CumDeltaLow", "CumDeltaClose"))),
        (f"Sessions with positive delta (last {len(window)})", f"{up_sessions} of {len(window)}"),
        ("5-session CD change", _signed(float(cd.iloc[-1] - cd.iloc[-6])) if len(cd) > 5 else "N/A"),
        ("Divergence", divergence),
    ]
    shown = _since(table, since)
    cdt = pd.DataFrame({"Date": shown["Date"], "Close": shown["Close"], "Delta": shown["Delta"].round().astype(int),
                        "CD open": shown["CumDeltaOpen"].round().astype(int),
                        "CD high": shown["CumDeltaHigh"].round().astype(int),
                        "CD low": shown["CumDeltaLow"].round().astype(int),
                        "CD close": shown["CumDeltaClose"].round().astype(int),
                        "Candle": np.where(shown["CumDeltaClose"] >= shown["CumDeltaOpen"], "up", "down")})
    return Result(headline, facts, [("Cumulative delta by session", cdt)],
                  [METHOD_NOTE, *_date_gap_note(df, intraday)])


# ---------------------------------------------------------------------------
# GomMPProLevels
# ---------------------------------------------------------------------------


@dataclass
class ProfileLevels:
    period: str
    start: pd.Timestamp
    poc: float
    vah: float
    val: float
    vwap: float
    hvns: list[float]
    lvns: list[float]


def _merge(fps: list[Footprint], data: str) -> tuple[int, np.ndarray]:
    base = min(fp.base for fp in fps)
    top = max(fp.base + len(fp.buys) - 1 for fp in fps)
    prof = np.zeros(top - base + 1)
    for fp in fps:
        values = fp.ticks if data == "tick" else fp.total
        prof[fp.base - base: fp.base - base + len(values)] += values
    return base, prof


def value_area(prof: np.ndarray, share: float) -> tuple[int, int, int]:
    """POC index and the value area grown from it, one level at a time toward the
    larger neighbour, until it holds ``share`` of the profile."""
    poc = int(np.argmax(prof))
    lo = hi = poc
    target, held = share * prof.sum(), prof[poc]
    while held < target and (lo > 0 or hi < len(prof) - 1):
        below = prof[lo - 1] if lo > 0 else -1.0
        above = prof[hi + 1] if hi < len(prof) - 1 else -1.0
        if above >= below:
            hi += 1
            held += prof[hi]
        else:
            lo -= 1
            held += prof[lo]
    return poc, lo, hi


def volume_nodes(prof: np.ndarray, size: int, smooth: int) -> tuple[list[int], list[int]]:
    """High/low volume nodes: levels that are the strict max (min) of the smoothed
    profile within ``size`` levels on each side, not at the profile's ends."""
    if smooth > 1:
        prof = pd.Series(prof).rolling(smooth, center=True, min_periods=1).mean().to_numpy()
    size = max(1, size)
    hv, lv = [], []
    for i in range(size, len(prof) - size):
        win = np.r_[prof[i - size:i], prof[i + 1:i + size + 1]]
        if prof[i] > win.max():
            hv.append(i)
        elif prof[i] < win.min():
            lv.append(i)
    hv.sort(key=lambda i: -prof[i])
    lv.sort(key=lambda i: prof[i])
    return hv, lv


def profile_levels(fps: list[Footprint], intraday: pd.DataFrame, period: str,
                   params: GomParams = DEFAULT_PARAMS) -> list[ProfileLevels]:
    """Profiles of the last two periods (``D``, ``W`` or ``M``), oldest first."""
    sessions = pd.Series([fp.session for fp in fps])
    keys = sessions.dt.to_period(period)
    out = []
    for key in keys.unique()[-2:]:
        members = [fp for fp, k in zip(fps, keys, strict=True) if k == key]
        base, prof = _merge(members, params.profile_data)
        poc, lo, hi = value_area(prof, params.va_percent)
        level = members[0].level
        bars = intraday[intraday["Session"].dt.to_period(period) == key]
        typical = (bars["High"] + bars["Low"] + bars["Close"]) / 3
        vwap = float((typical * bars["Volume"]).sum() / bars["Volume"].sum()) if bars["Volume"].sum() > 0 \
            else float(typical.mean())
        hv, lv = volume_nodes(prof, params.vn_size, params.nb_smooth)
        out.append(ProfileLevels(str(key), members[0].session, (base + poc) * level, (base + hi) * level,
                                 (base + lo) * level, vwap, [(base + i) * level for i in hv[:NEAREST]],
                                 [(base + i) * level for i in lv[:NEAREST]]))
    return out


def _value_position(close: float, p: ProfileLevels) -> str:
    if close > p.vah:
        return "above value"
    if close < p.val:
        return "below value"
    return "inside value"


def compute_market_profile(df: pd.DataFrame, since: pd.Timestamp, intraday: pd.DataFrame,
                           params: GomParams = DEFAULT_PARAMS) -> Result:
    if (refused := _stale(df, intraday)) is not None:
        return refused
    if params.profile_data == "volume" and _no_volume(intraday):
        params = GomParams(**{**params.__dict__, "profile_data": "tick"})
    level = price_level(intraday, params)
    fps = build_footprints(intraday, level)
    close = fps[-1].close
    rows, by = [], {}
    for code, name in (("D", "Daily"), ("W", "Weekly"), ("M", "Monthly")):
        levels = profile_levels(fps, intraday, code, params)
        by[name] = levels
        for which, p in zip(("previous", "current"), levels[-2:] if len(levels) == 2 else [None, *levels],
                            strict=True):
            if p is None:
                continue
            rows.append({"Period": f"{name} ({which}, {p.period})", "POC": p.poc, "VAH": p.vah, "VAL": p.val,
                         "VWAP": p.vwap, "Close vs value": _value_position(close, p),
                         "Close vs VWAP": _away(close, p.vwap)})
    week, month = by["Weekly"][-1], by["Monthly"][-1]
    prev_week = by["Weekly"][0] if len(by["Weekly"]) == 2 else None
    migration = ""
    if prev_week is not None:
        migration = (f"; the weekly POC moved {'up' if week.poc > prev_week.poc else 'down' if week.poc < prev_week.poc else 'nowhere'}"
                     f" from {num(prev_week.poc)}")
    headline = (f"Close {num(close)} is {_value_position(close, week)} of the week (VAL {num(week.val)} – VAH "
                f"{num(week.vah)}, POC {num(week.poc)}) and {'above' if close >= week.vwap else 'below'} the weekly "
                f"VWAP {num(week.vwap)}{migration}.")
    facts = [
        ("Profile data", f"{params.profile_data} at price, value area {params.va_percent * 100:g}%, level {num(level)}"),
        ("Monthly value", f"{num(month.val)}–{num(month.vah)}, POC {num(month.poc)}, VWAP {num(month.vwap)} "
                          f"({_value_position(close, month)})"),
        ("Weekly high-volume nodes", ", ".join(num(x) for x in sorted(week.hvns)) or "none"),
        ("Weekly low-volume nodes", ", ".join(num(x) for x in sorted(week.lvns)) or "none"),
        ("Monthly high-volume nodes", ", ".join(num(x) for x in sorted(month.hvns)) or "none"),
        ("Monthly low-volume nodes", ", ".join(num(x) for x in sorted(month.lvns)) or "none"),
    ]
    notes = [METHOD_NOTE, *_date_gap_note(df, intraday)]
    if params.profile_data == "tick":
        notes.append("Time at price: each level counts the hourly bars that traded it.")
    return Result(headline, facts, [("Profile levels by period", pd.DataFrame(rows))], notes)
