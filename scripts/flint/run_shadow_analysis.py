#!/usr/bin/env python3
"""Run TradingAgents as a Flint shadow-analysis comparator.

This wrapper keeps TradingAgents state inside this sibling repo instead of
writing to ~/.tradingagents. It does not submit trades or write into Flint.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "output"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents_service.runner import ShadowRunRequest, run_shadow_job


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a TradingAgents advisory shadow analysis for Flint."
    )
    parser.add_argument("ticker", help="Ticker to analyze, preserving exchange suffixes.")
    parser.add_argument("trade_date", help="Analysis date in YYYY-MM-DD format.")
    parser.add_argument(
        "--analysts",
        default="market,news,fundamentals",
        help="Comma-separated analysts: market,social,news,fundamentals.",
    )
    parser.add_argument("--provider", help="Override TRADINGAGENTS_LLM_PROVIDER.")
    parser.add_argument("--deep-model", help="Override TRADINGAGENTS_DEEP_MODEL.")
    parser.add_argument("--quick-model", help="Override TRADINGAGENTS_QUICK_MODEL.")
    parser.add_argument("--checkpoint", action="store_true", help="Enable checkpoint resume.")
    parser.add_argument("--max-debate-rounds", type=int, default=1)
    parser.add_argument("--max-risk-rounds", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    for path in (OUTPUT_ROOT / "logs", OUTPUT_ROOT / "cache", OUTPUT_ROOT / "memory"):
        path.mkdir(parents=True, exist_ok=True)

    selected_analysts = [
        item.strip()
        for item in args.analysts.split(",")
        if item.strip()
    ]
    _load_env_file(REPO_ROOT / ".env.flint-shadow")
    provider = args.provider or os.getenv("TRADINGAGENTS_LLM_PROVIDER", "ollama")
    deep_model = args.deep_model or os.getenv("TRADINGAGENTS_DEEP_MODEL", "llama3:latest")
    quick_model = args.quick_model or os.getenv("TRADINGAGENTS_QUICK_MODEL", deep_model)

    result = run_shadow_job(
        ShadowRunRequest(
            ticker=args.ticker,
            trade_date=args.trade_date,
            selected_analysts=selected_analysts,
            provider=provider,
            deep_model=deep_model,
            quick_model=quick_model,
            shadow_run_id=str(uuid4()),
            checkpoint_enabled=bool(args.checkpoint),
            max_debate_rounds=int(args.max_debate_rounds),
            max_risk_rounds=int(args.max_risk_rounds),
            debug=bool(args.debug),
            repo_root=REPO_ROOT,
            env_file=REPO_ROOT / ".env.flint-shadow",
        )
    )

    summary = {
        "ticker": result.ticker,
        "trade_date": result.trade_date,
        "decision": result.decision,
        "final_trade_decision": result.final_trade_decision,
        "state_log_dir": result.state_log_dir,
        "memory_log_path": result.memory_log_path,
        "provider": result.provider,
        "deep_model": result.deep_model,
        "quick_model": result.quick_model,
        "shadow_run_id": result.shadow_run_id,
        "artifacts": result.artifacts,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
