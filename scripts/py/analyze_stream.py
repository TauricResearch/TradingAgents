#!/usr/bin/env python3
"""Run TradingAgents analysis and emit JSON-line events to stdout.

Each line is a JSON object with an "event" key and optional "data".
The Hono SSE endpoint reads these lines and forwards them as SSE events.

Events emitted:
  {"event":"start","data":{"ticker":"TKA.DE","date":"2026-05-02","position_context":"500 shares @ 8.45","retry":false}}
  {"event":"heartbeat","data":{"tick":1}}           # written to stderr, 15s interval
  {"event":"agent_report","data":{"agent":"market","content":"..."}}
  {"event":"debate_round","data":{"round":1,"data":"..."}}
  {"event":"decision","data":{"signal":"buy","reasoning":"...","confidence":0.7}}
  {"event":"complete","data":{"ticker":"TKA.DE"}}
  {"event":"error","data":{"message":"..."}}
"""
import argparse
import datetime
import json
import os
import signal
import sys
import threading
import time
import traceback
from queue import Queue, Empty
from dotenv import load_dotenv

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ── Global queues for threaded communication ─────────────────────────────────

AGENT_REPORT_QUEUE: Queue = Queue()
DEBATE_ROUND_QUEUE: Queue = Queue()
GRAPH_ERROR: list = []  # [error] populated by thread if propagate() fails

# ── Heartbeat thread ─────────────────────────────────────────────────────────

def heartbeat_loop(interval: int, stop_event: threading.Event):
    """Write heartbeat events to stderr every `interval` seconds.

    stderr is used (not stdout) to avoid corrupting the JSON-line protocol.
    The Bun SSE handler reads stderr separately via child.stderr handlers.
    """
    tick = 0
    while not stop_event.is_set():
        time.sleep(interval)
        if stop_event.is_set():
            break
        tick += 1
        line = json.dumps({"event": "heartbeat", "data": {"tick": tick}}, ensure_ascii=False)
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


# ── Background thread for graph.propagate() ─────────────────────────────────

def run_propagate(analysts, config, ticker, date, position_context, result_holder: list):
    """Run TradingAgentsGraph.propagate() in a background thread.

    result_holder[0] will be set to (final_state, decision) on success,
    or re-raised as an exception on failure.
    position_context is injected before propagate() so it affects the decision.
    """
    try:
        graph = TradingAgentsGraph(analysts, config=config, debug=False)

        # Inject position context before propagate() runs
        if position_context:
            try:
                if hasattr(graph, "memory_log") and graph.memory_log._log_path:
                    _inject_position_context(
                        graph.memory_log,
                        ticker=ticker,
                        context=position_context,
                        date=date,
                    )
            except Exception:
                pass  # Non-fatal — position context is optional enrichment

        # Poll agent state in a tight loop, pushing reports to queues
        # as they appear in the graph state snapshot.
        seen_reports = set()
        seen_debates = set()

        def poll_state():
            state = graph.state
            # Agent reports — check all known report keys
            for report_key, agent_name in [
                ("market_report", "market"),
                ("news_report", "news"),
                ("fundamentals_report", "fundamentals"),
                ("sentiment_report", "sentiment"),
            ]:
                report = state.get(report_key, "")
                if report and report_key not in seen_reports:
                    seen_reports.add(report_key)
                    AGENT_REPORT_QUEUE.put((agent_name, report[:2000]))

            # Debate rounds
            debate = state.get("investment_debate_state", {})
            history = debate.get("history", [])
            if isinstance(history, list):
                for i, round_data in enumerate(history):
                    if i not in seen_debates:
                        seen_debates.add(i)
                        DEBATE_ROUND_QUEUE.put((i + 1, str(round_data)[:2000]))
            elif history and "debate_round_0" not in seen_debates:
                seen_debates.add("debate_round_0")
                DEBATE_ROUND_QUEUE.put((1, str(history)[:2000]))

            return state

        # Run propagate — TradingAgentsGraph is synchronous so we poll
        # after each "step" by checking the state snapshot.
        # Since propagate() blocks, we do a single snapshot at the end
        # and emit everything we found. Real-time streaming requires
        # async hooks into the graph — deferred per brief.
        final_state, decision = graph.propagate(ticker, date)

        # Final snapshot — emit any reports not caught during polling
        poll_state()

        result_holder.append((final_state, decision))
    except Exception as exc:
        GRAPH_ERROR.append(exc)


