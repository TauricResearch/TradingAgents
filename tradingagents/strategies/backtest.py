"""Backtest: compare decision quality with vs without strategy signals.

Loads historical TA decisions from two analysis runs:
  - "baseline" (pre-strategy-signals, e.g. eval_results/ 2026-03-25)
  - "enhanced" (with strategy signals, e.g. tradingagents/results/ 2026-04-14)

For each, retroactively computes strategy signals and measures:
  1. Signal–decision alignment: did the TA decision agree with strategy signals?
  2. Decision accuracy: did the TA decision predict the correct price direction?
  3. Signal accuracy: did the strategy signals predict the correct price direction?

Outputs a JSON report + markdown summary.

Usage:
    python -m tradingagents.strategies.backtest --baseline-date 2026-03-25 --enhanced-date 2026-04-14
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yfinance as yf

from tradingagents.strategies import compute_signals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BULLISH_RATINGS = {"Buy", "Overweight"}
BEARISH_RATINGS = {"Sell", "Underweight"}
NEUTRAL_RATINGS = {"Hold"}

RATING_DIRECTION = {
    "Buy": "BULLISH", "Overweight": "BULLISH",
    "Sell": "BEARISH", "Underweight": "BEARISH",
    "Hold": "NEUTRAL",
}


def _extract_rating(text: str) -> str:
    m = re.search(r"Rating:\s*\*{0,2}(Buy|Sell|Hold|Overweight|Underweight)\*{0,2}", text, re.IGNORECASE)
    return m.group(1).capitalize() if m else "Hold"


def _get_price_change(ticker: str, from_date: str, to_date: str) -> float | None:
    """Percentage price change between two dates."""
    try:
        hist = yf.Ticker(ticker).history(start=from_date, end=to_date)
        if hist.empty or len(hist) < 2:
            return None
        return ((hist["Close"].iloc[-1] / hist["Close"].iloc[0]) - 1) * 100
    except Exception:
        return None


def _load_eval_results(date: str) -> dict[str, str]:
    """Load decisions from eval_results/{TICKER}/TradingAgentsStrategy_logs/."""
    results = {}
    base = Path("eval_results")
    if not base.exists():
        return results
    for ticker_dir in base.iterdir():
        if not ticker_dir.is_dir():
            continue
        f = ticker_dir / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            state = data.get(date, data)  # nested or flat
            ftd = state.get("final_trade_decision", "")
            if ftd:
                results[ticker_dir.name] = ftd
        except Exception:
            pass
    return results


def _load_results(date: str) -> dict[str, str]:
    """Load decisions from tradingagents/results/{TICKER}/TradingAgentsStrategy_logs/."""
    results = {}
    base = Path("tradingagents/results")
    if not base.exists():
        return results
    for ticker_dir in base.iterdir():
        if not ticker_dir.is_dir():
            continue
        f = ticker_dir / "TradingAgentsStrategy_logs" / f"full_states_log_{date}.json"
        if not f.exists():
            continue
        try:
            data = json.loads(f.read_text())
            state = data.get(date, data)
            ftd = state.get("final_trade_decision", "")
            if ftd:
                results[ticker_dir.name] = ftd
        except Exception:
            pass
    return results


def _signal_consensus(signals: list[dict]) -> str:
    """Determine overall signal consensus: BULLISH, BEARISH, or NEUTRAL."""
    supports = sum(1 for s in signals if s.get("direction") == "SUPPORTS")
    contradicts = sum(1 for s in signals if s.get("direction") == "CONTRADICTS")
    if supports > contradicts:
        return "BULLISH"
    elif contradicts > supports:
        return "BEARISH"
    return "NEUTRAL"


# ---------------------------------------------------------------------------
# Core backtest
# ---------------------------------------------------------------------------

def backtest_run(
    decisions: dict[str, str],
    analysis_date: str,
    eval_date: str,
    label: str,
) -> list[dict]:
    """Score a set of decisions against actual price movement.

    For each ticker:
    - Extract rating from decision text
    - Compute strategy signals retroactively for analysis_date
    - Get actual price change from analysis_date to eval_date
    - Score decision accuracy and signal accuracy

    Returns list of per-ticker result dicts.
    """
    results = []
    for ticker in sorted(decisions):
        ftd = decisions[ticker]
        rating = _extract_rating(ftd)
        rating_dir = RATING_DIRECTION.get(rating, "NEUTRAL")

        # Actual price movement
        pct = _get_price_change(ticker, analysis_date, eval_date)
        if pct is None:
            continue
        actual_dir = "BULLISH" if pct > 1 else "BEARISH" if pct < -1 else "NEUTRAL"

        # Retroactive strategy signals
        try:
            signals = compute_signals(ticker, analysis_date)
        except Exception:
            signals = []

        sig_consensus = _signal_consensus(signals) if signals else "N/A"

        # Decision accuracy: did rating predict direction?
        if rating_dir == "NEUTRAL":
            decision_correct = None  # not a directional call
        else:
            decision_correct = (rating_dir == actual_dir)

        # Signal accuracy: did consensus predict direction?
        if sig_consensus in ("N/A", "NEUTRAL"):
            signal_correct = None
        else:
            signal_correct = (sig_consensus == actual_dir)

        # Alignment: did decision agree with signals?
        if sig_consensus in ("N/A", "NEUTRAL") or rating_dir == "NEUTRAL":
            aligned = None
        else:
            aligned = (rating_dir == sig_consensus)

        n_supports = sum(1 for s in signals if s.get("direction") == "SUPPORTS")
        n_contradicts = sum(1 for s in signals if s.get("direction") == "CONTRADICTS")

        results.append({
            "ticker": ticker,
            "label": label,
            "analysis_date": analysis_date,
            "eval_date": eval_date,
            "rating": rating,
            "rating_direction": rating_dir,
            "pct_change": round(pct, 2),
            "actual_direction": actual_dir,
            "decision_correct": decision_correct,
            "signal_consensus": sig_consensus,
            "signal_correct": signal_correct,
            "aligned": aligned,
            "n_signals": len(signals),
            "n_supports": n_supports,
            "n_contradicts": n_contradicts,
        })

    return results


def _accuracy(results: list[dict], key: str) -> tuple[int, int, float]:
    """Count correct/total/pct for a boolean key (skipping None)."""
    scored = [r for r in results if r.get(key) is not None]
    if not scored:
        return 0, 0, 0.0
    correct = sum(1 for r in scored if r[key])
    return correct, len(scored), correct / len(scored) if scored else 0.0


def generate_report(baseline: list[dict], enhanced: list[dict], output_dir: Path) -> Path:
    """Generate markdown + JSON backtest comparison report."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    all_results = {"baseline": baseline, "enhanced": enhanced}
    json_path = output_dir / "backtest_results.json"
    json_path.write_text(json.dumps(all_results, indent=2))

    # Markdown
    b_dec_c, b_dec_t, b_dec_pct = _accuracy(baseline, "decision_correct")
    e_dec_c, e_dec_t, e_dec_pct = _accuracy(enhanced, "decision_correct")
    b_sig_c, b_sig_t, b_sig_pct = _accuracy(baseline, "signal_correct")
    e_sig_c, e_sig_t, e_sig_pct = _accuracy(enhanced, "signal_correct")
    e_align_c, e_align_t, e_align_pct = _accuracy(enhanced, "aligned")

    b_date = baseline[0]["analysis_date"] if baseline else "?"
    e_date = enhanced[0]["analysis_date"] if enhanced else "?"
    eval_date = enhanced[0]["eval_date"] if enhanced else baseline[0]["eval_date"] if baseline else "?"

    lines = [
        "# Strategy Signals Backtest Report\n",
        f"Comparing decision quality **with** vs **without** strategy signals.\n",
        "## Summary\n",
        f"| Metric | Baseline ({b_date}) | Enhanced ({e_date}) | Delta |",
        "|--------|---:|---:|---:|",
        f"| Tickers analyzed | {len(baseline)} | {len(enhanced)} | |",
        f"| Decision accuracy | {b_dec_c}/{b_dec_t} ({b_dec_pct:.0%}) | {e_dec_c}/{e_dec_t} ({e_dec_pct:.0%}) | {e_dec_pct - b_dec_pct:+.0%} |",
        f"| Signal accuracy (retroactive) | {b_sig_c}/{b_sig_t} ({b_sig_pct:.0%}) | {e_sig_c}/{e_sig_t} ({e_sig_pct:.0%}) | {e_sig_pct - b_sig_pct:+.0%} |",
        f"| Decision–signal alignment | — | {e_align_c}/{e_align_t} ({e_align_pct:.0%}) | |",
        f"| Evaluation date | {eval_date} | {eval_date} | |",
        "",
        "*Decision accuracy: did the rating (Buy/Sell) predict the correct price direction?*",
        "*Signal accuracy: did the strategy signal consensus predict the correct direction?*",
        "*Alignment: did the enhanced decision agree with strategy signals?*\n",
    ]

    # Overlap analysis — tickers in both sets
    b_tickers = {r["ticker"]: r for r in baseline}
    e_tickers = {r["ticker"]: r for r in enhanced}
    overlap = sorted(set(b_tickers) & set(e_tickers))

    if overlap:
        lines.append("## Head-to-Head (overlapping tickers)\n")
        lines.append("| Ticker | Baseline Rating | Enhanced Rating | Actual Move | Baseline Correct | Enhanced Correct | Signals Agreed |")
        lines.append("|--------|----------------|----------------|------------|:---:|:---:|:---:|")
        for t in overlap:
            b = b_tickers[t]
            e = e_tickers[t]
            b_icon = "✅" if b["decision_correct"] else "❌" if b["decision_correct"] is False else "—"
            e_icon = "✅" if e["decision_correct"] else "❌" if e["decision_correct"] is False else "—"
            a_icon = "✅" if e["aligned"] else "❌" if e["aligned"] is False else "—"
            lines.append(
                f"| {t} | {b['rating']} | {e['rating']} | {e['pct_change']:+.1f}% | {b_icon} | {e_icon} | {a_icon} |"
            )

        # Overlap accuracy
        o_baseline = [b_tickers[t] for t in overlap]
        o_enhanced = [e_tickers[t] for t in overlap]
        ob_c, ob_t, ob_pct = _accuracy(o_baseline, "decision_correct")
        oe_c, oe_t, oe_pct = _accuracy(o_enhanced, "decision_correct")
        lines.append(f"\nOverlap accuracy: baseline {ob_c}/{ob_t} ({ob_pct:.0%}) vs enhanced {oe_c}/{oe_t} ({oe_pct:.0%})\n")

    # Per-strategy signal accuracy
    all_signals_data: list[dict] = []
    for r in baseline + enhanced:
        ticker = r["ticker"]
        date = r["analysis_date"]
        actual = r["actual_direction"]
        try:
            sigs = compute_signals(ticker, date)
        except Exception:
            continue
        for s in sigs:
            d = s.get("direction", "NEUTRAL")
            if d == "NEUTRAL":
                continue
            predicted = "BULLISH" if d == "SUPPORTS" else "BEARISH"
            all_signals_data.append({
                "strategy": s.get("name", "?"),
                "correct": predicted == actual,
            })

    if all_signals_data:
        strat_stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
        for s in all_signals_data:
            strat_stats[s["strategy"]]["total"] += 1
            if s["correct"]:
                strat_stats[s["strategy"]]["correct"] += 1

        lines.append("## Per-Strategy Accuracy (across all tickers)\n")
        lines.append("| Strategy | Correct | Total | Accuracy |")
        lines.append("|----------|--------:|------:|---------:|")
        for name in sorted(strat_stats, key=lambda n: strat_stats[n]["correct"] / max(strat_stats[n]["total"], 1), reverse=True):
            st = strat_stats[name]
            acc = st["correct"] / st["total"] if st["total"] else 0
            display = name.replace("_", " ").title()
            lines.append(f"| {display} | {st['correct']} | {st['total']} | {acc:.0%} |")
        lines.append("")

    lines.append(f"\n---\n*Generated by `python -m tradingagents.strategies.backtest`*\n")

    md_path = output_dir / "backtest_report.md"
    md_path.write_text("\n".join(lines))
    return md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Backtest strategy signals vs historical decisions")
    parser.add_argument("--baseline-date", default="2026-03-25", help="Date of baseline (no signals) analysis")
    parser.add_argument("--enhanced-date", default="2026-04-14", help="Date of enhanced (with signals) analysis")
    parser.add_argument("--eval-date", default="2026-04-16", help="Date to evaluate price movement against")
    parser.add_argument("--output", default="./data/backtest", help="Output directory for report")
    args = parser.parse_args()

    print(f"Loading baseline decisions ({args.baseline_date})...", file=sys.stderr)
    baseline_decisions = _load_eval_results(args.baseline_date)
    if not baseline_decisions:
        baseline_decisions = _load_results(args.baseline_date)
    print(f"  {len(baseline_decisions)} tickers", file=sys.stderr)

    print(f"Loading enhanced decisions ({args.enhanced_date})...", file=sys.stderr)
    enhanced_decisions = _load_results(args.enhanced_date)
    if not enhanced_decisions:
        enhanced_decisions = _load_eval_results(args.enhanced_date)
    print(f"  {len(enhanced_decisions)} tickers", file=sys.stderr)

    if not baseline_decisions and not enhanced_decisions:
        print("No decisions found. Ensure eval_results/ or tradingagents/results/ exist.", file=sys.stderr)
        sys.exit(1)

    print(f"Computing strategy signals + price changes (eval: {args.eval_date})...", file=sys.stderr)
    baseline = backtest_run(baseline_decisions, args.baseline_date, args.eval_date, "baseline")
    enhanced = backtest_run(enhanced_decisions, args.enhanced_date, args.eval_date, "enhanced")

    print(f"Baseline: {len(baseline)} scored, Enhanced: {len(enhanced)} scored", file=sys.stderr)

    report_path = generate_report(baseline, enhanced, Path(args.output))
    print(f"\nReport: {report_path}", file=sys.stderr)
    print(report_path.read_text())


if __name__ == "__main__":
    main()
