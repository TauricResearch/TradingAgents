import argparse
import json
import math
from pathlib import Path
from statistics import mean, median


def _to_float(x):
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _bucket(score: float) -> str:
    edges = [0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
    labels = ["0.0-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]
    for i in range(len(labels)):
        if edges[i] <= score < edges[i + 1]:
            return labels[i]
    return "unknown"


def _safe_mean(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return mean(xs) if xs else None


def _safe_median(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    return median(xs) if xs else None


def _win_rate(r_mults):
    xs = [x for x in r_mults if x is not None and not math.isnan(x)]
    if not xs:
        return None
    return sum(1 for x in xs if x > 0) / len(xs)


def _get_nested(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
    return cur if cur is not None else default


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", required=True, help="Path to calibration_dataset.jsonl")
    parser.add_argument("--out", default="", help="Write report to file (markdown). Default prints to stdout.")
    parser.add_argument("--min-count", type=int, default=20)
    args = parser.parse_args()

    in_path = Path(args.inp).expanduser()
    rows = []
    for line in in_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue

    resolved = [r for r in rows if not r.get("pending")]
    if not resolved:
        text = "# Calibration Report\n\nNo resolved entries found.\n"
        if args.out:
            Path(args.out).expanduser().write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0

    def extract_trade(r):
        meta = r.get("meta") or {}
        outcome = r.get("outcome") or {}
        score = _to_float(_get_nested(meta, "trade_filter_details", "score", default=_get_nested(meta, "trade_filter", "score")))
        if score is None:
            score = _to_float(_get_nested(meta, "trade_filter", "score", default=0.0)) or 0.0
        regime = _get_nested(meta, "trade_levels", "regime", default="unknown")
        filtered_out = bool(_get_nested(outcome, "trade_filtered_out", default=_get_nested(meta, "trade_filter", "filtered_out", default=False)))
        r_mult = _to_float(_get_nested(outcome, "approx_r_multiple"))
        raw = _to_float(_get_nested(outcome, "raw_return", default=_get_nested(r, "raw")))
        alpha = _to_float(_get_nested(outcome, "alpha_return", default=_get_nested(r, "alpha")))
        market_q = _to_float(_get_nested(meta, "trade_filter_details", "market_quality"))
        exec_q = _to_float(_get_nested(meta, "trade_filter_details", "execution_quality"))
        signal_q = _to_float(_get_nested(meta, "trade_filter_details", "signal_quality"))
        hard_reject = bool(_get_nested(meta, "trade_filter_details", "hard_reject", default=False))
        return {
            "ticker": r.get("ticker"),
            "date": r.get("date"),
            "score": float(score),
            "bucket": _bucket(float(score)),
            "regime": str(regime),
            "filtered_out": filtered_out,
            "hard_reject": hard_reject,
            "r_mult": r_mult,
            "raw": raw,
            "alpha": alpha,
            "market_q": market_q,
            "exec_q": exec_q,
            "signal_q": signal_q,
        }

    trades = [extract_trade(r) for r in resolved]
    trades_with_r = [t for t in trades if t["r_mult"] is not None]

    lines = []
    lines.append("# Calibration Report")
    lines.append("")
    lines.append(f"- Resolved entries: {len(resolved)}")
    lines.append(f"- With approx_r_multiple: {len(trades_with_r)}")

    def summarize(group):
        r_mults = [t["r_mult"] for t in group]
        return {
            "count": len(group),
            "mean_r": _safe_mean(r_mults),
            "median_r": _safe_median(r_mults),
            "win_rate": _win_rate(r_mults),
        }

    lines.append("")
    lines.append("## By Filter Bucket (approx_r_multiple)")
    for b in ["0.0-0.5", "0.5-0.6", "0.6-0.7", "0.7-0.8", "0.8-0.9", "0.9-1.0"]:
        g = [t for t in trades_with_r if t["bucket"] == b and not t["hard_reject"]]
        s = summarize(g)
        if s["count"] == 0:
            continue
        mean_r = "n/a" if s["mean_r"] is None else f"{s['mean_r']:+.2f}"
        med_r = "n/a" if s["median_r"] is None else f"{s['median_r']:+.2f}"
        wr = "n/a" if s["win_rate"] is None else f"{s['win_rate']*100:.1f}%"
        lines.append(f"- {b}: n={s['count']}, win={wr}, meanR={mean_r}, medianR={med_r}")

    lines.append("")
    lines.append("## By Regime (approx_r_multiple)")
    for regime in sorted({t["regime"] for t in trades_with_r}):
        g = [t for t in trades_with_r if t["regime"] == regime and not t["hard_reject"]]
        s = summarize(g)
        if s["count"] == 0:
            continue
        mean_r = "n/a" if s["mean_r"] is None else f"{s['mean_r']:+.2f}"
        wr = "n/a" if s["win_rate"] is None else f"{s['win_rate']*100:.1f}%"
        lines.append(f"- {regime}: n={s['count']}, win={wr}, meanR={mean_r}")

    lines.append("")
    lines.append("## Threshold Sweep (suggested)")
    thresholds = [round(x, 2) for x in [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]]
    best = None
    for thr in thresholds:
        g = [t for t in trades_with_r if (t["score"] >= thr) and not t["hard_reject"]]
        if len(g) < args.min_count:
            continue
        s = summarize(g)
        mean_r = s["mean_r"] if s["mean_r"] is not None else -999.0
        if best is None or mean_r > best["mean_r"]:
            best = {"thr": thr, "mean_r": mean_r, "count": s["count"], "win_rate": s["win_rate"]}
        wr = "n/a" if s["win_rate"] is None else f"{s['win_rate']*100:.1f}%"
        lines.append(f"- thr>={thr:.2f}: n={s['count']}, win={wr}, meanR={mean_r:+.2f}")
    if best:
        wr = "n/a" if best["win_rate"] is None else f"{best['win_rate']*100:.1f}%"
        lines.append("")
        lines.append(f"**Suggested threshold**: {best['thr']:.2f} (n={best['count']}, win={wr}, meanR={best['mean_r']:+.2f})")
    else:
        lines.append("")
        lines.append(f"No threshold met min-count={args.min_count} with approx_r_multiple available.")

    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
