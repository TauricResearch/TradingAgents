"""Calibration layer: aggregate settled multi-horizon outcomes into a compact
record of how well the model's rating direction has actually played out, per
ticker and cross-ticker.

Pure aggregation over the parsed memory log — no LLM call — so it is cheap to
recompute on every run and inject as context. The rating's expected direction is:

    Buy/Overweight  -> positive alpha
    Sell/Underweight -> negative alpha
    Hold            -> roughly flat (|alpha| within a small band)

A "hit" is the alpha at a horizon landing on the expected side of the benchmark.
Aggregates are win-rate per horizon; the anchor horizon (the fast signal) is the
primary one. With no settled, scored entries yet every aggregate is empty and the
rendered line is blank, so this is a no-op until decisions start settling in.
"""

from __future__ import annotations

_BULL = {"buy", "overweight"}
_BEAR = {"sell", "underweight"}
_HOLD = {"hold", "neutral"}
_HOLD_BAND = 0.02  # within ±2% alpha counts as a "hold" hit (no clear move)


def _hit(rating, alpha):
    """True/False whether ``alpha`` landed on ``rating``'s expected side, or
    None when the rating or the alpha is not evaluable."""
    if alpha is None:
        return None
    r = (rating or "").strip().lower()
    if r in _BULL:
        return alpha > 0
    if r in _BEAR:
        return alpha < 0
    if r in _HOLD:
        return abs(alpha) < _HOLD_BAND
    return None


def build_calibration(entries, ticker, anchor, as_of=None):
    """Aggregate outcome hits for ``ticker`` and (cross) the full log.

    ``entries`` are the parsed memory-log dicts (see
    ``TradingMemoryLog.load_entries``); ``anchor`` is the primary horizon.
    Returns::

        {"ticker": {"n": int, "by_horizon": {h: {"n","hits","rate"}},
                    "anchor_rate": rate|None, "realized": {"n","hits","rate"}},
         "cross":  {... same shape over all tickers ...}}

    Only horizons actually present and evaluable count toward a horizon's rate.
    The ``realized`` bucket aggregates recorded real-portfolio P&L (ground
    truth, see ``memory/realized.py``). ``as_of`` (a ``YYYY-MM-DD`` string)
    drops entries that were not yet known by that date, keeping the figure
    point-in-time for backtests (#1251).
    """
    if as_of is not None:
        entries = [e for e in entries
                   if e.get("resolved") and e["resolved"] <= as_of]

    def _agg(subset):
        by_h: dict[int, dict] = {}
        real_n = 0
        real_hits = 0
        for e in subset:
            for h, v in (e.get("horizons") or {}).items():
                hit = _hit(e.get("rating"), (v or {}).get("alpha"))
                if hit is None:
                    continue
                d = by_h.setdefault(h, {"n": 0, "hits": 0})
                d["n"] += 1
                d["hits"] += 1 if hit else 0
            r = e.get("realized")
            if isinstance(r, dict) and r.get("return") is not None:
                hit = _hit(e.get("rating"), r["return"])
                if hit is not None:
                    real_n += 1
                    real_hits += 1 if hit else 0
        for d in by_h.values():
            d["rate"] = (d["hits"] / d["n"]) if d["n"] else None
        realized = {"n": real_n, "hits": real_hits,
                   "rate": (real_hits / real_n) if real_n else None}
        return by_h, realized

    def _pack(subset):
        by_h, realized = _agg(subset)
        n = sum(d["n"] for d in by_h.values()) + realized["n"]
        anchor_rate = by_h[anchor]["rate"] if anchor in by_h else None
        return {"n": n, "by_horizon": by_h, "anchor_rate": anchor_rate, "realized": realized}

    same = [e for e in entries if e.get("ticker") == ticker]
    return {"ticker": _pack(same), "cross": _pack(entries)}


def render_calibration(calib, ticker, max_horizons=4) -> str:
    """One compact line for context injection; empty when nothing has settled."""
    if not calib:
        return ""

    def _fmt(pack):
        bits = []
        rz = pack.get("realized")
        if rz and rz.get("n"):
            bits.append(f"realized {rz['hits']}/{rz['n']}")  # ground truth first
        if pack.get("by_horizon"):
            bits += [f"{h}d {d['hits']}/{d['n']}"
                     for h, d in sorted(pack["by_horizon"].items())[:max_horizons]]
        if not bits:
            return "no outcomes yet"
        return " ".join(bits)

    t, c = calib["ticker"], calib["cross"]
    if t["n"] == 0 and c["n"] == 0:
        return ""
    parts = []
    if t["n"]:
        parts.append(f"{ticker} {t['n']} calls: {_fmt(t)}")
    if c["n"]:
        parts.append(f"all tickers {c['n']} calls: {_fmt(c)}")
    return "CALIBRATION — " + " | ".join(parts)
