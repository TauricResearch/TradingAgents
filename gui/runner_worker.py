"""Subprocess worker that runs a single ``propagate`` and streams NDJSON to stdout.

Invoked by ``gui.runner`` as:
    python -m gui.runner_worker <path-to-job.json>

The job file is a JSON document with the run config (ticker, date, provider,
models, depth, vendors). Stdout is a stream of newline-delimited JSON events:
each event is one line, parsed by the GUI process. Stderr is reserved for
unexpected Python tracebacks; ordinary errors flow through ``error`` events on
stdout so the GUI can render them.

Events emitted:
    {"type":"start", ...}             -- once at startup
    {"type":"node_start", "node":...} -- LangGraph node entered
    {"type":"node_end", "node":...}   -- LangGraph node exited
    {"type":"tool_start", "tool":...} -- agent tool call begins
    {"type":"tool_end", "tool":...}   -- agent tool call returns
    {"type":"chunk", "section":..., "content":...} -- raw agent message text
    {"type":"stats", ...}             -- token / call counters
    {"type":"done", "decision":..., "report_path":...}
    {"type":"error", "message":..., "traceback":...}

The point of running in a subprocess is isolation: a crash in LangChain or
LangGraph kills the worker, not the Streamlit process. The user can also
cancel a run by terminating the subprocess.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import AIMessage


def emit(event: Dict[str, Any]) -> None:
    """Write one NDJSON event to stdout and flush."""
    sys.stdout.write(json.dumps(event, default=str) + "\n")
    sys.stdout.flush()


class GuiCallbackHandler(BaseCallbackHandler):
    """Aggregates stats and forwards LangChain events to the GUI as NDJSON."""

    def __init__(self) -> None:
        super().__init__()
        self.llm_calls = 0
        self.tool_calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self._last_emit = 0.0

    def _stats_snapshot(self) -> Dict[str, int]:
        return {
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }

    def _maybe_emit_stats(self) -> None:
        now = time.time()
        if now - self._last_emit < 0.25:
            return
        self._last_emit = now
        emit({"type": "stats", **self._stats_snapshot()})

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        self.llm_calls += 1
        self._maybe_emit_stats()

    def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[Any]], **kwargs: Any) -> None:
        self.llm_calls += 1
        self._maybe_emit_stats()

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        try:
            generation = response.generations[0][0]
        except (IndexError, TypeError):
            return
        usage_metadata = None
        if hasattr(generation, "message"):
            message = generation.message
            if isinstance(message, AIMessage) and hasattr(message, "usage_metadata"):
                usage_metadata = message.usage_metadata
        if usage_metadata:
            self.tokens_in += usage_metadata.get("input_tokens", 0) or 0
            self.tokens_out += usage_metadata.get("output_tokens", 0) or 0
        self._maybe_emit_stats()

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        self.tool_calls += 1
        tool_name = (serialized or {}).get("name") or "unknown"
        emit({"type": "tool_start", "tool": tool_name, "input": (input_str or "")[:500]})
        self._maybe_emit_stats()

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        text = str(output) if output is not None else ""
        emit({"type": "tool_end", "preview": text[:500]})
        self._maybe_emit_stats()

    def on_chain_start(self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any) -> None:
        name = (serialized or {}).get("name")
        if not name:
            return
        if name in {"LangGraph", "RunnableSequence", "RunnableLambda"}:
            return
        emit({"type": "node_start", "node": name})

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        return  # node_end fires too noisily; rely on chunk + done


SECTION_KEYS = (
    "market_report",
    "sentiment_report",
    "news_report",
    "fundamentals_report",
    "investment_plan",
    "trader_investment_plan",
    "final_trade_decision",
)


def _emit_chunk(chunk: Dict[str, Any], prev_seen: Dict[str, str]) -> None:
    """Pull the latest message + any new section reports out of a LangGraph chunk.

    The graph streams in ``values`` mode so each chunk is a full state dict.
    We diff against ``prev_seen`` and emit a ``section`` event whenever one
    of the report keys gains content. We also forward the most recent
    message as a ``chunk`` event so the live log shows raw agent thinking.
    """
    # Section reports — emit on first appearance / change.
    for key in SECTION_KEYS:
        val = chunk.get(key)
        if val and val != prev_seen.get(key):
            prev_seen[key] = val
            emit({"type": "section", "key": key, "content": str(val)})

    # Investment debate history (bull/bear).
    debate = chunk.get("investment_debate_state") or {}
    for history_key, label in (("bull_history", "bull"), ("bear_history", "bear")):
        val = debate.get(history_key)
        if val and val != prev_seen.get(history_key):
            prev_seen[history_key] = val
            emit({"type": "debate", "side": label, "content": str(val)})
    judge = debate.get("judge_decision")
    if judge and judge != prev_seen.get("research_judge"):
        prev_seen["research_judge"] = judge
        emit({"type": "section", "key": "research_judge", "content": str(judge)})

    # Risk debate history (aggressive/conservative/neutral).
    risk = chunk.get("risk_debate_state") or {}
    for history_key, label in (("aggressive_history", "aggressive"),
                                ("conservative_history", "conservative"),
                                ("neutral_history", "neutral")):
        val = risk.get(history_key)
        if val and val != prev_seen.get(history_key):
            prev_seen[history_key] = val
            emit({"type": "risk", "side": label, "content": str(val)})

    # Latest raw message (for the live log).
    messages = chunk.get("messages")
    if messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if content:
            if isinstance(content, list):
                parts: List[str] = []
                for p in content:
                    if isinstance(p, dict):
                        parts.append(p.get("text", "") or p.get("content", "") or "")
                    else:
                        parts.append(str(p))
                content = "".join(parts)
            role = type(last).__name__
            emit({"type": "chunk", "role": role, "content": str(content)[:4000]})


def run(job: Dict[str, Any]) -> None:
    ticker = job["ticker"]
    trade_date = job["trade_date"]

    emit({"type": "start", "ticker": ticker, "trade_date": trade_date})

    # Imports here so any ImportError surfaces as an ``error`` event rather
    # than killing the worker before it can report.
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.dataflows.utils import safe_ticker_component

    safe_ticker_component(ticker)  # validate; raises ValueError otherwise

    config = DEFAULT_CONFIG.copy()
    for k in ("llm_provider", "deep_think_llm", "quick_think_llm",
              "max_debate_rounds", "max_risk_discuss_rounds",
              "checkpoint_enabled", "output_language"):
        if k in job and job[k] is not None:
            config[k] = job[k]
    if job.get("data_vendors"):
        config["data_vendors"] = dict(job["data_vendors"])
    if job.get("backend_url"):
        config["backend_url"] = job["backend_url"]

    handler = GuiCallbackHandler()
    ta = TradingAgentsGraph(debug=False, config=config, callbacks=[handler])

    # ``propagate()`` sets ``self.ticker`` as its very first line; ``_log_state``
    # later reads it via ``safe_ticker_component(self.ticker)``. Our custom
    # streaming loop replaces ``propagate``, so we have to set it ourselves
    # or the post-stream log write blows up with "ticker must be a non-empty
    # string, got None" — even though the analysis itself succeeded.
    ta.ticker = ticker

    # We replicate ``_run_graph`` here so we can iterate ``graph.stream`` and
    # emit chunk events as nodes complete. The original ``debug=True`` path
    # only pretty-prints to stdout — we want structured events.
    past_context = ta.memory_log.get_past_context(ticker)
    init_state = ta.propagator.create_initial_state(ticker, trade_date, past_context=past_context)
    args = ta.propagator.get_graph_args()

    # Resolve any prior pending entries before the run (same as ta.propagate does).
    ta._resolve_pending_entries(ticker)

    final_state: Optional[Dict[str, Any]] = None
    prev_seen: Dict[str, str] = {}
    try:
        for chunk in ta.graph.stream(init_state, **args):
            _emit_chunk(chunk, prev_seen)
            final_state = chunk
    except Exception as e:
        emit({
            "type": "error",
            "message": str(e),
            "traceback": traceback.format_exc(),
        })
        return

    if final_state is None:
        emit({"type": "error", "message": "graph produced no output"})
        return

    ta.curr_state = final_state

    # Compute the canonical path the same way ``_log_state`` does so we can
    # archive after writing.
    report_dir = Path(config["results_dir"]) / safe_ticker_component(ticker) / "TradingAgentsStrategy_logs"
    canonical_path = report_dir / f"full_states_log_{trade_date}.json"

    # Write the canonical state log. If this fails we still try to archive
    # whatever we have, and we still emit ``done`` — the analysis itself
    # succeeded; a log-write failure shouldn't paint the run red.
    log_warning: Optional[str] = None
    try:
        ta._log_state(trade_date, final_state)
    except Exception as e:
        log_warning = f"could not write canonical state log: {e}"

    # Archive a per-run copy so re-running the same ticker/date never
    # overwrites a prior run's transcript. Path is
    # ``<report_dir>/runs/<run_id>__<UTC_timestamp>.json``.
    archive_path: Optional[Path] = None
    run_id = job.get("run_id") or "norunid"
    archive_dir = report_dir / "runs"
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive_path = archive_dir / f"{run_id}__{trade_date}__{ts}.json"
        if canonical_path.exists():
            shutil.copy2(canonical_path, archive_path)
        else:
            # Canonical write failed — write the state dict directly so the
            # run is preserved.
            archive_path.write_text(
                json.dumps(_state_for_archive(final_state), indent=2, default=str),
                encoding="utf-8",
            )
    except Exception as e:
        if log_warning:
            log_warning = f"{log_warning}; archive also failed: {e}"
        else:
            log_warning = f"could not archive state log: {e}"
        archive_path = None

    decision_text = final_state.get("final_trade_decision", "")
    ta.memory_log.store_decision(ticker=ticker, trade_date=trade_date,
                                 final_trade_decision=decision_text)

    decision = ta.process_signal(decision_text)

    if log_warning:
        emit({"type": "warning", "message": log_warning})

    emit({"type": "stats", **handler._stats_snapshot()})
    emit({
        "type": "done",
        "decision": decision,
        "report_path": str(canonical_path),
        "archive_path": str(archive_path) if archive_path else None,
        **handler._stats_snapshot(),
    })


def _state_for_archive(state: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-serialisable bits out of a graph state for direct JSON write."""
    out: Dict[str, Any] = {}
    for k, v in state.items():
        if k == "messages":
            continue  # message objects are not JSON-friendly
        out[k] = v
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m gui.runner_worker <job.json>", file=sys.stderr)
        return 2
    job_path = Path(sys.argv[1])
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except Exception as e:
        emit({"type": "error", "message": f"could not read job file: {e}"})
        return 1
    try:
        run(job)
        return 0
    except Exception as e:
        emit({"type": "error", "message": str(e), "traceback": traceback.format_exc()})
        return 1


if __name__ == "__main__":
    sys.exit(main())
