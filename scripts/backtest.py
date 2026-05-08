"""Backtest the Polymarket research engine against already-resolved markets.

Pulls a sample of resolved Polymarket markets from gamma, runs `propagate_market`
on each at a midpoint YES price, then compares the bot's direction to the
actual resolution outcome.

CAVEAT - look-ahead bias is real and inherent to this design:
  - Exa search returns articles published any time, including AFTER the market
    resolved.
  - The LLM's training data may include information about how the market
    resolved.
Treat the output as a SANITY CHECK on prompt quality (does the bot at least
recognise post-hoc-correct directions?), NOT a true historical backtest. A
real backtest needs point-in-time news + price at decision moment.

Usage:
    python scripts/backtest.py --limit 20 --model openai/gpt-4o-mini
    python scripts/backtest.py --limit 10 --model anthropic/claude-sonnet-4-6

Writes one JSONL row per market to:
    ~/.tradingagents/polymarket/backtest-YYYY-MM-DD-{model_slug}.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

from tradingagents.dataflows.polymarket_data import (
    DEFAULT_TIMEOUT,
    GAMMA_BASE,
    GammaAPIError,
    _normalise_market,
)
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.exchange.scoring import MarketOutcome, classify_outcome
from tradingagents.graph.trading_graph import TradingAgentsGraph

OUTPUT_DIR = Path.home() / ".tradingagents" / "polymarket"


def _fetch_resolved_markets(limit: int, min_volume: float = 10000.0) -> list[dict]:
    """Pull resolved (closed) markets from gamma for backtesting.

    Filters out:
      - cancelled markets (CANCELED outcome)
      - data anomalies (UNKNOWN outcome from [0,0] outcomePrices)
      - markets below min_volume cumulative trade volume (resolved markets
        always have $0 current liquidity, so volume is the right
        "was this a real, traded market?" signal)
      - markets without token IDs
    """
    params = {
        "closed": "true",
        "limit": str(max(limit * 8, 100)),  # over-fetch for filtering
        "order": "endDate",
        "ascending": "false",  # most recently closed first
    }
    try:
        resp = httpx.get(f"{GAMMA_BASE}/markets", params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise GammaAPIError(f"Gamma /markets returned {e.response.status_code}: {e}") from e
    except httpx.RequestError as e:
        raise GammaAPIError(f"Gamma /markets request failed: {e}") from e

    out: list[dict] = []
    for raw_m in resp.json():
        m = _normalise_market(raw_m)
        if m is None:
            continue
        if m["volume"] < min_volume:
            continue
        if not m.get("yes_token_id") or not m.get("no_token_id"):
            continue
        prices = [m["yes_price"], 1.0 - m["yes_price"]]
        outcome, _ = classify_outcome(closed=True, outcome_prices=prices)
        if outcome not in (MarketOutcome.YES_WINS, MarketOutcome.NO_WINS):
            continue  # skip cancelled / data anomalies
        m["_actual_outcome"] = outcome
        out.append(m)
        if len(out) >= limit:
            break
    return out


def _model_slug(model: str) -> str:
    return model.replace("/", "-").replace(":", "-")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10, help="Number of resolved markets to backtest")
    parser.add_argument(
        "--model",
        default="openai/gpt-4o-mini",
        help="OpenRouter model id (default: openai/gpt-4o-mini)",
    )
    parser.add_argument(
        "--min-volume",
        type=float,
        default=10000.0,
        help=(
            "Skip resolved markets below this cumulative-volume threshold "
            "(default: $10,000). Volume is used instead of liquidity because "
            "resolved markets always show $0 current liquidity."
        ),
    )
    args = parser.parse_args()

    if not all(os.environ.get(k) for k in ["EXA_API_KEY", "OPENROUTER_API_KEY"]):
        print("ERROR: EXA_API_KEY and OPENROUTER_API_KEY must be set", file=sys.stderr)
        return 2

    print(f"Fetching {args.limit} resolved markets (>= ${args.min_volume:,.0f} cumulative volume)...")
    try:
        markets = _fetch_resolved_markets(args.limit, args.min_volume)
    except GammaAPIError as e:
        print(f"ERROR: gamma fetch failed: {e}", file=sys.stderr)
        return 3

    if not markets:
        print("ERROR: zero resolved markets matched filters", file=sys.stderr)
        return 4

    print(f"Got {len(markets)} resolved markets to backtest with model={args.model}\n")
    print(
        "CAVEAT: look-ahead bias is real. Exa may return post-resolution news; "
        "the LLM may know how this resolved. Use as a sanity check, not a "
        "true backtest.\n"
    )

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openrouter"
    config["quick_think_llm"] = args.model
    config["deep_think_llm"] = args.model
    ta = TradingAgentsGraph(config=config)

    now = datetime.now(timezone.utc)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_path = OUTPUT_DIR / f"backtest-{now.strftime('%Y-%m-%d')}-{_model_slug(args.model)}.jsonl"

    correct = 0
    total_scored = 0
    holds = 0

    for i, m in enumerate(markets, start=1):
        actual = m["_actual_outcome"]
        question = m.get("question") or "(no question)"
        # Use 0.50 midpoint to remove anchor bias from showing the bot a
        # near-1.0 or near-0.0 final price.
        yes_price_used = 0.50

        print(f"[{i}/{len(markets)}] actual={actual.value:<9}  {question[:65]}")

        def _on_step(label: str) -> None:
            print(f"    .. {label}", flush=True)

        try:
            _, decision = ta.propagate_market(
                market_id=m["id"],
                question=question,
                yes_price=yes_price_used,
                resolution_date=m.get("end_date") or "",
                on_step=_on_step,
            )
        except Exception as e:  # noqa: BLE001
            print(f"    FAILED: {type(e).__name__}: {e}", file=sys.stderr)
            continue

        is_hold = decision.direction.value == "HOLD"
        is_correct = (
            (decision.direction.value == "BUY_YES" and actual == MarketOutcome.YES_WINS)
            or (decision.direction.value == "BUY_NO" and actual == MarketOutcome.NO_WINS)
        )

        if is_hold:
            holds += 1
        else:
            total_scored += 1
            if is_correct:
                correct += 1

        marker = "HOLD" if is_hold else ("OK" if is_correct else "WRONG")
        print(f"    -> {decision.direction.value:<8} (conf {decision.confidence:.2f})  [{marker}]")

        row = {
            "ts": now.isoformat(),
            "model": args.model,
            "market_id": m["id"],
            "question": question,
            "yes_price_used": yes_price_used,
            "actual_outcome": actual.value,
            "predicted_direction": decision.direction.value,
            "confidence": decision.confidence,
            "correct": is_correct,
            "is_hold": is_hold,
            "rationale": decision.rationale,
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, separators=(",", ":")) + "\n")

    print()
    print("=" * 70)
    print(f"BACKTEST RESULTS  ({args.model})")
    print("=" * 70)
    print(f"  Resolved markets analysed:  {len(markets)}")
    print(f"  Decisions (non-HOLD):       {total_scored}")
    print(f"  HOLDs (excluded from acc):  {holds}")
    if total_scored > 0:
        acc = correct / total_scored
        print(f"  Correct directional calls:  {correct}/{total_scored}")
        print(f"  Accuracy:                   {acc*100:.1f}%")
        print(f"  (random baseline:           50.0%)")
    print(f"  Log:                        {log_path}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
