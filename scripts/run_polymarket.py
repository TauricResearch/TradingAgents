"""Run the Polymarket research engine over N live open markets.

Usage:
    python scripts/run_polymarket.py [--limit 5] [--model openai/gpt-4o-mini]

Writes one JSON line per decision to:
    ~/.tradingagents/polymarket/decisions-YYYY-MM-DD.jsonl

This is the file the future backtesting harness (TODOS.md item 1) will read.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# Resolve paths before importing tradingagents so `.env` is loaded first.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from tradingagents.dataflows.polymarket_data import (
    CLOBAPIError,
    GammaAPIError,
    get_open_markets,
    get_order_book,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.exchange.paper_fill import simulate_fill
from tradingagents.graph.trading_graph import TradingAgentsGraph

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path.home() / ".tradingagents" / "polymarket"


def _decision_log_path(now: datetime) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"decisions-{now.strftime('%Y-%m-%d')}.jsonl"


def _fill_log_path(now: datetime) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / f"paper-fills-{now.strftime('%Y-%m-%d')}.jsonl"


def _append_jsonl(path: Path, payload: dict) -> None:
    """Append one JSONL line. Atomic-enough for single-process polling."""
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, separators=(",", ":")) + "\n")


def _append_decision(path: Path, payload: dict) -> None:
    _append_jsonl(path, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Number of markets to analyse")
    parser.add_argument(
        "--model",
        default="openai/gpt-4o-mini",
        help="OpenRouter model id (default: openai/gpt-4o-mini)",
    )
    parser.add_argument(
        "--budget",
        type=float,
        default=100.0,
        help="USDC budget per non-HOLD decision for paper fill (default: 100.0)",
    )
    parser.add_argument(
        "--no-fill",
        action="store_true",
        help="Skip the paper-fill step; persist decisions only",
    )
    parser.add_argument(
        "--days-until-close",
        type=int,
        default=None,
        help=(
            "Filter to markets closing within N days. Sorts by closest end date "
            "first. Useful for fast feedback: markets closing soon resolve fast."
        ),
    )
    parser.add_argument(
        "--min-liquidity",
        type=float,
        default=0.0,
        help=(
            "Skip markets with liquidity below this USDC threshold. "
            "Recommended >= 5000 to avoid lottery-ticket markets the bot "
            "tends to misprice. Default: 0 (no filter)."
        ),
    )
    parser.add_argument("--quiet", action="store_true", help="Print only the JSONL path")
    args = parser.parse_args()

    if not os.environ.get("EXA_API_KEY"):
        print("ERROR: EXA_API_KEY not set in environment or .env", file=sys.stderr)
        return 2
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set in environment or .env", file=sys.stderr)
        return 2

    market_kwargs: dict = {"limit": args.limit}
    if args.days_until_close is not None:
        today = datetime.now(timezone.utc).date()
        market_kwargs["order"] = "endDate"
        market_kwargs["ascending"] = True
        market_kwargs["end_date_min"] = today.isoformat()
        market_kwargs["end_date_max"] = (
            today + timedelta(days=args.days_until_close)
        ).isoformat()

    # Over-fetch when filtering client-side so we still end up with --limit
    # markets after low-liquidity ones are dropped.
    fetch_limit = args.limit
    if args.min_liquidity > 0:
        fetch_limit = max(args.limit * 5, 25)
    market_kwargs["limit"] = fetch_limit

    try:
        markets = get_open_markets(**market_kwargs)
    except GammaAPIError as e:
        print(f"ERROR: Gamma fetch failed: {e}", file=sys.stderr)
        return 3

    if args.min_liquidity > 0:
        before = len(markets)
        markets = [m for m in markets if m.get("liquidity", 0) >= args.min_liquidity]
        markets = markets[: args.limit]
        if not args.quiet:
            print(
                f"Filtered to {len(markets)} of {before} markets "
                f"(liquidity >= ${args.min_liquidity:,.0f})"
            )

    if not markets:
        print(
            "ERROR: zero markets matched filters (try lowering --min-liquidity "
            "or widening --days-until-close)",
            file=sys.stderr,
        )
        return 4

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openrouter"
    config["quick_think_llm"] = args.model
    config["deep_think_llm"] = args.model

    ta = TradingAgentsGraph(config=config)
    now = datetime.now(timezone.utc)
    log_path = _decision_log_path(now)
    fill_log_path = _fill_log_path(now)

    if not args.quiet:
        print(f"=== Analysing {len(markets)} markets with model={args.model} ===")
        print(f"  Decisions  -> {log_path}")
        if not args.no_fill:
            print(f"  Paper fills -> {fill_log_path}  (budget=${args.budget:.0f}/decision)")
        print()

    for i, m in enumerate(markets, start=1):
        question = m.get("question") or "(no question)"
        if not args.quiet:
            print(f"--- [{i}/{len(markets)}] {question[:80]}")
            print(f"    yes_price={m['yes_price']:.3f}  end={m.get('end_date')}")

        def _on_step(label: str) -> None:
            if not args.quiet:
                print(f"    .. {label}", flush=True)

        try:
            _, decision = ta.propagate_market(
                market_id=m["id"],
                question=question,
                yes_price=m["yes_price"],
                resolution_date=m.get("end_date") or "",
                on_step=_on_step,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("propagate_market failed for %s", m["id"])
            print(f"    FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            continue

        payload = {
            "ts": now.isoformat(),
            "model": args.model,
            **decision.model_dump(mode="json"),
        }
        _append_decision(log_path, payload)

        if not args.quiet:
            print(f"    -> {decision.direction.value} (conf {decision.confidence:.2f})")
            print(f"       {decision.rationale[:200]}")

        # Paper fill against the live order book (skip for HOLD or --no-fill).
        if args.no_fill or decision.direction.value == "HOLD":
            if not args.quiet:
                print()
            continue

        token_id = m.get("yes_token_id") if decision.direction.value == "BUY_YES" else m.get("no_token_id")
        if not token_id:
            if not args.quiet:
                print(f"    fill: SKIP — no token id available\n")
            continue

        try:
            book = get_order_book(token_id)
        except CLOBAPIError as e:
            if not args.quiet:
                print(f"    fill: SKIP — CLOB error: {e}\n")
            continue

        fill = simulate_fill(book["asks"], budget_usd=args.budget)
        fill_payload = {
            "ts": now.isoformat(),
            "market_id": m["id"],
            "question": question,
            "direction": decision.direction.value,
            "yes_price_at_analysis": decision.yes_price_at_analysis,
            "budget_usd": args.budget,
            **fill,
        }
        # Drop the verbose per-level fills array from the persisted log; keep
        # the aggregates. The full level breakdown is available by re-running.
        fill_payload.pop("fills", None)
        _append_jsonl(fill_log_path, fill_payload)

        if not args.quiet:
            if fill["filled"]:
                print(
                    f"    fill: {fill['contracts']:.1f} contracts @ vwap {fill['vwap']:.3f}  "
                    f"slippage {fill['slippage_pp']:.2f}pp  fee_if_win ${fill['fee_estimate_if_win']:.2f}"
                )
            else:
                print(f"    fill: UNFILLED — empty/thin book")
            print()

    if args.quiet:
        print(str(log_path))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
