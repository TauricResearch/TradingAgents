"""Score Polymarket paper fills against current/resolved market outcomes.

Usage:
    python scripts/score_fills.py                    # all dated fill files
    python scripts/score_fills.py --date 2026-05-08  # one specific date
    python scripts/score_fills.py --verbose          # add per-position rows

Reads `~/.tradingagents/polymarket/paper-fills-YYYY-MM-DD.jsonl`, fetches
each unique market's current state from gamma, classifies the outcome, and
prints a per-position table plus aggregate stats. Realized P&L for resolved
markets, mark-to-market P&L for still-open ones.

This is the feedback loop. Run it after the engine has accumulated a few
days of fills. When markets resolve, the script's "RESOLVED_WIN/LOSS" buckets
fill up and you can see if the bot has edge.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from tradingagents.dataflows.polymarket_data import GammaAPIError, get_market_by_id
from tradingagents.exchange.scoring import (
    MarketOutcome,
    classify_outcome,
    score_position,
)


FILL_DIR = Path.home() / ".tradingagents" / "polymarket"


def _load_fills(date: str | None) -> list[dict]:
    """Load fills from one date or all dates."""
    if date:
        paths = [FILL_DIR / f"paper-fills-{date}.jsonl"]
    else:
        paths = sorted(FILL_DIR.glob("paper-fills-*.jsonl"))

    fills: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    fills.append(json.loads(line))
    return fills


def _fetch_outcomes(market_ids: set[str]) -> dict[str, dict]:
    """Fetch each market once. Returns {market_id: {outcome, current_yes_price}}."""
    out: dict[str, dict] = {}
    for mid in sorted(market_ids):
        try:
            m = get_market_by_id(mid)
        except GammaAPIError as e:
            print(f"  warn: market {mid} fetch failed: {e}", file=sys.stderr)
            out[mid] = {"outcome": MarketOutcome.UNKNOWN, "current_yes_price": None}
            continue

        # Reconstruct outcome_prices from normalised fields. The normalised
        # market dict in polymarket_data exposes yes_price; no_price = 1 - yes
        # is implied for binary markets. classify_outcome reads both.
        prices = [m["yes_price"], 1.0 - m["yes_price"]]
        outcome, current_yes = classify_outcome(closed=m["closed"], outcome_prices=prices)
        out[mid] = {"outcome": outcome, "current_yes_price": current_yes}
    return out


def _color(s: str, c: str) -> str:
    if not sys.stdout.isatty():
        return s
    codes = {"green": "32", "red": "31", "yellow": "33", "cyan": "36", "dim": "2"}
    return f"\x1b[{codes.get(c, '0')}m{s}\x1b[0m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=None,
        help="Date in YYYY-MM-DD format; defaults to all dates",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show per-position rows",
    )
    args = parser.parse_args()

    fills = _load_fills(args.date)
    if not fills:
        target = args.date or "all dates"
        print(f"No fills found for {target}.", file=sys.stderr)
        return 1

    market_ids = {f["market_id"] for f in fills}
    print(f"Loaded {len(fills)} fills across {len(market_ids)} markets")
    print(f"Fetching current outcomes from gamma-api...")
    outcomes = _fetch_outcomes(market_ids)

    rows = []
    for f in fills:
        info = outcomes.get(f["market_id"], {})
        outcome = info.get("outcome", MarketOutcome.UNKNOWN)
        current_yes = info.get("current_yes_price")
        score = score_position(f, outcome, current_yes)
        rows.append({"fill": f, "outcome": outcome, "score": score})

    by_status: dict[str, list] = {}
    for r in rows:
        by_status.setdefault(r["score"]["status"], []).append(r)

    realized_pnl = sum(
        r["score"]["pnl_usd"]
        for r in rows
        if r["score"]["status"] in ("RESOLVED_WIN", "RESOLVED_LOSS", "CANCELED")
    )
    mtm_pnl = sum(
        (r["score"]["mtm_pnl_usd"] or 0)
        for r in rows
        if r["score"]["status"] == "PENDING"
    )
    total_invested = sum(r["fill"]["filled_usd"] for r in rows)
    wins = len(by_status.get("RESOLVED_WIN", []))
    losses = len(by_status.get("RESOLVED_LOSS", []))
    resolved = wins + losses

    print()
    print("=" * 80)
    print(f"PORTFOLIO SUMMARY  ({len(rows)} positions, ${total_invested:.2f} invested)")
    print("=" * 80)
    for status in ["RESOLVED_WIN", "RESOLVED_LOSS", "CANCELED", "PENDING", "UNRESOLVED"]:
        bucket = by_status.get(status, [])
        if not bucket:
            continue
        if status == "RESOLVED_WIN":
            sub_pnl = sum(r["score"]["pnl_usd"] for r in bucket)
            print(f"  {_color(status, 'green'):<25} {len(bucket):>3}   pnl: ${sub_pnl:+.2f}")
        elif status == "RESOLVED_LOSS":
            sub_pnl = sum(r["score"]["pnl_usd"] for r in bucket)
            print(f"  {_color(status, 'red'):<25} {len(bucket):>3}   pnl: ${sub_pnl:+.2f}")
        elif status == "PENDING":
            sub_pnl = sum((r["score"]["mtm_pnl_usd"] or 0) for r in bucket)
            print(f"  {_color(status, 'cyan'):<25} {len(bucket):>3}   mtm: ${sub_pnl:+.2f}")
        elif status == "CANCELED":
            sub_pnl = sum(r["score"]["pnl_usd"] for r in bucket)
            print(f"  {_color(status, 'yellow'):<25} {len(bucket):>3}   pnl: ${sub_pnl:+.2f}")
        else:
            print(f"  {_color(status, 'dim'):<25} {len(bucket):>3}")

    print()
    if resolved > 0:
        win_rate = wins / resolved
        roi = realized_pnl / total_invested if total_invested > 0 else 0
        print(f"  Win rate (resolved):  {wins}/{resolved} = {win_rate*100:.1f}%")
        print(f"  Realized P&L:         ${realized_pnl:+.2f}")
        print(f"  Realized ROI:         {roi*100:+.1f}%")
    else:
        print("  No resolved markets yet.")

    print(f"  Open MTM P&L:         ${mtm_pnl:+.2f}")
    print(f"  Total (real + MTM):   ${realized_pnl + mtm_pnl:+.2f}")
    print("=" * 80)

    if args.verbose:
        print()
        print("PER-POSITION DETAIL")
        print("-" * 100)
        print(f"{'Status':<14} {'Dir':<8} {'$Invested':>10} {'P&L':>10}  Question")
        for r in rows:
            f, s = r["fill"], r["score"]
            pnl_field = s["pnl_usd"] if s["status"] != "PENDING" else (s["mtm_pnl_usd"] or 0)
            print(
                f"{s['status']:<14} {f['direction']:<8} "
                f"${f['filled_usd']:>9.2f} ${pnl_field:>+9.2f}  "
                f"{f['question'][:60]}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
