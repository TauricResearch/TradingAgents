"""A fake worker.py for streaming tests: reads the stdin request, emits canned
NDJSON (started → 2 chunks → stats → done) without touching the LLM engine.
"""
import json
import sys

req = json.loads(sys.stdin.read())
ticker = req.get("ticker", "TEST")


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


emit({"kind": "started"})
emit({"kind": "chunk", "data": {"market_report": f"market for {ticker}"}})
emit({"kind": "chunk", "data": {"final_trade_decision": "BUY with conviction"}})
emit({"kind": "stats", "data": {"llm_calls": 3, "tool_calls": 2}})
emit({"kind": "done", "decision": "BUY"})
