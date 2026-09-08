from types import SimpleNamespace

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel

from tradingagents.llm_clients import codex_client
from tradingagents.llm_clients.codex_client import (
    CodexChatModel,
    CodexSetupError,
    _available_model_ids,
    _codex_setup_message,
    _looks_like_schema_error,
    _model_recovery_steps,
)
from tradingagents.llm_clients.factory import create_llm_client


class SampleStructuredOutput(BaseModel):
    recommendation: str
    confidence: float


class OptionalStructuredOutput(BaseModel):
    required_value: str
    optional_value: str | None = None


@pytest.mark.unit
def test_codex_factory_returns_chat_model(monkeypatch):
    monkeypatch.setattr(codex_client, "preflight_codex_runtime", lambda model: ["gpt-5.4"])

    client = create_llm_client("codex", "gpt-5.4")
    llm = client.get_llm()

    assert isinstance(llm, CodexChatModel)
    assert llm.model_name == "gpt-5.4"


@pytest.mark.unit
def test_codex_plain_response(monkeypatch):
    llm = CodexChatModel(model_name="gpt-5.4")
    monkeypatch.setattr(llm, "_run_codex", lambda prompt: "Final analysis")

    result = llm.invoke("Analyze SPY")

    assert result.content == "Final analysis"
    assert result.tool_calls == []


@pytest.mark.unit
def test_codex_json_tool_response(monkeypatch):
    llm = CodexChatModel(model_name="gpt-5.4").bind_tools([
        SimpleNamespace(
            name="get_stock_data",
            description="Fetch stock data",
            args={"ticker": {"type": "string"}},
        )
    ])
    monkeypatch.setattr(
        llm,
        "_run_codex",
        lambda prompt: '{"tool_calls":[{"name":"get_stock_data","args":{"ticker":"SPY"}}]}',
    )

    result = llm.invoke("Analyze SPY")

    assert result.content == ""
    assert result.tool_calls == [
        {
            "name": "get_stock_data",
            "args": {"ticker": "SPY"},
            "id": "codex_tool_0",
            "type": "tool_call",
        }
    ]


@pytest.mark.unit
def test_codex_structured_output_parses_pydantic_model(monkeypatch):
    llm = CodexChatModel(model_name="gpt-5.4")
    received_schema = None

    def run_codex(prompt, *, output_schema=None):
        nonlocal received_schema
        received_schema = output_schema
        return '{"recommendation":"Hold","confidence":0.75}'

    monkeypatch.setattr(
        llm,
        "_run_codex",
        run_codex,
    )

    result = llm.with_structured_output(SampleStructuredOutput).invoke("Decide")

    assert result == SampleStructuredOutput(recommendation="Hold", confidence=0.75)
    assert received_schema["additionalProperties"] is False
    assert received_schema["required"] == ["recommendation", "confidence"]


@pytest.mark.unit
def test_codex_strict_schema_forbids_extra_properties_and_requires_optional_fields():
    schema = codex_client._strict_json_schema(OptionalStructuredOutput.model_json_schema())

    assert schema["additionalProperties"] is False
    assert schema["required"] == ["required_value", "optional_value"]


@pytest.mark.unit
def test_codex_detects_structured_output_schema_errors():
    assert _looks_like_schema_error("invalid_json_schema: additionalProperties is required")


@pytest.mark.unit
def test_codex_accepts_openai_style_message_dicts(monkeypatch):
    llm = CodexChatModel(model_name="gpt-5.4")
    monkeypatch.setattr(llm, "_run_codex", lambda prompt: "Trader response")

    result = llm.invoke([
        {"role": "system", "content": "Follow the trading plan."},
        {"role": "user", "content": "Make a recommendation."},
    ])

    assert result.content == "Trader response"


@pytest.mark.unit
def test_codex_reports_native_structured_output_and_fallback_to_callbacks(monkeypatch):
    class StatusHandler(BaseCallbackHandler):
        def __init__(self):
            self.structured_outputs = 0
            self.fallbacks = []

        def on_codex_structured_output(self):
            self.structured_outputs += 1

        def on_codex_structured_fallback(self, *, agent_name, error):
            self.fallbacks.append((agent_name, error))

    handler = StatusHandler()
    llm = CodexChatModel(model_name="gpt-5.4", callbacks=[handler])
    monkeypatch.setattr(
        llm,
        "_run_codex",
        lambda prompt, *, output_schema=None: '{"recommendation":"Hold","confidence":0.75}',
    )

    llm.with_structured_output(SampleStructuredOutput).invoke("Decide")
    llm.record_structured_fallback("Trader", ValueError("invalid output"))

    assert handler.structured_outputs == 1
    assert handler.fallbacks == [("Trader", "invalid output")]


