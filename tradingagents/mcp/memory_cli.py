"""Decision-log CLI for the Claude Code trade-decision workflow.

The multi-agent reasoning runs inside Claude (via the workflow), but the
append-only decision log at ``~/.tradingagents/memory/trading_memory.md`` has a
precise, regex-parsed on-disk format (see
:class:`tradingagents.agents.utils.memory.TradingMemoryLog`). Rather than have
Claude hand-edit that format, the ``/trade`` slash command shells out to this
CLI for the read/write/resolve operations and keeps only the *reasoning*
(the reflection paragraph) for itself.

Subcommands::

    get-context TICKER
        Print the past-decisions context block to inject into the run
        (same-ticker history + recent cross-ticker lessons). Empty if none.

    pending TICKER
        Print a JSON list of this ticker's unresolved decisions, as
        [{"date": "...", "rating": "..."}], so Claude knows which prior runs
        to reflect on with realized returns.

    store TICKER DATE --decision-file PATH
        Append a new pending decision entry (rating parsed from the decision
        text). Idempotent per (date, ticker).

    resolve TICKER DATE --raw R --alpha A --holding D --reflection-file PATH
        Resolve a pending entry with realized returns and a reflection.

This module makes no LLM calls. It shares the format with the native pipeline,
so logs written here remain readable by the Python CLI and vice versa.
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from tradingagents.agents.utils.memory import TradingMemoryLog
from tradingagents.dataflows.config import set_config
from tradingagents.default_config import DEFAULT_CONFIG


def _memory_log() -> TradingMemoryLog:
    load_dotenv()
    config = DEFAULT_CONFIG.copy()
    set_config(config)
    return TradingMemoryLog(config)


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def _cmd_get_context(args: argparse.Namespace) -> int:
    log = _memory_log()
    sys.stdout.write(log.get_past_context(args.ticker))
    return 0


def _cmd_pending(args: argparse.Namespace) -> int:
    log = _memory_log()
    pending = [
        {"date": e["date"], "rating": e["rating"]}
        for e in log.get_pending_entries()
        if e["ticker"] == args.ticker
    ]
    sys.stdout.write(json.dumps(pending))
    return 0


def _cmd_store(args: argparse.Namespace) -> int:
    log = _memory_log()
    decision = _read_file(args.decision_file)
    log.store_decision(ticker=args.ticker, trade_date=args.date, final_trade_decision=decision)
    sys.stdout.write(f"stored pending decision for {args.ticker} @ {args.date}")
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    log = _memory_log()
    reflection = _read_file(args.reflection_file)
    log.update_with_outcome(
        ticker=args.ticker,
        trade_date=args.date,
        raw_return=args.raw,
        alpha_return=args.alpha,
        holding_days=args.holding,
        reflection=reflection,
    )
    sys.stdout.write(f"resolved {args.ticker} @ {args.date}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tradingagents-memory",
        description="Decision-log read/write for the Claude Code trade-decision workflow.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ctx = sub.add_parser("get-context", help="Print past-decisions context for a ticker.")
    p_ctx.add_argument("ticker")
    p_ctx.set_defaults(func=_cmd_get_context)

    p_pend = sub.add_parser("pending", help="Print JSON list of unresolved decisions for a ticker.")
    p_pend.add_argument("ticker")
    p_pend.set_defaults(func=_cmd_pending)

    p_store = sub.add_parser("store", help="Append a pending decision entry.")
    p_store.add_argument("ticker")
    p_store.add_argument("date", help="Trade date, yyyy-mm-dd")
    p_store.add_argument("--decision-file", required=True, help="Path to the final decision markdown.")
    p_store.set_defaults(func=_cmd_store)

    p_res = sub.add_parser("resolve", help="Resolve a pending entry with realized returns + reflection.")
    p_res.add_argument("ticker")
    p_res.add_argument("date", help="Trade date, yyyy-mm-dd")
    p_res.add_argument("--raw", type=float, required=True, help="Realized raw return (e.g. 0.034).")
    p_res.add_argument("--alpha", type=float, required=True, help="Alpha vs benchmark (e.g. -0.012).")
    p_res.add_argument("--holding", type=int, required=True, help="Holding days.")
    p_res.add_argument("--reflection-file", required=True, help="Path to the reflection paragraph.")
    p_res.set_defaults(func=_cmd_resolve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
