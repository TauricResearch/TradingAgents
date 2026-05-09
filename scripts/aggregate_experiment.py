"""Aggregate the experiment runner's JSONL results into a comparison table.

Reads ``experiments/results.jsonl`` (or ``--results-path``) and prints, per
variation, mean alpha vs SPY (signed by the agent's signal direction),
hit rate (% of decisions that produced positive alpha when scored),
mean elapsed seconds, and the per-date rows. The table is plain text so
it pastes cleanly back into the conversation.

Usage:
    python scripts/aggregate_experiment.py
    python scripts/aggregate_experiment.py --results-path experiments/results.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional


def load_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        print(f"No results file at {path}", file=sys.stderr)
        return rows
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def fmt_pct(x: Optional[float]) -> str:
    return "    n/a" if x is None else f"{x * 100:+6.2f}%"


def fmt_signal(s: Optional[str]) -> str:
    return (s or "—").ljust(11)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--results-path",
        default=str(Path(__file__).resolve().parent.parent / "experiments" / "results.jsonl"),
    )
    args = p.parse_args()

    rows = load_rows(Path(args.results_path))
    if not rows:
        return 1

    by_var: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_var[r["variation"]].append(r)

    print()
    print("=" * 92)
    print(f"{'Variation':<18} {'Date':<12} {'Signal':<11} {'Raw ret':>10} {'Alpha vs SPY':>14} {'Scored':>10} {'OK':>4}")
    print("-" * 92)
    for variation, vrows in by_var.items():
        for r in sorted(vrows, key=lambda x: x["trade_date"]):
            print(
                f"{variation:<18} {r['trade_date']:<12} {fmt_signal(r.get('signal'))} "
                f"{fmt_pct(r.get('raw_return'))} {fmt_pct(r.get('alpha_vs_spy'))} "
                f"{fmt_pct(r.get('scored_alpha'))} {'Y' if r.get('ok') else 'N':>4}"
            )
    print("=" * 92)

    print()
    print("Summary by variation (across dates with realised data):")
    print("-" * 92)
    print(f"{'Variation':<18} {'Runs':>5} {'OK':>4} {'Mean alpha':>12} {'Mean scored':>13} {'Hit rate':>10} {'Mean sec':>10}")
    print("-" * 92)
    for variation, vrows in by_var.items():
        ok = [r for r in vrows if r.get("ok")]
        scored = [r["scored_alpha"] for r in ok if r.get("scored_alpha") is not None]
        alphas = [r["alpha_vs_spy"] for r in ok if r.get("alpha_vs_spy") is not None]
        elapsed = [r.get("elapsed_sec") for r in ok if r.get("elapsed_sec") is not None]
        hit_rate = (sum(1 for x in scored if x > 0) / len(scored)) if scored else None
        print(
            f"{variation:<18} {len(vrows):>5} {len(ok):>4} "
            f"{fmt_pct(mean(alphas) if alphas else None):>12} "
            f"{fmt_pct(mean(scored) if scored else None):>13} "
            f"{(f'{hit_rate * 100:>5.1f}%' if hit_rate is not None else '   n/a'):>10} "
            f"{(f'{mean(elapsed):>6.1f}' if elapsed else '  n/a'):>10}"
        )
    print("=" * 92)
    print()
    print(
        "Notes:\n"
        "- 'Mean alpha' = realised return of the ticker minus SPY over the holding period (sign-agnostic)\n"
        "- 'Mean scored' = alpha multiplied by the agent's signal direction (Buy=+1, Sell=-1, Hold=0)\n"
        "  so a correct Sell on a falling stock scores positively.\n"
        "- Hit rate counts scored_alpha > 0 across decisions where the agent took a directional view.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
