"""Unit tests for the codex provider adapter.

Mocks ``subprocess.run`` so the suite runs in CI without the real
codex CLI installed or authenticated.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from tradingagents.llm_clients import codex_client as mod
from tradingagents.llm_clients.factory import create_llm_client


ADAPTER_LOGGER = "tradingagents.llm_clients.codex_client"


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Build a stub for subprocess.CompletedProcess."""
    return subprocess.CompletedProcess(
        args=["codex"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def _patch_run(monkeypatch, fake):
    """Replace ``subprocess.run`` for the duration of one test."""
    monkeypatch.setattr(mod.subprocess, "run", fake)


def _patch_which(monkeypatch, found: bool):
    """Pretend ``shutil.which`` finds (or doesn't find) the codex binary."""
    monkeypatch.setattr(
        mod.shutil, "which",
        lambda name: "/usr/local/bin/codex" if found else None,
    )


# ---------------------------------------------------------------------------
# _flatten_messages
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFlattenMessages:
    def test_human_only(self):
        assert mod._flatten_messages([HumanMessage(content="hi")]) == "hi"

    def test_system_then_human_labels_system(self):
        out = mod._flatten_messages(
            [SystemMessage(content="be terse"), HumanMessage(content="hi")]
        )
        assert "[System]" in out
        assert "be terse" in out
        assert "hi" in out

    def test_prior_ai_turn_marked(self):
        out = mod._flatten_messages(
            [
                HumanMessage(content="q1"),
                AIMessage(content="a1"),
                HumanMessage(content="q2"),
            ]
        )
        assert "[Previous assistant turn]" in out
        assert "a1" in out
        assert "q1" in out and "q2" in out

    def test_empty_content_skipped(self):
        out = mod._flatten_messages(
            [HumanMessage(content=""), HumanMessage(content="kept")]
        )
        assert out == "kept"

    def test_empty_list_returns_empty(self):
        assert mod._flatten_messages([]) == ""


# ---------------------------------------------------------------------------
# Factory + client wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFactoryWiring:
    def test_factory_returns_codex_client(self, monkeypatch):
        _patch_which(monkeypatch, True)
        c = create_llm_client("codex", "o4-mini")
        assert isinstance(c, mod.CodexClient)
        assert c.get_provider_name() == "codex"

    def test_validate_known_model(self):
        c = create_llm_client("codex", "o4-mini")
        assert c.validate_model() is True

    def test_validate_unknown_model(self):
        c = create_llm_client("codex", "weird-codex-model")
        assert c.validate_model() is False

    def test_base_url_rejected(self):
        with pytest.raises(ValueError, match="no base_url"):
            create_llm_client("codex", "o4-mini", base_url="https://x")

    def test_get_llm_returns_chat_model(self, monkeypatch):
        _patch_which(monkeypatch, True)
        llm = create_llm_client("codex", "o4-mini").get_llm()
        assert isinstance(llm, mod.CodexChatModel)
        assert llm._llm_type == "codex"
        assert llm.model == "o4-mini"

    def test_get_llm_raises_when_codex_missing(self, monkeypatch):
        _patch_which(monkeypatch, False)
        with pytest.raises(RuntimeError, match="codex CLI"):
            create_llm_client("codex", "o4-mini").get_llm()


# ---------------------------------------------------------------------------
# Phase-1 contracts: bind_tools and structured-output both refuse
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhase1Contracts:
    def test_bind_tools_raises(self):
        llm = mod.CodexChatModel()
        with pytest.raises(NotImplementedError, match="bind_tools"):
            llm.bind_tools([])

    def test_with_structured_output_raises(self):
        # ``bind_structured`` in tradingagents catches this and degrades
        # manager / trader / portfolio agents to free-text — pin the
        # contract so the fallback actually fires.
        llm = mod.CodexChatModel()
        with pytest.raises(NotImplementedError, match="structured_output"):
            llm.with_structured_output(dict)


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildArgv:
    def test_default_flags_present(self):
        argv = mod.CodexChatModel(model="o4-mini")._build_argv("hello")
        assert argv[0] == "codex"
        # Quiet mode is non-negotiable — without it the CLI streams
        # intermediate reasoning into stdout and pollutes the report.
        assert "-q" in argv
        assert "-m" in argv and "o4-mini" in argv
        assert "-a" in argv and "full-auto" in argv
        # ``--no-project-doc`` keeps a stray codex.md in cwd from
        # silently changing the model's behaviour.
        assert "--no-project-doc" in argv
        assert argv[-1] == "hello"

    def test_approval_mode_override(self):
        argv = mod.CodexChatModel(approval_mode="auto-edit")._build_argv("p")
        assert "auto-edit" in argv


# ---------------------------------------------------------------------------
# _generate happy + error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGenerate:
    def test_happy_path_returns_ai_message(self, monkeypatch, caplog):
        captured: dict[str, Any] = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return _completed(stdout="hello back\n")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel(model="o4-mini")

        with caplog.at_level(logging.INFO, logger=ADAPTER_LOGGER):
            out = llm.invoke("hi")

        assert isinstance(out, AIMessage)
        assert out.content == "hello back"
        # argv shape: codex -q -m o4-mini -a full-auto --no-project-doc <prompt>
        assert captured["argv"][0] == "codex"
        assert captured["argv"][-1] == "hi"
        # capture_output=True and text=True force string IO + capture.
        assert captured["kwargs"]["capture_output"] is True
        assert captured["kwargs"]["text"] is True
        # Usage line emitted exactly once.
        usage = [r.getMessage() for r in caplog.records if "codex call" in r.getMessage()]
        assert len(usage) == 1
        assert "model=o4-mini" in usage[0]

    def test_nonzero_exit_raises_with_stderr_snippet(self, monkeypatch):
        def fake_run(argv, **kwargs):
            return _completed(returncode=1, stderr="Missing OpenAI API key.\nFix it.")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        with pytest.raises(RuntimeError, match="Missing OpenAI API key"):
            llm.invoke("hi")

    def test_empty_stdout_raises(self, monkeypatch):
        def fake_run(argv, **kwargs):
            return _completed(stdout="   \n  ", stderr="")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        with pytest.raises(RuntimeError, match="empty stdout"):
            llm.invoke("hi")

    def test_codex_missing_translates_to_runtime_error(self, monkeypatch):
        # ``subprocess.run`` raises FileNotFoundError when argv[0] is
        # missing — surface that as an actionable install message
        # rather than a bare OSError.
        def fake_run(argv, **kwargs):
            raise FileNotFoundError(2, "No such file or directory: 'codex'")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        with pytest.raises(RuntimeError, match=r"codex.+CLI is not on PATH"):
            llm.invoke("hi")

    def test_timeout_translates_to_runtime_error(self, monkeypatch):
        def fake_run(argv, **kwargs):
            raise subprocess.TimeoutExpired(cmd=argv, timeout=600)

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel(timeout_s=600)

        with pytest.raises(RuntimeError, match="exceeded the 600s timeout"):
            llm.invoke("hi")

    def test_empty_prompt_raises_before_subprocess(self, monkeypatch):
        called = {"n": 0}

        def fake_run(*a, **kw):
            called["n"] += 1
            return _completed(stdout="should not run")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        # ChatPromptTemplate-style call with no actual content — must
        # short-circuit so we don't spend a subprocess turn on nothing.
        with pytest.raises(ValueError, match="empty prompt"):
            llm._generate([])
        assert called["n"] == 0
