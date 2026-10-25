"""One turn of a tool-using analyst, and its last turn once its tool rounds are spent."""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

WRAP_UP = (
    "You have used every tool round this report allows. Write your final report "
    "now from the tool results above, and say which data you could not retrieve."
)
_MAX_WRAP_UP_HISTORY_CHARS = 48_000
_TRUNCATED = "\n[Earlier tool output truncated to keep this final report within the model context.]\n"


def take_turn(prompt, llm, tools, messages):
    """The analyst's reply and its report, which stays empty while it calls tools.

    Told to wrap up, it answers without tools: a model offered tools may call one
    whatever it is told. Its earlier calls and their results reach it as text,
    since a provider may refuse a history holding tool calls when none are bound.
    """
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == WRAP_UP:
        # The prompt lists the tools it offers; a model told of tools it cannot
        # call may still try, and some providers then answer with nothing.
        prompt = prompt.partial(tool_names="none; your tool rounds are spent")
        result = (prompt | llm).invoke(_as_text(messages))
        return result, result.content
    result = (prompt | llm.bind_tools(tools)).invoke(messages)
    return result, "" if result.tool_calls else result.content


def _as_text(messages):
    """The history with its tool calls and tool results written out as plain messages."""
    written = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            said = message.content if isinstance(message.content, str) else ""
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], default=str)})" for c in message.tool_calls)
            written.append(AIMessage(content=f"{said}\n[Called {calls}]".strip()))
        elif isinstance(message, ToolMessage):
            written.append(HumanMessage(content=f"[{message.name or 'Tool'} returned]\n{message.content}"))
        else:
            written.append(message)
    return _trim_history(written)


def _trim_history(messages):
    """Keep recent tool results when a long tool loop would exceed model context."""
    excess = sum(len(str(message.content)) for message in messages) - _MAX_WRAP_UP_HISTORY_CHARS
    if excess <= 0:
        return messages

    for message in messages:
        if excess <= 0:
            break
        if (not isinstance(message, HumanMessage) or not isinstance(message.content, str)
                or not message.content.startswith("[")):
            continue
        content = message.content
        minimum = len(_TRUNCATED) + 1
        removable = max(0, len(content) - minimum)
        removed = min(excess, removable)
        if removed:
            keep = len(content) - removed - len(_TRUNCATED)
            message.content = content[:keep] + _TRUNCATED
            excess -= removed
    return messages
