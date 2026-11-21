"""Harmonic pattern scanner modelled on the HPC (Harmonic Pattern Collection) suite.

What was taken from the NinjaTrader 8 package ``HPCIndicatorsNinja8_181017A``,
and what was not:

* The managed assembly is protected with Agile.NET: its method bodies are
  encrypted and only the protector's loader strings are readable. The pattern
  engine itself is a native Delphi library (``harmonicPatterns64.dll``) whose
  exports (``initEngine``, ``setBooleanParams``, ``primaryScan``,
  ``secondaryScan``, ``requestPattern``, ``getPendingCount`` ...) name its
  steps but not its formulas. Neither was decompiled or reproduced.
* What *is* public is the indicator's parameter surface (the generated
  NinjaScript wrapper and the shipped chart templates): the pattern set (AB=CD,
  Bat, Butterfly, Gartley, Crab, Shark, 5-0), a strict AB=CD in ATRs (default
  1.5), a minimum/maximum pattern length (30..300 bars on intraday charts),
  at most two points shared between patterns, hiding patterns inside others,
  and three states: confirmed, pending and potential. Those options are mirrored
  here.

Everything numeric below is written from the commonly published harmonic
ratios (Carney's Gartley/Bat/Butterfly/Crab/Shark/5-0 and AB=CD). The swing
detection, scoring, targets and stops are rules of our own, stated in the
report notes. HPC's oscillators (HSI, AmpRSI, RSI BAMM), its Pi/Phi bands and
its volume spike are proprietary formulas in the native engine and are not
reproduced.

Ratios, with X-A-B-C-D the five swing points (D the reversal point):
``XB`` = AB/XA, ``AC`` = BC/AB, ``XD`` = AD/XA, ``BD`` = CD/BC, ``XCD`` = CD/XC.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tradingagents.dataflows.strategy_indicators import calc
from tradingagents.dataflows.strategy_indicators.calc import Pivot, Result, day, num

Band = tuple[float, float]


@dataclass(frozen=True)
class PatternSpec:
    name: str
    ratios: dict[str, Band]
    ideal: dict[str, float]
    d_from: tuple[str, ...]     # which ratios project the D zone (PRZ)
    points: int = 5             # 5 for X-A-B-C-D, 4 for A-B-C-D


# Published ratio windows, widened by a few hundredths where the definition
# names a single value (0.618, 0.786, 0.886, 1.618 ...).
PATTERNS: dict[str, PatternSpec] = {
    "Gartley": PatternSpec(
        "Gartley",
        {"XB": (0.588, 0.648), "AC": (0.382, 0.886), "XD": (0.756, 0.816), "BD": (1.13, 1.618)},
        {"XB": 0.618, "XD": 0.786}, ("XD", "BD")),
    "Bat": PatternSpec(
        "Bat",
        {"XB": (0.382, 0.50), "AC": (0.382, 0.886), "XD": (0.856, 0.916), "BD": (1.618, 2.618)},
        {"XB": 0.50, "XD": 0.886}, ("XD", "BD")),
    "Butterfly": PatternSpec(
        "Butterfly",
        {"XB": (0.756, 0.816), "AC": (0.382, 0.886), "XD": (1.27, 1.618), "BD": (1.618, 2.24)},
        {"XB": 0.786, "XD": 1.27}, ("XD", "BD")),
    "Crab": PatternSpec(
        "Crab",
        {"XB": (0.382, 0.618), "AC": (0.382, 0.886), "XD": (1.588, 1.648), "BD": (2.24, 3.618)},
        {"XD": 1.618}, ("XD", "BD")),
    "Shark": PatternSpec(
        "Shark",
        {"XB": (0.382, 0.886), "AC": (1.13, 1.618), "XCD": (0.856, 1.13), "BD": (1.618, 2.24)},
        {"AC": 1.13, "XCD": 0.886}, ("XCD", "BD")),
    "5-0": PatternSpec(
        "5-0",
        {"XB": (1.13, 1.618), "AC": (1.618, 2.24), "BD": (0.47, 0.53)},
        {"BD": 0.50}, ("BD",)),
    "AB=CD": PatternSpec(
        "AB=CD",
        {"AC": (0.382, 0.886), "BD": (1.13, 2.618)},
        {}, ("BD",), points=4),
}

# Retracements of AD from D used as targets (the usual 38.2% / 61.8% of the
# pattern's last leg).
TARGETS = (("T1", 0.382), ("T2", 0.618))


@dataclass(frozen=True)
class ScanSettings:
    """HPC's pattern options, with defaults chosen for daily bars."""

    patterns: tuple[str, ...] = tuple(PATTERNS)
    show_bullish: bool = True
    show_bearish: bool = True
    strict_abcd: bool = True
    strict_atrs: float = 1.5          # |CD - AB| allowed, in ATR(14) at C
    min_pattern_length: int = 8       # bars from the first point to D
    max_pattern_length: int = 300
    max_points_shared: int = 2        # between two reported patterns
    hide_inside: bool = True          # drop a pattern lying inside a better one of the same bias
    show_pending: bool = True
    show_potential: bool = True


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def _named(pts: list[Pivot], spec: PatternSpec) -> dict[str, Pivot]:
    """Name a run of swings X, A, B, C[, D] (A, B, C[, D] for AB=CD)."""
    keys = "XABCD" if spec.points == 5 else "ABCD"
    return dict(zip(keys, pts, strict=False))


