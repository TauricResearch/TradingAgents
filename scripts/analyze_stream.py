#!/usr/bin/env python3
"""Run TradingAgents analysis and emit JSON-line events to stdout.

Each line is a JSON object with an "event" key and optional "data".
The Hono SSE endpoint reads these lines and forwards them as SSE events.

Events emitted:
  {"event":"start","data":{"ticker":"TKA.DE","date":"2026-05-02"}}
  {"event":"agent_report","data":{"agent":"market","content":"..."}}
  {"event":"debate_round","data":{"round":1,"bull":"...","bear":"..."}}
  {"event":"risk_assessment","data":{"signal":"buy","confidence":0.7}}
  {"event":"decision","data":{"signal":"buy","reasoning":"...","confidence":0.7}}
  {"event":"complete","data":{"ticker":"TKA.DE"}}
  {"event":"error","data":{"message":"..."}}
"""
import argparse
import datetime
import json
import sys
import traceback
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


def emit(event: str, data: dict):
    """Write a JSON-line event to stdout."""
    line = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents analysis with SSE output")
    parser.add_argument("ticker", help="Ticker symbol (e.g. TKA.DE)")
    parser.add_argument("--date", default="today", help="Analysis date (YYYY-MM-DD or 'today')")
    parser.add_argument("--debates", type=int, default=1, help="Number of debate rounds")
    parser.add_argument("--analysts", default="market,news,fundamentals",
                        help="Comma-separated analyst types")
    args = parser.parse_args()

    load_dotenv()

    if args.date == "today":
        args.date = datetime.date.today().isoformat()

    emit("start", {"ticker": args.ticker, "date": args.date})

    try:
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "openrouter"
        config["deep_think_llm"] = "openai/gpt-5.4"
        config["quick_think_llm"] = "openai/gpt-5.4-mini"
        config["max_debate_rounds"] = args.debates
        config["max_risk_discuss_rounds"] = args.debates
        config["debug"] = False  # We handle our own streaming

        analysts = [a.strip() for a in args.analysts.split(",")]

        graph = TradingAgentsGraph(analysts, config=config, debug=False)
        final_state, decision = graph.propagate(args.ticker, args.date)

        # Emit reports from final state
        for agent_key, report_key in [
            ("market", "market_report"),
            ("news", "news_report"),
            ("fundamentals", "fundamentals_report"),
            ("sentiment", "sentiment_report"),
        ]:
            report = final_state.get(report_key, "")
            if report:
                emit("agent_report", {"agent": agent_key, "content": report[:2000]})

        # Emit debate state if present
        debate = final_state.get("investment_debate_state", {})
        if isinstance(debate.get("history"), list):
            for i, round_data in enumerate(debate["history"]):
                emit("debate_round", {"round": i + 1, "data": str(round_data)[:2000]})
        elif debate.get("history"):
            # History is a single string — emit once
            emit("debate_round", {"round": 1, "data": str(debate["history"])[:2000]})

        # Emit decision
        # process_signal() may return a string or a dict
        if isinstance(decision, dict):
            emit("decision", {
                "signal": decision.get("action", "hold"),
                "reasoning": decision.get("reasoning", "")[:2000],
                "confidence": decision.get("confidence", 0.5),
            })
        else:
            # decision is a string like "buy", "sell", "hold"
            emit("decision", {
                "signal": str(decision).strip(),
                "reasoning": "",
                "confidence": 0.5,
            })

        emit("complete", {"ticker": args.ticker})

    except Exception as e:
        emit("error", {"message": str(e), "traceback": traceback.format_exc()})
        sys.exit(1)


if __name__ == "__main__":
    main()
