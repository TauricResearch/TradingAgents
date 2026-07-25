from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, ToolMessage

from tradingagents.graph.context_compaction import microcompact_tool_messages
from tradingagents.graph.runtime_events import runtime_event_sink
from tradingagents.graph.setup import _compact_debate_node, _limit_tool_calls_node
from tradingagents.observability.graph_tasks import _record_context_cleared_if_present


class _SummaryLlm:
    def invoke(self, _prompt):
        return type("Response", (), {"content": "- Public evidence remains disputed."})()


def _long_debate() -> str:
    return "\n".join(
        f"{speaker}: Publicly reviewable evidence {fill * 3_400}"
        for speaker, fill in (
            ("Bull Analyst", "a"),
            ("Bear Analyst", "b"),
            ("Bull Analyst", "c"),
            ("Bear Analyst", "d"),
        )
    )


def test_context_overflow_retries_once_with_recent_turns_and_safe_marker():
    calls = []
    events = []

    def node(state):
        history = state["investment_debate_state"]["history"]
        calls.append(len(history))
        if len(history) > 12_000:
            raise RuntimeError("maximum context length exceeded")
        return {"investment_debate_state": {"history": history}}

    wrapped = _compact_debate_node("Bull Researcher", node, _SummaryLlm())
    with runtime_event_sink(lambda event_type, detail_code, metadata: events.append((event_type, detail_code, metadata))):
        result = wrapped(
            {
                "investment_debate_state": {"history": _long_debate()},
                "context_compaction_facts": [],
            }
        )

    assert len(calls) == 2
    assert calls[1] <= 12_000
    assert "Recent debate turns" in result["investment_debate_state"]["history"]
    assert result["context_compaction_facts"]
    assert events == [
        (
            "microcompact",
            "context_overflow_retry_compacted",
            {"preserved_turn_count": 3, "public_fact_count": 1},
        )
    ]


def test_tool_call_limit_preserves_declared_order_and_only_records_counts():
    events = []
    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_stock_data", "args": {"symbol": "600519.SH"}, "id": f"call-{index}"}
            for index in range(3)
        ],
    )
    wrapped = _limit_tool_calls_node(lambda _state: {"messages": [message]}, 2)

    with runtime_event_sink(lambda event_type, detail_code, metadata: events.append((event_type, detail_code, metadata))):
        result = wrapped({})

    assert [call["id"] for call in result["messages"][0].tool_calls] == ["call-0", "call-1"]
    assert events == [
        (
            "tool_limit",
            "maximum_tool_calls_reached",
            {
                "requested_tool_call_count": 3,
                "allowed_tool_call_count": 2,
                "discarded_tool_call_count": 1,
            },
        )
    ]


class _Observer:
    def __init__(self):
        self.calls = []

    def record_scratchpad(self, **kwargs):
        self.calls.append(kwargs)


def test_message_clear_marker_uses_actual_remove_operations_and_no_message_content():
    observer = _Observer()
    original = HumanMessage(content="private prompt", id="human-1")
    replacement = HumanMessage(content="private replacement", id="human-2")

    _record_context_cleared_if_present(
        observer,
        {"messages": [original]},
        {"messages": [RemoveMessage(id="human-1"), replacement]},
        "maintenance",
    )

    assert observer.calls == [
        {
            "event_type": "context_cleared",
            "detail_code": "analyst_message_context_reset",
            "metadata": {
                "removed_message_count": 1,
                "prior_message_count": 1,
                "replacement_message_count": 1,
            },
        }
    ]


def test_microcompact_removes_only_older_tool_messages_and_keeps_current_batch():
    events = []
    old = [
        ToolMessage(content=f"old {index}", tool_call_id=f"old-call-{index}", id=f"old-{index}")
        for index in range(3)
    ]
    incoming = [
        ToolMessage(content=f"new {index}", tool_call_id=f"new-call-{index}", id=f"new-{index}")
        for index in range(2)
    ]
    with runtime_event_sink(lambda event_type, detail_code, metadata: events.append((event_type, detail_code, metadata))):
        result = microcompact_tool_messages(
            {"messages": old},
            {"messages": incoming},
            maximum_messages=3,
        )

    assert [message.id for message in result["messages"] if isinstance(message, ToolMessage)] == [
        "new-0",
        "new-1",
    ]
    assert [message.id for message in result["messages"] if isinstance(message, RemoveMessage)] == [
        "old-0",
        "old-1",
    ]
    assert events == [
        (
            "microcompact",
            "old_tool_messages_trimmed",
            {
                "removed_tool_message_count": 2,
                "retained_tool_message_count": 3,
                "incoming_tool_message_count": 2,
                "removed_ai_message_count": 0,
            },
        )
    ]


def test_microcompact_removes_owning_ai_message_alongside_tool_messages():
    """Removing a ToolMessage must also remove the AIMessage that issued its
    tool_call, otherwise DeepSeek/OpenAI reject the orphaned tool_calls."""
    from langchain_core.messages import AIMessage

    old = [
        AIMessage(
            content="calling tools",
            tool_calls=[
                {"id": "call-1", "name": "get_stock_data", "args": {}},
                {"id": "call-2", "name": "get_indicators", "args": {}},
            ],
            id="ai-old",
        ),
        ToolMessage(content="result 1", tool_call_id="call-1", id="tool-1"),
        ToolMessage(content="result 2", tool_call_id="call-2", id="tool-2"),
        AIMessage(
            content="calling tools again",
            tool_calls=[{"id": "call-3", "name": "get_stock_data", "args": {}}],
            id="ai-keep",
        ),
        ToolMessage(content="result 3", tool_call_id="call-3", id="tool-3"),
    ]
    incoming = [
        ToolMessage(content="new result", tool_call_id="call-4", id="new-1"),
    ]
    result = microcompact_tool_messages(
        {"messages": old},
        {"messages": incoming},
        maximum_messages=2,
    )

    removed_ids = {message.id for message in result["messages"] if isinstance(message, RemoveMessage)}
    retained_tools = [message.id for message in result["messages"] if isinstance(message, ToolMessage)]
    assert removed_ids == {"tool-1", "tool-2", "ai-old"}
    assert retained_tools == ["new-1"]


def test_microcompact_expands_straddling_turn_to_keep_pairing_intact():
    """When the retention cut splits a multi-tool-call AIMessage, the entire
    turn is removed rather than leaving half its tool_calls orphaned."""
    from langchain_core.messages import AIMessage

    old = [
        AIMessage(
            content="first batch",
            tool_calls=[{"id": "call-1", "name": "t", "args": {}}],
            id="ai-1",
        ),
        ToolMessage(content="r1", tool_call_id="call-1", id="tool-1"),
        AIMessage(
            content="split batch",
            tool_calls=[
                {"id": "call-2", "name": "t", "args": {}},
                {"id": "call-3", "name": "t", "args": {}},
            ],
            id="ai-2",
        ),
        ToolMessage(content="r2", tool_call_id="call-2", id="tool-2"),
        ToolMessage(content="r3", tool_call_id="call-3", id="tool-3"),
    ]
    incoming = [
        ToolMessage(content="new", tool_call_id="call-4", id="new-1"),
    ]
    result = microcompact_tool_messages(
        {"messages": old},
        {"messages": incoming},
        maximum_messages=2,
    )

    removed_ids = {message.id for message in result["messages"] if isinstance(message, RemoveMessage)}
    retained_tools = [message.id for message in result["messages"] if isinstance(message, ToolMessage)]
    assert removed_ids == {"tool-1", "tool-2", "tool-3", "ai-1", "ai-2"}
    assert retained_tools == ["new-1"]