def ratios_of(pts: dict[str, Pivot]) -> dict[str, float]:
    """Every ratio the named points define; D may still be missing."""
    def leg(p: str, q: str) -> float:
        return abs(pts[q].price - pts[p].price) if p in pts and q in pts else 0.0

    out: dict[str, float] = {}
    for key, num_leg, den_leg in (("XB", ("A", "B"), ("X", "A")), ("AC", ("B", "C"), ("A", "B")),
                                  ("XD", ("A", "D"), ("X", "A")), ("BD", ("C", "D"), ("B", "C")),
                                  ("XCD", ("C", "D"), ("X", "C"))):
        top, bottom = leg(*num_leg), leg(*den_leg)
        if bottom > 0 and all(p in pts for p in (*num_leg, *den_leg)):
            out[key] = top / bottom
    return out


def prz(spec: PatternSpec, pts: dict[str, Pivot]) -> tuple[float, float] | None:
    """The D zone: where every D-projecting ratio of ``spec`` holds at once.

    Falls back to the first (primary) projection when they do not overlap.
    """
    c = pts["C"]
    # D lies below a C high and above a C low; A is on C's side of the
    # pattern, so AD runs the same way.
    toward = -1.0 if c.kind == "H" else 1.0
    measured = {"XD": ("A", "X"), "XCD": ("C", "X"), "BD": ("C", "B")}
    ranges = []
    for key in spec.d_from:
        lo, hi = spec.ratios[key]
        origin_name, other = measured[key]
        origin = pts[origin_name].price
        leg = abs(origin - pts[other].price)
        if leg <= 0:
            return None
        ranges.append(tuple(sorted((origin + toward * lo * leg, origin + toward * hi * leg))))
    lo_, hi_ = max(r[0] for r in ranges), min(r[1] for r in ranges)
    if lo_ > hi_:
        lo_, hi_ = ranges[0]
    return float(lo_), float(hi_)


def _matches(spec: PatternSpec, ratios: dict[str, float], keys) -> bool:
    return all(k in ratios and spec.ratios[k][0] <= ratios[k] <= spec.ratios[k][1] for k in keys)


def quality(spec: PatternSpec, ratios: dict[str, float]) -> float:
    """100 at the ideal ratios, falling linearly to 0 at a window's edge.

    Ratios without a single ideal value score against their window's middle.
    """
    errs = []
    for key, (lo, hi) in spec.ratios.items():
        if key not in ratios:
            continue
        target = spec.ideal.get(key, (lo + hi) / 2)
        half = max(target - lo, hi - target, 1e-9)
        errs.append(min(1.0, abs(ratios[key] - target) / half))
    return 100.0 * (1 - float(np.mean(errs))) if errs else 0.0


