from __future__ import annotations

import argparse
import json
import signal
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

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

_LLM_KIND_MAP = {
    "Market Analyst": "quick",
    "Bull Researcher": "quick",
    "Bear Researcher": "quick",
    "Research Manager": "deep",
    "Trader": "quick",
    "Aggressive Analyst": "quick",
    "Conservative Analyst": "quick",
    "Neutral Analyst": "quick",
    "Portfolio Manager": "deep",
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
    parser.add_argument("--dump-dir", default="orchestrator/profile_runs")
    parser.add_argument("--dump-raw-on-failure", action="store_true")
    return parser


class _ProfileTimeout(Exception):
    pass


def _jsonable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return repr(value)


def _extract_research_state(event: dict) -> tuple[str | None, str | None, int | None, int | None]:
    node_payload = next(iter(event.values()), {})
    if not isinstance(node_payload, dict):
        return None, None, None, None
    debate_state = node_payload.get("investment_debate_state") or {}
    if not isinstance(debate_state, dict):
        return None, None, None, None
    history = debate_state.get("history") or ""
    current = debate_state.get("current_response") or ""
    return (
        debate_state.get("research_status"),
        debate_state.get("degraded_reason"),
        len(history),
        len(current),
    )


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
    raw_events = []
    started_at = time.monotonic()
    last_at = started_at
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dump_dir = Path(args.dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_path = dump_dir / f"{args.ticker.replace('/', '_')}_{args.date}_{run_id}.json"

    def alarm_handler(signum, frame):
        raise _ProfileTimeout(f"profiling timeout after {args.overall_timeout}s")

    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(args.overall_timeout)

    try:
        for event in graph.graph.stream(state, stream_mode="updates", config=config_kwargs):
            now = time.monotonic()
            nodes = list(event.keys())
            phases = sorted({_PHASE_MAP.get(node, "unknown") for node in nodes})
            llm_kinds = sorted({_LLM_KIND_MAP.get(node, "unknown") for node in nodes})
            delta = round(now - last_at, 3)
            research_status, degraded_reason, history_len, response_len = _extract_research_state(event)
            entry = {
                "run_id": run_id,
                "nodes": nodes,
                "phases": phases,
                "llm_kinds": llm_kinds,
                "start_at": round(last_at - started_at, 3),
                "end_at": round(now - started_at, 3),
                "elapsed_ms": int(delta * 1000),
                "selected_analysts": selected_analysts,
                "analysis_prompt_style": args.analysis_prompt_style,
                "research_status": research_status,
                "degraded_reason": degraded_reason,
                "history_len": history_len,
                "response_len": response_len,
            }
            node_timings.append(entry)
            raw_events.append(_jsonable(event))
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
            "dump_path": str(dump_path),
            "raw_events": raw_events if args.dump_raw_on_failure else [],
        }
    except Exception as exc:
        payload = {
            "run_id": run_id,
            "status": "error",
            "ticker": args.ticker,
            "date": args.date,
            "selected_analysts": selected_analysts,
            "analysis_prompt_style": args.analysis_prompt_style,
            "error": str(exc),
            "exception_type": type(exc).__name__,
            "node_timings": node_timings,
            "phase_totals_seconds": {key: round(value, 3) for key, value in phase_totals.items()},
            "dump_path": str(dump_path),
            "raw_events": raw_events,
        }
    finally:
        signal.alarm(0)

    dump_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
