"""JFTS Forces: the "market forces" indicator set of the JFTS AutoTrader, on daily bars.

Ported from the NinjaTrader 8 add-on ``JFTSAutoTrader.dll`` (assembly
JFTSAutoTrader 2.0.0.35). Its CIL bodies were read statically, without loading
or running the assembly, and the bar logic of its seven indicators is
reproduced here. Where the source depends on NinjaTrader's runtime, the
adaptation is noted next to it.

The indicators and how they feed one another:

* ``JFTSForcesRV`` — the engine. Each bar is classified as part of a bull leg
  (higher high and higher low than the bar before) or a bear leg (lower high,
  low not above); an inside or outside bar keeps the leg it is in. Completed
  legs are kept, newest first, in lists of ``chart_stop_period`` entries
  (high, low, end bar and the leg's amplitude against the opposite leg before
  it). The highest bull-leg high and the lowest bear-leg low of those lists
  feed two EMAs with period ``chart_stop_period``: ``EMAFilterHigh`` and
  ``EMAFilterLow``. A high above ``EMAFilterHigh`` makes the bar "ready" for
  bulls; a low below ``EMAFilterLow`` for bears. It also tracks sideways
  ranges: a leg that stays inside the previous opposite leg.
* ``JFTSForcesStop`` — ``EMAFilterLow`` is the long stop and ``EMAFilterHigh``
  the short stop, rounded to the tick, with the close's distance to each in
  ticks.
* ``JFTSForcesPatterns`` — six entry patterns on the leg lists: ``0`` (two
  doji bars with equal highs/lows, confirmed by a two-bar breakout), ``1``
  (1B: the first shallow pullback after an impulse more than ``rate_1b_spike``
  times the pullback before it), ``2`` (2B: two contained pullbacks, the latest
  leg making a new extreme), ``L`` (a ladder of three rising leg highs and
  pullback lows), ``R`` (the ladder breaking its sideways range) and ``Rx`` (a
  sideways range of at least ``chart_stop_period`` pullbacks broken). One
  pattern is taken per pullback leg, and a pattern is not repeated on the next
  bar.
* ``JFTSForcesFreeToGo`` — the entry signal: long when the bar is ready for
  bulls *and* a long pattern fired *and* the long stop is below the close
  (short mirrored); otherwise none.
* ``JFTSForcesBookAB`` — "volume pressure", the dominance of buying over
  selling in [-100, 100]. Away from live bid/ask data the add-on uses each
  candle's body (in ticks) as its volume, summed per session.
* ``JFTSForcesSession`` / ``JFTSForcesCore`` — the trading-hours window, the
  session's change from its open, and the chart panels and alerts. On daily
  bars every bar is inside the window.

Adaptations for daily bars, which the add-on was not written for:

* NinjaTrader computes on the first tick of a new bar, reading the bars that
  just closed. This port runs once per completed daily bar with the same
  offsets, as NinjaTrader does on historical bars. A bar's high and low are
  therefore the whole day's, and a signal on a date is knowable at its close.
* Volume pressure is summed over a rolling ``pressure_window`` of bars instead
  of being reset every session, since on daily bars a session is one bar.
* The tick size is not known from daily bars; it is ``tick_size`` when given,
  else 0.01 (0.0001 below a price of 1). It sets the doji tests of pattern
  ``0``, the rounding of the stops and the stop distances in ticks.
* The add-on's order management, account-risk and target logic (the
  ``JFTSAutoTrader`` strategy itself) places orders and is not ported.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradingagents.dataflows.strategy_indicators.calc import Result, day, num

PATTERN_NAMES: dict[str, str] = {
    "0": "0D (double doji breakout)",
    "1": "1B (first pullback after a spike)",
    "2": "2B (second contained pullback)",
    "L": "L (ladder)",
    "R": "R (ladder breaking its range)",
    "Rx": "Rx (sideways range breakout)",
}
PATTERN_ORDER: tuple[str, ...] = ("0", "1", "2", "L", "R", "Rx")


@dataclass(frozen=True)
class JFTSParams:
    """The add-on's inputs, with its defaults.

    ``Rate1BPullBack`` and ``PBQtyForRange`` are inputs of the add-on too, but
    no calculation reads them, so they are left out.
    """

    chart_stop_period: int = 4
    rate_1b_spike: float = 2.0
    patterns: tuple[str, ...] = PATTERN_ORDER
    tick_size: float | None = None
    pressure_window: int = 20


DEFAULT_PARAMS = JFTSParams()


def default_tick(close: pd.Series) -> float:
    return 0.0001 if float(close.median()) < 1 else 0.01


def _round_tick(value: float, tick: float) -> float:
    return round(value / tick) * tick


# ---------------------------------------------------------------------------
# JFTSForcesRV: legs, sideways ranges and the EMA filter
# ---------------------------------------------------------------------------


class _RV:
    """Bar-by-bar state of ``JFTSForcesRV``; series are indexed by bar."""

    def __init__(self, o, h, lo, c, n_period: int):
        self.h, self.lo, self.c = h, lo, c
        self.N = n_period
        n = len(c)
        f = lambda: np.zeros(n)  # noqa: E731
        self.ema_low, self.ema_high, self.var_min, self.var_max = f(), f(), f(), f()
        self.bears_low, self.bulls_high, self.bears_low_last, self.bulls_high_last = f(), f(), f(), f()
        self.ready_bulls, self.ready_bears = f(), f()
        # pullback (leg) series
        self.pb = {side: {k: f() for k in ("start", "end", "high", "low", "bars", "amp", "rate")}
                   for side in ("bulls", "bears")}
        self.bullish = np.zeros(n, dtype=bool)
        self.bearish = np.zeros(n, dtype=bool)
        # sideways series
        self.sw = {side: {k: f() for k in ("start", "end", "high", "low", "bars", "pbs")}
                   for side in ("bulls", "bears")}
        # lists, newest first
        self.li = {side: {k: [] for k in ("end", "high", "low", "rate")} for side in ("bulls", "bears")}
        self.li_bulls_sorted: list[float] = []
        self.li_bears_sorted: list[float] = []
        self.last_bulls: list[float] = []
        self.last_bears: list[float] = []
        # scalar state
        self.in_bears = self.in_bulls = False
        self.sideway = 0
        self.sideway_pbs = 0
        self.high_range_bulls = self.high_range_bears = float(np.finfo(float).max)
        self.low_range_bulls = self.low_range_bears = 0.0

    def update(self, t: int) -> None:
        if t < self.N:
            self._warm_up(t)
            return
        self._pullbacks(t)
        self._sideway(t)
        self._lists(t)
        self._filter(t)
        self._sideway_occurs(t)
        self.ready_bulls[t] = 1.0 if self.h[t] > self.ema_high[t] else 0.0
        self.ready_bears[t] = -1.0 if self.lo[t] < self.ema_low[t] else 0.0

    def _warm_up(self, t: int) -> None:
        x = self.c[t]  # NinjaTrader's Input: the close
        for arr in (self.ema_low, self.ema_high, self.var_min, self.var_max, self.bears_low, self.bulls_high,
                    self.bears_low_last, self.bulls_high_last):
            arr[t] = x
        for side in ("bulls", "bears"):
            p = self.pb[side]
            p["start"][t] = p["end"][t] = p["amp"][t] = p["bars"][t] = p["rate"][t] = 0.0
            p["high"][t] = p["low"][t] = x
            li = self.li[side]
            li["end"].insert(0, float(t))
            li["high"].insert(0, x)
            li["low"].insert(0, x)
            li["rate"].insert(0, 0.0)
            s = self.sw[side]
            s["start"][t] = s["end"][t] = s["bars"][t] = s["pbs"][t] = 0.0
            s["high"][t] = s["low"][t] = x
        self.li_bulls_sorted.insert(0, x)
        self.li_bears_sorted.insert(0, x)
        if len(self.last_bulls) <= self.N:
            self.last_bears.insert(0, x)
            self.last_bulls.insert(0, x)

    def _pullbacks(self, t: int) -> None:
        h, lo = self.h, self.lo
        delta_min = abs(lo[t - 1] - lo[t - 2])
        delta_max = abs(h[t - 1] - h[t - 2])
        self.var_min[t] = max(lo[t - 1], lo[t - 2]) - delta_min
        self.var_max[t] = min(h[t - 1], h[t - 2]) + delta_max
        bears = bulls = False
        if self.var_max[t] > h[t - 1] and self.var_min[t] == lo[t - 1]:
            bears = True
        elif self.var_min[t] < lo[t - 1] and self.var_max[t] == h[t - 1]:
            bulls = True
        if not bears and not bulls:  # inside or outside bar: stay in the leg
            if self.bearish[t - 1]:
                bears = True
            else:
                bulls = True
        self.bullish[t], self.bearish[t] = bulls, bears
        for side, active, attr in (("bears", bears, "in_bears"), ("bulls", bulls, "in_bulls")):
            p = self.pb[side]
            if active and not getattr(self, attr):
                setattr(self, attr, True)
                p["start"][t], p["end"][t] = t - 2, t - 1
                p["high"][t], p["low"][t] = h[t - 1], lo[t - 1]
                p["amp"][t] = h[t - 1] - lo[t - 1]
                p["bars"][t] = 1
            elif active:
                p["start"][t], p["end"][t] = p["start"][t - 1], t - 1
                p["high"][t] = max(p["high"][t - 1], self.var_max[t])
                p["low"][t] = min(p["low"][t - 1], self.var_min[t])
                p["amp"][t] = p["high"][t] - p["low"][t]
                p["bars"][t] = p["bars"][t - 1] + 1
            else:
                setattr(self, attr, False)
                for k in ("start", "end", "high", "low", "amp", "bars"):
                    p[k][t] = p[k][t - 1]
        bu, be = self.pb["bulls"], self.pb["bears"]
        if self.bullish[t - 1]:
            be["rate"][t] = be["rate"][t - 1]
            bu["rate"][t] = bu["amp"][t - 1] / be["amp"][t - 1] if be["amp"][t - 1] != 0 else bu["rate"][t - 1]
        else:
            bu["rate"][t] = bu["rate"][t - 1]
            be["rate"][t] = be["amp"][t - 1] / bu["amp"][t - 1] if bu["amp"][t - 1] != 0 else be["rate"][t - 1]

    def _sideway(self, t: int) -> None:
        bu, be = self.pb["bulls"], self.pb["bears"]
        if (self.sideway and t - bu["start"][t] == 2) or t - be["start"][t] == 2:
            self.sideway_pbs += 1
        if self.sideway == 1 and (self.h[t] > self.high_range_bulls or self.lo[t] < self.low_range_bulls):
            self.sideway = 0
        if self.sideway == -1 and (self.h[t] > self.high_range_bears or self.lo[t] < self.low_range_bears):
            self.sideway = 0
        sb, sr = self.sw["bulls"], self.sw["bears"]
        for s in (sb, sr):
            for k in ("start", "high", "low"):
                s[k][t] = s[k][t - 1]
        if self.sideway == 0:
            for s in (sb, sr):
                s["bars"][t], s["pbs"][t], s["end"][t] = s["bars"][t - 1], 0.0, s["end"][t - 1]
        elif self.sideway == 1:
            sr["bars"][t], sr["pbs"][t], sr["end"][t] = sr["bars"][t - 1] + 1, self.sideway_pbs, t
            sb["bars"][t], sb["pbs"][t], sb["end"][t] = sb["bars"][t - 1], sb["pbs"][t - 1], sb["end"][t - 1]
        else:
            sr["bars"][t], sr["pbs"][t], sr["end"][t] = sr["bars"][t - 1], sr["pbs"][t - 1], sr["end"][t - 1]
            sb["bars"][t], sb["pbs"][t], sb["end"][t] = sb["bars"][t - 1] + 1, self.sideway_pbs, t

    def _lists(self, t: int) -> None:
        # A leg that just started closes the opposite one: file it, newest first.
        for opened, closed in (("bulls", "bears"), ("bears", "bulls")):
            flag = self.bullish if opened == "bulls" else self.bearish
            if flag[t] and self.pb[opened]["bars"][t] == 1:
                li, p = self.li[closed], self.pb[closed]
                if len(li["end"]) == self.N:
                    for k in li:
                        li[k].pop()
                li["end"].insert(0, float(round(p["end"][t])))
                li["high"].insert(0, p["high"][t])
                li["low"].insert(0, p["low"][t])
                li["rate"].insert(0, p["rate"][t])
                return

    def _filter(self, t: int) -> None:
        self.bulls_high[t] = max(self.li["bulls"]["high"])
        self.bears_low[t] = min(self.li["bears"]["low"])
        if self.bears_low[t] != self.bears_low[t - 1]:
            self.last_bears.insert(0, self.bears_low[t])
        if self.bulls_high[t] != self.bulls_high[t - 1]:
            self.last_bulls.insert(0, self.bulls_high[t])
        if len(self.last_bears) > self.N:
            self.last_bears.pop()
        if len(self.last_bulls) > self.N:
            self.last_bulls.pop()
        self.bears_low_last[t] = self.last_bears[-1]
        self.bulls_high_last[t] = self.last_bulls[-1]
        alpha = 2.0 / (1 + self.N)
        self.ema_low[t] = self.bears_low_last[t] * alpha + (1 - alpha) * self.ema_low[t - 1]
        self.ema_high[t] = self.bulls_high_last[t] * alpha + (1 - alpha) * self.ema_high[t - 1]

    def _sideway_occurs(self, t: int) -> None:
        if self.sideway:
            return
        bu, be = self.pb["bulls"], self.pb["bears"]
        sb, sr = self.sw["bulls"], self.sw["bears"]
        if t - bu["start"][t] == 2 and bu["high"][t] <= be["high"][t] and bu["low"][t] >= be["low"][t]:
            self.sideway, self.sideway_pbs = 1, 1
            self.high_range_bulls, self.low_range_bulls = be["high"][t], be["low"][t]
            sr["start"][t], sr["high"][t], sr["low"][t] = t - 2, be["high"][t], be["low"][t]
            sr["bars"][t], sr["pbs"][t], sr["end"][t] = be["bars"][t] + 2, 1, t
        if t - be["start"][t] == 2 and be["high"][t] <= bu["high"][t] and be["low"][t] >= bu["low"][t]:
            self.sideway, self.sideway_pbs = -1, 1
            self.high_range_bears, self.low_range_bears = bu["high"][t], bu["low"][t]
            sb["start"][t], sb["high"][t], sb["low"][t] = t - 2, bu["high"][t], bu["low"][t]
            sb["bars"][t], sb["end"][t] = bu["bars"][t] + 2, t


# ---------------------------------------------------------------------------
# JFTSForcesPatterns
# ---------------------------------------------------------------------------


class _Patterns:
    def __init__(self, rv: _RV, o, h, lo, c, params: JFTSParams, tick: float):
        self.rv, self.o, self.h, self.lo, self.c = rv, o, h, lo, c
        self.p, self.tick = params, tick
        n = len(c)
        self.ready = np.zeros(n)
        self.entry_leg = np.zeros(n)
        self.pattern = [""] * n
        self.entry_bar = 0
        self.entry_leg_seen = 0.0
        self.breakout_high = self.breakout_low = False

    def update(self, t: int) -> None:
        h, lo = self.h, self.lo
        self.breakout_high = t >= 2 and h[t] > max(h[t - 1], h[t - 2])
        self.breakout_low = t >= 2 and lo[t] < min(lo[t - 1], lo[t - 2])
        if t < 5:
            self.ready[t], self.pattern[t] = 0.0, ""
            return
        self._entry(t)
        rv = self.rv
        self.entry_leg[t] = max(rv.pb["bears"]["start"][t - 1], rv.pb["bulls"]["start"][t - 1])
        self._occurs(t)

    def _mark(self, t: int, side: int, name: str) -> None:
        self.ready[t], self.pattern[t] = side, name
        self.entry_bar = t
        self.entry_leg_seen = self.entry_leg[t - 1]

    def _entry(self, t: int) -> None:
        if self.entry_bar == t:
            self.ready[t] = self.ready[t - 1]
        elif self.entry_leg_seen == self.entry_leg[t - 1] and self.entry_bar:
            self.ready[t], self.pattern[t] = 0.0, ""  # one pattern per pullback leg
        else:
            self.entry_bar = 0
            self.pattern[t] = ""

    def _occurs(self, t: int) -> None:
        if self.entry_bar:
            return
        self.pattern[t] = ""
        checks = {"0": self._p0, "1": self._p1, "2": self._p2, "L": self._pL, "R": self._pR, "Rx": self._pRx}
        for name in PATTERN_ORDER:
            if name in self.p.patterns and self.pattern[t - 1] != name:
                checks[name](t)
        if self.pattern[t] == "0" and (
            (self.ready[t] == 1 and not self.breakout_high) or (self.ready[t] == -1 and not self.breakout_low)
        ):
            self.pattern[t], self.ready[t] = "", 0.0
            self.entry_bar = 0

    def _ticks(self, x: float) -> int:
        return int(round(abs(x) / self.tick))

    def _p0(self, t: int) -> None:
        o, h, lo, c = self.o, self.h, self.lo, self.c
        size, body = 3, 1
        if (self._ticks(h[t - 1] - lo[t - 1]) <= size and self._ticks(h[t - 2] - lo[t - 2]) <= size
                and self._ticks(c[t - 1] - o[t - 1]) <= body and self._ticks(c[t - 2] - o[t - 2]) <= body):
            if self.rv.bullish[t]:
                if abs(h[t - 1] - h[t - 2]) < self.tick:
                    self._mark(t, 1, "0")
            elif self.rv.bearish[t] and abs(lo[t - 1] - lo[t - 2]) < self.tick:
                self._mark(t, -1, "0")

    def _p1(self, t: int) -> None:
        bu, be = self.rv.li["bulls"], self.rv.li["bears"]
        if (self.rv.bullish[t] and be["high"][0] < bu["high"][0] and be["low"][0] > bu["low"][0]
                and bu["rate"][0] > self.p.rate_1b_spike):
            self._mark(t, 1, "1")
        if (self.rv.bearish[t] and bu["high"][0] < be["high"][0] and bu["low"][0] > be["low"][0]
                and be["rate"][0] > self.p.rate_1b_spike):
            self._mark(t, -1, "1")

    def _enough(self, k: int) -> bool:
        li = self.rv.li
        return all(len(li[s][f]) > k for s in ("bulls", "bears") for f in ("high", "low"))

    def _p2(self, t: int) -> None:
        if not self._enough(2):
            return
        bu, be = self.rv.li["bulls"], self.rv.li["bears"]
        if (self.rv.bullish[t] and be["high"][0] < bu["high"][0] and be["low"][0] > bu["low"][0]
                and be["high"][1] < bu["high"][1] and be["low"][1] > bu["low"][1] and bu["high"][0] > bu["high"][1]):
            self._mark(t, 1, "2")
        if (self.rv.bearish[t] and bu["high"][0] < be["high"][0] and bu["low"][0] > be["low"][0]
                and bu["high"][1] < be["high"][1] and bu["low"][1] > be["low"][1] and bu["low"][0] < bu["low"][1]):
            self._mark(t, -1, "2")

    def _ladder_up(self) -> bool:
        bu, be = self.rv.li["bulls"], self.rv.li["bears"]
        return (bu["high"][1] > bu["high"][2] > bu["high"][3] and be["low"][1] > be["low"][2] > be["low"][3]
                and bu["high"][0] > bu["high"][1])

    def _ladder_down(self) -> bool:
        bu, be = self.rv.li["bulls"], self.rv.li["bears"]
        return (be["low"][3] > be["low"][2] > be["low"][1] and bu["high"][3] > bu["high"][2] > bu["high"][1]
                and bu["low"][0] < bu["low"][1])

    def _pL(self, t: int) -> None:
        if not self._enough(3):
            return
        if self.rv.bullish[t] and self._ladder_up():
            self._mark(t, 1, "L")
        if self.rv.bearish[t] and self._ladder_down():
            self._mark(t, -1, "L")

    def _pR(self, t: int) -> None:
        if not self._enough(3):
            return
        sw = self.rv.sw
        if self.rv.bullish[t] and self._ladder_up() and self.h[t] > sw["bulls"]["high"][t - 1]:
            self._mark(t, 1, "R")
        if self.rv.bearish[t] and self._ladder_down() and self.lo[t] < sw["bears"]["low"][t - 1]:
            self._mark(t, -1, "R")

    def _pRx(self, t: int) -> None:
        sw, n = self.rv.sw, self.p.chart_stop_period
        if sw["bulls"]["pbs"][t - 1] >= n and self.h[t] > sw["bulls"]["high"][t - 1]:
            self._mark(t, 1, "Rx")
        if sw["bears"]["pbs"][t - 1] >= n and self.lo[t] < sw["bears"]["low"][t - 1]:
            self._mark(t, -1, "Rx")


# ---------------------------------------------------------------------------
# The whole set
# ---------------------------------------------------------------------------


def volume_pressure(df: pd.DataFrame, window: int, tick: float) -> np.ndarray:
    """JFTSForcesBookAB on historical bars: candle bodies in ticks as volume."""
    o, c = df["Open"].to_numpy(float), df["Close"].to_numpy(float)
    body = np.maximum(1.0, np.abs(c - o) / tick)
    buy = pd.Series(np.where(c >= o, body, 0.0)).rolling(window, min_periods=1).sum().to_numpy()
    sell = -pd.Series(np.where(c < o, body, 0.0)).rolling(window, min_periods=1).sum().to_numpy()
    total = np.abs(buy) + np.abs(sell)
    share_sell = np.where(total == 0, 1.0, sell / np.where(total == 0, 1, total))
    share_buy = np.where(total == 0, 1.0, buy / np.where(total == 0, 1, total))
    hi = np.maximum(np.abs(share_sell), np.abs(share_buy))
    lo = np.minimum(np.abs(share_sell), np.abs(share_buy))
    result = np.where(hi == 0, 0.0, (1 - lo / np.where(hi == 0, 1, hi)) * 100)
    result = np.where(np.abs(share_sell) > np.abs(share_buy), -result, result)
    result[:5] = 0.0
    return result


def jfts_forces(df: pd.DataFrame, params: JFTSParams = DEFAULT_PARAMS) -> pd.DataFrame:
    """Every JFTS Forces series, one row per bar of ``df``."""
    o, h, lo, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    tick = params.tick_size or default_tick(df["Close"])
    n = len(df)
    rv = _RV(o, h, lo, c, params.chart_stop_period)
    pat = _Patterns(rv, o, h, lo, c, params, tick)
    stop_long, stop_short = c.copy(), c.copy()
    long_ticks, short_ticks = np.zeros(n), np.zeros(n)
    signal = np.zeros(n)
    sideways = np.zeros(n, dtype=int)
    for t in range(n):
        rv.update(t)
        sideways[t] = rv.sideway
        pat.update(t)
        if t >= 5:  # JFTSForcesStop
            stop_short[t] = _round_tick(rv.ema_high[t], tick)
            stop_long[t] = _round_tick(rv.ema_low[t], tick)
            short_ticks[t] = round((c[t] - stop_short[t]) / tick)
            long_ticks[t] = round((stop_long[t] - c[t]) / tick)
            # JFTSForcesFreeToGo; on daily bars every bar is in the trading window.
            go_long = rv.ready_bulls[t] == 1 and pat.ready[t] == 1 and long_ticks[t] < 0
            go_short = rv.ready_bears[t] == -1 and pat.ready[t] == -1 and short_ticks[t] < 0
            signal[t] = 1 if go_long else -1 if go_short else 0
    return pd.DataFrame({
        "Date": df["Date"].to_numpy(),
        "Close": c,
        "Leg": np.where(rv.bullish, "bull", np.where(rv.bearish, "bear", "-")),
        "EMAFilterLow": rv.ema_low,
        "EMAFilterHigh": rv.ema_high,
        "StopLong": stop_long,
        "StopShort": stop_short,
        "StopLongTicks": long_ticks,
        "StopShortTicks": short_ticks,
        "ReadyBulls": rv.ready_bulls,
        "ReadyBears": rv.ready_bears,
        "Pattern": pat.pattern,
        "PatternSide": pat.ready,
        "Signal": signal,
        "VolPressure": volume_pressure(df, params.pressure_window, tick),
        "Sideways": np.select([sideways == 1, sideways == -1],
                              ["bull leg inside the last bear leg", "bear leg inside the last bull leg"], "none"),
    })


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _side(x: float) -> str:
    return "long" if x > 0 else "short" if x < 0 else "-"


def _pressure_reading(now: float, prev: float) -> str:
    if now > 0:
        return "buyers dominate, strengthening" if now >= prev else "buyers dominate, weakening"
    if now < 0:
        return "sellers dominate, strengthening" if now <= prev else "sellers dominate, weakening"
    return "balanced"


def compute_jfts_forces(df: pd.DataFrame, since: pd.Timestamp, params: JFTSParams = DEFAULT_PARAMS) -> Result:
    s = jfts_forces(df, params)
    last = s.iloc[-1]
    close = float(last["Close"])
    # The add-on decides a bar's leg on the next bar; line the legs up with their own bars.
    bar_leg = s["Leg"].shift(-1).fillna("pending")
    leg_end = len(s) - 2
    leg = str(bar_leg.iloc[leg_end])
    leg_start = leg_end
    while leg_start > 0 and bar_leg.iloc[leg_start - 1] == leg:
        leg_start -= 1

    signals = s[s["Signal"] != 0]
    shown = signals[signals["Date"] >= since]
    candidates = s[(s["Pattern"] != "") & (s["Date"] >= since)]
    last_signal = signals.iloc[-1] if not signals.empty else None

    if last["Signal"] != 0:
        side = _side(last["Signal"])
        stop = last["StopLong"] if side == "long" else last["StopShort"]
        headline = (f"{side.upper()} entry signal on {day(last['Date'])} (pattern "
                    f"{PATTERN_NAMES[last['Pattern']]}); stop {num(float(stop))}.")
    else:
        where = ("above the high filter" if last["ReadyBulls"] == 1 else
                 "below the low filter" if last["ReadyBears"] == -1 else "inside the filter band")
        headline = (f"No entry signal on {day(last['Date'])}: {leg} leg from {day(s['Date'].iloc[leg_start])}, "
                    f"price {where} ({num(float(last['EMAFilterLow']))}–{num(float(last['EMAFilterHigh']))}).")
        if last_signal is not None:
            headline += f" Last signal: {_side(last_signal['Signal'])} on {day(last_signal['Date'])}."

    vp, vp_prev = float(last["VolPressure"]), float(s["VolPressure"].iloc[-2])
    facts = [
        ("Current leg", f"{leg}, {day(s['Date'].iloc[leg_start])} to {day(s['Date'].iloc[leg_end])} "
                        f"({leg_end - leg_start + 1} bars; the last bar's leg is decided on the next bar)"),
        ("EMA filter high / short stop", f"{num(float(last['EMAFilterHigh']))} / {num(float(last['StopShort']))}"),
        ("EMA filter low / long stop", f"{num(float(last['EMAFilterLow']))} / {num(float(last['StopLong']))}"),
        ("Ready for bulls (high above filter high)", "yes" if last["ReadyBulls"] == 1 else "no"),
        ("Ready for bears (low below filter low)", "yes" if last["ReadyBears"] == -1 else "no"),
        ("Close above long stop", f"{num(close - float(last['StopLong']))} ({(close / float(last['StopLong']) - 1) * 100:+.2f}%)"),
        ("Short stop above close", f"{num(float(last['StopShort']) - close)} ({(float(last['StopShort']) / close - 1) * 100:+.2f}%)"),
        (f"Volume pressure ({params.pressure_window} bars)", f"{vp:+.1f} — {_pressure_reading(vp, vp_prev)}"),
        ("Sideways range", str(last["Sideways"])),
        ("Signals in window", f"{len(shown)} ({int((shown['Signal'] > 0).sum())} long, {int((shown['Signal'] < 0).sum())} short)"),
    ]
    if last_signal is not None:
        facts.append(("Last signal", f"{_side(last_signal['Signal'])} {PATTERN_NAMES[last_signal['Pattern']]} on "
                                     f"{day(last_signal['Date'])} at close {num(float(last_signal['Close']))}"))

    tables = []
    if not shown.empty:
        tables.append(("Entry signals in window", pd.DataFrame({
            "Date": shown["Date"], "Signal": shown["Signal"].map(_side),
            "Pattern": shown["Pattern"].map(PATTERN_NAMES), "Close": shown["Close"],
            "Stop": np.where(shown["Signal"] > 0, shown["StopLong"], shown["StopShort"]),
        })))
    filtered = candidates[candidates["Signal"] == 0]
    if not filtered.empty:
        tables.append(("Patterns not taken (filter or stop disagreed)", pd.DataFrame({
            "Date": filtered["Date"], "Side": filtered["PatternSide"].map(_side),
            "Pattern": filtered["Pattern"].map(PATTERN_NAMES), "Close": filtered["Close"],
            "Ready": np.where(filtered["PatternSide"] > 0, filtered["ReadyBulls"] == 1, filtered["ReadyBears"] == -1),
        })))
    in_window = s["Date"] >= since
    window = s[in_window]
    tables.append(("JFTS Forces", pd.DataFrame({
        "Date": window["Date"], "Close": window["Close"], "Leg": bar_leg[in_window],
        "Filter low": window["EMAFilterLow"], "Filter high": window["EMAFilterHigh"],
        "Vol pressure": window["VolPressure"].round(1),
        "Signal": window["Signal"].map(lambda x: _side(x) if x else ""),
    })))
    notes = [
        "Ported from the JFTS AutoTrader (NinjaTrader 8) Forces indicators; computed on completed daily bars, "
        "so a signal is knowable at that day's close. A bar joins a bull leg on a higher high and higher low, "
        "a bear leg on a lower high; inside and outside bars stay in the leg they are in.",
        "Volume pressure uses candle bodies as volume, as the add-on does away from live bid/ask data, summed "
        f"over {params.pressure_window} bars instead of per session.",
    ]
    return Result(headline, facts, tables, notes)