def _strict_abcd_ok(pts: dict[str, Pivot], atr_at_c: float, settings: ScanSettings) -> bool:
    if not settings.strict_abcd or not np.isfinite(atr_at_c) or atr_at_c <= 0:
        return True
    ab = abs(pts["B"].price - pts["A"].price)
    cd = abs(pts["D"].price - pts["C"].price)
    return abs(cd - ab) <= settings.strict_atrs * atr_at_c


def _stop(spec: PatternSpec, pts: dict[str, Pivot], zone: tuple[float, float], atr_now: float) -> float:
    """Invalidation: X for patterns whose D stays inside XA (Gartley, Bat);
    otherwise one ATR beyond the PRZ's far edge."""
    bullish = pts["C"].kind == "H"
    if "XD" in spec.ratios and spec.ratios["XD"][1] < 1:
        return float(pts["X"].price)
    pad = atr_now if np.isfinite(atr_now) else 0.0
    return float(zone[0] - pad) if bullish else float(zone[1] + pad)


def _targets(a_price: float, d_price: float) -> dict[str, float]:
    return {name: float(d_price + f * (a_price - d_price)) for name, f in TARGETS}


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _confirmed_on(df: pd.DataFrame, d: Pivot, threshold: float) -> pd.Timestamp | None:
    """First bar after D whose price moved ``threshold`` away from it."""
    if d.kind == "L":
        hit = np.nonzero(df["High"].to_numpy(float)[d.i + 1:] >= d.price * (1 + threshold))[0]
    else:
        hit = np.nonzero(df["Low"].to_numpy(float)[d.i + 1:] <= d.price * (1 - threshold))[0]
    return df["Date"].iloc[d.i + 1 + int(hit[0])] if len(hit) else None


def _outcome(df: pd.DataFrame, d: Pivot, stop: float, targets: dict[str, float]) -> str:
    """How the trade from D played out on the bars that followed.

    A bar that touches both the stop and a target counts as stopped: daily
    bars do not say which came first.
    """
    sign = 1.0 if d.kind == "L" else -1.0      # +1: a long from a D low
    highs, lows = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    t1_hit = False
    for i in range(d.i + 1, len(df)):
        best, worst = (highs[i], lows[i]) if sign > 0 else (lows[i], highs[i])
        if sign * (worst - stop) <= 0:
            return "T1 hit then stopped" if t1_hit else "stopped"
        if sign * (best - targets["T2"]) >= 0:
            return "T2 hit"
        if sign * (best - targets["T1"]) >= 0:
            t1_hit = True
    return "T1 hit" if t1_hit else "open"


def _row(spec: PatternSpec, pts: dict[str, Pivot], ratios: dict[str, float]) -> dict:
    return {
        "Pattern": spec.name,
        "Bias": "bullish" if pts["C"].kind == "H" else "bearish",
        **{k: (pts[k].price if k in pts else float("nan")) for k in "XABC"},
        "Ratios": " ".join(f"{k} {ratios[k]:.3f}" for k in spec.ratios if k in ratios),
        "Quality": round(quality(spec, ratios), 1),
    }


def _wanted(bullish: bool, settings: ScanSettings) -> bool:
    return settings.show_bullish if bullish else settings.show_bearish


def find_completed(df: pd.DataFrame, pivots: list[Pivot], settings: ScanSettings, threshold: float) -> list[dict]:
    """Patterns whose D is a confirmed swing, with their PRZ, targets, stop and outcome.

    A D still forming is not here: :func:`find_potential` reports it as pending.
    """
    atr14 = calc.atr(df, 14).to_numpy(float)
    found = []
    for spec in (PATTERNS[n] for n in settings.patterns if n in PATTERNS):
        for k in range(len(pivots) - spec.points + 1):
            seq = pivots[k:k + spec.points]
            pts = _named(seq, spec)
            d = pts["D"]
            bullish = d.kind == "L"
            if not d.confirmed or not _wanted(bullish, settings):
                continue
            if not settings.min_pattern_length <= d.i - seq[0].i <= settings.max_pattern_length:
                continue
            ratios = ratios_of(pts)
            if not _matches(spec, ratios, spec.ratios):
                continue
            if spec.name == "AB=CD" and not _strict_abcd_ok(pts, atr14[pts["C"].i], settings):
                continue
            zone = prz(spec, pts)
            if zone is None:
                continue
            stop = _stop(spec, pts, zone, atr14[d.i])
            targets = _targets(pts["A"].price, d.price)
            row = _row(spec, pts, ratios)
            row.update({
                "D date": d.date, "D": d.price, "Status": "confirmed",
                "Confirmed on": _confirmed_on(df, d, threshold),
                "PRZ low": zone[0], "PRZ high": zone[1], "Stop": stop, **targets,
                "Outcome": _outcome(df, d, stop, targets),
                "_points": frozenset(p.i for p in seq), "_span": (seq[0].i, d.i), "_bullish": bullish,
            })
            found.append(row)
    return _filter_overlaps(found, settings)


