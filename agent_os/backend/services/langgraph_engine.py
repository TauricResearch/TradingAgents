import asyncio
import logging
import time
from typing import Dict, Any, AsyncGenerator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger("agent_os.engine")

# Maximum characters of prompt/response content to include in streamed events
_MAX_CONTENT_LEN = 300


class LangGraphEngine:
    """Orchestrates LangGraph pipeline executions and streams events."""

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.active_runs: Dict[str, Dict[str, Any]] = {}
        # Track node start times per run so we can compute latency
        self._node_start_times: Dict[str, Dict[str, float]] = {}

    # ------------------------------------------------------------------
    # Run helpers
    # ------------------------------------------------------------------

    async def run_scan(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the 3-phase macro scanner and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))

        scanner = ScannerGraph(config=self.config)

        logger.info("Starting SCAN run=%s date=%s", run_id, date)
        yield self._system_log(f"Starting macro scan for {date}")

        initial_state = {
            "scan_date": date,
            "messages": [],
            "geopolitical_report": "",
            "market_movers_report": "",
            "sector_performance_report": "",
            "industry_deep_dive_report": "",
            "macro_scan_summary": "",
            "sender": "",
        }

        self._node_start_times[run_id] = {}

        async for event in scanner.graph.astream_events(initial_state, version="v2"):
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        logger.info("Completed SCAN run=%s", run_id)

    async def run_pipeline(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run per-ticker analysis pipeline and stream events."""
        ticker = params.get("ticker", "AAPL")
        date = params.get("date", time.strftime("%Y-%m-%d"))
        analysts = params.get("analysts", ["market", "news", "fundamentals"])

        logger.info(
            "Starting PIPELINE run=%s ticker=%s date=%s", run_id, ticker, date
        )
        yield self._system_log(f"Starting analysis pipeline for {ticker} on {date}")

        graph_wrapper = TradingAgentsGraph(
            selected_analysts=analysts,
            config=self.config,
            debug=True,
        )

        initial_state = graph_wrapper.propagator.create_initial_state(ticker, date)

        self._node_start_times[run_id] = {}

        async for event in graph_wrapper.graph.astream_events(
            initial_state, version="v2"
        ):
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        logger.info("Completed PIPELINE run=%s", run_id)

    # ------------------------------------------------------------------
    # Event mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_node_name(event: Dict[str, Any]) -> str:
        """Extract the LangGraph node name from event metadata or tags."""
        # Prefer metadata.langgraph_node (most reliable)
        metadata = event.get("metadata") or {}
        node = metadata.get("langgraph_node")
        if node:
            return node

        # Fallback: tags like "graph:node:<name>"
        for tag in event.get("tags", []):
            if tag.startswith("graph:node:"):
                return tag.split(":", 2)[-1]

        # Last resort: the event name itself
        return event.get("name", "unknown")

    @staticmethod
    def _extract_content(obj: object) -> str:
        """Safely extract text content from a LangChain message or plain object."""
        content = getattr(obj, "content", None)
        return str(content) if content is not None else str(obj)

    @staticmethod
    def _truncate(text: str, max_len: int = _MAX_CONTENT_LEN) -> str:
        if len(text) <= max_len:
            return text
        return text[:max_len] + "…"

    @staticmethod
    def _system_log(message: str) -> Dict[str, Any]:
        """Create a log-type event for informational messages."""
        return {
            "id": f"log_{time.time_ns()}",
            "node_id": "__system__",
            "type": "log",
            "agent": "SYSTEM",
            "message": message,
            "metrics": {},
        }

    @staticmethod
    def _first_message_content(messages: Any) -> str:
        """Extract content from the first message in a LangGraph messages payload.

        ``messages`` may be a flat list of message objects or a list-of-lists.
        Returns an empty string when extraction fails.
        """
        if not isinstance(messages, list) or not messages:
            return ""
        first_item = messages[0]
        # Handle list-of-lists (nested batches)
        if isinstance(first_item, list):
            if not first_item:
                return ""
            first_item = first_item[0]
        content = getattr(first_item, "content", None)
        return str(content) if content is not None else str(first_item)

    def _map_langgraph_event(
        self, run_id: str, event: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Map LangGraph v2 events to AgentOS frontend contract."""
        kind = event.get("event", "")
        name = event.get("name", "unknown")
        node_name = self._extract_node_name(event)

        starts = self._node_start_times.get(run_id, {})

        # ------ LLM start ------
        if kind == "on_chat_model_start":
            starts[node_name] = time.monotonic()

            # Extract the prompt being sent to the LLM
            prompt_snippet = ""
            messages = (event.get("data") or {}).get("messages")
            if messages:
                raw = self._first_message_content(messages)
                if raw:
                    prompt_snippet = self._truncate(raw)

            model = "unknown"
            inv_params = (event.get("data") or {}).get("invocation_params") or {}
            model = inv_params.get("model_name") or inv_params.get("model") or "unknown"

            logger.info(
                "LLM start node=%s model=%s run=%s", node_name, model, run_id
            )

            return {
                "id": event["run_id"],
                "node_id": node_name,
                "parent_node_id": "start",
                "type": "thought",
                "agent": node_name.upper(),
                "message": f"Prompting {model}…"
                + (f" | {prompt_snippet}" if prompt_snippet else ""),
                "metrics": {"model": model},
            }

        # ------ Tool call ------
        elif kind == "on_tool_start":
            tool_input = ""
            inp = (event.get("data") or {}).get("input")
            if inp:
                tool_input = self._truncate(str(inp))

            logger.info("Tool start tool=%s node=%s run=%s", name, node_name, run_id)

            return {
                "id": event["run_id"],
                "node_id": f"tool_{name}",
                "parent_node_id": node_name,
                "type": "tool",
                "agent": node_name.upper(),
                "message": f"▶ Tool: {name}"
                + (f" | {tool_input}" if tool_input else ""),
                "metrics": {},
            }

        # ------ Tool result ------
        elif kind == "on_tool_end":
            tool_output = ""
            out = (event.get("data") or {}).get("output")
            if out is not None:
                tool_output = self._truncate(self._extract_content(out))

            logger.info("Tool end tool=%s node=%s run=%s", name, node_name, run_id)

            return {
                "id": f"{event['run_id']}_tool_end",
                "node_id": f"tool_{name}",
                "parent_node_id": node_name,
                "type": "tool",
                "agent": node_name.upper(),
                "message": f"✓ Tool result: {name}"
                + (f" | {tool_output}" if tool_output else ""),
                "metrics": {},
            }

        # ------ LLM end ------
        elif kind == "on_chat_model_end":
            output = (event.get("data") or {}).get("output")
            usage: Dict[str, Any] = {}
            model = "unknown"
            response_snippet = ""

            if output is not None:
                if hasattr(output, "usage_metadata") and output.usage_metadata:
                    usage = output.usage_metadata
                if hasattr(output, "response_metadata") and output.response_metadata:
                    model = output.response_metadata.get("model_name", model)
                raw = self._extract_content(output)
                if raw:
                    response_snippet = self._truncate(raw)

            latency_ms = 0
            start_t = starts.pop(node_name, None)
            if start_t is not None:
                latency_ms = round((time.monotonic() - start_t) * 1000)

            logger.info(
                "LLM end node=%s model=%s tokens_in=%s tokens_out=%s latency=%dms run=%s",
                node_name,
                model,
                usage.get("input_tokens", "?"),
                usage.get("output_tokens", "?"),
                latency_ms,
                run_id,
            )

            return {
                "id": f"{event['run_id']}_end",
                "node_id": node_name,
                "type": "result",
                "agent": node_name.upper(),
                "message": response_snippet or "Completed.",
                "metrics": {
                    "model": model,
                    "tokens_in": usage.get("input_tokens", 0),
                    "tokens_out": usage.get("output_tokens", 0),
                    "latency_ms": latency_ms,
                },
            }

        return None

    # ------------------------------------------------------------------
    # Background task wrappers
    # ------------------------------------------------------------------

    async def run_scan_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_scan(run_id, params):
            pass

    async def run_pipeline_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_pipeline(run_id, params):
            pass