@pytest.mark.unit
def test_codex_invocations_reuse_runtime_but_isolate_threads(monkeypatch):
    class FakeSandbox:
        read_only = object()

    class FakeThread:
        def __init__(self, response):
            self.response = response
            self.calls = []

        def run(self, prompt, **kwargs):
            self.calls.append((prompt, kwargs))
            return SimpleNamespace(final_response=self.response)

    class FakeCodex:
        def __init__(self):
            self.threads = []

        def models(self):
            return SimpleNamespace(data=[SimpleNamespace(id="gpt-5.4")])

        def thread_start(self, **kwargs):
            thread = FakeThread(f"response-{len(self.threads) + 1}")
            self.threads.append((kwargs, thread))
            return thread

    class FakeRuntime:
        def __init__(self):
            self.codex = FakeCodex()
            self.get_calls = 0

        def get(self):
            self.get_calls += 1
            return self.codex

    runtime = FakeRuntime()
    monkeypatch.setitem(__import__("sys").modules, "openai_codex", SimpleNamespace(Sandbox=FakeSandbox))
    monkeypatch.setattr(codex_client, "_CODEX_RUNTIME", runtime)
    llm = CodexChatModel(model_name="gpt-5.4")

    assert llm._run_codex("first") == "response-1"
    assert llm._run_codex("second") == "response-2"

    assert runtime.get_calls == 2
    assert len(runtime.codex.threads) == 2
    assert all(kwargs["ephemeral"] is True for kwargs, _ in runtime.codex.threads)


@pytest.mark.unit
def test_available_model_ids_extracts_codex_sdk_models():
    codex = SimpleNamespace(
        models=lambda: SimpleNamespace(
            data=[
                SimpleNamespace(id="gpt-5.5"),
                SimpleNamespace(model="gpt-5.4-mini"),
            ]
        )
    )

    assert _available_model_ids(codex) == ["gpt-5.5", "gpt-5.4-mini"]


@pytest.mark.unit
def test_available_model_ids_supports_newer_cli_protocol_values():
    codex = SimpleNamespace(
        _client=SimpleNamespace(
            _request_raw=lambda method, params: {
                "data": [
                    {"id": "gpt-5.6-luna", "supportedReasoningEfforts": [{"reasoningEffort": "ultra"}]},
                    {"id": "gpt-5.6-sol", "supportedReasoningEfforts": [{"reasoningEffort": "max"}]},
                ]
            }
        )
    )

    assert _available_model_ids(codex) == ["gpt-5.6-luna", "gpt-5.6-sol"]


@pytest.mark.unit
def test_codex_model_error_shows_model_recovery_without_login_instruction():
    message = _codex_setup_message(
        "This Codex model requires a newer Codex app/CLI/SDK.",
        original_error="gpt-5.6-luna requires a newer version of Codex",
        available_models=["gpt-5.5", "gpt-5.4-mini"],
        recovery_steps=_model_recovery_steps(cli_available=True),
    )

    assert "codex update" in message
    assert "codex --version" in message
    assert "codex login" not in message
    assert "gpt-5.5, gpt-5.4-mini" in message


@pytest.mark.unit
def test_codex_model_error_without_cli_shows_install_login_and_restart_steps():
    steps = _model_recovery_steps(cli_available=False)

    assert "npm install -g @openai/codex" in steps[0]
    assert "codex --version" in steps[1]
    assert "codex login" in steps[2]
    assert "Restart TradingAgents" in steps[3]


@pytest.mark.unit
def test_preflight_rejects_unavailable_runtime_model(monkeypatch):
    class FakeCodex:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def account(self):
            return object()

        def models(self):
            return SimpleNamespace(data=[SimpleNamespace(id="gpt-5.5")])

    monkeypatch.setitem(__import__("sys").modules, "openai_codex", SimpleNamespace(Codex=FakeCodex))
    monkeypatch.setattr(codex_client, "_new_codex_client", FakeCodex)
    monkeypatch.setattr(codex_client, "_codex_cli_path", lambda: None)

    with pytest.raises(CodexSetupError) as exc:
        codex_client.preflight_codex_runtime("gpt-5.6-luna")

    assert "requires the standalone Codex CLI" in str(exc.value)
    assert "npm install -g @openai/codex" in str(exc.value)