def _filter_overlaps(rows: list[dict], settings: ScanSettings) -> list[dict]:
    """Best quality first; drop patterns sharing too many points with, or lying
    inside, a better one already kept."""
    kept: list[dict] = []
    for row in sorted(rows, key=lambda r: -r["Quality"]):
        if any(len(row["_points"] & k["_points"]) > settings.max_points_shared for k in kept):
            continue
        if settings.hide_inside and any(
            k["_bullish"] == row["_bullish"] and k["_span"][0] <= row["_span"][0] and row["_span"][1] <= k["_span"][1]
            and k["_span"] != row["_span"] for k in kept
        ):
            continue
        kept.append(row)
    return sorted(kept, key=lambda r: r["D date"])


def find_potential(df: pd.DataFrame, pivots: list[Pivot], settings: ScanSettings) -> list[dict]:
    """Patterns whose points up to C are confirmed swings and whose D leg is still forming.

    If the leg in progress has already reached the PRZ, the pattern is *pending*
    (reversal awaited); if it has run through the PRZ, the pattern failed and
    is dropped; otherwise it is *potential*.
    """
    confirmed = [p for p in pivots if p.confirmed]
    if not confirmed:
        return []
    forming = pivots[-1] if not pivots[-1].confirmed else None
    close = float(df["Close"].iloc[-1])
    atr_now = float(calc.atr(df, 14).iloc[-1])
    out = []
    for spec in (PATTERNS[n] for n in settings.patterns if n in PATTERNS):
        need = spec.points - 1
        if len(confirmed) < need:
            continue
        seq = confirmed[-need:]
        pts = _named(seq, spec)
        c = pts["C"]
        bullish = c.kind == "H"
        if not _wanted(bullish, settings) or c.i - seq[0].i > settings.max_pattern_length:
            continue
        ratios = ratios_of(pts)
        if not _matches(spec, ratios, [k for k in ("XB", "AC") if k in spec.ratios]):
            continue
        zone = prz(spec, pts)
        if zone is None:
            continue
        if spec.name == "AB=CD" and settings.strict_abcd and np.isfinite(atr_now):
            # Strict AB=CD narrows the zone to CD = AB within the ATR allowance.
            ab = abs(pts["B"].price - pts["A"].price)
            toward = -1.0 if bullish else 1.0
            eq = sorted(c.price + toward * (ab + s * settings.strict_atrs * atr_now) for s in (-1, 1))
            lo_, hi_ = max(zone[0], eq[0]), min(zone[1], eq[1])
            if lo_ > hi_:
                continue
            zone = (float(lo_), float(hi_))
        stop = _stop(spec, pts, zone, atr_now)
        # The D leg's extreme so far: the forming swing after C (the zigzag
        # alternates, so it runs away from C); before one exists, the close.
        extreme = forming.price if forming is not None and forming.kind != c.kind else close
        far = zone[0] if bullish else zone[1]
        if (extreme < far) if bullish else (extreme > far):
            continue    # the D leg ran through the zone: the pattern failed
        in_zone = zone[0] <= extreme <= zone[1]
        if in_zone and not settings.show_pending:
            continue
        if not in_zone and not settings.show_potential:
            continue
        near = zone[1] if bullish else zone[0]
        row = _row(spec, pts, ratios)
        row.update({"Status": "pending (in PRZ)" if in_zone else "potential",
                    "D leg extreme": extreme, "PRZ low": zone[0], "PRZ high": zone[1], "Stop": stop,
                    "Distance to PRZ": "inside" if in_zone else calc._relative(near, close)})
        out.append(row)
    out.sort(key=lambda r: (r["Status"] != "pending (in PRZ)", -r["Quality"]))
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _public(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows])


