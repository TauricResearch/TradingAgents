from __future__ import annotations

import argparse
import json
import signal
import time
from collections import defaultdict

from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph

_PHASE_MAP = {
    "Market Analyst": "analyst",
    "Bull Researcher": "research",
    "Bear Researcher": "research",
    "Research Manager": "research",
    "Trader": "trading",
    "Aggressive Analyst": "risk",
    "Conservative Analyst": "risk",
    "Neutral Analyst": "risk",
    "Portfolio Manager": "portfolio",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile TradingAgents graph stage timings.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--date", required=True)
    parser.add_argument("--provider", default="anthropic")
    parser.add_argument("--model", default="MiniMax-M2.7-highspeed")
    parser.add_argument("--base-url", default="https://api.minimaxi.com/anthropic")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--analysis-prompt-style", default="compact")
    parser.add_argument("--selected-analysts", default="market")
    parser.add_argument("--overall-timeout", type=int, default=120)
    return parser


class _ProfileTimeout(Exception):
    pass


def main() -> None:
    args = build_parser().parse_args()
    selected_analysts = [item.strip() for item in args.selected_analysts.split(",") if item.strip()]
    config = {
        "llm_provider": args.provider,
        "deep_think_llm": args.model,
        "quick_think_llm": args.model,
        "backend_url": args.base_url,
        "selected_analysts": selected_analysts,
        "analysis_prompt_style": args.analysis_prompt_style,
        "llm_timeout": args.timeout,
        "llm_max_retries": args.max_retries,
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
    }

    graph = TradingAgentsGraph(selected_analysts=selected_analysts, config=config)
    state = Propagator().create_initial_state(args.ticker, args.date)
    config_kwargs = {"recursion_limit": 100, "max_concurrency": 1}

    node_timings = []
    phase_totals = defaultdict(float)
    started_at = time.monotonic()
    last_at = started_at

    def alarm_handler(signum, frame):
        raise _ProfileTimeout(f"profiling timeout after {args.overall_timeout}s")

    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(args.overall_timeout)

    try:
        for event in graph.graph.stream(state, stream_mode="updates", config=config_kwargs):
            now = time.monotonic()
            nodes = list(event.keys())
            phases = sorted({_PHASE_MAP.get(node, "unknown") for node in nodes})
            delta = round(now - last_at, 3)
            entry = {
                "nodes": nodes,
                "phases": phases,
                "delta_seconds": delta,
                "elapsed_seconds": round(now - started_at, 3),
            }
            node_timings.append(entry)
            for phase in phases:
                phase_totals[phase] += delta
            last_at = now

        payload = {
            "status": "ok",
            "ticker": args.ticker,
            "date": args.date,
            "selected_analysts": selected_analysts,
            "analysis_prompt_style": args.analysis_prompt_style,
            "node_timings": node_timings,
            "phase_totals_seconds": {key: round(value, 3) for key, value in phase_totals.items()},
        }
    except Exception as exc:
        payload = {
            "status": "error",
            "ticker": args.ticker,
            "date": args.date,
            "selected_analysts": selected_analysts,
            "analysis_prompt_style": args.analysis_prompt_style,
            "error": str(exc),
            "node_timings": node_timings,
            "phase_totals_seconds": {key: round(value, 3) for key, value in phase_totals.items()},
        }
    finally:
        signal.alarm(0)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
