import subprocess

import pytest
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from tradingagents.llm_clients import create_llm_client
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import get_model_options
from tradingagents.llm_clients.subscription_client import SubscriptionCLIChatModel, _extract_json


class Rating(BaseModel):
    rating: str
    confidence: int


def test_subscription_providers_do_not_require_api_keys():
    assert get_api_key_env("codex-cli") is None
    assert get_api_key_env("claude-code") is None


def test_subscription_providers_are_in_model_catalog():
    assert get_model_options("codex-cli", "quick")
    assert get_model_options("claude-code", "deep")


def test_factory_creates_subscription_clients(monkeypatch):
    monkeypatch.setenv("CODEX_CLI_COMMAND", "/bin/echo")
    client = create_llm_client("codex-cli", "default")
    llm = client.get_llm()

    assert isinstance(llm, SubscriptionCLIChatModel)
    assert llm.provider == "codex-cli"
    assert llm.command == "/bin/echo"


def test_codex_cli_uses_output_last_message(monkeypatch, tmp_path):
    def fake_run(cmd, input, text, capture_output, timeout, check, cwd):
        output_path = cmd[cmd.index("-o") + 1]
        with open(output_path, "w") as handle:
            handle.write("subscription response")
        return subprocess.CompletedProcess(cmd, 0, stdout="logs", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm = SubscriptionCLIChatModel(
        provider="codex-cli",
        model="default",
        command="codex",
        workdir=str(tmp_path),
    )

    result = llm.invoke([HumanMessage(content="hello")])

    assert result.content == "subscription response"


def test_claude_cli_reads_stdout(monkeypatch, tmp_path):
    def fake_run(cmd, input, text, capture_output, timeout, check, cwd):
        assert cmd[:3] == ["claude", "--print", "--output-format"]
        return subprocess.CompletedProcess(cmd, 0, stdout="claude response\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm = SubscriptionCLIChatModel(
        provider="claude-code",
        model="sonnet",
        command="claude",
        workdir=str(tmp_path),
    )

    result = llm.invoke("hello")

    assert result.content == "claude response"


def test_subscription_structured_output_parses_pydantic(monkeypatch, tmp_path):
    def fake_run(cmd, input, text, capture_output, timeout, check, cwd):
        assert "JSON Schema" in input
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"rating":"buy","confidence":87}',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm = SubscriptionCLIChatModel(
        provider="claude-code",
        model="sonnet",
        command="claude",
        workdir=str(tmp_path),
    )

    structured = llm.with_structured_output(Rating)
    result = structured.invoke("rate NVDA")

    assert result == Rating(rating="buy", confidence=87)


def test_extract_json_ignores_trailing_braces():
    text = 'Here is the result: {"rating":"buy","confidence":87} and a note {not json}'

    assert _extract_json(text) == {"rating": "buy", "confidence": 87}


def test_extract_json_handles_nested_strings():
    text = '```json\n{"rating":"buy","confidence":87,"note":"uses } inside a string"}\n```'

    assert _extract_json(text) == {
        "rating": "buy",
        "confidence": 87,
        "note": "uses } inside a string",
    }