def _playbook(rows: list[dict]) -> pd.DataFrame:
    """Per pattern and bias: how many confirmed patterns reached T1, T2 or the stop."""
    done = [r for r in rows if r["Status"] == "confirmed" and r["Outcome"] != "open"]
    stats = []
    for (name, bias), group in pd.DataFrame(done).groupby(["Pattern", "Bias"]) if done else []:
        n = len(group)
        t1 = group["Outcome"].str.startswith(("T1", "T2")).sum()
        t2 = (group["Outcome"] == "T2 hit").sum()
        stopped = (group["Outcome"] == "stopped").sum()
        stats.append({"Pattern": name, "Bias": bias, "Closed": n,
                      "Reached T1": f"{t1}/{n}", "Reached T2": f"{t2}/{n}", "Stopped first": f"{stopped}/{n}"})
    return pd.DataFrame(stats)


def compute_harmonic_scanner(df: pd.DataFrame, since: pd.Timestamp, settings: ScanSettings | None = None) -> Result:
    settings = settings or ScanSettings()
    threshold = calc.zigzag_threshold(df)
    pivots = calc.zigzag(df, threshold)
    completed = find_completed(df, pivots, settings, threshold)
    potential = find_potential(df, pivots, settings)
    recent = [r for r in completed if r["D date"] >= since]
    pending = [r for r in potential if r["Status"].startswith("pending")]
    facts = [
        ("Swing threshold", f"{threshold * 100:.1f}%"),
        ("Patterns scanned", ", ".join(settings.patterns)),
        ("Confirmed in window", str(sum(r["Status"] == "confirmed" for r in recent))),
        ("Pending (in PRZ, reversal awaited)", str(len(pending))),
        ("Potential (D leg forming)", str(sum(r["Status"] == "potential" for r in potential))),
    ]
    if pending:
        p = pending[0]
        headline = (f"Pending {p['Bias']} {p['Pattern']}: price is inside the reversal zone "
                    f"{num(p['PRZ low'])} – {num(p['PRZ high'])} (stop {num(p['Stop'])}); reversal not yet confirmed.")
    elif potential:
        p = potential[0]
        headline = (f"Potential {p['Bias']} {p['Pattern']} (quality {p['Quality']:.0f}): reversal zone "
                    f"{num(p['PRZ low'])} – {num(p['PRZ high'])}, {p['Distance to PRZ']} from the close.")
    elif recent:
        p = recent[-1]
        headline = (f"Latest confirmed: {p['Bias']} {p['Pattern']} with D {num(p['D'])} on {day(p['D date'])}, "
                    f"outcome so far: {p['Outcome']}.")
    else:
        headline = "No harmonic pattern confirmed in the window, pending or forming."

    tables = []
    if potential:
        tables.append(("Pending and potential patterns (D leg forming)", _public(potential)))
    if recent:
        tables.append(("Patterns completed in window", _public(recent)))
    playbook = _playbook(completed)
    if not playbook.empty:
        tables.append(("How confirmed patterns played out on this instrument (full history)", playbook))
    notes = [
        "Swings are zigzag pivots that reversed by an adaptive threshold (three median daily ATRs). A D is "
        "confirmed on the first bar that moved that threshold away from it.",
        "Ratios follow the commonly published definitions (XB = AB/XA, AC = BC/AB, XD = AD/XA, BD = CD/BC, "
        "XCD = CD/XC). Quality is 100 at the ideal ratios and 0 at a window's edge.",
        f"Strict AB=CD: CD must equal AB within {settings.strict_atrs} ATR(14). Patterns sharing more than "
        f"{settings.max_points_shared} points with, or lying inside, a better one are hidden.",
        "Targets are 38.2% (T1) and 61.8% (T2) retracements of AD from D. The stop is X for Gartley and Bat, "
        "otherwise one ATR beyond the PRZ's far edge. A bar touching both a target and the stop counts as stopped.",
        "Pattern options mirror HPC's harmonic pattern indicator; its formulas are not public and were not used.",
    ]
    return Result(headline, facts, tables, notes)
