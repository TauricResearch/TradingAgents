#!/usr/bin/env python3
"""
Hypothesis comparison — computes 7d returns for hypothesis picks and
compares them against the baseline scanner in performance_database.json.

Usage (called by hypothesis-runner.yml after min_days elapsed):
    python scripts/compare_hypothesis.py \
        --hypothesis-id options_flow-scan-3-expirations \
        --picks-json '[{"date": "2026-04-01", "ticker": "AAPL", ...}]' \
        --scanner options_flow \
        --db-path data/recommendations/performance_database.json

Prints a JSON conclusion to stdout.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tradingagents.dataflows.y_finance import download_history

_MIN_EVALUATED = 5
_WIN_RATE_DELTA_THRESHOLD = 5.0
_AVG_RETURN_DELTA_THRESHOLD = 1.0


def compute_7d_return(ticker: str, pick_date: str) -> Tuple[Optional[float], Optional[bool]]:
    """Fetch 7-day return for a pick using yfinance. Returns (pct, is_win) or (None, None)."""
    try:
        entry_dt = datetime.strptime(pick_date, "%Y-%m-%d")
        exit_dt = entry_dt + timedelta(days=10)
        df = download_history(
            ticker,
            start=entry_dt.strftime("%Y-%m-%d"),
            end=exit_dt.strftime("%Y-%m-%d"),
        )
        if df.empty or len(df) < 2:
            return None, None
        close = df["Close"]
        entry_price = float(close.iloc[0])
        exit_idx = min(6, len(close) - 1)
        exit_price = float(close.iloc[exit_idx])
        if entry_price <= 0:
            return None, None
        ret = (exit_price - entry_price) / entry_price * 100
        return round(ret, 4), ret > 0
    except Exception:
        return None, None


def enrich_picks_with_returns(picks: list) -> list:
    """Compute 7d return for each pick >= 7 days old that lacks return_7d."""
    cutoff = (datetime.utcnow() - timedelta(days=14)).strftime("%Y-%m-%d")
    for pick in picks:
        if pick.get("return_7d") is not None:
            continue
        if pick.get("date", "9999-99-99") > cutoff:
            continue
        ret, win = compute_7d_return(pick["ticker"], pick["date"])
        pick["return_7d"] = ret
        pick["win_7d"] = win
    return picks


def compute_metrics(picks: list) -> dict:
    """Compute win rate and avg return. Only picks with non-None return_7d are evaluated."""
    evaluated = [p for p in picks if p.get("return_7d") is not None]
    if not evaluated:
        return {"count": len(picks), "evaluated": 0, "win_rate": None, "avg_return": None}
    wins = sum(1 for p in evaluated if p.get("win_7d"))
    avg_ret = sum(p["return_7d"] for p in evaluated) / len(evaluated)
    return {
        "count": len(picks),
        "evaluated": len(evaluated),
        "win_rate": round(wins / len(evaluated) * 100, 1),
        "avg_return": round(avg_ret, 2),
    }


def load_baseline_metrics(scanner: str, db_path: str) -> dict:
    """Load baseline metrics for a scanner from performance_database.json."""
    path = Path(db_path)
    if not path.exists():
        return {"count": 0, "win_rate": None, "avg_return": None}
    try:
        with open(path) as f:
            db = json.load(f)
    except Exception:
        return {"count": 0, "win_rate": None, "avg_return": None}
    picks = []
    for recs in db.get("recommendations_by_date", {}).values():
        for rec in (recs if isinstance(recs, list) else []):
            if rec.get("strategy_match") == scanner and rec.get("return_7d") is not None:
                picks.append(rec)
    return compute_metrics(picks)


def make_decision(hypothesis: dict, baseline: dict) -> Tuple[str, str]:
    """Decide accepted/rejected. Requires _MIN_EVALUATED evaluated picks."""
    evaluated = hypothesis.get("evaluated", 0)
    if evaluated < _MIN_EVALUATED:
        return (
            "rejected",
            f"Insufficient data: only {evaluated} evaluated picks (need {_MIN_EVALUATED})",
        )
    hyp_wr = hypothesis.get("win_rate")
    hyp_ret = hypothesis.get("avg_return")
    base_wr = baseline.get("win_rate")
    base_ret = baseline.get("avg_return")
    reasons = []
    if hyp_wr is not None and base_wr is not None:
        delta_wr = hyp_wr - base_wr
        if delta_wr > _WIN_RATE_DELTA_THRESHOLD:
            reasons.append(
                f"win rate improved by {delta_wr:+.1f}pp ({base_wr:.1f}% → {hyp_wr:.1f}%)"
            )
    if hyp_ret is not None and base_ret is not None:
        delta_ret = hyp_ret - base_ret
        if delta_ret > _AVG_RETURN_DELTA_THRESHOLD:
            reasons.append(
                f"avg return improved by {delta_ret:+.2f}% ({base_ret:+.2f}% → {hyp_ret:+.2f}%)"
            )
    if reasons:
        return "accepted", "; ".join(reasons)
    wr_str = (
        f"{hyp_wr:.1f}% vs baseline {base_wr:.1f}%" if hyp_wr is not None else "no win rate data"
    )
    ret_str = (
        f"{hyp_ret:+.2f}% vs baseline {base_ret:+.2f}%" if hyp_ret is not None else "no return data"
    )
    return "rejected", f"No significant improvement — win rate: {wr_str}; avg return: {ret_str}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--picks-json", required=True)
    parser.add_argument("--scanner", required=True)
    parser.add_argument("--db-path", default="data/recommendations/performance_database.json")
    args = parser.parse_args()
    picks = json.loads(args.picks_json)
    picks = enrich_picks_with_returns(picks)
    hyp_metrics = compute_metrics(picks)
    base_metrics = load_baseline_metrics(args.scanner, args.db_path)
    decision, reason = make_decision(hyp_metrics, base_metrics)
    result = {
        "hypothesis_id": args.hypothesis_id,
        "decision": decision,
        "reason": reason,
        "hypothesis": hyp_metrics,
        "baseline": base_metrics,
        "enriched_picks": picks,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
