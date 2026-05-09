"""Agent-structure A/B experiment runner.

Runs each variation in ``tradingagents.graph.variations.VALID_VARIATIONS``
against a single ticker on multiple trade dates, captures the resulting
signal and rendered decision, then scores realised return + alpha vs SPY
at a fixed holding horizon. Saves one JSONL row per (variation, date)
to ``experiments/results.jsonl`` so the aggregator can produce a
comparison table without re-running.

Default config: NVDA on four Fridays in Feb–Apr 2026, shallow depth
(1 debate / 1 risk round), Claude Code subscription provider. Override
via flags.

Usage:
    python scripts/run_experiment.py
    python scripts/run_experiment.py --ticker AAPL --dates 2026-03-06,2026-04-03
    python scripts/run_experiment.py --variations baseline,no_debate
    python scripts/run_experiment.py --provider anthropic \
        --quick-model claude-haiku-4-5 --deep-model claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yfinance as yf

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.variations import VALID_VARIATIONS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("experiment")

DEFAULT_TICKER = "NVDA"
DEFAULT_DATES = ["2026-02-13", "2026-03-06", "2026-03-27", "2026-04-17"]
DEFAULT_HOLDING_DAYS = 21  # ~1 month of trading days
RESULTS_PATH = Path(__file__).resolve().parent.parent / "experiments" / "results.jsonl"

PROVIDER_DEFAULTS: Dict[str, Tuple[str, str]] = {
    # (quick_model, deep_model)
    "claude_code": ("haiku", "sonnet"),
    "anthropic": ("claude-haiku-4-5", "claude-sonnet-4-6"),
    "openai": ("gpt-5.4-mini", "gpt-5.4"),
    "google": ("gemini-2.5-flash", "gemini-2.5-pro"),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ticker", default=DEFAULT_TICKER, help=f"Ticker to test (default: {DEFAULT_TICKER})")
    p.add_argument(
        "--dates",
        default=",".join(DEFAULT_DATES),
        help="Comma-separated YYYY-MM-DD trade dates",
    )
    p.add_argument(
        "--variations",
        default=",".join(VALID_VARIATIONS),
        help=f"Comma-separated variations to run. Valid: {','.join(VALID_VARIATIONS)}",
    )
    p.add_argument(
        "--provider",
        default="claude_code",
        choices=list(PROVIDER_DEFAULTS),
        help="LLM provider (default: claude_code)",
    )
    p.add_argument("--quick-model", default=None, help="Override quick-thinking model")
    p.add_argument("--deep-model", default=None, help="Override deep-thinking model")
    p.add_argument("--analysts", default="market,news,fundamentals", help="Comma-separated analyst types")
    p.add_argument("--holding-days", type=int, default=DEFAULT_HOLDING_DAYS, help="Trading days for return scoring")
    p.add_argument("--results-path", default=str(RESULTS_PATH), help="Where to append JSONL results")
    p.add_argument("--debate-rounds", type=int, default=1, help="max_debate_rounds (shallow=1)")
    p.add_argument("--risk-rounds", type=int, default=1, help="max_risk_discuss_rounds (shallow=1)")
    p.add_argument("--dry-run", action="store_true", help="Print plan without running")
    return p.parse_args()


def fetch_realised(
    ticker: str, trade_date: str, holding_days: int
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """Return (raw_return, alpha_vs_spy, actual_holding_days). None if data unavailable."""
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days * 2 + 14)
        end_str = end.strftime("%Y-%m-%d")
        stk = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        spy = yf.Ticker("SPY").history(start=trade_date, end=end_str)
        if len(stk) < 2 or len(spy) < 2:
            return None, None, None
        actual = min(holding_days, len(stk) - 1, len(spy) - 1)
        raw = float((stk["Close"].iloc[actual] - stk["Close"].iloc[0]) / stk["Close"].iloc[0])
        spy_ret = float((spy["Close"].iloc[actual] - spy["Close"].iloc[0]) / spy["Close"].iloc[0])
        return raw, raw - spy_ret, actual
    except Exception as e:
        logger.warning("Realised return fetch failed for %s on %s: %s", ticker, trade_date, e)
        return None, None, None


def run_one(
    variation: str,
    ticker: str,
    trade_date: str,
    base_config: Dict[str, Any],
    selected_analysts: List[str],
) -> Dict[str, Any]:
    """Run one (variation, date) combo. Returns the result row to log."""
    started = time.time()
    config = copy.deepcopy(base_config)
    # Force a clean memory log per variation so prior decisions don't bleed across.
    config["memory_log_path"] = str(
        Path(config["memory_log_path"]).parent / f"experiment_{variation}_memory.md"
    )

    logger.info("=== %s | %s | %s ===", variation, ticker, trade_date)
    try:
        ta = TradingAgentsGraph(
            selected_analysts=selected_analysts,
            debug=False,
            config=config,
            variation=variation,
        )
        final_state, processed_signal = ta.propagate(ticker, trade_date)
        decision_md = final_state.get("final_trade_decision", "")
        return {
            "variation": variation,
            "ticker": ticker,
            "trade_date": trade_date,
            "signal": processed_signal,
            "decision_markdown": decision_md,
            "veto_reason": final_state.get("risk_officer_veto", ""),
            "elapsed_sec": round(time.time() - started, 1),
            "ok": True,
        }
    except Exception as e:
        logger.exception("Run failed: %s", e)
        return {
            "variation": variation,
            "ticker": ticker,
            "trade_date": trade_date,
            "signal": None,
            "decision_markdown": "",
            "veto_reason": "",
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
            "elapsed_sec": round(time.time() - started, 1),
            "ok": False,
        }


def signal_to_position(signal: Optional[str]) -> int:
    """Map the SignalProcessor output to a position sign for scoring.

    SignalProcessor returns one of Buy/Overweight/Hold/Underweight/Sell.
    We score realised alpha multiplied by this sign so a correct Sell
    on a falling stock scores positively.
    """
    if not signal:
        return 0
    s = signal.strip().lower()
    if s in ("buy", "overweight"):
        return 1
    if s in ("sell", "underweight"):
        return -1
    return 0


def main() -> int:
    args = parse_args()
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    variations = [v.strip() for v in args.variations.split(",") if v.strip()]
    analysts = [a.strip() for a in args.analysts.split(",") if a.strip()]

    for v in variations:
        if v not in VALID_VARIATIONS:
            print(f"Unknown variation '{v}'. Valid: {VALID_VARIATIONS}", file=sys.stderr)
            return 2

    quick_model, deep_model = PROVIDER_DEFAULTS[args.provider]
    if args.quick_model:
        quick_model = args.quick_model
    if args.deep_model:
        deep_model = args.deep_model

    base_config = copy.deepcopy(DEFAULT_CONFIG)
    base_config.update(
        {
            "llm_provider": args.provider,
            "quick_think_llm": quick_model,
            "deep_think_llm": deep_model,
            "max_debate_rounds": args.debate_rounds,
            "max_risk_discuss_rounds": args.risk_rounds,
        }
    )

    print(f"Plan: {len(variations)} variation(s) x {len(dates)} date(s) on {args.ticker}")
    print(f"  variations: {variations}")
    print(f"  dates:      {dates}")
    print(f"  analysts:   {analysts}")
    print(f"  provider:   {args.provider} (quick={quick_model}, deep={deep_model})")
    print(f"  rounds:     debate={args.debate_rounds}, risk={args.risk_rounds}")
    print(f"  scoring:    {args.holding_days} trading-day holding period vs SPY")
    print(f"  output:     {args.results_path}")
    if args.dry_run:
        return 0

    results_path = Path(args.results_path)
    results_path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    with results_path.open("a", encoding="utf-8") as fh:
        for variation in variations:
            for trade_date in dates:
                row = run_one(variation, args.ticker, trade_date, base_config, analysts)
                raw, alpha, days = fetch_realised(args.ticker, trade_date, args.holding_days)
                row["raw_return"] = raw
                row["alpha_vs_spy"] = alpha
                row["holding_days"] = days
                row["scored_alpha"] = (alpha * signal_to_position(row["signal"])) if alpha is not None else None
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)

    print()
    print(f"Wrote {len(rows)} rows to {results_path}")
    print("Run scripts/aggregate_experiment.py for the comparison table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
