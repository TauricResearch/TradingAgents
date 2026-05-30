"""Test dell'event-hook che impone store=false/stream=true/instructions."""
import json

import httpx

from tradingagents.llm_clients.oauth.body import enforce_codex_constraints


def _request(body: dict, path="/backend-api/codex/responses", method="POST") -> httpx.Request:
    return httpx.Request(method, f"https://chatgpt.com{path}", json=body)


def _body(request) -> dict:
    return json.loads(request.content)


def _wire_body(request) -> dict:
    """Body come lo legge il transport reale di httpx: iterando request.stream."""
    return json.loads(b"".join(request.stream))


def test_forces_store_false_and_stream_true():
    req = _request({"model": "gpt-5.3-codex", "store": True, "stream": False,
                    "instructions": "x", "input": []})
    enforce_codex_constraints(req)
    payload = _body(req)
    assert payload["store"] is False
    assert payload["stream"] is True
    assert req.headers["Content-Length"] == str(len(req.content))


def test_modifies_the_actual_wire_stream_not_just_content():
    # Regression: httpx invia request.stream, non _content. L'hook DEVE
    # aggiornare entrambi o il body vecchio finisce sul filo.
    req = _request({"model": "m", "store": True, "stream": False, "input": []})
    enforce_codex_constraints(req)
    wire = _wire_body(req)
    assert wire["store"] is False
    assert wire["stream"] is True
    assert wire["instructions"].strip()
    assert req.content == b"".join(req.stream)


def test_fills_missing_instructions():
    req = _request({"model": "m", "store": False, "stream": True, "input": []})
    enforce_codex_constraints(req)
    assert _body(req)["instructions"].strip()


def test_fills_empty_instructions():
    req = _request({"instructions": "   ", "store": False, "stream": True})
    enforce_codex_constraints(req)
    assert _body(req)["instructions"].strip()


def test_leaves_compliant_body_untouched():
    req = _request({"model": "m", "store": False, "stream": True,
                    "instructions": "sys", "input": []})
    before = req.content
    enforce_codex_constraints(req)
    assert req.content == before


def test_ignores_non_responses_path():
    req = _request({"store": True}, path="/backend-api/codex/models")
    before = req.content
    enforce_codex_constraints(req)
    assert req.content == before


def test_ignores_get_requests():
    req = _request({"store": True}, method="GET")
    before = req.content
    enforce_codex_constraints(req)
    assert req.content == before
