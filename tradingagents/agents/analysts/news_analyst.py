import logging

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import (
    build_instrument_context,
    get_global_news,
    get_language_instruction,
    get_news,
)
from tradingagents.dataflows.config import get_config


logger = logging.getLogger(__name__)


def _describe_invalid_tool_call(tool_call) -> str:
    if isinstance(tool_call, dict):
        name = tool_call.get("name", "unknown")
        tool_call_id = tool_call.get("id", "unknown")
        args = tool_call.get("args")
        error = tool_call.get("error")
    else:
        name = getattr(tool_call, "name", "unknown")
        tool_call_id = getattr(tool_call, "id", "unknown")
        args = getattr(tool_call, "args", None)
        error = getattr(tool_call, "error", None)

    parts = [f"tool={name}", f"id={tool_call_id}"]
    if args is not None:
        parts.append(f"args={args}")
    if error:
        parts.append(f"error={error}")
    return " | ".join(parts)


def _retry_messages_for_invalid_tool_calls(
    messages, assistant_message: AIMessage, invalid_tool_calls
) -> list:
    retry_hint_lines = [
        "The previous tool call was invalid.",
        "Please correct the tool arguments and retry with valid JSON only.",
        "Do not change the analysis intent; just fix the tool call payload.",
    ]
    tool_messages = []
    valid_tool_call_ids = {
        tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        for tc in getattr(assistant_message, "tool_calls", []) or []
    }
    for tool_call in invalid_tool_calls:
        retry_hint_lines.append(f"- {_describe_invalid_tool_call(tool_call)}")
        if isinstance(tool_call, dict):
            tool_call_id = tool_call.get("id", "unknown")
            error = tool_call.get("error") or "Invalid tool call arguments."
        else:
            tool_call_id = getattr(tool_call, "id", "unknown")
            error = getattr(tool_call, "error", None) or "Invalid tool call arguments."
        tool_messages.append(ToolMessage(content=error, tool_call_id=tool_call_id, status="error"))
        valid_tool_call_ids.discard(tool_call_id)
    for tool_call_id in valid_tool_call_ids:
        if tool_call_id:
            tool_messages.append(
                ToolMessage(
                    content=(
                        "Tool call execution deferred due to other invalid tool calls "
                        "in the same turn."
                    ),
                    tool_call_id=tool_call_id,
                    status="error",
                )
            )
    return list(messages) + [assistant_message] + tool_messages + [
        HumanMessage(content="\n".join(retry_hint_lines))
    ]


def _sanitize_ai_message(message: AIMessage) -> AIMessage:
    """Drop invalid-tool metadata so the graph can continue safely."""
    invalid_tool_ids = {
        tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
        for tc in getattr(message, "invalid_tool_calls", []) or []
    }
    additional_kwargs = dict(message.additional_kwargs or {})
    if "tool_calls" in additional_kwargs:
        raw_tool_calls = additional_kwargs.get("tool_calls") or []
        if invalid_tool_ids:
            filtered_tool_calls = []
            for tool_call in raw_tool_calls:
                tool_call_id = (
                    tool_call.get("id")
                    if isinstance(tool_call, dict)
                    else getattr(tool_call, "id", None)
                )
                if tool_call_id not in invalid_tool_ids:
                    filtered_tool_calls.append(tool_call)
            additional_kwargs["tool_calls"] = filtered_tool_calls
            if not additional_kwargs["tool_calls"]:
                additional_kwargs.pop("tool_calls", None)
        else:
            additional_kwargs.pop("tool_calls", None)
    return AIMessage(
        content=message.content,
        additional_kwargs=additional_kwargs,
        response_metadata=dict(message.response_metadata or {}),
        name=message.name,
        id=message.id,
        tool_calls=list(message.tool_calls or []),
        invalid_tool_calls=[],
    )


def create_news_analyst(llm):
    def news_analyst_node(state):
        current_date = state["trade_date"]
        asset_type = state.get("asset_type", "stock")
        asset_label = "company" if asset_type == "stock" else "asset"
        instrument_context = build_instrument_context(
            state["company_of_interest"], asset_type
        )

        tools = [
            get_news,
            get_global_news,
        ]

        system_message = (
            f"You are a news researcher tasked with analyzing recent news and trends over the past week. Please write a comprehensive report of the current state of the world that is relevant for trading and macroeconomics. Use the available tools: get_news(query, start_date, end_date) for {asset_label}-specific or targeted news searches, and get_global_news(curr_date, look_back_days, limit) for broader macroeconomic news. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
            + """ Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."""
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke(state["messages"])
        invalid_tool_calls = list(getattr(result, "invalid_tool_calls", []) or [])

        if invalid_tool_calls:
            for invalid_tool_call in invalid_tool_calls:
                logger.warning(
                    "News Analyst produced invalid tool call; retrying once: %s",
                    _describe_invalid_tool_call(invalid_tool_call),
                )

            retry_result = chain.invoke(
                _retry_messages_for_invalid_tool_calls(
                    state["messages"], result, invalid_tool_calls
                )
            )
            retry_invalid_tool_calls = list(
                getattr(retry_result, "invalid_tool_calls", []) or []
            )

            if retry_invalid_tool_calls:
                logger.warning(
                    "News Analyst still produced invalid tool calls after retry; "
                    "continuing with sanitized message.",
                )
                result = _sanitize_ai_message(retry_result)
            else:
                result = retry_result

        report = ""

        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "news_report": report,
        }

    return news_analyst_node
