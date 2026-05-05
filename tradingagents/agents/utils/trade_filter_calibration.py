import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class TradeCalibrationRow:
    ticker: str
    date: str
    r_mult: float
    market_q: float
    execution_q: float
    signal_q: float
    hard_reject: bool


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _get_nested(d: Any, *path: str, default: Any = None) -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def load_calibration_rows(jsonl_path: str, *, include_hard_reject: bool = False) -> List[TradeCalibrationRow]:
    p = Path(jsonl_path).expanduser()
    rows: List[TradeCalibrationRow] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue

        if rec.get("pending"):
            continue

        meta = rec.get("meta") or {}
        outcome = rec.get("outcome") or {}

        r_mult = _to_float(_get_nested(outcome, "approx_r_multiple"))
        if r_mult is None or math.isnan(r_mult):
            continue

        details = _get_nested(meta, "trade_filter_details", default={}) or {}
        market_q = _to_float(_get_nested(details, "market_quality"))
        execution_q = _to_float(_get_nested(details, "execution_quality"))
        signal_q = _to_float(_get_nested(details, "signal_quality"))
        hard_reject = bool(_get_nested(details, "hard_reject", default=False))

        if market_q is None or execution_q is None or signal_q is None:
            continue
        if hard_reject and not include_hard_reject:
            continue

        ticker = str(rec.get("ticker") or "")
        date = str(rec.get("date") or "")
        rows.append(
            TradeCalibrationRow(
                ticker=ticker,
                date=date,
                r_mult=float(r_mult),
                market_q=float(market_q),
                execution_q=float(execution_q),
                signal_q=float(signal_q),
                hard_reject=hard_reject,
            )
        )
    return rows


def _safe_mean(xs: Iterable[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not math.isnan(x)]
    return mean(vals) if vals else None


def _safe_median(xs: Iterable[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not math.isnan(x)]
    return median(vals) if vals else None


def _win_rate(xs: Iterable[float]) -> Optional[float]:
    vals = [x for x in xs if x is not None and not math.isnan(x)]
    if not vals:
        return None
    return sum(1 for x in vals if x > 0) / len(vals)


def score_from_weights(
    *,
    market_q: float,
    execution_q: float,
    signal_q: float,
    w_market: float,
    w_execution: float,
    w_signal: float,
) -> float:
    s = w_market * market_q + w_execution * execution_q + w_signal * signal_q
    if s < 0.0:
        return 0.0
    if s > 1.0:
        return 1.0
    return float(s)


def evaluate_config(
    rows: List[TradeCalibrationRow],
    *,
    w_market: float,
    w_execution: float,
    w_signal: float,
    threshold: float,
    min_count: int = 30,
    objective: str = "mean_r",
) -> Dict[str, Any]:
    selected = []
    for r in rows:
        s = score_from_weights(
            market_q=r.market_q,
            execution_q=r.execution_q,
            signal_q=r.signal_q,
            w_market=w_market,
            w_execution=w_execution,
            w_signal=w_signal,
        )
        if s >= threshold:
            selected.append((s, r))

    n = len(selected)
    r_mults = [r.r_mult for _, r in selected]
    mean_r = _safe_mean(r_mults)
    med_r = _safe_median(r_mults)
    win = _win_rate(r_mults)

    if mean_r is None:
        mean_r = -999.0
    if objective == "mean_r":
        base = float(mean_r)
    elif objective == "median_r":
        base = float(med_r) if med_r is not None else -999.0
    elif objective == "win_rate":
        base = float(win) if win is not None else -999.0
    else:
        base = float(mean_r)

    if n <= 0:
        adj = -999.0
    else:
        adj = base * min(1.0, math.sqrt(n / max(1, min_count)))

    return {
        "objective": objective,
        "objective_adj": float(adj),
        "n": int(n),
        "mean_r": float(mean_r),
        "median_r": float(med_r) if med_r is not None else None,
        "win_rate": float(win) if win is not None else None,
        "weights": {"market": float(w_market), "execution": float(w_execution), "signal": float(w_signal)},
        "threshold": float(threshold),
    }


def generate_weight_grid(step: float = 0.05) -> List[Tuple[float, float, float]]:
    vals = []
    i = 0
    while i <= int(round(1.0 / step)):
        w_market = round(i * step, 10)
        j = 0
        while j <= int(round((1.0 - w_market) / step)):
            w_exec = round(j * step, 10)
            w_sig = round(1.0 - w_market - w_exec, 10)
            if w_sig < -1e-9:
                j += 1
                continue
            if abs(w_market + w_exec + w_sig - 1.0) < 1e-6:
                vals.append((float(w_market), float(w_exec), float(w_sig)))
            j += 1
        i += 1
    return vals


def generate_thresholds(start: float = 0.5, end: float = 0.9, step: float = 0.02) -> List[float]:
    out = []
    x = start
    while x <= end + 1e-9:
        out.append(float(round(x, 4)))
        x += step
    return out


def grid_search(
    rows: List[TradeCalibrationRow],
    *,
    weight_step: float = 0.05,
    thresholds: Optional[List[float]] = None,
    min_count: int = 30,
    objective: str = "mean_r",
    top_k: int = 10,
) -> Dict[str, Any]:
    wgrid = generate_weight_grid(weight_step)
    tgrid = thresholds or generate_thresholds()

    scored: List[Dict[str, Any]] = []
    for (w_m, w_e, w_s) in wgrid:
        for thr in tgrid:
            res = evaluate_config(
                rows,
                w_market=w_m,
                w_execution=w_e,
                w_signal=w_s,
                threshold=thr,
                min_count=min_count,
                objective=objective,
            )
            if res["n"] >= min_count:
                scored.append(res)

    scored.sort(key=lambda r: (r["objective_adj"], r["mean_r"], r["n"]), reverse=True)
    best = scored[0] if scored else None
    return {"best": best, "top": scored[: max(1, top_k)], "searched": len(wgrid) * len(tgrid), "kept": len(scored)}
