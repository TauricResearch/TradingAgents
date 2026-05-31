import json
import math
import time
from datetime import datetime
from typing import Any, Iterator

from web.config_builder import build_web_config
from web.models import AnalysisRequest, StreamEvent


ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_MAP = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}

FIXED_AGENTS = (
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Neutral Analyst",
    "Conservative Analyst",
    "Portfolio Manager",
)

REPORT_SECTIONS = {
    "market_report": "market",
    "sentiment_report": "social",
    "news_report": "news",
    "fundamentals_report": "fundamentals",
    "investment_plan": None,
    "trader_investment_plan": None,
    "final_trade_decision": None,
}


def _json_safe(value: Any) -> Any:
    """Return a recursively JSON-serializable representation."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _content_string(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        stripped = content.strip()
        return stripped or None
    if isinstance(content, dict):
        text = content.get("text")
        return _content_string(text)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = _content_string(item.get("text"))
            else:
                text = _content_string(item)
            if text:
                parts.append(text)
        return " ".join(parts) if parts else None
    return str(content).strip() or None


def _classify_message_type(message: Any) -> tuple[str, str | None]:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    content = _content_string(getattr(message, "content", None))

    if isinstance(message, HumanMessage):
        if content and content.strip() == "Continue":
            return "Control", content
        return "User", content
    if isinstance(message, ToolMessage):
        return "Data", content
    if isinstance(message, AIMessage):
        return "Agent", content
    return "System", content


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def sse(event: StreamEvent) -> str:
    payload = _json_safe(event.model_dump())
    return f"data: {json.dumps(payload, ensure_ascii=False, allow_nan=False)}\n\n"


def _event(event_type: str, payload: dict) -> str:
    return sse(StreamEvent(type=event_type, payload=_json_safe(payload)))


class _StreamAccumulator:
    def __init__(self, selected_analysts: list[str]) -> None:
        self.selected_analysts = selected_analysts
        self.processed_message_ids: set[str] = set()
        self.agent_status = {
            ANALYST_AGENT_NAMES[analyst]: "pending"
            for analyst in selected_analysts
            if analyst in ANALYST_AGENT_NAMES
        }
        self.agent_status.update({agent: "pending" for agent in FIXED_AGENTS})
        self.report_sections = {
            section: None
            for section, analyst in REPORT_SECTIONS.items()
            if analyst is None or analyst in selected_analysts
        }
        self._previous_message_signatures: list[str] = []

    def _message_signature(self, message: Any) -> str:
        msg_id = getattr(message, "id", None)
        if msg_id is not None:
            return f"id:{msg_id}"

        return "fallback:" + json.dumps(
            _json_safe(
                {
                    "class": message.__class__.__name__,
                    "content": getattr(message, "content", None),
                    "tool_call_id": getattr(message, "tool_call_id", None),
                    "tool_calls": getattr(message, "tool_calls", None),
                }
            ),
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )

    def new_message_start_index(self, messages: list[Any]) -> int:
        signatures = [self._message_signature(message) for message in messages]
        previous = self._previous_message_signatures
        if len(signatures) >= len(previous) and signatures[: len(previous)] == previous:
            start_index = len(previous)
        else:
            max_overlap = min(len(previous), len(signatures))
            start_index = 0
            for overlap in range(max_overlap, 0, -1):
                if previous[-overlap:] == signatures[:overlap]:
                    start_index = overlap
                    break
        self._previous_message_signatures = signatures
        return start_index

    def is_new_id_message(self, message: Any) -> bool:
        msg_id = getattr(message, "id", None)
        if msg_id is None:
            return True
        key = f"id:{msg_id}"
        if key in self.processed_message_ids:
            return False
        self.processed_message_ids.add(key)
        return True

    def update_agent_status(self, agent: str, status: str) -> str | None:
        if agent not in self.agent_status:
            return None
        if self.agent_status[agent] == status:
            return None
        self.agent_status[agent] = status
        return _event(
            "agent_status",
            {"agent": agent, "status": status, "statuses": self.agent_status, "agents": self.agent_status},
        )

    def update_report_section(self, section: str, content: Any) -> str | None:
        if section not in self.report_sections:
            return None
        self.report_sections[section] = content
        return _event(
            "report_section",
            {"section": section, "content": _json_safe(content)},
        )

    def emit_analyst_statuses(
        self,
        chunk: dict[str, Any],
        wall_time_tracker: Any,
        sync_analyst_tracker_from_chunk: Any,
    ) -> list[str]:
        events: list[str] = []
        sync_analyst_tracker_from_chunk(wall_time_tracker, chunk)

        found_active = False
        for analyst_key in ANALYST_ORDER:
            if analyst_key not in self.selected_analysts:
                continue

            agent_name = ANALYST_AGENT_NAMES[analyst_key]
            report_key = ANALYST_REPORT_MAP[analyst_key]

            if chunk.get(report_key):
                report_event = self.update_report_section(report_key, chunk[report_key])
                if report_event is not None:
                    events.append(report_event)

            if self.report_sections.get(report_key):
                status = "completed"
            elif not found_active:
                status = "in_progress"
                found_active = True
            else:
                status = "pending"

            status_event = self.update_agent_status(agent_name, status)
            if status_event is not None:
                events.append(status_event)

        if not found_active and self.selected_analysts:
            status_event = self.update_agent_status("Bull Researcher", "in_progress")
            if status_event is not None:
                events.append(status_event)

        return events

    def complete_all_agents(self) -> list[str]:
        events: list[str] = []
        for agent in list(self.agent_status):
            status_event = self.update_agent_status(agent, "completed")
            if status_event is not None:
                events.append(status_event)
        return events


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _stats_payload(
    stats_handler: Any,
    start_time: float,
    wall_time_tracker: Any,
) -> dict[str, Any]:
    stats = stats_handler.get_stats()
    stats["elapsed_seconds"] = round(time.time() - start_time, 3)
    stats["analyst_wall_times"] = wall_time_tracker.get_wall_times()
    stats["analyst_wall_time_summary"] = wall_time_tracker.format_summary()
    return _json_safe(stats)


def _tool_call_parts(tool_call: Any) -> tuple[str, Any]:
    if isinstance(tool_call, dict):
        return str(tool_call.get("name", "")), tool_call.get("args", {})
    return str(getattr(tool_call, "name", "")), getattr(tool_call, "args", {})


def _emit_research_team_events(
    accumulator: _StreamAccumulator,
    debate_state: dict[str, Any],
) -> list[str]:
    events: list[str] = []
    bull_hist = _clean_text(debate_state.get("bull_history"))
    bear_hist = _clean_text(debate_state.get("bear_history"))
    judge = _clean_text(debate_state.get("judge_decision"))

    if bull_hist or bear_hist:
        for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
            status_event = accumulator.update_agent_status(agent, "in_progress")
            if status_event is not None:
                events.append(status_event)
    report_parts = []
    if bull_hist:
        report_parts.append(f"### Bull Researcher Analysis\n{bull_hist}")
    if bear_hist:
        report_parts.append(f"### Bear Researcher Analysis\n{bear_hist}")
    if judge:
        report_parts.append(f"### Research Manager Decision\n{judge}")
    if report_parts:
        report_event = accumulator.update_report_section(
            "investment_plan", "\n\n".join(report_parts)
        )
        if report_event is not None:
            events.append(report_event)

    if judge:
        for agent in ("Bull Researcher", "Bear Researcher", "Research Manager"):
            status_event = accumulator.update_agent_status(agent, "completed")
            if status_event is not None:
                events.append(status_event)
        status_event = accumulator.update_agent_status("Trader", "in_progress")
        if status_event is not None:
            events.append(status_event)

    return events


def _emit_risk_team_events(
    accumulator: _StreamAccumulator,
    risk_state: dict[str, Any],
) -> list[str]:
    events: list[str] = []
    risk_sections = (
        ("aggressive_history", "Aggressive Analyst", "### Aggressive Analyst Analysis"),
        ("conservative_history", "Conservative Analyst", "### Conservative Analyst Analysis"),
        ("neutral_history", "Neutral Analyst", "### Neutral Analyst Analysis"),
    )

    report_parts = []
    for state_key, agent, heading in risk_sections:
        history = _clean_text(risk_state.get(state_key))
        if not history:
            continue
        if accumulator.agent_status.get(agent) != "completed":
            status_event = accumulator.update_agent_status(agent, "in_progress")
            if status_event is not None:
                events.append(status_event)
        report_parts.append(f"{heading}\n{history}")

    judge = _clean_text(risk_state.get("judge_decision"))
    if judge:
        report_parts.append(f"### Portfolio Manager Decision\n{judge}")

    if report_parts:
        report_event = accumulator.update_report_section(
            "final_trade_decision", "\n\n".join(report_parts)
        )
        if report_event is not None:
            events.append(report_event)

    if judge and accumulator.agent_status.get("Portfolio Manager") != "completed":
        status_event = accumulator.update_agent_status("Portfolio Manager", "in_progress")
        if status_event is not None:
            events.append(status_event)
        for agent in (
            "Aggressive Analyst",
            "Conservative Analyst",
            "Neutral Analyst",
            "Portfolio Manager",
        ):
            status_event = accumulator.update_agent_status(agent, "completed")
            if status_event is not None:
                events.append(status_event)

    return events


def stream_analysis(request: AnalysisRequest, run_id: str) -> Iterator[str]:
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.graph.checkpointer import (
        checkpoint_step,
        clear_checkpoint,
        get_checkpointer,
        thread_id,
    )
    from tradingagents.graph.analyst_execution import (
        AnalystWallTimeTracker,
        build_analyst_execution_plan,
        get_initial_analyst_node,
        sync_analyst_tracker_from_chunk,
    )
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config, selected_analyst_keys, asset_type = build_web_config(request)
    stats_handler = StatsCallbackHandler()
    analyst_execution_plan = build_analyst_execution_plan(
        selected_analyst_keys,
        concurrency_limit=config["analyst_concurrency_limit"],
    )
    analyst_wall_time_tracker = AnalystWallTimeTracker(analyst_execution_plan)
    graph = TradingAgentsGraph(
        selected_analyst_keys,
        config=config,
        debug=True,
        callbacks=[stats_handler],
    )
    accumulator = _StreamAccumulator(selected_analyst_keys)
    start_time = time.time()
    checkpointer_ctx = None

    yield _event(
        "run_started",
        {
            "run_id": run_id,
            "ticker": request.ticker,
            "analysis_date": request.analysis_date,
            "asset_type": asset_type,
            "analysts": selected_analyst_keys,
            "research_depth": request.research_depth,
            "llm_provider": request.llm_provider.lower(),
            "checkpoint_enabled": config.get("checkpoint_enabled", False),
            "agents": accumulator.agent_status,
            "statuses": accumulator.agent_status,
        },
    )
    yield _event(
        "message",
        {
            "timestamp": _timestamp(),
            "message_type": "System",
            "content": f"Selected ticker: {request.ticker}",
        },
    )
    yield _event(
        "message",
        {
            "timestamp": _timestamp(),
            "message_type": "System",
            "content": f"Detected asset type: {asset_type}",
        },
    )

    first_analyst = get_initial_analyst_node(analyst_execution_plan)
    analyst_wall_time_tracker.mark_started(selected_analyst_keys[0])
    first_status_event = accumulator.update_agent_status(first_analyst, "in_progress")
    if first_status_event is not None:
        yield first_status_event

    graph.ticker = request.ticker
    graph._resolve_pending_entries(request.ticker)
    if config.get("checkpoint_enabled"):
        checkpointer_ctx = get_checkpointer(config["data_cache_dir"], request.ticker)
        saver = checkpointer_ctx.__enter__()
        graph.graph = graph.workflow.compile(checkpointer=saver)
        step = checkpoint_step(config["data_cache_dir"], request.ticker, request.analysis_date)
        yield _event(
            "message",
            {
                "timestamp": _timestamp(),
                "message_type": "System",
                "content": (
                    f"Resuming from step {step} for {request.ticker} on {request.analysis_date}"
                    if step is not None
                    else f"Starting fresh for {request.ticker} on {request.analysis_date}"
                ),
            },
        )

    past_context = graph.memory_log.get_past_context(request.ticker)
    init_agent_state = graph.propagator.create_initial_state(
        request.ticker,
        request.analysis_date,
        asset_type=asset_type,
        past_context=past_context,
    )
    args = graph.propagator.get_graph_args(callbacks=[stats_handler])
    if config.get("checkpoint_enabled"):
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id(
            request.ticker, request.analysis_date
        )

    trace: list[dict[str, Any]] = []
    try:
        stream = graph.graph.stream(init_agent_state, **args)
        for chunk in stream:
            yield from _stream_chunk_events(
                chunk,
                accumulator,
                analyst_wall_time_tracker,
                sync_analyst_tracker_from_chunk,
                stats_handler,
                start_time,
            )
            trace.append(chunk)
    finally:
        if checkpointer_ctx is not None:
            checkpointer_ctx.__exit__(None, None, None)
            graph.graph = graph.workflow.compile()

    final_state: dict[str, Any] = {}
    for chunk in trace:
        final_state.update(chunk)

    accumulated_sections = {"investment_plan", "final_trade_decision"}
    for section in accumulator.report_sections:
        if (
            section in final_state
            and not (section in accumulated_sections and accumulator.report_sections[section])
        ):
            report_event = accumulator.update_report_section(section, final_state[section])
            if report_event is not None:
                yield report_event

    for event in accumulator.complete_all_agents():
        yield event

    final_trade_decision = _clean_text(final_state.get("final_trade_decision"))
    decision = graph.process_signal(final_trade_decision)
    graph.curr_state = final_state
    graph._log_state(request.analysis_date, final_state)
    graph.memory_log.store_decision(
        ticker=request.ticker,
        trade_date=request.analysis_date,
        final_trade_decision=final_trade_decision,
    )
    if config.get("checkpoint_enabled"):
        clear_checkpoint(config["data_cache_dir"], request.ticker, request.analysis_date)

    yield _event(
        "message",
        {
            "timestamp": _timestamp(),
            "message_type": "System",
            "content": f"Completed analysis for {request.analysis_date}",
        },
    )
    yield _event("stats", _stats_payload(stats_handler, start_time, analyst_wall_time_tracker))
    yield _event(
        "run_completed",
        {
            "run_id": run_id,
            "ticker": request.ticker,
            "analysis_date": request.analysis_date,
            "decision": decision,
            "reports": accumulator.report_sections,
            "stats": _stats_payload(stats_handler, start_time, analyst_wall_time_tracker),
        },
    )


def _stream_chunk_events(
    chunk: dict[str, Any],
    accumulator: _StreamAccumulator,
    analyst_wall_time_tracker: Any,
    sync_analyst_tracker_from_chunk: Any,
    stats_handler: Any,
    start_time: float,
) -> Iterator[str]:
    messages = list(chunk.get("messages", []))
    new_start_index = accumulator.new_message_start_index(messages)
    for position, message in enumerate(messages):
        if position < new_start_index and getattr(message, "id", None) is None:
            continue
        if not accumulator.is_new_id_message(message):
            continue

        msg_type, content = _classify_message_type(message)
        if content and content.strip():
            yield _event(
                "message",
                {
                    "timestamp": _timestamp(),
                    "message_type": msg_type,
                    "content": content,
                },
            )

        for tool_call in getattr(message, "tool_calls", []) or []:
            tool_name, tool_args = _tool_call_parts(tool_call)
            yield _event(
                "tool_call",
                {
                    "timestamp": _timestamp(),
                    "name": tool_name,
                    "args": _json_safe(tool_args),
                },
            )

    for event in accumulator.emit_analyst_statuses(
        chunk,
        analyst_wall_time_tracker,
        sync_analyst_tracker_from_chunk,
    ):
        yield event

    if chunk.get("investment_debate_state"):
        for event in _emit_research_team_events(
            accumulator,
            chunk["investment_debate_state"],
        ):
            yield event

    if chunk.get("trader_investment_plan"):
        report_event = accumulator.update_report_section(
            "trader_investment_plan", chunk["trader_investment_plan"]
        )
        if report_event is not None:
            yield report_event
        status_event = accumulator.update_agent_status("Trader", "completed")
        if status_event is not None:
            yield status_event
        status_event = accumulator.update_agent_status("Aggressive Analyst", "in_progress")
        if status_event is not None:
            yield status_event

    if chunk.get("risk_debate_state"):
        for event in _emit_risk_team_events(accumulator, chunk["risk_debate_state"]):
            yield event

    yield _event(
        "stats",
        _stats_payload(stats_handler, start_time, analyst_wall_time_tracker),
    )