# ── Position context injection ───────────────────────────────────────────────

def _inject_position_context(memory_log, ticker: str, context: str, date: str) -> None:
    """Write a synthetic entry to the memory log so get_past_context() includes it.

    Uses the same markdown format as store_decision() so the parser picks it up.
    This is a 'wrap, don't fork' approach — no TradingAgents core modifications.
    """
    if not memory_log._log_path:
        return

    log_path = memory_log._log_path
    log_path.parent.mkdir(parents=True, exist_ok=True)

    tag = f"[{date} | {ticker} | neutral | n/a | n/a | n/a]"
    entry = (
        f"{tag}\n\n"
        f"DECISION:\n"
        f"**Position context (current holding):** {context}\n\n"
        f"REFLECTION:\n"
        f"Position context injected from portfolio database.\n"
        f"{memory_log._SEPARATOR}"
    )

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(entry)


# ── Emitters ─────────────────────────────────────────────────────────────────

def emit_stdout(event: str, data: dict):
    """Write a JSON-line event to stdout (SSE data)."""
    line = json.dumps({"event": event, "data": data}, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


# ── Timeout handler ──────────────────────────────────────────────────────────

class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Analysis timed out")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run TradingAgents analysis with SSE output")
    parser.add_argument("ticker", help="Ticker symbol (e.g. TKA.DE)")
    parser.add_argument("--date", default="today", help="Analysis date (YYYY-MM-DD or 'today')")
    parser.add_argument("--debates", type=int, default=1, help="Number of debate rounds")
    parser.add_argument("--analysts", default="market,news,fundamentals",
                        help="Comma-separated analyst types")
    parser.add_argument("--position-context", default=None,
                        help="Position context string (e.g. '500 shares @ 8.45 — thesis: value play')")
    parser.add_argument("--llm-api-base", default=None,
                        help="LLM API base URL (e.g. http://localhost:8080/v1 for BiFrost proxy)")
    parser.add_argument("--timeout", type=int, default=240,
                        help="Timeout in seconds (default: 240)")
    parser.add_argument("--heartbeat-interval", type=int, default=15,
                        help="Heartbeat interval in seconds (default: 15)")
    parser.add_argument("--retry", action="store_true",
                        help="Indicates this is a retry after transient failure")
    # LLM config args (override hardcoded defaults)
    parser.add_argument("--llm-provider", default=None,
                        help="LLM provider (openrouter/openai/anthropic)")
    parser.add_argument("--deep-think-llm", default=None,
                        help="Model for deep thinking (e.g. deepseek/deepseek-v4-flash)")
    parser.add_argument("--quick-think-llm", default=None,
                        help="Model for quick thinking (e.g. deepseek/deepseek-v4-flash)")
    parser.add_argument("--debrief", action="store_true",
                        help="Write analysis results to debriefs/ directory")

    args = parser.parse_args()

    load_dotenv()

    if args.date == "today":
        args.date = datetime.date.today().isoformat()

    emit_stdout("start", {
        "ticker": args.ticker,
        "date": args.date,
        "position_context": args.position_context,
        "retry": args.retry,
    })

    # ── Build config ───────────────────────────────────────────────────────────
    config = DEFAULT_CONFIG.copy()

    # Default: use OpenRouter directly with Ernie 4.5
    config["llm_provider"] = args.llm_provider or "openrouter"
    config["deep_think_llm"] = args.deep_think_llm or "baidu/ernie-4.5-21b-a3b-thinking"
    config["quick_think_llm"] = args.quick_think_llm or "baidu/ernie-4.5-21b-a3b-thinking"

    # BiFrost proxy routing
    if args.llm_api_base:
        config["backend_url"] = args.llm_api_base
        config["llm_provider"] = "openai"  # BiFrost proxy is OpenAI-compatible
        config["deep_think_llm"] = args.deep_think_llm or "deepseek/deepseek-v4-flash"
        config["quick_think_llm"] = args.quick_think_llm or "deepseek/deepseek-v4-flash"

    config["max_debate_rounds"] = args.debates
    config["max_risk_discuss_rounds"] = args.debates
    config["debug"] = False

    analysts = [a.strip() for a in args.analysts.split(",")]

    # ── Start heartbeat thread ─────────────────────────────────────────────────
    stop_heartbeat = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat_loop,
        args=(args.heartbeat_interval, stop_heartbeat),
        daemon=True,
    )
    heartbeat_thread.start()

    # ── Set Python-level timeout (signal.alarm fallback) ──────────────────────
    # The Bun side also enforces timeout via AbortSignal.timeout() — this is
    # a defence-in-depth layer that works even if Bun doesn't kill the process.
    old_alarm_handler = None
    if hasattr(signal, "SIGALRM"):
        old_alarm_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(args.timeout)

    result_holder: list = []

    try:
        # Run graph.propagate() in background thread so we can:
        # 1. Poll for real-time agent reports
        # 2. Still handle heartbeat (main thread is sleeping)
        propagate_thread = threading.Thread(
            target=run_propagate,
            args=(analysts, config, args.ticker, args.date, args.position_context, result_holder),
            daemon=True,
        )
        propagate_thread.start()

        # Poll queues while the thread runs
        while propagate_thread.is_alive():
            propagate_thread.join(timeout=2)

            # Drain agent report queue
            while True:
                try:
                    agent_name, content = AGENT_REPORT_QUEUE.get_nowait()
                    emit_stdout("agent_report", {"agent": agent_name, "content": content})
                except Empty:
                    break

            # Drain debate round queue
            while True:
                try:
                    round_num, data = DEBATE_ROUND_QUEUE.get_nowait()
                    emit_stdout("debate_round", {"round": round_num, "data": data})
                except Empty:
                    break

        # Propagate thread has finished — check for errors
        if GRAPH_ERROR:
            raise GRAPH_ERROR[0]

        if not result_holder:
            raise RuntimeError("graph.propagate() returned no result")

        final_state, decision = result_holder[0]

        # Emit any remaining reports from final state
        for agent_key, report_key in [
            ("market", "market_report"),
            ("news", "news_report"),
            ("fundamentals", "fundamentals_report"),
            ("sentiment", "sentiment_report"),
        ]:
            report = final_state.get(report_key, "")
            if report:
                emit_stdout("agent_report", {"agent": agent_key, "content": report[:2000]})

        # Emit debate state if present
        debate = final_state.get("investment_debate_state", {})
        if isinstance(debate.get("history"), list):
            for i, round_data in enumerate(debate["history"]):
                emit_stdout("debate_round", {"round": i + 1, "data": str(round_data)[:2000]})
        elif debate.get("history"):
            emit_stdout("debate_round", {"round": 1, "data": str(debate["history"])[:2000]})

        # Emit decision
        if isinstance(decision, dict):
            emit_stdout("decision", {
                "signal": decision.get("action", "hold"),
                "reasoning": decision.get("reasoning", "")[:2000],
                "confidence": decision.get("confidence", 0.5),
            })
        else:
            emit_stdout("decision", {
                "signal": str(decision).strip(),
                "reasoning": "",
                "confidence": 0.5,
            })

        emit_stdout("complete", {"ticker": args.ticker})

        # Write debrief if requested
        if args.debrief:
            import os as _os
            debrief_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "debriefs")
            _os.makedirs(debrief_dir, exist_ok=True)
            debrief_file = _os.path.join(debrief_dir, f"debrief-{args.ticker}-{args.date}.json")
            with open(debrief_file, "w") as f:
                json.dump({
                    "ticker": args.ticker,
                    "date": args.date,
                    "position_context": args.position_context,
                    "final_state_keys": list(final_state.keys()) if final_state else [],
                    "decision": decision if isinstance(decision, dict) else {"action": str(decision)},
                }, f, indent=2)

    except TimeoutError:
        # Stop heartbeat
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        emit_stdout("error", {
            "message": f"Analysis timed out after {args.timeout}s",
            "traceback": "Python signal.SIGALRM triggered",
        })
        sys.exit(1)

    except Exception as e:
        # Stop heartbeat
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
        emit_stdout("error", {"message": str(e), "traceback": traceback.format_exc()})
        sys.exit(1)

    finally:
        # Clean up alarm
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
            if old_alarm_handler is not None:
                signal.signal(signal.SIGALRM, old_alarm_handler)
        # Stop heartbeat
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)


if __name__ == "__main__":
    main()