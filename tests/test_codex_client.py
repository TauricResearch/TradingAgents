"""Unit tests for the codex provider adapter.

Mocks ``subprocess.run`` so the suite runs in CI without the real
codex CLI installed or authenticated.
"""

from __future__ import annotations

import logging
import os
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
        c = create_llm_client("codex", "gpt-5.4-mini")
        assert isinstance(c, mod.CodexClient)
        assert c.get_provider_name() == "codex"

    def test_validate_known_model(self):
        c = create_llm_client("codex", "gpt-5.4-mini")
        assert c.validate_model() is True

    def test_validate_unknown_model(self):
        c = create_llm_client("codex", "weird-codex-model")
        assert c.validate_model() is False

    def test_base_url_rejected(self):
        with pytest.raises(ValueError, match="no base_url"):
            create_llm_client("codex", "gpt-5.4-mini", base_url="https://x")

    def test_get_llm_returns_chat_model(self, monkeypatch):
        _patch_which(monkeypatch, True)
        llm = create_llm_client("codex", "gpt-5.4-mini").get_llm()
        assert isinstance(llm, mod.CodexChatModel)
        assert llm._llm_type == "codex"
        assert llm.model == "gpt-5.4-mini"

    def test_get_llm_raises_when_codex_missing(self, monkeypatch):
        _patch_which(monkeypatch, False)
        with pytest.raises(RuntimeError, match="codex CLI"):
            create_llm_client("codex", "gpt-5.4-mini").get_llm()


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
        argv = mod.CodexChatModel(model="gpt-5.4-mini")._build_argv("/tmp/out.md")
        # Non-interactive subcommand: ``codex exec`` is the only public
        # entry point that does not require a TTY.
        assert argv[:2] == ["codex", "exec"]
        assert "-m" in argv and "gpt-5.4-mini" in argv
        # Sandbox the model's shell commands to read-only by default.
        assert "-s" in argv and "read-only" in argv
        # Run outside a git repo (TradingAgents-driven invocations may
        # not be in a repo) and don't persist a session file.
        assert "--skip-git-repo-check" in argv
        assert "--ephemeral" in argv
        # ``-o <file>`` is how we get the final assistant text without
        # parsing the agent-loop's progress events out of stdout.
        oi = argv.index("-o")
        assert argv[oi + 1] == "/tmp/out.md"
        # ``-`` as the positional prompt makes codex read from stdin.
        assert argv[-1] == "-"

    def test_sandbox_mode_override(self):
        argv = mod.CodexChatModel(
            sandbox_mode="workspace-write"
        )._build_argv("/tmp/x")
        assert "workspace-write" in argv


# ---------------------------------------------------------------------------
# _generate happy + error paths
# ---------------------------------------------------------------------------


def _output_writer(content: str):
    """Build a fake ``subprocess.run`` that mimics codex writing its
    final reply to the ``-o <file>`` path."""

    def fake_run(argv, **kwargs):
        out_idx = argv.index("-o") + 1
        with open(argv[out_idx], "w", encoding="utf-8") as fh:
            fh.write(content)
        return _completed(stdout="")
    return fake_run


@pytest.mark.unit
class TestGenerate:
    def test_happy_path_returns_ai_message(self, monkeypatch, caplog):
        captured: dict[str, Any] = {}

        def fake_run(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            out_idx = argv.index("-o") + 1
            with open(argv[out_idx], "w", encoding="utf-8") as fh:
                fh.write("hello back\n")
            return _completed(stdout="")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel(model="gpt-5.4-mini")

        with caplog.at_level(logging.INFO, logger=ADAPTER_LOGGER):
            out = llm.invoke("hi")

        assert isinstance(out, AIMessage)
        assert out.content == "hello back"
        # argv first two: ``codex exec``; prompt comes via stdin (``-``).
        assert captured["argv"][:2] == ["codex", "exec"]
        assert captured["argv"][-1] == "-"
        # The full flattened prompt must reach the CLI through stdin.
        assert captured["kwargs"]["input"] == "hi"
        assert captured["kwargs"]["capture_output"] is True
        assert captured["kwargs"]["text"] is True
        # Usage line emitted exactly once.
        usage = [r.getMessage() for r in caplog.records if "codex call" in r.getMessage()]
        assert len(usage) == 1
        assert "model=gpt-5.4-mini" in usage[0]

    def test_nonzero_exit_raises_with_stderr_snippet(self, monkeypatch):
        def fake_run(argv, **kwargs):
            return _completed(returncode=1, stderr="Missing OpenAI API key.\nFix it.")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        with pytest.raises(RuntimeError, match="Missing OpenAI API key"):
            llm.invoke("hi")

    def test_empty_response_file_raises(self, monkeypatch):
        # codex returned 0 but never wrote anything to ``-o`` — surface
        # a clean error rather than handing downstream an empty
        # AIMessage.
        def fake_run(argv, **kwargs):
            return _completed(stderr="")

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        with pytest.raises(RuntimeError, match="empty response file"):
            llm.invoke("hi")

    def test_output_file_is_cleaned_up_on_success(self, monkeypatch):
        captured: dict[str, str] = {}

        def fake_run(argv, **kwargs):
            out_idx = argv.index("-o") + 1
            captured["path"] = argv[out_idx]
            with open(argv[out_idx], "w") as fh:
                fh.write("done")
            return _completed()

        _patch_run(monkeypatch, fake_run)
        mod.CodexChatModel().invoke("hi")
        # Adapter is responsible for cleaning up its own temp file.
        assert not os.path.exists(captured["path"])

    def test_output_file_is_cleaned_up_on_failure(self, monkeypatch):
        captured: dict[str, str] = {}

        def fake_run(argv, **kwargs):
            out_idx = argv.index("-o") + 1
            captured["path"] = argv[out_idx]
            return _completed(returncode=1, stderr="boom")

        _patch_run(monkeypatch, fake_run)
        with pytest.raises(RuntimeError):
            mod.CodexChatModel().invoke("hi")
        assert not os.path.exists(captured["path"])

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
            return _completed()

        _patch_run(monkeypatch, fake_run)
        llm = mod.CodexChatModel()

        # ChatPromptTemplate-style call with no actual content — must
        # short-circuit so we don't spend a subprocess turn on nothing.
        with pytest.raises(ValueError, match="empty prompt"):
            llm._generate([])
        assert called["n"] == 0
