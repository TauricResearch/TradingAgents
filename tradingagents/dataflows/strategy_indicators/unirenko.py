"""UniRenko bars and prior-day levels, on daily bars.

A clean-room equivalent of the EPyF Basic Pack for NinjaTrader 8
(``EPyFBasicPackNT8V1.dll``: the ``EPyFBarsType`` bar type, the
``EPyFCandles`` indicator and ``EPyFPriorDayLevels``). The add-on's
calculation methods are encrypted by its protector (Agile.NET), so its code
was not read. What its metadata does show is the shape:

* ``EPyFBarsType`` keeps ``trendOffset``, ``reversalOffset``, ``openOffset``,
  ``fakeOpen``, ``barMax``/``barMin`` and ``barDirection``: the inputs and
  state of a UniRenko-style bar type.
* ``EPyFCandles`` plots the bar's open, high, low and close plus
  ``EPyFCandleUpEnd`` and ``EPyFCandleDownEnd``: the prices at which the bar in
  progress completes up or down.
* ``EPyFPriorDayLevels`` plots ``PriorHigh``, ``PriorLow`` and ``PriorOpen``.

This module implements the published UniRenko rules those names point to, so
its bricks can differ from EPyF's own:

* The bar in progress started at the close of the last completed bar. It
  completes *up* when price reaches that close plus the trend offset (when the
  last bar was up, or there is none yet) or plus the reversal offset (when the
  last bar was down); *down* mirrored. The completed bar closes exactly at that
  level, so continuation needs one trend offset and a turn needs one reversal
  offset.
* The next bar's drawn open is the completed close moved back by the open
  offset (the "fake open"). It changes how the bar is drawn, not when it
  completes.
* A bar's high and low are the extremes traded while it was forming.

Adaptations for daily bars:

* There are no ticks. Each day is walked as previous close → open → low →
  high → close on an up day (close at or above the open) and open → high →
  low → close on a down day, and every offset crossed on the way completes a
  bar, so one day can complete several bars or none.
* The offsets are in price, not ticks. By default they are multiples of the
  ATR(14) on the last bar on or before the analysis date (trend 0.5, reversal
  1.5, open offset 0 — UniRenko's usual 1:3 trend-to-reversal ratio), rounded
  to the tick, and applied to the whole history. Absolute offsets can be
  given instead.
* The tick size is ``tick_size`` when given, else 0.01 (0.0001 below a
  price of 1), as in :mod:`jfts_forces`.
* The prior day is the previous daily bar.
* ``EPyFOneClickOrders`` (chart order entry) places orders and is not ported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from tradingagents.dataflows.strategy_indicators.calc import Result, atr, day, num


@dataclass(frozen=True)
class UniRenkoParams:
    """Offsets as ATR multiples, or as absolute prices when given."""

    trend_atr: float = 0.5
    reversal_atr: float = 1.5
    open_offset_atr: float = 0.0
    atr_length: int = 14
    trend: float | None = None
    reversal: float | None = None
    open_offset: float | None = None
    tick_size: float | None = None


DEFAULT_PARAMS = UniRenkoParams()


@dataclass(frozen=True)
class Offsets:
    trend: float
    reversal: float
    open_offset: float
    tick: float
    atr: float


def default_tick(close: pd.Series) -> float:
    return 0.0001 if float(close.median()) < 1 else 0.01


def _to_tick(value: float, tick: float) -> float:
    return round(value / tick) * tick


def offsets(df: pd.DataFrame, params: UniRenkoParams = DEFAULT_PARAMS) -> Offsets:
    """The trend, reversal and open offsets in price, on the tick grid."""
    tick = params.tick_size or default_tick(df["Close"])
    vol = float(atr(df, params.atr_length).iloc[-1]) if len(df) >= params.atr_length else math.nan
    if not math.isfinite(vol) or vol <= 0:
        vol = float((df["High"] - df["Low"]).mean())
    if not math.isfinite(vol) or vol <= 0:
        vol = tick

    def size(absolute: float | None, multiple: float, floor: float) -> float:
        raw = absolute if absolute is not None else multiple * vol
        return max(floor, _to_tick(raw, tick))

    trend = size(params.trend, params.trend_atr, tick)
    reversal = size(params.reversal, params.reversal_atr, tick)
    open_offset = min(size(params.open_offset, params.open_offset_atr, 0.0), trend)
    return Offsets(trend, reversal, open_offset, tick, vol)


class _Engine:
    """The UniRenko state machine, fed one price move at a time."""

    def __init__(self, start: float, off: Offsets):
        self.off = off
        self.eps = off.tick * 1e-6
        self.direction = 0  # of the last completed bar; 0 before the first
        self.base = start  # close of the last completed bar
        self.open = self.high = self.low = start
        self.bricks: list[tuple[int, float, float, float, float, int]] = []

    def up_end(self) -> float:
        return self.base + (self.off.reversal if self.direction < 0 else self.off.trend)

    def down_end(self) -> float:
        return self.base - (self.off.reversal if self.direction > 0 else self.off.trend)

    def _complete(self, level: float, direction: int, bar: int) -> None:
        high, low = max(self.high, level), min(self.low, level)
        self.bricks.append((bar, self.open, high, low, level, direction))
        self.direction, self.base = direction, level
        self.open = level - direction * self.off.open_offset
        self.high, self.low = max(level, self.open), min(level, self.open)

    def move(self, p0: float, p1: float, bar: int) -> None:
        if p1 > p0:
            while p1 >= self.up_end() - self.eps:
                self._complete(self.up_end(), 1, bar)
        elif p1 < p0:
            while p1 <= self.down_end() + self.eps:
                self._complete(self.down_end(), -1, bar)
        self.high, self.low = max(self.high, p1), min(self.low, p1)


def _day_path(o: float, h: float, lo: float, c: float) -> tuple[float, ...]:
    return (o, lo, h, c) if c >= o else (o, h, lo, c)


def unirenko(df: pd.DataFrame, params: UniRenkoParams = DEFAULT_PARAMS) -> tuple[pd.DataFrame, pd.DataFrame, Offsets]:
    """Completed bars, the end-of-day state of the bar in progress, and the offsets used.

    The bars frame has one row per completed bar (the date it completed on);
    the daily frame one row per input bar with the open bar's levels at that
    day's close: ``UpEnd``/``DownEnd`` are EPyFCandles' CandleUpEnd and
    CandleDownEnd.
    """
    off = offsets(df, params)
    o, h, lo, c = (df[k].to_numpy(dtype=float) for k in ("Open", "High", "Low", "Close"))
    eng = _Engine(_to_tick(o[0], off.tick), off)
    rows = []
    prev = eng.base
    for t in range(len(df)):
        before = len(eng.bricks)
        path = (prev, *_day_path(o[t], h[t], lo[t], c[t]))
        for p0, p1 in zip(path[:-1], path[1:], strict=True):
            eng.move(p0, p1, t)
        prev = c[t]
        rows.append({
            "Date": df["Date"].iloc[t], "Close": c[t], "Direction": eng.direction,
            "BarOpen": eng.open, "BarHigh": eng.high, "BarLow": eng.low, "Base": eng.base,
            "UpEnd": eng.up_end(), "DownEnd": eng.down_end(), "Completed": len(eng.bricks) - before,
        })
    daily = pd.DataFrame(rows)
    bricks = pd.DataFrame(eng.bricks, columns=["Bar", "Open", "High", "Low", "Close", "Direction"])
    bricks.insert(0, "Date", df["Date"].iloc[bricks["Bar"]].to_numpy() if len(bricks) else pd.Series(dtype="datetime64[ns]"))
    bricks["Reversal"] = bricks["Direction"].ne(bricks["Direction"].shift()) & bricks.index.to_series().gt(0)
    for col in ("Open", "High", "Low", "Close"):
        bricks[col] = bricks[col].map(lambda x: _to_tick(x, off.tick))
    for col in ("BarOpen", "BarHigh", "BarLow", "Base", "UpEnd", "DownEnd"):
        daily[col] = daily[col].map(lambda x: _to_tick(x, off.tick))
    return bricks.drop(columns="Bar"), daily, off


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _dir(d: int) -> str:
    return "up" if d > 0 else "down" if d < 0 else "-"


def _distance(level: float, close: float, unit: float) -> str:
    return (f"{num(level)} ({'+' if level >= close else ''}{num(level - close)}, {(level / close - 1) * 100:+.2f}%, "
            f"{(level - close) / unit:+.1f} trend offsets from the close)")


def compute_unirenko(df: pd.DataFrame, since: pd.Timestamp, params: UniRenkoParams = DEFAULT_PARAMS) -> Result:
    bricks, daily, off = unirenko(df, params)
    last = daily.iloc[-1]
    close = float(last["Close"])
    up_end, down_end = float(last["UpEnd"]), float(last["DownEnd"])
    prior = df.iloc[-2]
    prior_high, prior_low, prior_open = float(prior["High"]), float(prior["Low"]), float(prior["Open"])

    if bricks.empty:
        headline = (f"No UniRenko bar has completed yet: price stayed between {num(down_end)} and {num(up_end)}; "
                    f"the first bar completes up at {num(up_end)} or down at {num(down_end)}.")
        run, run_start = 0, None
    else:
        d = int(bricks["Direction"].iloc[-1])
        run = 0
        for x in reversed(bricks["Direction"].tolist()):
            if x != d:
                break
            run += 1
        run_start = bricks["Date"].iloc[len(bricks) - run]
        cont, turn = (up_end, down_end) if d > 0 else (down_end, up_end)
        headline = (f"UniRenko {_dir(d)} trend: {run} {_dir(d)} bar{'s' if run != 1 else ''} in a row since "
                    f"{day(run_start)}; the open bar continues {_dir(d)} at {num(cont)} and turns "
                    f"{_dir(-d)} at {num(turn)} (close {num(close)}).")

    shown = bricks[bricks["Date"] >= since]
    reversals = bricks[bricks["Reversal"]]
    facts = [
        ("Offsets", f"trend {num(off.trend)}, reversal {num(off.reversal)}, open {num(off.open_offset)} "
                    f"(ATR({params.atr_length}) {num(off.atr)}, tick {off.tick:g})"),
        ("Last completed bar", "none yet" if bricks.empty else
         f"{_dir(int(bricks['Direction'].iloc[-1]))}, closed {num(float(bricks['Close'].iloc[-1]))} on "
         f"{day(bricks['Date'].iloc[-1])}"),
        ("Bars in a row", f"{run}" + (f" since {day(run_start)}" if run_start is not None else "")),
        ("Last turn", f"{_dir(int(reversals['Direction'].iloc[-1]))} on {day(reversals['Date'].iloc[-1])}"
                      if not reversals.empty else "none"),
        ("Open bar", f"from {num(float(last['Base']))}, drawn open {num(float(last['BarOpen']))}, "
                     f"high {num(float(last['BarHigh']))}, low {num(float(last['BarLow']))}"),
        ("Up end (completes up)", _distance(up_end, close, off.trend)),
        ("Down end (completes down)", _distance(down_end, close, off.trend)),
        ("Bars in window", f"{len(shown)} ({int((shown['Direction'] > 0).sum())} up, "
                           f"{int((shown['Direction'] < 0).sum())} down, turns: {int(shown['Reversal'].sum())})"),
        ("Prior-day high", f"{num(prior_high)} — close {'above' if close > prior_high else 'below' if close < prior_high else 'at'} it"),
        ("Prior-day low", f"{num(prior_low)} — close {'above' if close > prior_low else 'below' if close < prior_low else 'at'} it"),
        ("Prior-day open", f"{num(prior_open)} — close {'above' if close > prior_open else 'below' if close < prior_open else 'at'} it"),
    ]

    levels = pd.DataFrame([
        {"Level": "Up end", "Price": up_end},
        {"Level": "Down end", "Price": down_end},
        {"Level": "Prior-day high", "Price": prior_high},
        {"Level": "Prior-day low", "Price": prior_low},
        {"Level": "Prior-day open", "Price": prior_open},
    ])
    levels["From close"] = levels["Price"] - close
    levels["Trend offsets"] = (levels["From close"] / off.trend).round(1)
    levels = levels.sort_values("Price", ascending=False, kind="stable").reset_index(drop=True)

    tables = [("Level map (open bar ends and prior-day levels)", levels)]
    if not shown.empty:
        tables.append(("Completed UniRenko bars in window", pd.DataFrame({
            "Date": shown["Date"], "Direction": shown["Direction"].map(_dir), "Open": shown["Open"],
            "High": shown["High"], "Low": shown["Low"], "Close": shown["Close"], "Turn": shown["Reversal"],
        })))
    window = daily[daily["Date"] >= since]
    tables.append(("Daily state of the open bar", pd.DataFrame({
        "Date": window["Date"], "Close": window["Close"], "Last bar": window["Direction"].map(_dir),
        "Down end": window["DownEnd"], "Up end": window["UpEnd"], "Completed": window["Completed"],
    })))
    notes = [
        "Clean-room equivalent of the EPyF Basic Pack (NinjaTrader 8) candles, bar type and prior-day levels. "
        "The add-on's calculation code is encrypted and was not read; this follows the published UniRenko "
        "rules its field names point to, so its bars can differ from EPyF's.",
        "Built from daily bars: each day is walked open → low → high → close on up days and open → high → low "
        "→ close on down days, so the order of the day's high and low is assumed. The offsets come from the "
        "ATR on the last bar and are applied to the whole history.",
    ]
    return Result(headline, facts, tables, notes)
