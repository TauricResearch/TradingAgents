import json
from typing import Any, Iterable, Mapping, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage


class CodexMessageCodecError(ValueError):
    """Raised when TradingAgents inputs cannot be normalized for Codex."""


def normalize_input_messages(
    value: str | Sequence[BaseMessage | Mapping[str, Any]],
) -> list[BaseMessage]:
    """Normalize TradingAgents model inputs into LangChain messages."""
    if isinstance(value, str):
        return [HumanMessage(content=value)]

    normalized: list[BaseMessage] = []
    for item in value:
        if isinstance(item, BaseMessage):
            normalized.append(item)
            continue

        if not isinstance(item, Mapping):
            raise CodexMessageCodecError(
                f"Unsupported message input type: {type(item).__name__}"
            )

        normalized.append(_message_from_dict(item))

    return normalized


def format_messages_for_codex(
    messages: Sequence[BaseMessage],
    *,
    tool_names: Iterable[str] = (),
    tool_schemas: Sequence[Mapping[str, Any]] = (),
    tool_choice: str | None = None,
    tool_arguments_as_json_string: bool = False,
    retry_message: str | None = None,
) -> str:
    """Render a chat transcript into a single text prompt for Codex."""
    tool_list = list(tool_names)
    lines = [
        "You are answering on behalf of TradingAgents.",
        "The conversation transcript is provided below.",
        "Treat tool outputs as authoritative execution results from the host application.",
    ]
    if tool_list:
        lines.append(
            "If external data is still needed, respond with tool calls using only these tools: "
            + ", ".join(tool_list)
            + "."
        )
    else:
        lines.append("No host tools are available for this turn.")
    if tool_choice == "none":
        lines.append("Do not request tool calls for this turn.")
    elif tool_choice in {"any", "required"}:
        lines.append("You must respond with one or more tool calls for this turn.")
    elif tool_choice and tool_choice != "auto":
        lines.append(f"You must call the tool named `{tool_choice}` for this turn.")
    elif tool_choice == "auto":
        lines.append("Use tool calls only if they are necessary to answer correctly.")
    if tool_arguments_as_json_string:
        lines.append(
            "When returning tool calls, encode each tool argument object as a JSON string in `arguments_json`."
        )
    schema_lines = _format_tool_schema_lines(tool_schemas)
    if schema_lines:
        lines.append("Tool argument requirements:")
        lines.extend(schema_lines)
    lines.append("Respond only with JSON that matches the requested output schema.")
    if retry_message:
        lines.append(retry_message)

    transcript: list[str] = []
    for message in messages:
        transcript.append(_format_message(message))

    return "\n\n".join(lines + ["Conversation transcript:", *transcript])


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("```")
        if len(parts) >= 3:
            candidate = parts[1]
            if candidate.lstrip().startswith("json"):
                candidate = candidate.lstrip()[4:]
            return candidate.strip()
    return stripped


def _message_from_dict(message: Mapping[str, Any]) -> BaseMessage:
    role = str(message.get("role", "")).lower()
    content = _content_to_text(message.get("content", ""))

    if role == "system":
        return SystemMessage(content=content)
    if role == "user":
        return HumanMessage(content=content)
    if role == "tool":
        tool_call_id = str(message.get("tool_call_id") or message.get("toolCallId") or "")
        if not tool_call_id:
            raise CodexMessageCodecError("Tool messages require tool_call_id.")
        return ToolMessage(content=content, tool_call_id=tool_call_id)
    if role == "assistant":
        raw_tool_calls = message.get("tool_calls") or message.get("toolCalls") or []
        tool_calls = _normalize_tool_calls(raw_tool_calls)
        return AIMessage(content=content, tool_calls=tool_calls)

    raise CodexMessageCodecError(f"Unsupported message role: {role!r}")


def _normalize_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not raw_tool_calls:
        return normalized

    if not isinstance(raw_tool_calls, Sequence):
        raise CodexMessageCodecError("assistant.tool_calls must be a sequence")

    for item in raw_tool_calls:
        if not isinstance(item, Mapping):
            raise CodexMessageCodecError("assistant.tool_calls items must be objects")

        if "function" in item:
            function = item.get("function")
            if not isinstance(function, Mapping):
                raise CodexMessageCodecError("assistant.tool_calls.function must be an object")
            raw_args = function.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError as exc:
                    raise CodexMessageCodecError(
                        f"assistant tool arguments must be valid JSON: {raw_args!r}"
                    ) from exc
            else:
                args = raw_args
            if not isinstance(args, Mapping):
                raise CodexMessageCodecError("assistant tool arguments must decode to an object")
            normalized.append(
                {
                    "name": str(function.get("name", "")),
                    "args": dict(args),
                    "id": str(item.get("id") or ""),
                }
            )
            continue

        args = item.get("args", {})
        if not isinstance(args, Mapping):
            raise CodexMessageCodecError("assistant tool args must be an object")
        normalized.append(
            {
                "name": str(item.get("name", "")),
                "args": dict(args),
                "id": str(item.get("id") or ""),
            }
        )

    return normalized


def _format_message(message: BaseMessage) -> str:
    role = type(message).__name__.replace("Message", "") or "Message"
    body = _content_to_text(message.content)

    if isinstance(message, AIMessage) and message.tool_calls:
        tool_call_json = json.dumps(
            [
                {
                    "id": tool_call.get("id"),
                    "name": tool_call.get("name"),
                    "args": tool_call.get("args", {}),
                }
                for tool_call in message.tool_calls
            ],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        return f"[{role}]\n{body}\nTool calls:\n{tool_call_json}".strip()

    if isinstance(message, ToolMessage):
        return f"[Tool:{message.tool_call_id}]\n{body}".strip()

    return f"[{role}]\n{body}".strip()


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                else:
                    parts.append(json.dumps(dict(item), ensure_ascii=False))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _format_tool_schema_lines(tool_schemas: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for tool_schema in tool_schemas:
        function = tool_schema.get("function")
        if not isinstance(function, Mapping):
            continue
        name = function.get("name")
        parameters = function.get("parameters") or {}
        if not isinstance(name, str) or not isinstance(parameters, Mapping):
            continue
        required = parameters.get("required") or []
        properties = parameters.get("properties") or {}
        summary = {
            "required": required if isinstance(required, list) else [],
            "properties": properties if isinstance(properties, Mapping) else {},
        }
        lines.append(
            f"- {name}: {json.dumps(summary, ensure_ascii=False, sort_keys=True)}"
        )
    return lines
