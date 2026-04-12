def ingest_chunk_messages(message_buffer, chunk, classify_message_type) -> None:
    """Ingest all newly seen messages from a graph stream chunk."""
    for message in chunk.get("messages", []):
        msg_id = getattr(message, "id", None)
        if msg_id is not None:
            if msg_id in message_buffer._processed_message_ids:
                continue
            message_buffer._processed_message_ids.add(msg_id)

        msg_type, content = classify_message_type(message)
        if content and content.strip():
            message_buffer.add_message(msg_type, content)

        if hasattr(message, "tool_calls") and message.tool_calls:
            for tool_call in message.tool_calls:
                if isinstance(tool_call, dict):
                    message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                else:
                    message_buffer.add_tool_call(tool_call.name, tool_call.args)
