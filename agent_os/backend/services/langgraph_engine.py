import asyncio
import logging
import time
from typing import Dict, Any, AsyncGenerator
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.scanner_graph import ScannerGraph
from tradingagents.graph.portfolio_graph import PortfolioGraph
from tradingagents.default_config import DEFAULT_CONFIG

logger = logging.getLogger("agent_os.engine")

# Maximum characters of prompt/response content to include in the short message
_MAX_CONTENT_LEN = 300

# Maximum characters of prompt/response for the full fields (generous limit)
_MAX_FULL_LEN = 50_000


class LangGraphEngine:
    """Orchestrates LangGraph pipeline executions and streams events."""

    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self.active_runs: Dict[str, Dict[str, Any]] = {}
        # Track node start times per run so we can compute latency
        self._node_start_times: Dict[str, Dict[str, float]] = {}
        # Track the last prompt per node so we can attach it to result events
        self._node_prompts: Dict[str, Dict[str, str]] = {}

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
        self._node_prompts.pop(run_id, None)
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
            initial_state,
            version="v2",
            config={"recursion_limit": graph_wrapper.propagator.max_recur_limit},
        ):
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        self._node_prompts.pop(run_id, None)
        logger.info("Completed PIPELINE run=%s", run_id)

    async def run_portfolio(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the portfolio manager workflow and stream events."""
        date = params.get("date", time.strftime("%Y-%m-%d"))
        portfolio_id = params.get("portfolio_id", "main_portfolio")

        logger.info(
            "Starting PORTFOLIO run=%s portfolio=%s date=%s",
            run_id, portfolio_id, date,
        )
        yield self._system_log(
            f"Starting portfolio manager for {portfolio_id} on {date}"
        )

        portfolio_graph = PortfolioGraph(config=self.config)

        initial_state = {
            "portfolio_id": portfolio_id,
            "scan_date": date,
            "messages": [],
        }

        self._node_start_times[run_id] = {}

        async for event in portfolio_graph.graph.astream_events(
            initial_state, version="v2"
        ):
            mapped = self._map_langgraph_event(run_id, event)
            if mapped:
                yield mapped

        self._node_start_times.pop(run_id, None)
        self._node_prompts.pop(run_id, None)
        logger.info("Completed PORTFOLIO run=%s", run_id)

    async def run_auto(
        self, run_id: str, params: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run the full auto pipeline: scan → pipeline → portfolio."""
        date = params.get("date", time.strftime("%Y-%m-%d"))

        logger.info("Starting AUTO run=%s date=%s", run_id, date)
        yield self._system_log(f"Starting full auto workflow for {date}")

        # Phase 1: Market scan
        yield self._system_log("Phase 1/3: Running market scan…")
        async for evt in self.run_scan(f"{run_id}_scan", {"date": date}):
            yield evt

        # Phase 2: Pipeline analysis (default ticker for now)
        ticker = params.get("ticker", "AAPL")
        yield self._system_log(f"Phase 2/3: Running analysis pipeline for {ticker}…")
        async for evt in self.run_pipeline(
            f"{run_id}_pipeline", {"ticker": ticker, "date": date}
        ):
            yield evt

        # Phase 3: Portfolio management
        yield self._system_log("Phase 3/3: Running portfolio manager…")
        async for evt in self.run_portfolio(
            f"{run_id}_portfolio", {"date": date, **params}
        ):
            yield evt

        logger.info("Completed AUTO run=%s", run_id)

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
        # Handle cases where .content might be a method instead of a property
        if content is not None and callable(content):
            content = None
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

    def _extract_all_messages_content(self, messages: Any) -> str:
        """Extract text from ALL messages in a LangGraph messages payload.

        Returns the concatenated content of every message so the user can
        inspect the full prompt that was sent to the LLM.

        Handles several structures observed across LangChain / LangGraph versions:
        - flat list of message objects  ``[SystemMessage, HumanMessage, ...]``
        - list-of-lists (batched)       ``[[SystemMessage, HumanMessage, ...]]``
        - list of plain dicts            ``[{"role": "system", "content": "..."}]``
        - tuple wrapper                  ``([SystemMessage, ...],)``
        """
        if not messages:
            return ""

        # Unwrap single-element tuple / list-of-lists
        items: list = messages if isinstance(messages, list) else list(messages)
        if items and isinstance(items[0], (list, tuple)):
            items = list(items[0])

        parts: list[str] = []
        for msg in items:
            # LangChain message objects have .content and .type
            content = getattr(msg, "content", None)
            role = getattr(msg, "type", None)
            # Plain-dict messages (e.g. {"role": "user", "content": "..."})
            if content is None and isinstance(msg, dict):
                content = msg.get("content", "")
                role = msg.get("role") or msg.get("type") or "unknown"
            if role is None:
                role = "unknown"
            text = str(content) if content is not None else str(msg)
            parts.append(f"[{role}] {text}")

        return "\n\n".join(parts)

    def _extract_model(self, event: Dict[str, Any]) -> str:
        """Best-effort extraction of the model name from a LangGraph event."""
        data = event.get("data") or {}

        # 1. invocation_params (standard LangChain)
        inv = data.get("invocation_params") or {}
        model = inv.get("model_name") or inv.get("model") or ""
        if model:
            return model

        # 2. Serialized kwargs (OpenRouter / ChatOpenAI)
        serialized = event.get("serialized") or data.get("serialized") or {}
        kwargs = serialized.get("kwargs") or {}
        model = kwargs.get("model_name") or kwargs.get("model") or ""
        if model:
            return model

        # 3. metadata.ls_model_name (LangSmith tracing)
        metadata = event.get("metadata") or {}
        model = metadata.get("ls_model_name") or ""
        if model:
            return model

        return "unknown"

    @staticmethod
    def _safe_dict(obj: object) -> Dict[str, Any]:
        """Return *obj* if it is a dict, otherwise an empty dict.

        Many LangChain message objects expose dict-like metadata
        properties (``usage_metadata``, ``response_metadata``) but some
        providers return non-dict types (e.g. bound methods, None, or
        custom objects).  This helper guarantees safe ``.get()`` calls.
        """
        return obj if isinstance(obj, dict) else {}

    def _map_langgraph_event(
        self, run_id: str, event: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Map LangGraph v2 events to AgentOS frontend contract.

        Each branch is wrapped in a ``try / except`` so that a single
        unexpected object shape never crashes the whole streaming loop.
        """
        kind = event.get("event", "")
        name = event.get("name", "unknown")
        node_name = self._extract_node_name(event)

        starts = self._node_start_times.get(run_id, {})
        prompts = self._node_prompts.setdefault(run_id, {})

        # ------ LLM start ------
        if kind == "on_chat_model_start":
            try:
                starts[node_name] = time.monotonic()

                data = event.get("data") or {}

                # Extract the full prompt being sent to the LLM.
                # Try multiple paths observed in different LangChain versions:
                #   1. data.messages  (most common)
                #   2. data.input.messages  (newer LangGraph)
                #   3. data.input  (if it's a list of messages itself)
                #   4. data.kwargs.messages  (some providers)
                full_prompt = ""
                for source in (
                    data.get("messages"),
                    (data.get("input") or {}).get("messages") if isinstance(data.get("input"), dict) else None,
                    data.get("input") if isinstance(data.get("input"), (list, tuple)) else None,
                    (data.get("kwargs") or {}).get("messages"),
                ):
                    if source:
                        full_prompt = self._extract_all_messages_content(source)
                        if full_prompt:
                            break

                # If all structured extractions failed, dump a raw preview
                if not full_prompt:
                    raw_dump = str(data)[:_MAX_FULL_LEN]
                    if raw_dump and raw_dump != "{}":
                        full_prompt = f"[raw event data] {raw_dump}"

                prompt_snippet = self._truncate(
                    full_prompt.replace("\n", " "), _MAX_CONTENT_LEN
                ) if full_prompt else ""

                # Remember the full prompt so we can attach it to the result event
                prompts[node_name] = full_prompt

                model = self._extract_model(event)

                logger.info(
                    "LLM start node=%s model=%s run=%s", node_name, model, run_id
                )

                return {
                    "id": event.get("run_id", f"thought_{time.time_ns()}"),
                    "node_id": node_name,
                    "parent_node_id": "start",
                    "type": "thought",
                    "agent": node_name.upper(),
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
                    "message": f"Prompting LLM… (event parse error)",
                    "prompt": "",
                    "metrics": {},
                }

        # ------ Tool call ------
        elif kind == "on_tool_start":
            try:
                full_input = ""
                tool_input = ""
                inp = (event.get("data") or {}).get("input")
                if inp:
                    full_input = str(inp)[:_MAX_FULL_LEN]
                    tool_input = self._truncate(str(inp))

                logger.info("Tool start tool=%s node=%s run=%s", name, node_name, run_id)

                return {
                    "id": event.get("run_id", f"tool_{time.time_ns()}"),
                    "node_id": f"tool_{name}",
                    "parent_node_id": node_name,
                    "type": "tool",
                    "agent": node_name.upper(),
                    "message": f"▶ Tool: {name}"
                    + (f" | {tool_input}" if tool_input else ""),
                    "prompt": full_input,
                    "metrics": {},
                }
            except Exception:
                logger.exception("Error mapping on_tool_start run=%s", run_id)
                return None

        # ------ Tool result ------
        elif kind == "on_tool_end":
            try:
                full_output = ""
                tool_output = ""
                out = (event.get("data") or {}).get("output")
                if out is not None:
                    raw = self._extract_content(out)
                    full_output = raw[:_MAX_FULL_LEN]
                    tool_output = self._truncate(raw)

                logger.info("Tool end tool=%s node=%s run=%s", name, node_name, run_id)

                return {
                    "id": f"{event.get('run_id', 'tool_end')}_{time.time_ns()}",
                    "node_id": f"tool_{name}",
                    "parent_node_id": node_name,
                    "type": "tool_result",
                    "agent": node_name.upper(),
                    "message": f"✓ Tool result: {name}"
                    + (f" | {tool_output}" if tool_output else ""),
                    "response": full_output,
                    "metrics": {},
                }
            except Exception:
                logger.exception("Error mapping on_tool_end run=%s", run_id)
                return None

        # ------ LLM end ------
        elif kind == "on_chat_model_end":
            try:
                output = (event.get("data") or {}).get("output")
                usage: Dict[str, Any] = {}
                model = "unknown"
                response_snippet = ""
                full_response = ""

                if output is not None:
                    # Safely extract usage & response metadata (must be dicts)
                    usage_raw = getattr(output, "usage_metadata", None)
                    usage = self._safe_dict(usage_raw)

                    resp_meta = getattr(output, "response_metadata", None)
                    resp_dict = self._safe_dict(resp_meta)
                    if resp_dict:
                        model = resp_dict.get("model_name") or resp_dict.get("model", model)

                    # Extract the response text – handle message objects and dicts
                    raw = self._extract_content(output)

                    # If .content was empty or the repr of the whole object, try harder
                    if not raw or raw.startswith("<") or raw == str(output):
                        # Some providers wrap in .text or .message
                        potential_text = getattr(output, "text", None)
                        if potential_text is None or callable(potential_text):
                            potential_text = ""
                        if not isinstance(potential_text, str):
                            potential_text = str(potential_text)

                        raw = (
                            potential_text
                            or (output.get("content", "") if isinstance(output, dict) else "")
                        )

                    # Ensure raw is always a string before slicing
                    if not isinstance(raw, str):
                        raw = str(raw) if raw is not None else ""

                    if raw:
                        full_response = raw[:_MAX_FULL_LEN]
                        response_snippet = self._truncate(raw)

                # Fall back to event-level model extraction
                if model == "unknown":
                    model = self._extract_model(event)

                latency_ms = 0
                start_t = starts.pop(node_name, None)
                if start_t is not None:
                    latency_ms = round((time.monotonic() - start_t) * 1000)

                # Retrieve the prompt that started this LLM call
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
                    "message": "Completed (event parse error).",
                    "prompt": matched_prompt,
                    "response": "",
                    "metrics": {"model": "unknown", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0},
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

    async def run_portfolio_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_portfolio(run_id, params):
            pass

    async def run_auto_background(self, run_id: str, params: Dict[str, Any]):
        async for _ in self.run_auto(run_id, params):
            pass
