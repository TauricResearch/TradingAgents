import argparse
import json
from pathlib import Path

from tradingagents.agents.utils.trade_filter_calibration import grid_search, load_calibration_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", required=True)
    parser.add_argument("--out", default="", help="Write best config JSON to this path.")
    parser.add_argument("--report", default="", help="Write markdown report to this path.")
    parser.add_argument("--min-count", type=int, default=30)
    parser.add_argument("--objective", default="mean_r", choices=["mean_r", "median_r", "win_rate"])
    parser.add_argument("--weight-step", type=float, default=0.05)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()

    rows = load_calibration_rows(args.inp, include_hard_reject=False)
    result = grid_search(
        rows,
        weight_step=float(args.weight_step),
        min_count=int(args.min_count),
        objective=str(args.objective),
        top_k=int(args.top_k),
    )

    best = result.get("best")
    if not best:
        text = (
            "# Fit Trade Filter\n\n"
            f"- Rows with approx_r_multiple: {len(rows)}\n"
            f"- No candidate met min_count={args.min_count}\n"
        )
        if args.report:
            Path(args.report).expanduser().write_text(text, encoding="utf-8")
        else:
            print(text)
        return 0

    best_cfg = {
        "trade_filter_enabled": True,
        "trade_filter_threshold": best["threshold"],
        "trade_filter_weights": best["weights"],
        "trade_filter_objective": best["objective"],
    }

    if args.out:
        Path(args.out).expanduser().write_text(json.dumps(best_cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(best_cfg, ensure_ascii=False, indent=2))

    if args.report:
        lines = []
        lines.append("# Fit Trade Filter")
        lines.append("")
        lines.append(f"- Rows with approx_r_multiple: {len(rows)}")
        lines.append(f"- Search space: searched={result['searched']}, kept={result['kept']}")
        lines.append("")
        lines.append("## Best")
        lines.append(f"- objective_adj: {best['objective_adj']:+.4f}")
        lines.append(f"- n: {best['n']}")
        lines.append(f"- meanR: {best['mean_r']:+.3f}")
        if best.get("median_r") is not None:
            lines.append(f"- medianR: {best['median_r']:+.3f}")
        if best.get("win_rate") is not None:
            lines.append(f"- win_rate: {best['win_rate']*100:.1f}%")
        lines.append(f"- threshold: {best['threshold']:.2f}")
        w = best["weights"]
        lines.append(f"- weights: market={w['market']:.2f}, execution={w['execution']:.2f}, signal={w['signal']:.2f}")
        lines.append("")
        lines.append("## Top Candidates")
        for i, cand in enumerate(result.get("top") or [], start=1):
            w = cand["weights"]
            wr = cand.get("win_rate")
            wr_txt = "n/a" if wr is None else f"{wr*100:.1f}%"
            lines.append(
                f"- {i}. adj={cand['objective_adj']:+.4f}, n={cand['n']}, meanR={cand['mean_r']:+.3f}, win={wr_txt}, "
                f"thr={cand['threshold']:.2f}, w=({w['market']:.2f},{w['execution']:.2f},{w['signal']:.2f})"
            )
        Path(args.report).expanduser().write_text("\n".join(lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
