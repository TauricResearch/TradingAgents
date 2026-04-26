"""Map LangGraph v2 streaming events to AgentOS frontend contract.

Extracted from ``langgraph_engine.py`` to keep event-mapping logic
separate from orchestration (Single Responsibility Principle).
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("agent_os.engine")

# Maximum characters of prompt/response content to include in the short message
_MAX_CONTENT_LEN = 300
# Maximum characters for full prompt/response fields (generous limit)
_MAX_FULL_LEN = 50_000
# Keywords in tool output that indicate the error was handled gracefully
_GRACEFUL_SKIP_KEYWORDS = ("gracefully", "fallback", "skipped")

# ──────────────────────────────────────────────────────────────────────────────
# Tool-name → primary service mapping (best-effort, used for display only)
# ──────────────────────────────────────────────────────────────────────────────
TOOL_SERVICE_MAP: dict[str, str] = {
    # Core stock APIs
    "get_stock_data": "yfinance",
    "get_indicators": "yfinance",
    # Fundamental data
    "get_fundamentals": "yfinance",
    "get_balance_sheet": "yfinance",
    "get_cashflow": "yfinance",
    "get_income_statement": "yfinance",
    "get_ttm_analysis": "yfinance (derived)",
    "get_peer_comparison": "yfinance (derived)",
    "get_sector_relative": "yfinance (derived)",
    "get_macro_regime": "yfinance (derived)",
    # News
    "get_news": "yfinance",
    "get_global_news": "yfinance",
    "get_insider_transactions": "finnhub",
    # Scanner
    "get_market_movers": "yfinance",
    "get_market_indices": "finnhub",
    "get_sector_performance": "finnhub",
    "get_industry_performance": "yfinance",
    "get_topic_news": "finnhub",
    "get_earnings_calendar": "finnhub",
    "get_economic_calendar": "finnhub",
    # Finviz smart money
    "get_insider_buying_stocks": "finviz",
    "get_unusual_volume_stocks": "finviz",
    "get_breakout_accumulation_stocks": "finviz",
    # Portfolio (local)
    "get_enriched_holdings": "local",
    "compute_portfolio_risk_metrics": "local",
    "load_portfolio_risk_metrics": "local",
    "load_portfolio_decision": "local",
}


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class NodeWallClockBudgetExceeded(RuntimeError):
    """Raised when a LangGraph node exceeds the configured wall-clock budget."""

    def __init__(self, *, node_name: str, elapsed_sec: float, budget_sec: float) -> None:
        self.node_name = node_name
        self.elapsed_sec = elapsed_sec
        self.budget_sec = budget_sec
        super().__init__(
            f"Node {node_name} exceeded wall-clock budget: "
            f"{elapsed_sec:.2f}s elapsed > {budget_sec:.2f}s budget"
        )


def is_root_chain_end(event: dict[str, Any]) -> bool:
    """Return True for the root-graph terminal event in a LangGraph v2 stream.

    LangGraph v2 emits one ``on_chain_end`` event per node AND one for the
    root graph itself.  The root-graph event is distinguished by:

    * ``event["metadata"]`` has no ``langgraph_node`` key  (node events always do)
    * ``event["parent_ids"]`` is empty  (root has no parent run)

    Its ``data["output"]`` contains the **complete** final state — the
    canonical way to read the propagated state without re-running the graph.
    """
    if event.get("event") != "on_chain_end":
        return False
    metadata = event.get("metadata") or {}
    if metadata.get("langgraph_node"):
        return False  # This is a node event, not the root
    parent_ids = event.get("parent_ids")
    return parent_ids is not None and len(parent_ids) == 0


def extract_node_name(event: dict[str, Any]) -> str:
    """Extract the LangGraph node name from event metadata or tags."""
    metadata = event.get("metadata") or {}
    node = metadata.get("langgraph_node")
    if node:
        return node

    for tag in event.get("tags", []):
        if tag.startswith("graph:node:"):
            return tag.split(":", 2)[-1]

    return event.get("name", "unknown")


def system_log(message: str) -> dict[str, Any]:
    """Create a log-type event for informational messages."""
    return {
        "id": f"log_{time.time_ns()}",
        "node_id": "__system__",
        "type": "log",
        "agent": "SYSTEM",
        "message": message,
        "metrics": {},
    }


def _extract_content(obj: object) -> str:
    """Safely extract text content from a LangChain message or plain object."""
    content = getattr(obj, "content", None)
    if content is not None and callable(content):
        content = None
    return str(content) if content is not None else str(obj)


def _truncate(text: str, max_len: int = _MAX_CONTENT_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…"


def _safe_dict(obj: object) -> dict[str, Any]:
    """Return *obj* if it is a dict, otherwise an empty dict."""
    return obj if isinstance(obj, dict) else {}


def _extract_all_messages_content(messages: Any) -> str:
    """Extract text from ALL messages in a LangGraph messages payload.

    Returns the concatenated content of every message so the user can
    inspect the full prompt that was sent to the LLM.
    """
    if not messages:
        return ""

    items: list = messages if isinstance(messages, list) else list(messages)
    if items and isinstance(items[0], (list, tuple)):
        items = list(items[0])

    parts: list[str] = []
    for msg in items:
        content = getattr(msg, "content", None)
        role = getattr(msg, "type", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content", "")
            role = msg.get("role") or msg.get("type") or "unknown"
        if role is None:
            role = "unknown"
        text = str(content) if content is not None else str(msg)
        parts.append(f"[{role}] {text}")

    return "\n\n".join(parts)


def _extract_model(event: dict[str, Any]) -> str:
    """Best-effort extraction of the model name from a LangGraph event."""
    data = event.get("data") or {}

    inv = data.get("invocation_params") or {}
    model = inv.get("model_name") or inv.get("model") or ""
    if model:
        return model

    serialized = event.get("serialized") or data.get("serialized") or {}
    kwargs = serialized.get("kwargs") or {}
    model = kwargs.get("model_name") or kwargs.get("model") or ""
    if model:
        return model

    metadata = event.get("metadata") or {}
    model = metadata.get("ls_model_name") or ""
    if model:
        return model

    return "unknown"


# ---------------------------------------------------------------------------
# EventMapper — stateful per-run mapping
# ---------------------------------------------------------------------------


class EventMapper:
    """Maps LangGraph v2 events to the AgentOS frontend contract.

    One mapper instance is associated with one execution key.  The engine
    creates a fresh mapper for each run/rerun and delegates event translation.
    """

    def __init__(self, *, node_wall_clock_budget_sec: float | None = None) -> None:
        self._node_start_times: dict[str, dict[str, float]] = {}
        self._node_prompts: dict[str, dict[str, str]] = {}
        self._run_identifiers: dict[str, str] = {}
        self._latest_nodes: dict[str, str] = {}
        self.node_wall_clock_budget_sec = node_wall_clock_budget_sec

    # -- lifecycle helpers ---------------------------------------------------

    def register_run(self, execution_key: str, identifier: str) -> None:
        self._node_start_times[execution_key] = {}
        self._run_identifiers[execution_key] = identifier

    def unregister_run(self, execution_key: str) -> None:
        self._node_start_times.pop(execution_key, None)
        self._node_prompts.pop(execution_key, None)
        self._run_identifiers.pop(execution_key, None)
        self._latest_nodes.pop(execution_key, None)

    def failure_node(self, execution_key: str) -> str | None:
        return self._latest_nodes.get(execution_key)

    # -- core mapping --------------------------------------------------------

    def map_event(self, run_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        """Map a LangGraph v2 event to an AgentOS frontend event dict.

        Each branch is wrapped in ``try / except`` so that a single
        unexpected object shape never crashes the whole streaming loop.
        """
        kind = event.get("event", "")
        name = event.get("name", "unknown")
        node_name = extract_node_name(event)

        starts = self._node_start_times.get(run_id, {})
        prompts = self._node_prompts.setdefault(run_id, {})
        identifier = self._run_identifiers.get(run_id, "")
        node_timer_key = f"__node__:{node_name}"

        if kind == "on_chain_start":
            metadata = event.get("metadata") or {}
            if metadata.get("langgraph_node"):
                # Only log the top-level node execution (parent_ids is length 1)
                # to avoid double-logging for internal chains and subgraphs.
                if len(event.get("parent_ids", [])) != 1:
                    return None
                starts[node_timer_key] = time.monotonic()
                self._latest_nodes[run_id] = node_name
                logger.info("Node start node=%s run=%s", node_name, run_id)
                return {
                    "id": event.get("run_id", f"node_start_{time.time_ns()}").strip(),
                    "node_id": node_name,
                    "parent_node_id": "graph",
                    "type": "thought",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"Starting node: {node_name}",
                    "metrics": {"model": "langgraph_node"},
                }
            return None
        elif kind == "on_chain_end":
            metadata = event.get("metadata") or {}
            if metadata.get("langgraph_node") and len(event.get("parent_ids", [])) == 1:
                latency_ms = 0
                start_t = starts.pop(node_timer_key, None)
                if start_t is not None:
                    latency_ms = round((time.monotonic() - start_t) * 1000)
                    budget_sec = self.node_wall_clock_budget_sec
                    if budget_sec is not None and latency_ms > float(budget_sec) * 1000:
                        elapsed_sec = latency_ms / 1000
                        # Log the violation but do NOT raise: the node already
                        # completed successfully and its output is in the graph
                        # state.  Raising here would discard valid work and
                        # crash the streaming loop.  Operators should tighten
                        # the budget or scale compute if this fires frequently.
                        logger.error(
                            "Node wall-clock budget exceeded node=%s elapsed=%.2fs budget=%.2fs run=%s",
                            node_name,
                            elapsed_sec,
                            float(budget_sec),
                            run_id,
                        )
                self._latest_nodes[run_id] = node_name
                output = (event.get("data") or {}).get("output")
                output_text = _truncate(_extract_content(output)) if output is not None else ""
                logger.info("Node end node=%s latency=%dms run=%s", node_name, latency_ms, run_id)
                return {
                    "id": f"{event.get('run_id', 'node_end')}_{time.time_ns()}",
                    "node_id": node_name,
                    "type": "result",
                    "agent": node_name.upper(),
                    "identifier": identifier,
                    "message": f"Completed node: {node_name}",
                    "response": output_text,
                    "metrics": {"model": "langgraph_node", "latency_ms": latency_ms},
                }
            return None
        elif kind == "on_chat_model_start":
            return self._map_llm_start(event, run_id, node_name, starts, prompts, identifier)
        elif kind == "on_tool_start":
            return self._map_tool_start(event, run_id, name, node_name, identifier)
        elif kind == "on_tool_end":
            return self._map_tool_end(event, run_id, name, node_name, identifier)
        elif kind == "on_chat_model_end":
            return self._map_llm_end(event, run_id, node_name, starts, prompts, identifier)

        return None

    # -- per-event-kind handlers (private) -----------------------------------

    @staticmethod
    def _map_llm_start(
        event: dict[str, Any],
        run_id: str,
        node_name: str,
        starts: dict[str, float],
        prompts: dict[str, str],
        identifier: str,
    ) -> dict[str, Any]:
        try:
            starts[node_name] = time.monotonic()

            data = event.get("data") or {}
            full_prompt = ""
            for source in (
                data.get("messages"),
                (data.get("input") or {}).get("messages")
                if isinstance(data.get("input"), dict)
                else None,
                data.get("input") if isinstance(data.get("input"), (list, tuple)) else None,
                (data.get("kwargs") or {}).get("messages"),
            ):
                if source:
                    full_prompt = _extract_all_messages_content(source)
                    if full_prompt:
                        break

            if not full_prompt:
                raw_dump = str(data)[:_MAX_FULL_LEN]
                if raw_dump and raw_dump != "{}":
                    full_prompt = f"[raw event data] {raw_dump}"

            prompt_snippet = (
                _truncate(full_prompt.replace("\n", " "), _MAX_CONTENT_LEN) if full_prompt else ""
            )

            prompts[node_name] = full_prompt
            model = _extract_model(event)

            logger.info("LLM start node=%s model=%s run=%s", node_name, model, run_id)

            return {
                "id": event.get("run_id", f"thought_{time.time_ns()}").strip(),
                "node_id": node_name,
                "parent_node_id": "start",
                "type": "thought",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": f"Prompting {model}…"
                + (f" | {prompt_snippet}" if prompt_snippet else ""),
                "prompt": full_prompt,
                "metrics": {"model": model},
            }
        except Exception:
            logger.exception("Error mapping on_chat_model_start run=%s", run_id)
            return {
                "id": f"thought_err_{time.time_ns()}",
                "node_id": node_name,
                "type": "thought",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": "Prompting LLM… (event parse error)",
                "prompt": "",
                "metrics": {},
            }

    @staticmethod
    def _map_tool_start(
        event: dict[str, Any],
        run_id: str,
        name: str,
        node_name: str,
        identifier: str,
    ) -> dict[str, Any] | None:
        try:
            full_input = ""
            tool_input = ""
            inp = (event.get("data") or {}).get("input")
            if inp:
                full_input = str(inp)[:_MAX_FULL_LEN]
                tool_input = _truncate(str(inp))

            service = TOOL_SERVICE_MAP.get(name, "")

            logger.info(
                "Tool start tool=%s service=%s node=%s run=%s", name, service, node_name, run_id
            )

            return {
                "id": event.get("run_id", f"tool_{time.time_ns()}").strip(),
                "node_id": f"tool_{name}",
                "parent_node_id": node_name,
                "type": "tool",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": f"▶ Tool: {name}" + (f" | {tool_input}" if tool_input else ""),
                "prompt": full_input,
                "service": service,
                "status": "running",
                "metrics": {},
            }
        except Exception:
            logger.exception("Error mapping on_tool_start run=%s", run_id)
            return None

    @staticmethod
    def _map_tool_end(
        event: dict[str, Any],
        run_id: str,
        name: str,
        node_name: str,
        identifier: str,
    ) -> dict[str, Any] | None:
        try:
            full_output = ""
            tool_output = ""
            is_error = False
            error_message = ""
            graceful = False
            out = (event.get("data") or {}).get("output")
            if out is not None:
                raw = _extract_content(out)
                full_output = raw[:_MAX_FULL_LEN]
                tool_output = _truncate(raw)
                if raw.startswith("Error") or raw.startswith("Error calling "):
                    is_error = True
                    error_message = raw[:500]
                raw_lower = raw.lower()
                if any(kw in raw_lower for kw in _GRACEFUL_SKIP_KEYWORDS):
                    graceful = True
            evt_status = (event.get("data") or {}).get("status")
            if evt_status == "error":
                is_error = True
                if not error_message:
                    error_message = tool_output or "Unknown tool error"

            service = TOOL_SERVICE_MAP.get(name, "")
            status = "error" if is_error else ("graceful_skip" if graceful else "success")
            icon = "✗" if is_error else ("⚠" if graceful else "✓")

            logger.info(
                "Tool end tool=%s status=%s node=%s run=%s",
                name,
                status,
                node_name,
                run_id,
            )

            return {
                "id": f"{event.get('run_id', 'tool_end')}_{time.time_ns()}",
                "node_id": f"tool_{name}",
                "parent_node_id": node_name,
                "type": "tool_result",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": f"{icon} Tool result: {name}"
                + (f" | {tool_output}" if tool_output else ""),
                "response": full_output,
                "service": service,
                "status": status,
                "error": error_message if is_error else None,
                "metrics": {},
            }
        except Exception:
            logger.exception("Error mapping on_tool_end run=%s", run_id)
            return None

    @staticmethod
    def _map_llm_end(
        event: dict[str, Any],
        run_id: str,
        node_name: str,
        starts: dict[str, float],
        prompts: dict[str, str],
        identifier: str,
    ) -> dict[str, Any]:
        try:
            output = (event.get("data") or {}).get("output")
            usage: dict[str, Any] = {}
            model = "unknown"
            response_snippet = ""
            full_response = ""

            if output is not None:
                usage_raw = getattr(output, "usage_metadata", None)
                usage = _safe_dict(usage_raw)

                resp_meta = getattr(output, "response_metadata", None)
                resp_dict = _safe_dict(resp_meta)
                if resp_dict:
                    model = resp_dict.get("model_name") or resp_dict.get("model", model)

                raw = _extract_content(output)

                if not raw or raw.startswith("<") or raw == str(output):
                    potential_text = getattr(output, "text", None)
                    if potential_text is None or callable(potential_text):
                        potential_text = ""
                    if not isinstance(potential_text, str):
                        potential_text = str(potential_text)

                    raw = potential_text or (
                        output.get("content", "") if isinstance(output, dict) else ""
                    )

                if not isinstance(raw, str):
                    raw = str(raw) if raw is not None else ""

                if raw:
                    full_response = raw[:_MAX_FULL_LEN]
                    response_snippet = _truncate(raw)

            if model == "unknown":
                model = _extract_model(event)

            latency_ms = 0
            start_t = starts.pop(node_name, None)
            if start_t is not None:
                latency_ms = round((time.monotonic() - start_t) * 1000)

            matched_prompt = prompts.pop(node_name, "")

            tokens_in = usage.get("input_tokens", 0)
            tokens_out = usage.get("output_tokens", 0)

            logger.info(
                "LLM end node=%s model=%s tokens_in=%s tokens_out=%s latency=%dms run=%s",
                node_name,
                model,
                tokens_in or "?",
                tokens_out or "?",
                latency_ms,
                run_id,
            )

            return {
                "id": f"{event.get('run_id', 'result')}_{time.time_ns()}",
                "node_id": node_name,
                "type": "result",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": response_snippet or "Completed.",
                "prompt": matched_prompt,
                "response": full_response,
                "metrics": {
                    "model": model,
                    "tokens_in": tokens_in if isinstance(tokens_in, (int, float)) else 0,
                    "tokens_out": tokens_out if isinstance(tokens_out, (int, float)) else 0,
                    "latency_ms": latency_ms,
                },
            }
        except Exception:
            logger.exception("Error mapping on_chat_model_end run=%s", run_id)
            matched_prompt = prompts.pop(node_name, "")
            return {
                "id": f"result_err_{time.time_ns()}",
                "node_id": node_name,
                "type": "result",
                "agent": node_name.upper(),
                "identifier": identifier,
                "message": "Completed (event parse error).",
                "prompt": matched_prompt,
                "response": "",
                "metrics": {"model": "unknown", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0},
            }
