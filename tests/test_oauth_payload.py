"""Test della trasformazione del payload Responses per il backend Codex."""
from tradingagents.llm_clients.oauth.payload import apply_codex_payload_constraints


def _responses_payload(**over):
    base = {
        "model": "gpt-5.4-mini",
        "input": [
            {"role": "system", "content": "Sei un analista.", "type": "message"},
            {"role": "user", "content": "Analizza NVDA", "type": "message"},
        ],
    }
    base.update(over)
    return base


def test_forces_store_false_and_stream_true():
    p = apply_codex_payload_constraints(_responses_payload(store=True, stream=False))
    assert p["store"] is False
    assert p["stream"] is True


def test_hoists_system_message_into_instructions():
    p = apply_codex_payload_constraints(_responses_payload())
    assert p["instructions"] == "Sei un analista."
    roles = [m.get("role") for m in p["input"]]
    assert "system" not in roles and "developer" not in roles
    assert roles == ["user"]


def test_hoists_developer_message_too():
    payload = {
        "model": "m",
        "input": [
            {"role": "developer", "content": "dev rules", "type": "message"},
            {"role": "user", "content": "hi", "type": "message"},
        ],
    }
    p = apply_codex_payload_constraints(payload)
    assert "dev rules" in p["instructions"]
    assert [m["role"] for m in p["input"]] == ["user"]


def test_multiple_system_messages_concatenated():
    payload = {
        "model": "m",
        "input": [
            {"role": "system", "content": "A", "type": "message"},
            {"role": "system", "content": "B", "type": "message"},
            {"role": "user", "content": "hi", "type": "message"},
        ],
    }
    p = apply_codex_payload_constraints(payload)
    assert "A" in p["instructions"] and "B" in p["instructions"]


def test_extracts_text_from_list_content_parts():
    payload = {
        "model": "m",
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "sys via parts"}], "type": "message"},
            {"role": "user", "content": "hi", "type": "message"},
        ],
    }
    p = apply_codex_payload_constraints(payload)
    assert p["instructions"] == "sys via parts"


def test_default_instructions_when_no_system():
    payload = {"model": "m", "input": [{"role": "user", "content": "hi", "type": "message"}]}
    p = apply_codex_payload_constraints(payload)
    assert p["instructions"].strip()


def test_preserves_existing_instructions_when_no_system():
    payload = {"model": "m", "instructions": "keep me", "input": [{"role": "user", "content": "hi"}]}
    p = apply_codex_payload_constraints(payload)
    assert "keep me" in p["instructions"]


def test_strips_max_output_tokens():
    p = apply_codex_payload_constraints(_responses_payload(max_output_tokens=256))
    assert "max_output_tokens" not in p


def test_noop_on_non_responses_payload():
    # Chat Completions payload (ha 'messages', non 'input') -> intatto
    chat = {"model": "m", "messages": [{"role": "system", "content": "x"}]}
    p = apply_codex_payload_constraints(chat)
    assert p == chat
    assert "store" not in p
