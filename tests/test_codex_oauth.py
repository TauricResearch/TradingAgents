import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel

from tradingagents.llm_clients.codex_oauth import (
    CodexOAuthTokens,
    create_authorization_url,
    extract_account_id,
    extract_account_id_from_tokens,
)
from tradingagents.llm_clients.codex_oauth_client import (
    CODEX_RESPONSES_PATH,
    CodexOAuthChatModel,
    codex_models_to_options,
)


class SampleStructuredOutput(BaseModel):
    rating: str
    rationale: str


def _jwt(payload: dict) -> str:
    raw = json.dumps(payload).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return f"header.{encoded}.signature"


def test_extract_account_id_from_codex_claim():
    token = _jwt({
        "https://api.openai.com/auth": {
            "chatgpt_account_id": "acct_123",
        }
    })

    assert extract_account_id(token) == "acct_123"


def test_authorization_url_matches_codex_oauth_shape():
    url, verifier, state = create_authorization_url()

    assert "client_id=app_EMoamEEZ73f0CkXaXp7hrann" in url
    assert "scope=openid+profile+email+offline_access" in url
    assert "codex_cli_simplified_flow=true" in url
    assert "originator=opencode" in url
    assert verifier
    assert state


def test_extract_account_id_from_id_token_and_organizations():
    access_token = _jwt({})
    id_token = _jwt({
        "https://api.openai.com/auth": {
            "organizations": [{"id": "org_123"}],
        }
    })

    assert extract_account_id_from_tokens(access_token, id_token) == "org_123"


def test_codex_oauth_tokens_round_trip_shape():
    tokens = CodexOAuthTokens(
        access_token="access",
        refresh_token="refresh",
        expires_at=time.time() + 100,
        account_id="acct_123",
        id_token="id",
    )

    restored = CodexOAuthTokens.from_json(tokens.__dict__)

    assert restored.access_token == "access"
    assert restored.refresh_token == "refresh"
    assert restored.account_id == "acct_123"
    assert restored.id_token == "id"


def test_codex_models_to_options_uses_live_payload_shape():
    options = codex_models_to_options({
        "models": [
            {"slug": "gpt-5.5", "display_name": "GPT-5.5"},
            {"slug": "gpt-5.4-mini", "display_name": "GPT-5.4 Mini"},
            {"slug": "codex-auto-review", "display_name": "Codex Auto Review"},
            {"slug": "gpt-5.5", "display_name": "Duplicate"},
            {"slug": "", "display_name": "Missing"},
        ]
    })

    assert options == [
        ("GPT-5.5 - ChatGPT OAuth", "gpt-5.5"),
        ("GPT-5.4 Mini - ChatGPT OAuth", "gpt-5.4-mini"),
    ]


def test_codex_oauth_payload_maps_tools_and_tool_outputs():
    @tool
    def get_stock_data(ticker: str) -> str:
        """Fetch stock data."""
        return ticker

    llm = CodexOAuthChatModel(model_name="gpt-5.4-mini").bind_tools([get_stock_data])

    payload = llm._build_payload([HumanMessage(content="Fetch NVDA")])
    tool_payload = payload["tools"][0]

    assert payload["store"] is False
    assert payload["stream"] is True
    assert payload["instructions"]
    assert tool_payload["type"] == "function"
    assert tool_payload["name"] == "get_stock_data"

    followup = llm._build_payload([ToolMessage(content="price=1", tool_call_id="call_1")])

    assert followup["input"][0]["type"] == "function_call_output"
    assert followup["input"][0]["call_id"] == "call_1"

    prior_call = llm._build_payload([
        AIMessage(
            content="",
            tool_calls=[{
                "name": "get_stock_data",
                "args": {"ticker": "NVDA"},
                "id": "call_1",
                "type": "tool_call",
            }],
        )
    ])

    assert prior_call["input"][0]["type"] == "function_call"
    assert prior_call["input"][0]["call_id"] == "call_1"
    assert prior_call["input"][0]["arguments"] == '{"ticker": "NVDA"}'


def test_codex_oauth_structured_output_returns_pydantic_instance():
    class FakeStructuredCodex(CodexOAuthChatModel):
        def _post(self, payload):
            assert "JSON Schema" in payload["instructions"]
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"rating":"Buy","rationale":"strong setup"}',
                            }
                        ],
                    }
                ]
            }

    structured = FakeStructuredCodex().with_structured_output(SampleStructuredOutput)

    result = structured.invoke("Analyze")

    assert isinstance(result, SampleStructuredOutput)
    assert result.rating == "Buy"
    assert result.rationale == "strong setup"


