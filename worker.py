"""Subprocess worker for a single TradingAgents analysis run.

Why a separate process: ``tradingagents.dataflows.config`` keeps a module-level
global ``_config`` that ``TradingAgentsGraph()`` mutates on construction. Running
multiple analyses in one Python process (e.g. concurrent Streamlit sessions)
causes them to clobber each other's vendor / output-language / cache settings.
Isolating each run in its own subprocess gives total config isolation.

Wire protocol:
    - Reads JSON request from stdin (single document):
        {"config": {...}, "ticker": "...", "trade_date": "YYYY-MM-DD",
         "selected_analysts": [...]}
    - Writes NDJSON events to stdout:
        {"kind": "started"}
        {"kind": "chunk", "data": <projected chunk fields>}
        {"kind": "done", "decision": "<processed final signal>"}
        {"kind": "error", "type": "...", "msg": "...", "trace": "..."}
    - Stray writes from imported libraries are diverted to stderr so the
      stdout stream remains clean NDJSON.
"""
from __future__ import annotations

# ─── Stdout protection: only our emit() may write to fd 1 ───
import os
import sys

_REAL_STDOUT = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
sys.stdout = sys.stderr  # any other print/log → stderr, never mixes with NDJSON

import json
import traceback
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / ".env.enterprise", override=False)

from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.graph.checkpointer import (  # noqa: E402
    clear_checkpoint,
    get_checkpointer,
    thread_id as _thread_id,
)


CHUNK_FIELDS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)


def emit(obj: dict) -> None:
    """Write one NDJSON event to the original stdout."""
    json.dump(obj, _REAL_STDOUT, ensure_ascii=False)
    _REAL_STDOUT.write("\n")
    _REAL_STDOUT.flush()


def project_chunk(chunk: dict) -> dict:
    """Strip a graph chunk down to just the fields the UI cares about."""
    out: dict = {}
    for k in CHUNK_FIELDS:
        v = chunk.get(k)
        if v:
            out[k] = v
    debate = chunk.get("investment_debate_state")
    if debate:
        out["investment_debate_state"] = {
            k: debate.get(k, "") for k in
            ("bull_history", "bear_history", "judge_decision")
        }
    risk = chunk.get("risk_debate_state")
    if risk:
        out["risk_debate_state"] = {
            k: risk.get(k, "") for k in
            ("aggressive_history", "conservative_history",
             "neutral_history", "judge_decision")
        }
    return out


def main() -> int:
    # 1. Parse request
    try:
        req = json.loads(sys.stdin.read())
        config = req["config"]
        ticker = req["ticker"]
        trade_date = req["trade_date"]
        selected_analysts = req["selected_analysts"]
        user_research = req.get("user_research", "") or ""
        checkpoint_enabled = bool(config.get("checkpoint_enabled"))
    except Exception as e:
        emit({"kind": "error", "type": "BadRequest", "msg": str(e),
              "trace": traceback.format_exc()})
        return 2

    # 2. Build graph + run
    checkpoint_ctx = None
    try:
        ta = TradingAgentsGraph(
            selected_analysts=selected_analysts, debug=False, config=config
        )
        # propagate() sets self.ticker — we bypass propagate so set it manually,
        # otherwise _log_state crashes on a None ticker.
        ta.ticker = ticker
        ta._resolve_pending_entries(ticker)
        past_context = ta.memory_log.get_past_context(ticker)
        init_state = ta.propagator.create_initial_state(
            ticker, str(trade_date),
            past_context=past_context,
            user_research=user_research,
        )
        args = ta.propagator.get_graph_args()

        graph_to_stream = ta.graph
        if checkpoint_enabled:
            checkpoint_ctx = get_checkpointer(config["data_cache_dir"], ticker)
            saver = checkpoint_ctx.__enter__()
            graph_to_stream = ta.workflow.compile(checkpointer=saver)
            args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = (
                _thread_id(ticker, str(trade_date))
            )

        emit({"kind": "started"})

        final_state = None
        for chunk in graph_to_stream.stream(init_state, **args):
            emit({"kind": "chunk", "data": project_chunk(chunk)})
            final_state = chunk

        if not final_state:
            emit({"kind": "error", "type": "EmptyStream",
                  "msg": "graph.stream produced no chunks"})
            return 3

        # 3. Persist (mirrors what propagate() does after invoke)
        if checkpoint_ctx is not None:
            try:
                clear_checkpoint(config["data_cache_dir"], ticker, str(trade_date))
            finally:
                checkpoint_ctx.__exit__(None, None, None)
                checkpoint_ctx = None

        ta.curr_state = final_state
        ta._log_state(str(trade_date), final_state)
        ta.memory_log.store_decision(
            ticker=ticker, trade_date=str(trade_date),
            final_trade_decision=final_state.get("final_trade_decision", ""),
        )
        decision = ta.process_signal(final_state.get("final_trade_decision", ""))
        emit({"kind": "done", "decision": decision})
        return 0

    except Exception as e:
        if checkpoint_ctx is not None:
            try:
                checkpoint_ctx.__exit__(None, None, None)
            except Exception:
                pass
        emit({"kind": "error", "type": type(e).__name__, "msg": str(e),
              "trace": traceback.format_exc(),
              "checkpoint_preserved": checkpoint_enabled})
        return 1


if __name__ == "__main__":
    sys.exit(main())
