from cli.chunk_ingest import ingest_chunk_messages


class FakeToolCall:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class FakeMessage:
    def __init__(self, msg_id, content, tool_calls=None):
        self.id = msg_id
        self.content = content
        self.tool_calls = tool_calls or []


class FakeMessageBuffer:
    def __init__(self):
        self._processed_message_ids = set()
        self.messages = []
        self.tool_calls = []

    def add_message(self, message_type, content):
        self.messages.append((message_type, content))

    def add_tool_call(self, tool_name, args):
        self.tool_calls.append((tool_name, args))


def fake_classifier(message):
    return "Agent", message.content


def test_ingest_chunk_messages_records_all_tool_calls():
    message_buffer = FakeMessageBuffer()
    chunk = {
        "messages": [
            FakeMessage(
                "m1",
                "first",
                [
                    {"name": "tool_a", "args": {"x": 1}},
                    FakeToolCall("tool_b", {"y": 2}),
                ],
            ),
            FakeMessage("m2", "second", [FakeToolCall("tool_c", {"z": 3})]),
        ]
    }

    ingest_chunk_messages(message_buffer, chunk, fake_classifier)

    tool_names = [name for name, _ in message_buffer.tool_calls]
    assert tool_names == ["tool_a", "tool_b", "tool_c"]


def test_ingest_chunk_messages_skips_duplicate_message_ids():
    message_buffer = FakeMessageBuffer()
    chunk = {"messages": [FakeMessage("m1", "same", [{"name": "tool_a", "args": {}}])]}

    ingest_chunk_messages(message_buffer, chunk, fake_classifier)
    ingest_chunk_messages(message_buffer, chunk, fake_classifier)

    assert len(message_buffer.messages) == 1
    assert len(message_buffer.tool_calls) == 1
