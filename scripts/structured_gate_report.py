"""Which gate stopped each structured decision? (TradingAgents#19 step 4)

The structured mode has produced a directional call on 1 of 28 post-#21-fix
retro decisions. "Too conservative" and "correctly abstaining" look identical
from the rating alone, and they point at opposite fixes -- so the useful
question is not how many Holds there were but WHICH gate produced each one:

  catalyst_absent   dated_catalyst_present=False -- the extractor found no
                    catalyst at all. A cohort problem (or a prompt problem),
                    not a threshold problem. Re-tuning thresholds cannot move
                    these.
  catalyst_too_far  a real catalyst, outside the 24h close-to-open window.
                    Moving _MAX_CATALYST_HOURS is the only lever.
  score_below_band  both hard gates passed and the score still landed inside
                    the Hold band. THESE are the calibration cases -- and the
                    `gap` column says how far each one missed by.
  directional       fired.

Run over the .jsonl a retro batch writes:

    python scripts/structured_gate_report.py retro_catalyst_cohort_v2_structured_results.jsonl

Rows written before scripts/decide.py started persisting the scorer's output
have no `structured_score` and are reported as `unrecoverable` -- they are not
silently counted as anything, since assuming a gate for them is exactly the
guess this report exists to replace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tradingagents.agents.managers.decision_model import (  # noqa: E402
    _OVERWEIGHT_THRESHOLD,
    _RISK_FLAG_DAMPING_PER_FLAG,
    _UNDERWEIGHT_THRESHOLD,
)

DIRECTIONAL = {"Buy", "Overweight", "Sell", "Underweight"}


def classify(row: dict) -> dict:
    """One row -> its gate, plus the numbers needed to argue about it."""
    rating = row.get("structured_rating") or row.get("rating")
    factors = row.get("structured_factors")
    score = row.get("structured_score")

    out = {
        "ticker": row.get("ticker"),
        "trade_date": row.get("trade_date"),
        "rating": rating,
        "score": score,
        "flags": None,
        "hours": None,
        "gate": None,
        "gap": None,
    }

    if factors is None or score is None:
        out["gate"] = "unrecoverable"
        return out

    flags = factors.get("risk_flags") or []
    out["flags"] = len(flags)
    out["hours"] = factors.get("catalyst_hours_to_resolution")

    if rating in DIRECTIONAL:
        out["gate"] = "directional"
    elif not factors.get("dated_catalyst_present"):
        out["gate"] = "catalyst_absent"
    elif score == 0.0 and out["hours"] is not None:
        # compute_rating() zeroes the score on the window gate; a genuine 0.00
        # score that passed both gates is possible but reads the same, so this
        # stays a best-effort split and the reason string is authoritative.
        out["gate"] = "catalyst_too_far" if "beyond the" in (row.get("structured_reason") or "") \
            else "score_below_band"
    else:
        out["gate"] = "score_below_band"

    if out["gate"] == "score_below_band":
        # Distance to whichever directional band this score was heading for.
        out["gap"] = round(_OVERWEIGHT_THRESHOLD - score, 4) if score >= 0 \
            else round(score - _UNDERWEIGHT_THRESHOLD, 4)

    return out


def undamped(score: float, n_flags: int) -> float | None:
    """What the score would have been without risk-flag damping.

    The damping is multiplicative at 15%/flag, so four flags cut a score by
    60% -- on the observed rows it is a bigger lever than either threshold.
    Returns None where damping zeroed the score outright (>= 7 flags), which
    is not invertible."""
    damping = 1.0 - _RISK_FLAG_DAMPING_PER_FLAG * n_flags
    return round(score / damping, 4) if damping > 0 else None


def build_report(rows: list[dict]) -> dict:
    classified = [classify(r) for r in rows if not r.get("error")]
    counts: dict[str, int] = {}
    for c in classified:
        counts[c["gate"]] = counts.get(c["gate"], 0) + 1

    near_misses = sorted(
        (c for c in classified if c["gate"] == "score_below_band" and c["gap"] is not None),
        key=lambda c: c["gap"],
    )
    return {"rows": classified, "counts": counts, "near_misses": near_misses}


def print_report(report: dict) -> None:
    rows = report["rows"]
    print(f"{len(rows)} decisions\n")
    print(f"{'ticker':<16}{'date':<13}{'rating':<13}{'gate':<19}"
          f"{'score':>8}{'flags':>7}{'gap':>8}")
    print("-" * 84)
    for c in rows:
        # Formatted into locals first rather than inline: nesting the same
        # quote inside an f-string is PEP 701, and this package supports 3.10.
        score = format(c["score"], "+.3f") if c["score"] is not None else "-"
        flags = str(c["flags"]) if c["flags"] is not None else "-"
        gap = format(c["gap"], ".3f") if c["gap"] is not None else "-"
        print(f"{str(c['ticker']):<16}{str(c['trade_date']):<13}{str(c['rating']):<13}"
              f"{str(c['gate']):<19}{score:>8}{flags:>7}{gap:>8}")

    print("\nBy gate:")
    for gate, n in sorted(report["counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {gate:<20} {n}")

    if report["counts"].get("unrecoverable"):
        print(f"\n  NOTE: {report['counts']['unrecoverable']} row(s) predate score persistence "
              f"and cannot be attributed to a gate. Re-running them is the only way to recover "
              f"those, which is why decide.py now persists the scorer's output.")

    attributable = len(rows) - report["counts"].get("unrecoverable", 0)
    if not report["near_misses"]:
        if attributable == 0:
            print("\nNothing here is attributable, so nothing is known about which gate is "
                  "binding -- this batch predates score persistence entirely.")
        else:
            print(f"\nNone of the {attributable} attributable decision(s) passed both hard gates "
                  "and then failed on the score. Threshold calibration has nothing to act on "
                  "here -- the binding constraint is upstream (catalyst detection or the 24h "
                  "window).")
        return

    print(f"\nNear misses (passed both hard gates, Hold on score) -- "
          f"Overweight threshold is {_OVERWEIGHT_THRESHOLD:+.2f}:")
    for c in report["near_misses"]:
        line = (f"  {c['ticker']} @ {c['trade_date']}: scored {c['score']:+.3f}, "
                f"missed by {c['gap']:.3f}")
        if c["flags"]:
            raw = undamped(c["score"], c["flags"])
            line += (f" -- {c['flags']} risk flag(s) damped it"
                     + (f" from {raw:+.3f}" if raw is not None else ""))
            if raw is not None and abs(raw) >= _OVERWEIGHT_THRESHOLD:
                line += " (would have fired undamped)"
        print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="structured retro .jsonl file(s)")
    args = parser.parse_args()

    rows: list[dict] = []
    for path in args.files:
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]

    print_report(build_report(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