def test_codex_oauth_structured_output_extracts_json_from_fence():
    class FakeStructuredCodex(CodexOAuthChatModel):
        def _post(self, payload):
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": '```json\n{"rating":"Hold","rationale":"balanced"}\n```',
                            }
                        ],
                    }
                ]
            }

    result = FakeStructuredCodex().with_structured_output(SampleStructuredOutput).invoke("Analyze")

    assert result.rating == "Hold"


def test_codex_oauth_response_maps_text_and_function_calls():
    llm = CodexOAuthChatModel()

    tool_message = llm._parse_response({
        "output": [
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "get_stock_data",
                "arguments": '{"ticker":"NVDA"}',
            }
        ]
    })

    assert tool_message.tool_calls[0]["id"] == "call_1"
    assert tool_message.tool_calls[0]["name"] == "get_stock_data"
    assert tool_message.tool_calls[0]["args"] == {"ticker": "NVDA"}

    text_message = llm._parse_response({
        "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "analysis"}],
            }
        ]
    })

    assert text_message.content == "analysis"
    assert text_message.usage_metadata == {
        "input_tokens": 10,
        "output_tokens": 3,
        "total_tokens": 13,
    }


def test_codex_oauth_decodes_sse_response():
    class Response:
        headers = {"Content-Type": "text/event-stream"}
        text = "\n".join([
            'data: {"type":"response.output_text.delta","delta":"ana"}',
            'data: {"type":"response.output_text.delta","delta":"lysis"}',
            "data: [DONE]",
        ])

    payload = CodexOAuthChatModel()._decode_response(Response())

    assert payload == {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "analysis"}],
            }
        ]
    }


def test_codex_oauth_decodes_sse_when_completed_output_is_empty():
    class Response:
        headers = {}
        text = "\n".join([
            'event: response.output_text.delta',
            'data: {"type":"response.output_text.delta","delta":"ok"}',
            'event: response.completed',
            'data: {"type":"response.completed","response":{"output":[],"usage":{"input_tokens":1,"output_tokens":2,"total_tokens":3}}}',
        ])

    payload = CodexOAuthChatModel()._decode_response(Response())

    assert payload == {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
    }


def test_codex_oauth_post_uses_account_header_and_endpoint():
    calls = []

    class Response:
        status_code = 200
        text = ""
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"output_text": "ok"}

    def fake_post(url, json, headers, timeout):
        calls.append(SimpleNamespace(url=url, json=json, headers=headers, timeout=timeout))
        return Response()

    with (
        patch(
            "tradingagents.llm_clients.codex_oauth_client.get_valid_tokens",
            return_value=CodexOAuthTokens("access", "refresh", time.time() + 100, "acct_123"),
        ),
        patch("tradingagents.llm_clients.codex_oauth_client.requests.post", side_effect=fake_post),
    ):
        payload = CodexOAuthChatModel(base_url="https://chatgpt.example/backend-api")._post({"input": []})

    assert payload == {"output_text": "ok"}
    assert calls[0].url == f"https://chatgpt.example/backend-api{CODEX_RESPONSES_PATH}"
    assert calls[0].headers["Authorization"] == "Bearer access"
    assert calls[0].headers["ChatGPT-Account-ID"] == "acct_123"
    assert calls[0].headers["OpenAI-Beta"] == "responses=experimental"


def test_codex_oauth_post_refreshes_on_401():
    calls = []

    class Response401:
        status_code = 401
        text = "expired"
        headers = {"Content-Type": "application/json"}

    class Response200:
        status_code = 200
        text = ""
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"output_text": "ok"}

    def fake_post(url, json, headers, timeout):
        calls.append(headers["Authorization"])
        return Response401() if len(calls) == 1 else Response200()

    store = SimpleNamespace(
        load=lambda: CodexOAuthTokens("old", "refresh", time.time() + 100, "acct_old"),
        save=lambda tokens: None,
    )

    with (
        patch(
            "tradingagents.llm_clients.codex_oauth_client.get_valid_tokens",
            return_value=CodexOAuthTokens("old", "refresh", time.time() + 100, "acct_old"),
        ),
        patch("tradingagents.llm_clients.codex_oauth_client.CodexOAuthStore", return_value=store),
        patch(
            "tradingagents.llm_clients.codex_oauth_client.refresh_tokens",
            return_value=CodexOAuthTokens("new", "refresh2", time.time() + 100, "acct_new"),
        ),
        patch("tradingagents.llm_clients.codex_oauth_client.requests.post", side_effect=fake_post),
    ):
        payload = CodexOAuthChatModel()._post({"input": []})

    assert payload == {"output_text": "ok"}
    assert calls == ["Bearer old", "Bearer new"]
