import json


def _tool_call_signature(tool_call):
    if isinstance(tool_call, dict):
        name = tool_call["name"]
        args = tool_call["args"]
    else:
        name = tool_call.name
        args = tool_call.args
    return (name, json.dumps(args, sort_keys=True, default=str))


def _message_fingerprint(message, msg_type, content):
    tool_calls = tuple(_tool_call_signature(tool_call) for tool_call in getattr(message, "tool_calls", []) or [])
    return (
        message.__class__.__name__,
        msg_type,
        content.strip() if isinstance(content, str) else str(content),
        tool_calls,
    )


def ingest_chunk_messages(message_buffer, chunk, classify_message_type) -> None:
    """Ingest all newly seen messages from a graph stream chunk."""
    for message in chunk.get("messages", []):
        msg_type, content = classify_message_type(message)
        msg_id = getattr(message, "id", None)
        if msg_id is not None:
            if msg_id in message_buffer._processed_message_ids:
                continue
            message_buffer._processed_message_ids.add(msg_id)
        else:
            fingerprint = _message_fingerprint(message, msg_type, content)
            if fingerprint in message_buffer._processed_message_fingerprints:
                continue
            message_buffer._processed_message_fingerprints.add(fingerprint)

        if content and content.strip():
            message_buffer.add_message(msg_type, content)

        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                if isinstance(tool_call, dict):
                    message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                else:
                    message_buffer.add_tool_call(tool_call.name, tool_call.args)
