"""Headless single-ticker runner.

Bypasses the interactive Typer/questionary CLI so a parallel dispatcher
(scripts/run_top_tickers.sh) can spawn one container per ticker. All
LLM/provider/depth knobs are inherited from .env via DEFAULT_CONFIG;
this script only varies ticker and date.

Output folder layout matches the interactive CLI's "Save report?" path
so the docs/ Jekyll site renders new runs without changes.
"""

from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

from cli.main import save_report_to_disk
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


def main() -> int:
    ap = argparse.ArgumentParser(description="Headless TradingAgents run for one ticker.")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    args = ap.parse_args()

    cfg = DEFAULT_CONFIG.copy()
    # Max-power: deepest research depth + Anthropic high effort. .env may
    # already pin these via TRADINGAGENTS_MAX_DEBATE_ROUNDS / _MAX_RISK_ROUNDS;
    # only fill in when the env didn't.
    if not cfg.get("max_debate_rounds"):
        cfg["max_debate_rounds"] = 5
    if not cfg.get("max_risk_discuss_rounds"):
        cfg["max_risk_discuss_rounds"] = 5
    if not cfg.get("anthropic_effort"):
        cfg["anthropic_effort"] = "high"

    selected = ["market", "social", "news", "fundamentals"]
    ta = TradingAgentsGraph(selected, debug=False, config=cfg)
    final_state, _ = ta.propagate(args.ticker, args.date)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = cfg["deep_think_llm"].replace("/", "-").replace(":", "-")
    date_slug = args.date.replace("-", "")
    # Layout: <reports_dir>/<TICKER>/<DATE>_<MODEL>_<TS>/. The per-ticker
    # parent folder is what the Just-the-Docs site uses as a nav group.
    out = Path(cfg["reports_dir"]) / args.ticker / f"{date_slug}_{model_slug}_{ts}"
    save_report_to_disk(final_state, args.ticker, out)
    print(f"OK {args.ticker} -> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
