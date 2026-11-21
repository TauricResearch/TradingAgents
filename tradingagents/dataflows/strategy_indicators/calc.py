"""Strategy indicators computed from daily OHLCV bars.

Every calculation here is written from the public, textbook definition of the
technique (VWAP, volume/TPO profile, floor pivots, zigzag swings, Fibonacci
ratios, harmonic ratios, candlestick definitions, ...). No vendor code was used.

Each ``compute_*`` function takes a frame with ``Date`` (datetime64), ``Open``,
``High``, ``Low``, ``Close`` and ``Volume`` columns, sorted by date, holding only
rows on or before the analysis date, plus ``since``: the earliest date whose
events or series rows the report should list. A bar after the analysis date is
never read, so every value is one that was knowable on that date.

They return a :class:`Result`; rendering is ``report.py``'s job.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class Result:
    """One indicator's reading: a headline, key/value facts, tables and notes."""

    headline: str
    facts: list[tuple[str, str]] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["Close"].shift(1)
    return pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev).abs(), (df["Low"] - prev).abs()], axis=1
    ).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return wilder(true_range(df), n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = wilder(delta.clip(lower=0), n)
    loss = wilder((-delta).clip(lower=0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + gain / loss)
    return out


def pct(value: float, digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    return f"{value * 100:+.{digits}f}%"


def num(value: float) -> str:
    """Six significant digits, at least two decimals (as price_text does)."""
    if value is None or not math.isfinite(value):
        return "N/A"
    decimals = 2 if value == 0 else max(2, 5 - math.floor(math.log10(abs(value))))
    whole, _, fraction = f"{value:.{decimals}f}".partition(".")
    return f"{whole}.{fraction.rstrip('0').ljust(2, '0')}"


def day(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def has_volume(df: pd.DataFrame, bars: int | None = None) -> bool:
    vol = df["Volume"] if bars is None else df["Volume"].tail(bars)
    return bool((vol.fillna(0) > 0).sum() >= max(1, len(vol) // 2))


def _window(df: pd.DataFrame, since: pd.Timestamp, minimum: int = 1) -> pd.DataFrame:
    sub = df[df["Date"] >= since]
    return sub if len(sub) >= minimum else df.tail(minimum)


def _relative(price: float, ref: float) -> str:
    if not ref or not math.isfinite(ref):
        return "N/A"
    return pct(price / ref - 1)


# ---------------------------------------------------------------------------
# Swing detection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Pivot:
    i: int
    date: pd.Timestamp
    price: float
    kind: str          # "H" swing high, "L" swing low
    confirmed: bool    # False: the current extreme of the leg still forming


def zigzag_threshold(df: pd.DataFrame) -> float:
    """Reversal size for swings: three median daily ATRs, kept within 2%..25%."""
    atr_pct = (atr(df, 14) / df["Close"]).replace([np.inf, -np.inf], np.nan).dropna()
    base = float(atr_pct.tail(252).median()) if len(atr_pct) else 0.02
    return float(min(max(3 * base, 0.02), 0.25))


def zigzag(df: pd.DataFrame, threshold: float | None = None) -> list[Pivot]:
    """Swing highs and lows that reversed by at least ``threshold`` (a fraction).

    A pivot is confirmed once price has moved ``threshold`` away from it; the
    last pivot is the extreme of the leg still in progress and is unconfirmed.
    """
    th = threshold if threshold is not None else zigzag_threshold(df)
    hi = df["High"].to_numpy(float)
    lo = df["Low"].to_numpy(float)
    dates = list(df["Date"])
    n = len(df)
    if n < 2:
        return []
    found: list[tuple[int, str]] = []
    trend, hi_i, lo_i, cand = 0, 0, 0, 0
    for i in range(1, n):
        if trend == 0:
            if hi[i] > hi[hi_i]:
                hi_i = i
            if lo[i] < lo[lo_i]:
                lo_i = i
            if hi[hi_i] >= lo[lo_i] * (1 + th):
                if lo_i < hi_i:
                    found.append((lo_i, "L"))
                    trend, cand = 1, hi_i
                else:
                    found.append((hi_i, "H"))
                    trend, cand = -1, lo_i
        elif trend == 1:
            if hi[i] >= hi[cand]:
                cand = i
            elif lo[i] <= hi[cand] * (1 - th):
                found.append((cand, "H"))
                trend, cand = -1, i
        else:
            if lo[i] <= lo[cand]:
                cand = i
            elif hi[i] >= lo[cand] * (1 + th):
                found.append((cand, "L"))
                trend, cand = 1, i
    pivots = [Pivot(i, dates[i], float(hi[i] if k == "H" else lo[i]), k, True) for i, k in found]
    if trend:
        kind = "H" if trend == 1 else "L"
        pivots.append(Pivot(cand, dates[cand], float(hi[cand] if kind == "H" else lo[cand]), kind, False))
    return pivots


def fractal_pivots(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[Pivot]:
    """Bars whose high (low) exceeds the ``left`` bars before and ``right`` after.

    A fractal is only known ``right`` bars later, so the last ``right`` bars
    can never be pivots: nothing here reads a bar past the frame's end.
    """
    hi = df["High"].to_numpy(float)
    lo = df["Low"].to_numpy(float)
    dates = list(df["Date"])
    out: list[Pivot] = []
    for i in range(left, len(df) - right):
        if hi[i] > hi[i - left:i].max() and hi[i] >= hi[i + 1:i + right + 1].max():
            out.append(Pivot(i, dates[i], float(hi[i]), "H", True))
        if lo[i] < lo[i - left:i].min() and lo[i] <= lo[i + 1:i + right + 1].min():
            out.append(Pivot(i, dates[i], float(lo[i]), "L", True))
    return out


def label_structure(pivots: list[Pivot]) -> list[str]:
    """HH/LH for each swing high against the previous high, HL/LL for lows."""
    labels, last = [], {"H": None, "L": None}
    for p in pivots:
        prev = last[p.kind]
        if prev is None:
            labels.append("-")
        elif p.kind == "H":
            labels.append("HH" if p.price > prev else "LH")
        else:
            labels.append("HL" if p.price > prev else "LL")
        last[p.kind] = p.price
    return labels


def _structure_trend(pivots: list[Pivot], labels: list[str]) -> str:
    last_h = next((lab for p, lab in zip(reversed(pivots), reversed(labels), strict=True) if p.kind == "H" and lab != "-"), None)
    last_l = next((lab for p, lab in zip(reversed(pivots), reversed(labels), strict=True) if p.kind == "L" and lab != "-"), None)
    if last_h == "HH" and last_l == "HL":
        return "uptrend (higher highs and higher lows)"
    if last_h == "LH" and last_l == "LL":
        return "downtrend (lower highs and lower lows)"
    if last_h is None or last_l is None:
        return "undetermined (too few swings)"
    return f"mixed / range ({last_h} with {last_l})"


# ---------------------------------------------------------------------------
# VWAP and bands
# ---------------------------------------------------------------------------


def _band_position(z: float) -> str:
    if not math.isfinite(z):
        return "N/A"
    if z >= 2:
        return "above the +2σ band (stretched)"
    if z >= 1:
        return "between +1σ and +2σ"
    if z > -1:
        return "inside the ±1σ value channel"
    if z > -2:
        return "between -1σ and -2σ"
    return "below the -2σ band (stretched)"


def compute_vwap_bands(df: pd.DataFrame, since: pd.Timestamp, length: int = 20) -> Result:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    volume_ok = has_volume(df, length)
    w = df["Volume"].fillna(0).astype(float) if volume_ok else pd.Series(1.0, index=df.index)
    wsum = w.rolling(length, min_periods=length).sum()
    vwap = (tp * w).rolling(length, min_periods=length).sum() / wsum
    var = (w * tp**2).rolling(length, min_periods=length).sum() / wsum - vwap**2
    sd = np.sqrt(var.clip(lower=0))
    z = (df["Close"] - vwap) / sd.replace(0, np.nan)

    table = pd.DataFrame({
        "Date": df["Date"], "Close": df["Close"], "VWAP": vwap,
        "-2σ": vwap - 2 * sd, "-1σ": vwap - sd, "+1σ": vwap + sd, "+2σ": vwap + 2 * sd,
        "z": z.round(2),
    })[df["Date"] >= since]

    close = float(df["Close"].iloc[-1])
    last_z = float(z.iloc[-1]) if pd.notna(z.iloc[-1]) else float("nan")

    def anchored(start: int) -> float:
        ww = w.iloc[start:]
        total = float(ww.sum())
        return float((tp.iloc[start:] * ww).sum() / total) if total else float("nan")

    anchors: list[tuple[str, int]] = []
    year_start = df.index[df["Date"].dt.year == df["Date"].iloc[-1].year][0]
    anchors.append((f"Year start ({day(df['Date'].iloc[year_start])})", int(year_start)))
    confirmed = [p for p in zigzag(df) if p.confirmed]
    for kind, name in (("H", "Last swing high"), ("L", "Last swing low")):
        p = next((p for p in reversed(confirmed) if p.kind == kind), None)
        if p is not None:
            anchors.append((f"{name} ({day(p.date)})", p.i))

    anchored_rows = [
        {"Anchor": label, "Anchored VWAP": anchored(i), "Close vs AVWAP": _relative(close, anchored(i))}
        for label, i in anchors
    ]

    facts = [
        (f"Rolling {length}-bar VWAP", num(float(vwap.iloc[-1]))),
        ("Close", num(close)),
        ("Distance in σ (z)", f"{last_z:+.2f}" if math.isfinite(last_z) else "N/A"),
        ("±1σ channel", f"{num(float((vwap - sd).iloc[-1]))} – {num(float((vwap + sd).iloc[-1]))}"),
        ("±2σ bands", f"{num(float((vwap - 2 * sd).iloc[-1]))} – {num(float((vwap + 2 * sd).iloc[-1]))}"),
    ]
    notes = []
    if not volume_ok:
        notes.append("This instrument reports no volume, so the VWAP is an equal-weighted typical-price average.")
    headline = f"Close {num(close)} is {_band_position(last_z)} of the {length}-bar VWAP {num(float(vwap.iloc[-1]))}."
    return Result(headline, facts, [("Anchored VWAPs", pd.DataFrame(anchored_rows)),
                                    ("Rolling VWAP and deviation bands", table)], notes)


# ---------------------------------------------------------------------------
# Volume profile / TPO profile
# ---------------------------------------------------------------------------


def _profile(window: pd.DataFrame, bins: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Volume and TPO (bars touching) per price bin over ``window``."""
    lo_p, hi_p = float(window["Low"].min()), float(window["High"].max())
    if hi_p <= lo_p:
        hi_p = lo_p * 1.0001 + 1e-9
    edges = np.linspace(lo_p, hi_p, bins + 1)
    high = window["High"].to_numpy(float)[:, None]
    low = window["Low"].to_numpy(float)[:, None]
    vol = window["Volume"].fillna(0).to_numpy(float)[:, None]
    overlap = np.clip(np.minimum(high, edges[1:]) - np.maximum(low, edges[:-1]), 0, None)
    rng = high - low
    with np.errstate(divide="ignore", invalid="ignore"):
        share = np.where(rng > 0, overlap / rng, 0.0)
    flat = (rng[:, 0] <= 0)
    if flat.any():
        idx = np.clip(np.searchsorted(edges, low[flat, 0], side="right") - 1, 0, bins - 1)
        share[np.nonzero(flat)[0], idx] = 1.0
    touched = (overlap > 0) | (share > 0)
    return edges, (share * vol).sum(axis=0), touched.sum(axis=0).astype(float)


def value_area(edges: np.ndarray, profile: np.ndarray, share: float = 0.70) -> tuple[float, float, float]:
    """(POC, VAL, VAH): the fullest bin, grown toward its fuller neighbour to ``share``."""
    total = float(profile.sum())
    centers = (edges[:-1] + edges[1:]) / 2
    if total <= 0:
        return float("nan"), float("nan"), float("nan")
    poc = int(np.argmax(profile))
    lo = hi = poc
    acc = float(profile[poc])
    while acc < share * total and (lo > 0 or hi < len(profile) - 1):
        up = profile[hi + 1] if hi < len(profile) - 1 else -1.0
        dn = profile[lo - 1] if lo > 0 else -1.0
        if up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
    return float(centers[poc]), float(edges[lo]), float(edges[hi + 1])


def _against_value(close: float, val: float, vah: float) -> str:
    if not (math.isfinite(val) and math.isfinite(vah)):
        return "N/A"
    if close > vah:
        return "above value (acceptance higher or a stretch to fade)"
    if close < val:
        return "below value (acceptance lower or a stretch to fade)"
    return "inside the value area (balance)"


def compute_volume_profile(df: pd.DataFrame, since: pd.Timestamp, bins: int = 40) -> Result:
    window = _window(df, since, minimum=20)
    edges, vol_prof, tpo_prof = _profile(window, bins)
    volume_ok = has_volume(window)
    close = float(df["Close"].iloc[-1])

    tpo_poc, tpo_val, tpo_vah = value_area(edges, tpo_prof)
    facts = [("Profile window", f"{day(window['Date'].iloc[0])} → {day(window['Date'].iloc[-1])} ({len(window)} bars)")]
    if volume_ok:
        poc, val, vah = value_area(edges, vol_prof)
        facts += [("Volume POC", num(poc)), ("Value area (70% of volume)", f"{num(val)} – {num(vah)}")]
    else:
        poc, val, vah = tpo_poc, tpo_val, tpo_vah
    facts += [("TPO POC (most-visited price)", num(tpo_poc)),
              ("TPO value area (70% of bar-touches)", f"{num(tpo_val)} – {num(tpo_vah)}"),
              ("Close", f"{num(close)}, {_against_value(close, val, vah)}")]

    # POC migration: the same-length window just before this one.
    prior = df[df["Date"] < window["Date"].iloc[0]].tail(len(window))
    if len(prior) >= 10:
        p_edges, p_vol, p_tpo = _profile(prior, bins)
        p_poc = value_area(p_edges, p_vol if has_volume(prior) else p_tpo)[0]
        direction = "higher" if poc > p_poc else "lower" if poc < p_poc else "unchanged"
        facts.append(("Prior-window POC", f"{num(p_poc)} (POC migrated {direction})"))

    centers = (edges[:-1] + edges[1:]) / 2
    prof = vol_prof if volume_ok else tpo_prof
    total = float(prof.sum()) or 1.0
    order = np.argsort(prof)[::-1][:5]
    hvn = pd.DataFrame({
        "Price from": [edges[i] for i in order], "Price to": [edges[i + 1] for i in order],
        "Share of " + ("volume" if volume_ok else "bar-touches"): [f"{prof[i] / total * 100:.1f}%" for i in order],
    })
    inside = [i for i in range(1, bins - 1) if val <= centers[i] <= vah
              and prof[i] < prof[i - 1] and prof[i] < prof[i + 1]]
    inside = sorted(inside, key=lambda i: prof[i])[:3]
    lvn = pd.DataFrame({"Low-volume node": [centers[i] for i in inside],
                        "Share": [f"{prof[i] / total * 100:.1f}%" for i in inside]})

    notes = ["Built from daily bars: each bar's volume is spread evenly over its high–low range, "
             "so this approximates a tick-level profile rather than reproducing one."]
    if not volume_ok:
        notes.append("No volume is reported for this instrument; the TPO profile is used for the levels.")
    headline = f"POC {num(poc)}, value area {num(val)} – {num(vah)}; close {num(close)} is {_against_value(close, val, vah)}."
    tables = [("High-volume nodes", hvn)]
    if len(lvn):
        tables.append(("Low-volume nodes inside value", lvn))
    return Result(headline, facts, tables, notes)


# ---------------------------------------------------------------------------
# ZigZag swings and market structure
# ---------------------------------------------------------------------------


def compute_zigzag(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    th = zigzag_threshold(df)
    pivots = zigzag(df, th)
    if len(pivots) < 2:
        return Result("Too few swings to describe structure.", [("Reversal threshold", pct(th).lstrip("+"))])
    labels = label_structure(pivots)
    rows = []
    for k, p in enumerate(pivots):
        prev = pivots[k - 1] if k else None
        rows.append({
            "Date": p.date, "Swing": "High" if p.kind == "H" else "Low", "Price": p.price,
            "Move from previous": pct(p.price / prev.price - 1) if prev else "-",
            "Bars": p.i - prev.i if prev else "-", "Structure": labels[k],
            "Status": "confirmed" if p.confirmed else "forming",
        })
    table = pd.DataFrame(rows)
    shown = table[table["Date"] >= since]
    if len(shown) < 6:
        shown = table.tail(6)
    last = pivots[-1]
    leg = "up" if last.kind == "H" else "down"
    trend = _structure_trend(pivots, labels)
    facts = [("Reversal threshold", f"{th * 100:.1f}% (3× median daily ATR)"),
             ("Current leg", f"{leg} from {num(pivots[-2].price)} on {day(pivots[-2].date)} "
                             f"to {num(last.price)} on {day(last.date)} ({pct(last.price / pivots[-2].price - 1)})"),
             ("Market structure", trend)]
    notes = ["The last swing is the extreme of the leg in progress; it moves until price reverses by the threshold."]
    return Result(f"Market structure: {trend}; current leg {leg}.", facts, [("Swing points", shown)], notes)


# ---------------------------------------------------------------------------
# Relative volume
# ---------------------------------------------------------------------------


def compute_relative_volume(df: pd.DataFrame, since: pd.Timestamp, length: int = 20) -> Result:
    if not has_volume(df, length):
        return Result("No volume is reported for this instrument.", notes=["Relative volume needs reported volume."])
    vol = df["Volume"].astype(float)
    base = vol.shift(1).rolling(length, min_periods=length).mean()
    rvol = vol / base.replace(0, np.nan)
    chg = df["Close"].pct_change()
    table = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "Change": chg.map(pct),
                          "Volume": vol.astype("int64"), "RVOL": rvol.round(2)})[df["Date"] >= since]
    win = df["Date"] >= since
    up = vol[win & (chg > 0)].mean()
    down = vol[win & (chg < 0)].mean()
    last = float(rvol.iloc[-1])
    facts = [(f"Latest RVOL (vs prior {length}-bar average)", f"{last:.2f}×"),
             ("Bars at ≥ 2× average volume in window", str(int((rvol[win] >= 2).sum()))),
             ("Average volume on up days / down days", f"{up / down:.2f}" if down and math.isfinite(up / down) else "N/A")]
    tone = "above" if last > 1.2 else "below" if last < 0.8 else "near"
    ud = up / down if down else float("nan")
    flow = (" Up-day volume outweighs down-day volume (accumulation)." if ud > 1.15 else
            " Down-day volume outweighs up-day volume (distribution)." if ud < 0.87 else "")
    return Result(f"Volume is {tone} normal at {last:.2f}× its {length}-bar average.{flow}", facts,
                  [("Relative volume", table)])


# ---------------------------------------------------------------------------
# Relative strength against a benchmark
# ---------------------------------------------------------------------------


def compute_relative_strength(df: pd.DataFrame, since: pd.Timestamp, bench: pd.DataFrame, bench_symbol: str) -> Result:
    merged = pd.merge(df[["Date", "Close"]], bench[["Date", "Close"]].rename(columns={"Close": "Bench"}),
                      on="Date", how="inner")
    if len(merged) < 30:
        return Result(f"Too few overlapping rows with {bench_symbol}.")
    ratio = merged["Close"] / merged["Bench"]
    mansfield = (ratio / sma(ratio, 200) - 1) * 100
    win = merged["Date"] >= since
    start = ratio[win].iloc[0] if win.any() else ratio.iloc[0]
    table = pd.DataFrame({"Date": merged["Date"], "Close": merged["Close"], bench_symbol: merged["Bench"],
                          "RS line (window start = 100)": (ratio / start * 100).round(2),
                          "Mansfield RS": mansfield.round(2)})[win]
    perf = []
    for bars, label in ((21, "1 month"), (63, "3 months"), (126, "6 months"), (252, "12 months")):
        if len(merged) > bars:
            a = merged["Close"].iloc[-1] / merged["Close"].iloc[-1 - bars] - 1
            b = merged["Bench"].iloc[-1] / merged["Bench"].iloc[-1 - bars] - 1
            perf.append({"Period": label, "Instrument": pct(a), bench_symbol: pct(b), "Excess": pct(a - b)})
    last_m = float(mansfield.iloc[-1])
    high_52 = bool(ratio.iloc[-1] >= ratio.tail(252).max())
    low_52 = bool(ratio.iloc[-1] <= ratio.tail(252).min())
    facts = [("Benchmark", bench_symbol),
             ("Mansfield RS (ratio vs its 200-bar mean)", f"{last_m:+.2f}" if math.isfinite(last_m) else "N/A"),
             ("RS line at a 52-week extreme", "new high" if high_52 else "new low" if low_52 else "no")]
    if math.isfinite(last_m):
        lead = "outperforming" if last_m > 0 else "underperforming"
        headline = f"{lead.capitalize()} {bench_symbol}: Mansfield RS {last_m:+.2f}."
    else:
        headline = f"Relative strength against {bench_symbol} needs 200 overlapping bars for the Mansfield reading."
    return Result(headline, facts, [("Performance against the benchmark", pd.DataFrame(perf)),
                                    ("Relative strength line", table)])


# ---------------------------------------------------------------------------
# Estimated volume delta
# ---------------------------------------------------------------------------


def compute_volume_delta(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    if not has_volume(df):
        return Result("No volume is reported for this instrument.", notes=["Volume delta needs reported volume."])
    rng = (df["High"] - df["Low"]).replace(0, np.nan)
    clv = (((df["Close"] - df["Low"]) - (df["High"] - df["Close"])) / rng).fillna(0)
    vol = df["Volume"].astype(float)
    delta = vol * clv
    win = df["Date"] >= since
    cum = delta[win].cumsum()
    table = pd.DataFrame({"Date": df["Date"][win], "Close": df["Close"][win], "Volume": vol[win].astype("int64"),
                          "Est. delta": delta[win].round(0).astype("int64"),
                          "Cum. delta": cum.round(0).astype("int64"),
                          "Delta % of volume": (clv[win] * 100).round(1)})
    total = float(cum.iloc[-1]) if len(cum) else 0.0
    share = total / float(vol[win].sum()) if vol[win].sum() else float("nan")
    price_chg = float(df["Close"][win].iloc[-1] / df["Close"][win].iloc[0] - 1) if win.sum() > 1 else float("nan")
    agree = (total > 0) == (price_chg > 0)
    d20 = float(delta.tail(20).sum())
    p20 = float(df["Close"].iloc[-1] / df["Close"].iloc[-21] - 1) if len(df) > 21 else float("nan")
    facts = [("Cumulative estimated delta (window)", f"{total:,.0f} ({share * 100:+.1f}% of window volume)"),
             ("Price change (window)", pct(price_chg)),
             ("Last 20 bars", f"delta {d20:,.0f}, price {pct(p20)}")]
    if agree:
        headline = (f"Estimated buying and selling pressure confirms the move: cumulative delta {total:,.0f} "
                    f"with price {pct(price_chg)}.")
    else:
        headline = (f"Divergence: price {pct(price_chg)} while cumulative estimated delta is {total:,.0f}; "
                    "the move lacks volume support.")
    notes = ["Delta is estimated from where each bar closed within its range (close-location value × volume). "
             "It is not bid/ask volume, which needs tick or order-flow data."]
    return Result(headline, facts, [("Estimated volume delta", table)], notes)


# ---------------------------------------------------------------------------
# Floor / Camarilla pivots and period midpoints
# ---------------------------------------------------------------------------


def _pivot_levels(h: float, low: float, c: float) -> dict[str, float]:
    p = (h + low + c) / 3
    r = h - low
    return {
        "R3": h + 2 * (p - low), "R2": p + r, "R1": 2 * p - low, "P": p,
        "S1": 2 * p - h, "S2": p - r, "S3": low - 2 * (h - p),
        "Midpoint": (h + low) / 2, "Camarilla H4": c + r * 1.1 / 2, "Camarilla H3": c + r * 1.1 / 4,
        "Camarilla L3": c - r * 1.1 / 4, "Camarilla L4": c - r * 1.1 / 2,
        "Period high": h, "Period low": low,
    }


def compute_pivots(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    last_date = df["Date"].iloc[-1]
    columns: dict[str, dict[str, float]] = {}
    sources: list[tuple[str, str]] = []
    if len(df) >= 2:
        prev = df.iloc[-2]
        columns["Daily"] = _pivot_levels(prev["High"], prev["Low"], prev["Close"])
        sources.append(("Daily levels from", day(prev["Date"])))
    for label, freq in (("Weekly", "W"), ("Monthly", "M")):
        periods = df["Date"].dt.to_period(freq)
        done = df[periods < last_date.to_period(freq)]
        if done.empty:
            continue
        block = done[periods[done.index] == periods[done.index].iloc[-1]]
        columns[label] = _pivot_levels(block["High"].max(), block["Low"].min(), block["Close"].iloc[-1])
        sources.append((f"{label} levels from", f"{day(block['Date'].iloc[0])} → {day(block['Date'].iloc[-1])}"))
    table = pd.DataFrame(columns)
    table.insert(0, "Level", table.index)
    table = table.reset_index(drop=True)

    close = float(df["Close"].iloc[-1])
    levels = [(f"{col} {lvl}", v) for col, d in columns.items() for lvl, v in d.items()
              if not lvl.startswith("Period")]
    above = sorted((x for x in levels if x[1] > close), key=lambda x: x[1])[:3]
    below = sorted((x for x in levels if x[1] < close), key=lambda x: -x[1])[:3]
    facts = sources + [("Close", num(close)),
                       ("Nearest levels above", ", ".join(f"{n} {num(v)}" for n, v in above) or "none"),
                       ("Nearest levels below", ", ".join(f"{n} {num(v)}" for n, v in below) or "none")]
    first_above = f"{above[0][0]} {num(above[0][1])}" if above else "none"
    first_below = f"{below[0][0]} {num(below[0][1])}" if below else "none"
    headline = f"Close {num(close)} sits between {first_below} (below) and {first_above} (above)."
    notes = [f"Levels in force for the session of {day(last_date)}, each from the previous completed day, week and month."]
    return Result(headline, facts, [("Pivot levels", table)], notes)


# ---------------------------------------------------------------------------
# Zero-lag MACD
# ---------------------------------------------------------------------------


def zlema(s: pd.Series, n: int) -> pd.Series:
    lag = (n - 1) // 2
    return ema(s + (s - s.shift(lag)), n)


def compute_zero_lag_macd(df: pd.DataFrame, since: pd.Timestamp, fast: int = 12, slow: int = 26, signal: int = 9) -> Result:
    macd = zlema(df["Close"], fast) - zlema(df["Close"], slow)
    sig = zlema(macd, signal)
    hist = macd - sig
    table = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "ZL-MACD": macd,
                          "Signal": sig, "Histogram": hist})[df["Date"] >= since]
    cross = np.sign(hist).diff()
    events = []
    for i in df.index[(df["Date"] >= since) & (cross.abs() == 2)]:
        events.append({"Date": df["Date"][i], "Cross": "bullish" if cross[i] > 0 else "bearish",
                       "Side of zero": "above" if macd[i] > 0 else "below", "Close": df["Close"][i]})
    h_now, h_prev = float(hist.iloc[-1]), float(hist.iloc[-2])
    state = "bullish" if h_now > 0 else "bearish"
    momentum = "strengthening" if abs(h_now) > abs(h_prev) else "fading"
    facts = [("ZL-MACD", num(float(macd.iloc[-1]))), ("Signal", num(float(sig.iloc[-1]))),
             ("Histogram", f"{num(h_now)} ({momentum})")]
    tables = [("Crossovers in window", pd.DataFrame(events))] if events else []
    tables.append(("Zero-lag MACD", table))
    side = "above" if macd.iloc[-1] > 0 else "below"
    relation = "above" if h_now > 0 else "below"
    return Result(f"Zero-lag MACD is {relation} its signal ({state}), {side} zero, histogram {momentum}.",
                  facts, tables, ["Zero-lag EMAs add the lagged difference back to price, so crosses come earlier "
                                  "than in the standard MACD, at the cost of more whipsaws."])


# ---------------------------------------------------------------------------
# Triangular moving average with ATR bands
# ---------------------------------------------------------------------------


def compute_tma_bands(df: pd.DataFrame, since: pd.Timestamp, length: int = 20, mult: float = 2.5) -> Result:
    n1, n2 = (length + 2) // 2, (length + 1) // 2
    tma = sma(sma(df["Close"], n1), n2)
    band = atr(df, length) * mult
    upper, lower = tma + band, tma - band
    position = (df["Close"] - lower) / (upper - lower)
    table = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "TMA": tma, "Lower": lower, "Upper": upper,
                          "Position in band": (position * 100).round(1)})[df["Date"] >= since]
    win = df["Date"] >= since
    outside = []
    for i in df.index[win & ((df["Close"] > upper) | (df["Close"] < lower))]:
        outside.append({"Date": df["Date"][i], "Close": df["Close"][i],
                        "Side": "above upper" if df["Close"][i] > upper[i] else "below lower"})
    slope = float(tma.iloc[-1] / tma.iloc[-6] - 1) / 5 if len(tma) > 6 else float("nan")
    pos = float(position.iloc[-1])
    where = ("above the upper band" if pos > 1 else "below the lower band" if pos < 0
             else f"at {pos * 100:.0f}% of the band")
    facts = [(f"TMA({length})", num(float(tma.iloc[-1]))),
             (f"Bands (±{mult}×ATR{length})", f"{num(float(lower.iloc[-1]))} – {num(float(upper.iloc[-1]))}"),
             ("TMA slope", f"{slope * 100:+.3f}% per bar" if math.isfinite(slope) else "N/A"),
             ("Closes outside the bands in window", str(len(outside)))]
    tables = [("Closes outside the bands", pd.DataFrame(outside))] if outside else []
    tables.append(("TMA bands", table))
    direction = "rising" if slope > 0 else "falling"
    return Result(f"Close is {where}; the TMA is {direction}.", facts, tables,
                  ["This TMA is trailing (it uses past bars only); the centred TMA seen on charts redraws its recent values."])


# ---------------------------------------------------------------------------
# Price gaps
# ---------------------------------------------------------------------------


def compute_gaps(df: pd.DataFrame, since: pd.Timestamp, scan_bars: int = 252) -> Result:
    a = atr(df, 14)
    hi, lo = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    dates = list(df["Date"])
    close = float(df["Close"].iloc[-1])
    start = max(1, len(df) - scan_bars)
    open_rows, filled_rows = [], []
    for t in range(start, len(df)):
        min_size = 0.1 * a.iloc[t - 1] if pd.notna(a.iloc[t - 1]) else 0.001 * lo[t]
        if lo[t] > hi[t - 1] and lo[t] - hi[t - 1] >= min_size:
            kind, bottom, top = "up", hi[t - 1], lo[t]
        elif hi[t] < lo[t - 1] and lo[t - 1] - hi[t] >= min_size:
            kind, bottom, top = "down", hi[t], lo[t - 1]
        else:
            continue
        size = (top - bottom) / bottom
        fill_date, rem_lo, rem_hi = None, bottom, top
        for j in range(t + 1, len(df)):
            if kind == "up":
                rem_hi = min(rem_hi, lo[j])
                if lo[j] <= bottom:
                    fill_date = dates[j]
                    break
            else:
                rem_lo = max(rem_lo, hi[j])
                if hi[j] >= top:
                    fill_date = dates[j]
                    break
        row = {"Gap date": dates[t], "Direction": kind, "Zone low": bottom, "Zone high": top, "Size": f"{size * 100:.2f}%"}
        if fill_date is None:
            untouched = (rem_hi == top) if kind == "up" else (rem_lo == bottom)
            row.update({"Unfilled low": rem_lo, "Unfilled high": rem_hi,
                        "Status": "open" if untouched else "partly filled",
                        "Distance from close": _relative((rem_lo + rem_hi) / 2, close)})
            open_rows.append(row)
        elif fill_date >= since:
            row["Filled on"] = fill_date
            filled_rows.append(row)
    open_df = pd.DataFrame(open_rows)
    if len(open_df):
        open_df["_d"] = ((open_df["Unfilled low"] + open_df["Unfilled high"]) / 2 - close).abs()
        open_df = open_df.sort_values("_d").drop(columns="_d").head(12).reset_index(drop=True)
    above = [r for r in open_rows if r["Unfilled low"] > close]
    below = [r for r in open_rows if r["Unfilled high"] < close]
    facts = [("Gaps scanned", f"last {min(scan_bars, len(df) - 1)} bars, minimum size 0.1×ATR14"),
             ("Unfilled gaps", f"{len(open_rows)} ({len(above)} above price, {len(below)} below)"),
             ("Gaps filled in window", str(len(filled_rows)))]
    nearest = []
    if above:
        r = min(above, key=lambda r: r["Unfilled low"])
        nearest.append(f"nearest above {num(r['Unfilled low'])} – {num(r['Unfilled high'])} ({day(r['Gap date'])})")
    if below:
        r = max(below, key=lambda r: r["Unfilled high"])
        nearest.append(f"nearest below {num(r['Unfilled low'])} – {num(r['Unfilled high'])} ({day(r['Gap date'])})")
    headline = f"{len(open_rows)} unfilled gap(s)" + (f": {'; '.join(nearest)}." if nearest else ".")
    tables = []
    if len(open_df):
        tables.append(("Unfilled gaps (nearest first)", open_df))
    if filled_rows:
        tables.append(("Gaps filled in window", pd.DataFrame(filled_rows)))
    return Result(headline, facts, tables, ["Unfilled gaps often act as magnets or as support/resistance; "
                                            "a gap counts as filled once price trades back to its far edge."])


def compute_untested_levels(df: pd.DataFrame, since: pd.Timestamp, scan_bars: int = 252) -> Result:
    sub = df.tail(scan_bars + 3).reset_index(drop=True)
    hi, lo = sub["High"].to_numpy(float), sub["Low"].to_numpy(float)
    close = float(sub["Close"].iloc[-1])
    rows = []
    for p in fractal_pivots(sub, 3, 3):
        after_hi = hi[p.i + 1:]
        after_lo = lo[p.i + 1:]
        if p.kind == "H" and (after_hi.size == 0 or after_hi.max() < p.price):
            rows.append({"Formed": p.date, "Type": "untested swing high", "Price": p.price,
                         "Age (bars)": len(sub) - 1 - p.i, "Distance from close": _relative(p.price, close)})
        if p.kind == "L" and (after_lo.size == 0 or after_lo.min() > p.price):
            rows.append({"Formed": p.date, "Type": "untested swing low", "Price": p.price,
                         "Age (bars)": len(sub) - 1 - p.i, "Distance from close": _relative(p.price, close)})
    table = pd.DataFrame(rows)
    if len(table):
        table = table.assign(_d=(table["Price"] - close).abs()).sort_values("_d").drop(columns="_d").head(10)
    highs = [r for r in rows if r["Type"].endswith("high")]
    lows = [r for r in rows if r["Type"].endswith("low")]
    near_hi = min(highs, key=lambda r: r["Price"]) if highs else None
    near_lo = max(lows, key=lambda r: r["Price"]) if lows else None
    parts = []
    if near_hi:
        parts.append(f"resistance {num(near_hi['Price'])} ({day(near_hi['Formed'])})")
    if near_lo:
        parts.append(f"support {num(near_lo['Price'])} ({day(near_lo['Formed'])})")
    headline = "Nearest untested swing levels: " + (", ".join(parts) if parts else "none") + "."
    facts = [("Scan", f"last {scan_bars} bars, 3-bar fractal swings"),
             ("Untested highs / lows", f"{len(highs)} / {len(lows)}")]
    return Result(headline, facts, [("Untested swing levels (nearest first)", table)] if len(table) else [],
                  ["An untested level is a swing high (low) that no later bar has traded above (below)."])


# ---------------------------------------------------------------------------
# Candlestick patterns
# ---------------------------------------------------------------------------

BULLISH, BEARISH, NEUTRAL = "bullish", "bearish", "neutral"


def detect_candles(df: pd.DataFrame) -> list[tuple[int, str, str]]:
    """(bar index, pattern, bias) for every textbook pattern found."""
    o, h, low, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    body = np.abs(c - o)
    rng = h - low
    upper = h - np.maximum(o, c)
    lower = np.minimum(o, c) - low
    avg_body = pd.Series(body).rolling(14).mean().shift(1).to_numpy()
    s10 = sma(df["Close"], 10).to_numpy()
    bull = c > o
    bear = c < o
    found = []
    for t in range(15, len(df)):
        if rng[t] <= 0 or not np.isfinite(avg_body[t]):
            continue
        down = c[t - 1] < s10[t - 1] and s10[t - 1] <= s10[t - 3]
        up = c[t - 1] > s10[t - 1] and s10[t - 1] >= s10[t - 3]
        prev_big = body[t - 1] >= avg_body[t]
        mid_prev = (o[t - 1] + c[t - 1]) / 2

        if body[t] <= 0.1 * rng[t]:
            found.append((t, "Doji", NEUTRAL))
        elif lower[t] >= 2 * body[t] and upper[t] <= 0.3 * body[t] + 0.1 * rng[t]:
            if down:
                found.append((t, "Hammer", BULLISH))
            elif up:
                found.append((t, "Hanging man", BEARISH))
        elif upper[t] >= 2 * body[t] and lower[t] <= 0.3 * body[t] + 0.1 * rng[t]:
            if up:
                found.append((t, "Shooting star", BEARISH))
            elif down:
                found.append((t, "Inverted hammer", BULLISH))

        if bear[t - 1] and bull[t] and o[t] <= c[t - 1] and c[t] >= o[t - 1] and body[t] > body[t - 1] and down:
            found.append((t, "Bullish engulfing", BULLISH))
        elif bull[t - 1] and bear[t] and o[t] >= c[t - 1] and c[t] <= o[t - 1] and body[t] > body[t - 1] and up:
            found.append((t, "Bearish engulfing", BEARISH))
        elif prev_big and body[t] < 0.6 * body[t - 1] and max(o[t], c[t]) <= max(o[t - 1], c[t - 1]) \
                and min(o[t], c[t]) >= min(o[t - 1], c[t - 1]):
            if bear[t - 1] and down:
                found.append((t, "Bullish harami", BULLISH))
            elif bull[t - 1] and up:
                found.append((t, "Bearish harami", BEARISH))

        if bear[t - 1] and prev_big and bull[t] and o[t] < c[t - 1] and mid_prev < c[t] < o[t - 1] and down:
            found.append((t, "Piercing line", BULLISH))
        elif bull[t - 1] and prev_big and bear[t] and o[t] > c[t - 1] and o[t - 1] < c[t] < mid_prev and up:
            found.append((t, "Dark cloud cover", BEARISH))

        b1, b2 = t - 2, t - 1
        if body[b1] >= avg_body[t] and body[b2] <= 0.3 * body[b1]:
            mid1 = (o[b1] + c[b1]) / 2
            if bear[b1] and max(o[b2], c[b2]) < c[b1] and bull[t] and c[t] > mid1 and c[b1 - 1] < s10[b1 - 1]:
                found.append((t, "Morning star", BULLISH))
            elif bull[b1] and min(o[b2], c[b2]) > c[b1] and bear[t] and c[t] < mid1 and c[b1 - 1] > s10[b1 - 1]:
                found.append((t, "Evening star", BEARISH))

        three = range(t - 2, t + 1)
        if all(bull[k] and body[k] >= 0.6 * rng[k] for k in three) and c[t] > c[t - 1] > c[t - 2] \
                and all(min(o[k - 1], c[k - 1]) <= o[k] <= max(o[k - 1], c[k - 1]) for k in (t - 1, t)):
            found.append((t, "Three white soldiers", BULLISH))
        elif all(bear[k] and body[k] >= 0.6 * rng[k] for k in three) and c[t] < c[t - 1] < c[t - 2] \
                and all(min(o[k - 1], c[k - 1]) <= o[k] <= max(o[k - 1], c[k - 1]) for k in (t - 1, t)):
            found.append((t, "Three black crows", BEARISH))
    return found


def compute_candlestick_patterns(df: pd.DataFrame, since: pd.Timestamp, horizon: int = 5) -> Result:
    found = detect_candles(df)
    c = df["Close"].to_numpy(float)
    recent = [{"Date": df["Date"].iloc[t], "Pattern": name, "Bias": bias, "Close": c[t]}
              for t, name, bias in found if df["Date"].iloc[t] >= since]
    stats: dict[tuple[str, str], list[float]] = {}
    for t, name, bias in found:
        if bias == NEUTRAL or t + horizon >= len(df):
            continue
        stats.setdefault((name, bias), []).append(c[t + horizon] / c[t] - 1)
    rows = []
    for (name, bias), moves in sorted(stats.items(), key=lambda kv: -len(kv[1])):
        arr = np.array(moves)
        hit = (arr > 0).mean() if bias == BULLISH else (arr < 0).mean()
        rows.append({"Pattern": name, "Bias": bias, "Occurrences": len(arr),
                     f"Moved with bias after {horizon} bars": f"{hit * 100:.0f}%",
                     f"Average {horizon}-bar move": pct(float(arr.mean()))})
    last_bars = [r for r in recent if r["Date"] >= df["Date"].iloc[max(0, len(df) - 3)]]
    if last_bars:
        headline = "Latest patterns: " + "; ".join(f"{r['Pattern']} ({r['Bias']}) on {day(r['Date'])}" for r in last_bars) + "."
    elif recent:
        r = recent[-1]
        headline = f"No pattern on the last three bars; the most recent was {r['Pattern']} ({r['Bias']}) on {day(r['Date'])}."
    else:
        headline = "No candlestick pattern in the window."
    tables = [("Patterns in window", pd.DataFrame(recent))] if recent else []
    if rows:
        tables.append(("How each pattern played out on this instrument (history before the analysis date)",
                       pd.DataFrame(rows)))
    notes = ["Trend context: a bullish reversal pattern needs a prior close below a falling 10-bar SMA, and a "
             "bearish one a prior close above a rising one. The playout table is in-sample history, not a forecast."]
    return Result(headline, [("Patterns in window", str(len(recent)))], tables, notes)


# ---------------------------------------------------------------------------
# Fibonacci retracements, extensions and confluence
# ---------------------------------------------------------------------------

RETRACEMENTS = (0.236, 0.382, 0.5, 0.618, 0.786)
EXTENSIONS = (1.272, 1.618, 2.0)


def compute_fibonacci(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    pivots = zigzag(df)
    if len(pivots) < 2:
        return Result("Too few swings for Fibonacci levels.")
    close = float(df["Close"].iloc[-1])
    a, b = pivots[-2], pivots[-1]
    span = b.price - a.price
    rows = [{"Level": f"{r:.1%} retracement".replace(".0%", "%"), "Price": b.price - r * span,
             "Distance from close": _relative(b.price - r * span, close)} for r in RETRACEMENTS]
    rows += [{"Level": f"{e:.3g} extension", "Price": a.price + e * span,
              "Distance from close": _relative(a.price + e * span, close)} for e in EXTENSIONS]
    leg = pd.DataFrame(rows)

    tol = float(atr(df, 14).iloc[-1]) * 0.5
    levels: list[tuple[float, str]] = []
    tail = pivots[-7:]
    legs = list(zip(tail[:-1], tail[1:], strict=True))
    for x, y in legs:
        s = y.price - x.price
        tag = f"{day(x.date)}→{day(y.date)}"
        levels += [(y.price - r * s, f"{r:.3g} ret {tag}") for r in (0.382, 0.5, 0.618, 0.786)]
        levels += [(x.price + e * s, f"{e:.3g} ext {tag}") for e in (1.272, 1.618)]
    levels.sort()
    clusters, cur = [], [levels[0]] if levels else []
    for lv in levels[1:]:
        if lv[0] - cur[-1][0] <= tol:
            cur.append(lv)
        else:
            clusters.append(cur)
            cur = [lv]
    if cur:
        clusters.append(cur)
    zones = []
    for cl in clusters:
        legs_in = {lab.split(" ", 2)[2] for _, lab in cl}
        if len(cl) >= 2 and len(legs_in) >= 2:
            mid = sum(p for p, _ in cl) / len(cl)
            zones.append({"Zone low": cl[0][0], "Zone high": cl[-1][0], "Levels": len(cl),
                          "Distance from close": _relative(mid, close),
                          "Built from": "; ".join(lab for _, lab in cl), "_d": abs(mid - close)})
    zones_df = pd.DataFrame(zones)
    if len(zones_df):
        zones_df = zones_df.sort_values("_d").drop(columns="_d").head(6).reset_index(drop=True)

    direction = "up" if span > 0 else "down"
    facts = [("Measured leg", f"{direction} from {num(a.price)} ({day(a.date)}) to {num(b.price)} ({day(b.date)})"
                              + ("" if b.confirmed else ", still forming")),
             ("Retracement of the leg so far", f"{abs((b.price - close) / span) * 100:.1f}%" if span else "N/A"),
             ("Confluence tolerance", f"±{num(tol)} (0.5×ATR14)")]
    if len(zones_df):
        z = zones_df.iloc[0]
        headline = (f"Nearest Fibonacci confluence {num(z['Zone low'])} – {num(z['Zone high'])} "
                    f"({z['Levels']} levels, {z['Distance from close']} from close).")
    else:
        headline = f"No multi-swing confluence; levels below are from the latest {direction} leg."
    tables = [("Levels of the latest leg", leg)]
    if len(zones_df):
        tables.append(("Confluence zones (levels from two or more swings)", zones_df))
    return Result(headline, facts, tables)


# ---------------------------------------------------------------------------
# Supply and demand zones
# ---------------------------------------------------------------------------


def compute_supply_demand(df: pd.DataFrame, since: pd.Timestamp, scan_bars: int = 252) -> Result:
    a = atr(df, 14).to_numpy(float)
    o, h, low, c = (df[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    body, rng = np.abs(c - o), h - low
    dates = list(df["Date"])
    close = float(c[-1])
    zones = []
    for t in range(max(4, len(df) - scan_bars), len(df)):
        if not np.isfinite(a[t - 1]) or rng[t] < 1.5 * a[t - 1] or body[t] < 0.6 * rng[t]:
            continue
        base = []
        k = t - 1
        while k >= t - 3 and rng[k] > 0 and body[k] <= 0.5 * rng[k]:
            base.append(k)
            k -= 1
        if not base:
            continue
        demand = c[t] > o[t]
        if demand:
            distal = min(low[i] for i in base)
            proximal = max(max(o[i], c[i]) for i in base)
        else:
            distal = max(h[i] for i in base)
            proximal = min(min(o[i], c[i]) for i in base)
        if (demand and proximal <= distal) or (not demand and proximal >= distal):
            proximal = max(h[i] for i in base) if demand else min(low[i] for i in base)
        touches, inside, broken = 0, False, False
        for j in range(t + 1, len(df)):
            entered = low[j] <= proximal if demand else h[j] >= proximal
            if entered and not inside:
                touches += 1
            inside = entered
            if (demand and c[j] < distal) or (not demand and c[j] > distal):
                broken = True
                break
        if broken:
            continue
        zl, zh = (distal, proximal) if demand else (proximal, distal)
        zones.append({"Formed": dates[base[-1]], "Type": "demand" if demand else "supply",
                      "Zone low": zl, "Zone high": zh, "Departure": f"{rng[t] / a[t - 1]:.1f}×ATR",
                      "Touches": touches, "Status": "fresh" if touches == 0 else "tested",
                      "_lo": zl, "_hi": zh})
    kept: list[dict] = []
    for z in sorted(zones, key=lambda z: z["Formed"], reverse=True):
        if not any(k["Type"] == z["Type"] and z["_lo"] <= k["_hi"] and k["_lo"] <= z["_hi"] for k in kept):
            kept.append(z)
    for z in kept:
        if z["_lo"] <= close <= z["_hi"]:
            z["Distance from close"] = "price inside"
        else:
            edge = z["_hi"] if z["_hi"] < close else z["_lo"]
            z["Distance from close"] = _relative(edge, close)
        z["_d"] = 0.0 if z["_lo"] <= close <= z["_hi"] else min(abs(z["_lo"] - close), abs(z["_hi"] - close))
    kept.sort(key=lambda z: z["_d"])
    table = pd.DataFrame([{k: v for k, v in z.items() if not k.startswith("_")} for z in kept[:8]])
    demand_below = [z for z in kept if z["Type"] == "demand" and z["_hi"] <= close]
    supply_above = [z for z in kept if z["Type"] == "supply" and z["_lo"] >= close]
    inside = [z for z in kept if z["_lo"] <= close <= z["_hi"]]
    parts = []
    if inside:
        parts.append(f"price is inside a {inside[0]['Type']} zone {num(inside[0]['_lo'])} – {num(inside[0]['_hi'])}")
    if demand_below:
        z = demand_below[0]
        parts.append(f"nearest demand {num(z['_lo'])} – {num(z['_hi'])} ({z['Status']})")
    if supply_above:
        z = supply_above[0]
        parts.append(f"nearest supply {num(z['_lo'])} – {num(z['_hi'])} ({z['Status']})")
    headline = ("; ".join(parts) or "No active supply or demand zone") + "."
    facts = [("Active zones", f"{len(kept)} ({sum(z['Type'] == 'demand' for z in kept)} demand, "
                              f"{sum(z['Type'] == 'supply' for z in kept)} supply)"),
             ("Rule", "1–3 basing bars (body ≤ 50% of range) followed by a departure bar of ≥1.5×ATR14 "
                      "with a body ≥ 60% of its range; a close beyond the far edge retires the zone")]
    return Result(headline[0].upper() + headline[1:], facts,
                  [("Active supply and demand zones (nearest first)", table)] if len(table) else [])


# ---------------------------------------------------------------------------
# Harmonic patterns
# ---------------------------------------------------------------------------

# Ratio windows: B = AB/XA, C = BC/AB, D = AD/XA, CD = CD/BC.
HARMONICS: dict[str, dict[str, tuple[float, float]]] = {
    "Gartley": {"B": (0.57, 0.67), "C": (0.382, 0.886), "D": (0.75, 0.83), "CD": (1.13, 1.618)},
    "Bat": {"B": (0.35, 0.52), "C": (0.382, 0.886), "D": (0.85, 0.92), "CD": (1.618, 2.618)},
    "Butterfly": {"B": (0.75, 0.83), "C": (0.382, 0.886), "D": (1.24, 1.66), "CD": (1.618, 2.618)},
    "Crab": {"B": (0.35, 0.65), "C": (0.382, 0.886), "D": (1.56, 1.68), "CD": (2.24, 3.618)},
}


def _within(x: float, band: tuple[float, float]) -> bool:
    return band[0] <= x <= band[1]


def compute_harmonic_patterns(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    pivots = zigzag(df)
    close = float(df["Close"].iloc[-1])
    done = []
    for k in range(len(pivots) - 4):
        x, a, b, c, d = pivots[k:k + 5]
        xa, ab, bc, cd = abs(a.price - x.price), abs(b.price - a.price), abs(c.price - b.price), abs(d.price - c.price)
        if min(xa, ab, bc) <= 0:
            continue
        r = {"B": ab / xa, "C": bc / ab, "D": abs(a.price - d.price) / xa, "CD": cd / bc}
        for name, spec in HARMONICS.items():
            if all(_within(r[key], spec[key]) for key in spec):
                done.append({"D date": d.date, "Pattern": name, "Bias": "bullish" if x.kind == "L" else "bearish",
                             "X": x.price, "A": a.price, "B": b.price, "C": c.price, "D": d.price,
                             "Ratios B/C/D/CD": f"{r['B']:.3f}/{r['C']:.3f}/{r['D']:.3f}/{r['CD']:.3f}",
                             "D status": "confirmed" if d.confirmed else "forming"})
    for k in range(len(pivots) - 3):
        a, b, c, d = pivots[k:k + 4]
        ab, bc, cd = abs(b.price - a.price), abs(c.price - b.price), abs(d.price - c.price)
        if min(ab, bc) <= 0:
            continue
        if _within(bc / ab, (0.382, 0.886)) and _within(cd / bc, (1.13, 2.618)) and abs(cd / ab - 1) <= 0.1:
            done.append({"D date": d.date, "Pattern": "AB=CD", "Bias": "bullish" if a.kind == "H" else "bearish",
                         "X": float("nan"), "A": a.price, "B": b.price, "C": c.price, "D": d.price,
                         "Ratios B/C/D/CD": f"-/{bc / ab:.3f}/-/{cd / bc:.3f}",
                         "D status": "confirmed" if d.confirmed else "forming"})
    recent = sorted((p for p in done if p["D date"] >= since), key=lambda p: p["D date"])

    # Patterns whose X-A-B-C are in place, with the D leg still forming.
    confirmed = [p for p in pivots if p.confirmed]
    potential = []
    if len(confirmed) >= 4:
        x, a, b, c = confirmed[-4:]
        xa, ab, bc = abs(a.price - x.price), abs(b.price - a.price), abs(c.price - b.price)
        bullish = x.kind == "L"
        sgn = -1 if bullish else 1
        if min(xa, ab, bc) > 0:
            for name, spec in HARMONICS.items():
                if not (_within(ab / xa, spec["B"]) and _within(bc / ab, spec["C"])):
                    continue
                d_rng = sorted(a.price + sgn * f * xa for f in spec["D"])
                cd_rng = sorted(c.price + sgn * f * bc for f in spec["CD"])
                lo_, hi_ = max(d_rng[0], cd_rng[0]), min(d_rng[1], cd_rng[1])
                if lo_ > hi_:
                    lo_, hi_ = d_rng
                mid = (lo_ + hi_) / 2
                potential.append({"Pattern": name, "Bias at D": "bullish" if bullish else "bearish",
                                  "X": x.price, "A": a.price, "B": b.price, "C": c.price,
                                  "PRZ low": lo_, "PRZ high": hi_, "Distance from close": _relative(mid, close)})
    facts = [("Swing threshold", f"{zigzag_threshold(df) * 100:.1f}%"),
             ("Completed patterns in window", str(len(recent))),
             ("Potential patterns (D leg forming)", str(len(potential)))]
    if potential:
        p = potential[0]
        headline = (f"Potential {p['Bias at D']} {p['Pattern']}: reversal zone {num(p['PRZ low'])} – "
                    f"{num(p['PRZ high'])} ({p['Distance from close']} from close).")
    elif recent:
        p = recent[-1]
        headline = f"Latest completed pattern: {p['Bias']} {p['Pattern']} with D {num(p['D'])} on {day(p['D date'])}."
    else:
        headline = "No harmonic pattern completed in the window or forming."
    tables = []
    if potential:
        tables.append(("Potential patterns and their reversal zones (PRZ)", pd.DataFrame(potential)))
    if recent:
        tables.append(("Completed patterns in window", pd.DataFrame(recent)))
    return Result(headline, facts, tables,
                  ["Ratios follow the commonly published Gartley/Bat/Butterfly/Crab definitions with small tolerances. "
                   "A forming D can still extend; a pattern only matters if price reacts inside the PRZ."])


# ---------------------------------------------------------------------------
# Divergences
# ---------------------------------------------------------------------------


def compute_divergence(df: pd.DataFrame, since: pd.Timestamp, right: int = 3) -> Result:
    osc = {"RSI(14)": rsi(df["Close"], 14), "MACD(12,26)": ema(df["Close"], 12) - ema(df["Close"], 26)}
    pivots = fractal_pivots(df, 3, right)
    events = []
    for kind in ("H", "L"):
        seq = [p for p in pivots if p.kind == kind]
        for p1, p2 in zip(seq[:-1], seq[1:], strict=True):
            if not 5 <= p2.i - p1.i <= 60:
                continue
            confirmed_on = df["Date"].iloc[p2.i + right]
            for name, s in osc.items():
                o1, o2 = s.iloc[p1.i], s.iloc[p2.i]
                if pd.isna(o1) or pd.isna(o2):
                    continue
                if kind == "L":
                    label = ("regular bullish" if p2.price < p1.price and o2 > o1 else
                             "hidden bullish" if p2.price > p1.price and o2 < o1 else None)
                else:
                    label = ("regular bearish" if p2.price > p1.price and o2 < o1 else
                             "hidden bearish" if p2.price < p1.price and o2 > o1 else None)
                if label:
                    events.append({"Confirmed on": confirmed_on, "Divergence": label, "Oscillator": name,
                                   "Swing 1": f"{day(p1.date)} {num(p1.price)} ({num(float(o1))})",
                                   "Swing 2": f"{day(p2.date)} {num(p2.price)} ({num(float(o2))})"})
    events.sort(key=lambda e: e["Confirmed on"])
    recent = [e for e in events if e["Confirmed on"] >= since]
    r_now = float(osc["RSI(14)"].iloc[-1])
    facts = [("RSI(14)", num(r_now)), ("Divergences confirmed in window", str(len(recent)))]
    for label in ("regular bullish", "hidden bullish", "regular bearish", "hidden bearish"):
        n = sum(e["Divergence"] == label for e in recent)
        if n:
            facts.append((label.capitalize(), str(n)))
    if recent:
        e = recent[-1]
        headline = f"Most recent: {e['Divergence']} divergence on {e['Oscillator']}, confirmed {day(e['Confirmed on'])}."
    else:
        headline = "No price/oscillator divergence confirmed in the window."
    notes = [f"Swings are 3-bar fractals, known {right} bars after the swing bar; the confirmation date is that later bar. "
             "Regular divergence warns of reversal, hidden divergence of trend continuation."]
    return Result(headline, facts, [("Divergences in window", pd.DataFrame(recent))] if recent else [], notes)


# ---------------------------------------------------------------------------
# Volatility deviation stops
# ---------------------------------------------------------------------------

DEV_MULTS = (("Warning", 0.0), ("Dev 1", 1.0), ("Dev 2", 2.2), ("Dev 3", 3.6))


def compute_dev_stops(df: pd.DataFrame, since: pd.Timestamp, length: int = 30) -> Result:
    h2 = pd.concat([df["High"], df["High"].shift(1), df["Close"].shift(2)], axis=1).max(axis=1)
    l2 = pd.concat([df["Low"], df["Low"].shift(1), df["Close"].shift(2)], axis=1).min(axis=1)
    tr2 = h2 - l2
    avg, sd = sma(tr2, length), tr2.rolling(length, min_periods=length).std()
    up = sma(df["Close"], 10) > sma(df["Close"], 21)
    ref_long, ref_short = df["Close"].rolling(10).max(), df["Close"].rolling(10).min()
    stops = {}
    for name, m in DEV_MULTS:
        stops[name] = np.where(up, ref_long - (avg + m * sd), ref_short + (avg + m * sd))
    table = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "Trend": np.where(up, "up", "down"),
                          **stops})[df["Date"] >= since]
    close = float(df["Close"].iloc[-1])
    trend_up = bool(up.iloc[-1])
    last = {k: float(v[-1]) for k, v in stops.items()}
    hit = [k for k, v in last.items() if (close < v if trend_up else close > v)]
    facts = [("Trend (SMA10 vs SMA21)", "up" if trend_up else "down"), ("Close", num(close))]
    facts += [(f"{k} stop", num(v)) for k, v in last.items()]
    side = "long" if trend_up else "short"
    if hit:
        headline = f"Close {num(close)} has crossed the {hit[-1]} {side} stop {num(last[hit[-1]])}: the {side} trend is under pressure."
    else:
        headline = f"Close {num(close)} holds above all {side} stops (warning {num(last['Warning'])})." if trend_up else \
                   f"Close {num(close)} holds below all {side} stops (warning {num(last['Warning'])})."
    notes = ["Stops sit a multiple of the two-bar true range's mean plus 0, 1, 2.2 and 3.6 standard deviations "
             "away from the 10-bar highest (lowest) close; wider stops tolerate more noise."]
    return Result(headline, facts, [("Deviation stops", table)], notes)


# ---------------------------------------------------------------------------
# SuperTrend
# ---------------------------------------------------------------------------


def compute_supertrend(df: pd.DataFrame, since: pd.Timestamp, length: int = 10, mult: float = 3.0) -> Result:
    a = atr(df, length).to_numpy(float)
    hl2 = ((df["High"] + df["Low"]) / 2).to_numpy(float)
    c = df["Close"].to_numpy(float)
    n = len(df)
    upper, lower = hl2 + mult * a, hl2 - mult * a
    fu, fl = upper.copy(), lower.copy()
    st = np.full(n, np.nan)
    direction = np.zeros(n, dtype=int)
    start = int(np.argmax(np.isfinite(a))) if np.isfinite(a).any() else n
    for i in range(start, n):
        if i > start:
            fu[i] = upper[i] if upper[i] < fu[i - 1] or c[i - 1] > fu[i - 1] else fu[i - 1]
            fl[i] = lower[i] if lower[i] > fl[i - 1] or c[i - 1] < fl[i - 1] else fl[i - 1]
            prev = direction[i - 1]
            direction[i] = 1 if (prev == -1 and c[i] > fu[i]) else -1 if (prev == 1 and c[i] < fl[i]) else prev
        else:
            direction[i] = 1 if c[i] >= hl2[i] else -1
        st[i] = fl[i] if direction[i] == 1 else fu[i]
    table = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "SuperTrend": st,
                          "Direction": np.where(direction == 1, "up", np.where(direction == -1, "down", "-"))})
    flips = [{"Date": df["Date"].iloc[i], "Flip": "to up" if direction[i] == 1 else "to down", "Close": c[i]}
             for i in range(start + 1, n) if direction[i] != direction[i - 1] and df["Date"].iloc[i] >= since]
    d_now = "up" if direction[-1] == 1 else "down"
    since_i = next((i for i in range(n - 1, start, -1) if direction[i] != direction[i - 1]), start)
    facts = [(f"SuperTrend({length}, {mult})", num(float(st[-1]))), ("Direction", d_now),
             ("In this direction since", day(df["Date"].iloc[since_i])),
             ("Distance from close", _relative(float(st[-1]), float(c[-1])))]
    tables = [("Direction changes in window", pd.DataFrame(flips))] if flips else []
    tables.append(("SuperTrend", table[df["Date"] >= since]))
    return Result(f"SuperTrend is {d_now} since {day(df['Date'].iloc[since_i])}; trailing line {num(float(st[-1]))}.",
                  facts, tables)


# ---------------------------------------------------------------------------
# Multi-timeframe Ichimoku
# ---------------------------------------------------------------------------
#
# A clean-room take on the idea behind NinjaTrader's iMTF indicator: the
# Ichimoku cloud read on several timeframes at once, an entry/trailing-stop
# rule on the daily cloud and ATR extensions. iMTF's own formulas ship
# encrypted and were not recovered; everything below is the textbook Ichimoku
# (Hosoda's 9/26/52) plus rules of our own, stated in the notes. Intraday
# timeframes are left out: the reports work from daily bars.

ICHIMOKU_TIMEFRAMES = (("Daily", None), ("Weekly", "W"), ("Monthly", "M"))
ICHIMOKU_EXTENSIONS = (("Short", 2.0), ("Medium", 3.0), ("Extreme", 4.0))
_SIDE = {1: "above", 0: "inside", -1: "below"}
_TK = {1: "Tenkan > Kijun", 0: "Tenkan = Kijun", -1: "Tenkan < Kijun"}
_CHIKOU = {1: "above", 0: "level", -1: "below"}
_FUTURE = {1: "bullish (A > B)", 0: "flat", -1: "bearish (A < B)"}


def resample_bars(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Weekly ("W") or monthly ("M") bars from daily ones; ``Date`` is each period's last daily bar.

    The latest period may still be in progress; it only holds bars already known.
    """
    periods = df["Date"].dt.to_period(freq)
    g = df.groupby(periods, sort=True)
    out = pd.DataFrame({"Date": g["Date"].last(), "Open": g["Open"].first(), "High": g["High"].max(),
                        "Low": g["Low"].min(), "Close": g["Close"].last()})
    out.index.name = "Period"
    return out


def ichimoku(bars: pd.DataFrame, tenkan: int = 9, kijun: int = 26, senkou: int = 52) -> pd.DataFrame:
    """Ichimoku lines, plus each bar's reading as -1/0/+1 scores.

    The cloud under a bar (``SpanA``/``SpanB``) was projected ``kijun - 1`` bars
    earlier, as charting platforms plot it; ``LeadA``/``LeadB`` are the values
    being projected now (the future cloud). Chikou compares the close with the
    close ``kijun - 1`` bars back.
    """
    h, low, c = bars["High"], bars["Low"], bars["Close"]

    def mid(n: int) -> pd.Series:
        return (h.rolling(n, min_periods=n).max() + low.rolling(n, min_periods=n).min()) / 2

    lag = kijun - 1
    out = pd.DataFrame({"Tenkan": mid(tenkan), "Kijun": mid(kijun)}, index=bars.index)
    out["LeadA"] = (out["Tenkan"] + out["Kijun"]) / 2
    out["LeadB"] = mid(senkou)
    out["SpanA"] = out["LeadA"].shift(lag)
    out["SpanB"] = out["LeadB"].shift(lag)
    out["Cloud top"] = out[["SpanA", "SpanB"]].max(axis=1, skipna=False)
    out["Cloud bottom"] = out[["SpanA", "SpanB"]].min(axis=1, skipna=False)
    close = c.to_numpy(float)
    top, bottom = out["Cloud top"].to_numpy(float), out["Cloud bottom"].to_numpy(float)
    out["Side"] = np.select([close > top, close < bottom, (close <= top) & (close >= bottom)], [1.0, -1.0, 0.0],
                            default=np.nan)
    out["TK"] = np.sign(out["Tenkan"] - out["Kijun"])
    out["Chikou"] = np.sign(c - c.shift(lag))
    out["Future"] = np.sign(out["LeadA"] - out["LeadB"])
    out["Score"] = out[["Side", "TK", "Chikou", "Future"]].sum(axis=1, min_count=1)
    return out


def _bias(score: float) -> str:
    if not math.isfinite(score):
        return "N/A"
    return "bullish" if score >= 2 else "bearish" if score <= -2 else "neutral"


def _label(mapping: dict[int, str], value: float) -> str:
    return mapping[int(value)] if math.isfinite(value) else "N/A"


def _prior_period_side(df: pd.DataFrame, freq: str) -> np.ndarray:
    """For each daily bar, the cloud side of the last *completed* ``freq`` bar before it (NaN if none)."""
    bars = resample_bars(df, freq)
    side = ichimoku(bars)["Side"].to_numpy(float)
    ordinals = np.array([p.ordinal for p in bars.index])
    daily = np.array([p.ordinal for p in df["Date"].dt.to_period(freq)])
    idx = np.searchsorted(ordinals, daily, side="left") - 1
    return np.where(idx >= 0, side[np.clip(idx, 0, None)], np.nan)


def ichimoku_signals(df: pd.DataFrame, ich: pd.DataFrame, atr26: np.ndarray,
                     weekly_side: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Daily long/short state, trailing stop and the entry/exit events.

    Long entry: the first bar of close above the cloud, Tenkan above Kijun and
    Chikou above its reference, unless the last completed week closed below its
    cloud. Short entry mirrors it. The stop starts at the Kijun or one ATR(26)
    from the close, whichever is wider, then trails the Kijun and never loosens;
    a close through it exits.
    """
    c = df["Close"].to_numpy(float)
    kij = ich["Kijun"].to_numpy(float)
    side, tk, chik = (ich[k].to_numpy(float) for k in ("Side", "TK", "Chikou"))
    bull = (side == 1) & (tk == 1) & (chik == 1)
    bear = (side == -1) & (tk == -1) & (chik == -1)
    n = len(df)
    state = np.zeros(n, dtype=int)
    trail = np.full(n, np.nan)
    events: list[dict] = []
    pos, stop = 0, math.nan

    def event(i: int, what: str, level: float) -> None:
        events.append({"Date": df["Date"].iloc[i], "Event": what, "Close": c[i], "Stop": level})

    for i in range(n):
        if pos == 1:
            if math.isfinite(kij[i]):
                stop = max(stop, kij[i])
            if c[i] < stop:
                event(i, "long exit (stop)", stop)
                pos = 0
        elif pos == -1:
            if math.isfinite(kij[i]):
                stop = min(stop, kij[i])
            if c[i] > stop:
                event(i, "short exit (stop)", stop)
                pos = 0
        new_bull = bull[i] and not (i and bull[i - 1])
        new_bear = bear[i] and not (i and bear[i - 1])
        if new_bull and pos != 1 and weekly_side[i] != -1:
            if pos == -1:
                event(i, "short exit (reversal)", stop)
            far = c[i] - atr26[i] if math.isfinite(atr26[i]) else kij[i]
            pos, stop = 1, min(kij[i], far)
            event(i, "long entry", stop)
        elif new_bear and pos != -1 and weekly_side[i] != 1:
            if pos == 1:
                event(i, "long exit (reversal)", stop)
            far = c[i] + atr26[i] if math.isfinite(atr26[i]) else kij[i]
            pos, stop = -1, max(kij[i], far)
            event(i, "short entry", stop)
        state[i] = pos
        trail[i] = stop if pos else np.nan
    return state, trail, events


def compute_mtf_ichimoku(df: pd.DataFrame, since: pd.Timestamp) -> Result:
    close = float(df["Close"].iloc[-1])
    frames: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    for label, freq in ICHIMOKU_TIMEFRAMES:
        bars = df if freq is None else resample_bars(df, freq)
        frames[label] = (bars, ichimoku(bars))

    rows, levels, biases = [], [], {}
    for label, (bars, ich) in frames.items():
        last = ich.iloc[-1]
        biases[label] = _bias(float(last["Score"]))
        rows.append({"Timeframe": label, "Bars": len(bars), "Through": bars["Date"].iloc[-1],
                     "Tenkan": last["Tenkan"], "Kijun": last["Kijun"],
                     "Cloud top": last["Cloud top"], "Cloud bottom": last["Cloud bottom"],
                     "Close vs cloud": _label(_SIDE, last["Side"]), "TK": _label(_TK, last["TK"]),
                     "Chikou": _label(_CHIKOU, last["Chikou"]), "Future cloud": _label(_FUTURE, last["Future"]),
                     "Score": last["Score"], "Bias": biases[label]})
        for name in ("Tenkan", "Kijun", "Cloud top", "Cloud bottom"):
            if math.isfinite(float(last[name])):
                levels.append((f"{label} {name}", float(last[name])))

    daily = frames["Daily"][1]
    atr26 = atr(df, 26).to_numpy(float)
    state, trail, events = ichimoku_signals(df, daily, atr26, _prior_period_side(df, "W"))

    known = [b for b in biases.values() if b != "N/A"]
    bulls, bears = known.count("bullish"), known.count("bearish")
    if known and bulls == len(known):
        alignment = f"bullish on all {len(known)} timeframes"
    elif known and bears == len(known):
        alignment = f"bearish on all {len(known)} timeframes"
    else:
        alignment = f"mixed ({bulls} bullish, {bears} bearish of {len(known)})"

    pos, stop, kij, a = int(state[-1]), float(trail[-1]), float(daily["Kijun"].iloc[-1]), float(atr26[-1])
    facts = [("Timeframe alignment", alignment), ("Close", num(close))]
    facts += [(f"{label} bias", biases[label]) for label in biases]
    if pos:
        opened = next(e for e in reversed(events) if e["Event"].endswith("entry"))
        side_name = "long" if pos == 1 else "short"
        position = (f"{side_name} since {day(opened['Date'])} at {num(opened['Close'])}, "
                    f"trailing stop {num(stop)}")
        facts += [("Daily signal", position), ("Trailing stop", num(stop)),
                  ("Stop distance", _relative(stop, close))]
        sign = 1 if pos == 1 else -1
        facts += [(f"{name} extension (Kijun {'+' if sign > 0 else '-'} {m:g}×ATR26)", num(kij + sign * m * a))
                  for name, m in ICHIMOKU_EXTENSIONS]
    else:
        position = "no open daily signal"
        facts.append(("Daily signal", position))
    stretch = (close - kij) / a if a and math.isfinite(a) and math.isfinite(kij) else math.nan
    facts.append(("Close vs daily Kijun", "N/A" if not math.isfinite(stretch) else f"{stretch:+.2f} ATR(26)"))
    above = sorted((x for x in levels if x[1] > close), key=lambda x: x[1])[:3]
    below = sorted((x for x in levels if x[1] < close), key=lambda x: -x[1])[:3]
    facts += [("Nearest Ichimoku levels above", ", ".join(f"{n} {num(v)}" for n, v in above) or "none"),
              ("Nearest Ichimoku levels below", ", ".join(f"{n} {num(v)}" for n, v in below) or "none")]

    stretched = ""
    if pos and math.isfinite(stretch):
        beyond = [name for name, m in ICHIMOKU_EXTENSIONS if stretch * pos >= m]
        if beyond:
            stretched = f"; price is past the {beyond[-1].lower()} extension, stretched from the Kijun"
    headline = (f"Ichimoku is {alignment} (daily {biases['Daily']}, weekly {biases['Weekly']}, "
                f"monthly {biases['Monthly']}); {position}{stretched}.")

    series = pd.DataFrame({"Date": df["Date"], "Close": df["Close"], "Tenkan": daily["Tenkan"],
                           "Kijun": daily["Kijun"], "Cloud top": daily["Cloud top"],
                           "Cloud bottom": daily["Cloud bottom"],
                           "Signal": np.where(state == 1, "long", np.where(state == -1, "short", "flat")),
                           "Trailing stop": trail})[df["Date"] >= since]
    recent = [e for e in events if e["Date"] >= since]
    tables = [("Ichimoku by timeframe", pd.DataFrame(rows))]
    if recent:
        tables.append(("Daily signals in window", pd.DataFrame(recent)))
    tables.append(("Daily Ichimoku", series))

    notes = ["Clean-room multi-timeframe Ichimoku in the spirit of NinjaTrader's iMTF; iMTF's own formulas are "
             "encrypted in its DLL and were not used, so levels will differ from it.",
             "Tenkan/Kijun/Senkou B are 9/26/52-bar high-low midpoints; the cloud under each bar was projected 25 bars "
             "earlier; Chikou compares the close with the close 25 bars back. Weekly and monthly bars are built from "
             "the daily ones, the latest possibly still in progress. A timeframe needs 77 of its bars for a cloud.",
             "Score per timeframe: +1/-1 each for close above/below the cloud, Tenkan above/below Kijun, Chikou "
             "above/below and a bullish/bearish future cloud; ±2 or more is a bias.",
             "Daily entry: the first bar with close beyond the cloud, Tenkan/Kijun and Chikou all agreeing, unless "
             "the last completed week sits on the other side of its cloud. The stop starts at the wider of Kijun "
             "and 1×ATR(26), trails the Kijun and never loosens. Extensions are Kijun ± 2/3/4×ATR(26)."]
    return Result(headline, facts, tables, notes)
